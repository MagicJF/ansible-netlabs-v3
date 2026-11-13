#!/usr/bin/env python3
# PROPÓSITO: los ojos del motor: leer TODOS los invitados y los prerrequisitos de la
#   plataforma en UN proceso.
# INVARIANTES: una llamada a la API de PVE cuesta ~15-80 ms y una tarea de Ansible ~3 s;
#   todo lo que se pueda leer de golpe, se lee de golpe.
# VER: lo usan `apply.yml` y `preflight.yml`.
# ===========================================================================
# pve_read.py — the engine's eyes.
#
# Reads EVERY declared guest AND the platform prerequisites in ONE process,
# instead of one Ansible task per guest per question. That is the whole reason
# it exists: on the lab control node a single Ansible module execution costs
# ~3 s while a PVE API call costs ~15-80 ms, so twelve guest reads cost ~48 s
# spread over twelve tasks and 0.34 s in one process. The prerequisite checks
# (node online, storage active, template present, ISO present) therefore cost
# nothing extra here, where they used to cost a task per guest each.
#
# It also reads the lab's Resource Pool (`lab_pool`, ADR 0008): whether it
# exists, who is inside, and the two lists that decide everything — who the
# declaration says is in and the pool does not (`faltan`), and who the pool
# holds and the declaration does not know about (`extra`). `preflight` reports
# those lists and `apply` converges the first one; both read them from HERE, so
# the two verbs cannot disagree about the same question.
#
# It reads the declared state itself, so the manifest stays the single source of
# truth, and it writes the run_start/run_end markers into the API journal so the
# playbooks need no extra tasks for them.
#
# Credentials are resolved HERE and never pass through an Ansible argument or
# environment value, so the token cannot leak into a log or a command line:
#   the machine environment file (--entorno, `secrets.yaml`), the same one the
#   playbooks load with `include_vars`.
#
# Output: one JSON object on stdout. Nothing else is printed, ever.
# ===========================================================================
import declaracion
import argparse
import json
import os
import re
import subprocess
import sys
import time

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("pve_read.py: PyYAML is required (python3-yaml)")
try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("pve_read.py: the requests library is required")

# El entorno de la máquina (credenciales, puerto, rutas de claves) lo resuelve
# `entorno.py`, que es el único sitio que sabe dónde vive y con qué nombres se
# acepta. Aquí no se repite esa lógica: repetirla es cómo el fichero acaba
# pareciendo estar en uso sin estarlo.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import entorno  # noqa: E402

ISO_RE = re.compile(r"([^,:]+):iso/[^,]+")
VOLID_RE = re.compile(r"^([^:]+):")


class StrictLoader(yaml.SafeLoader):
    """SafeLoader that REFUSES duplicate mapping keys.

    YAML keeps the last value of a duplicated key without saying so, which turns
    a half-deleted list item into a silent reconfiguration of its neighbour: the
    entry above inherits the orphaned `manage:`/`config:` block and the next run
    converges the wrong application on the wrong guest. The declared state is the
    human interface to the infrastructure, so a duplicate key is a hard error
    naming the line, not a warning to scroll past.
    """


def _no_duplicate_keys(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                None, None,
                f"duplicate key {key!r} in the declared state (line {key_node.start_mark.line + 1}). "
                "A guest entry was probably deleted only halfway, leaving its block attached to the "
                "entry above; delete the whole entry, or none of it",
                key_node.start_mark)
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


def _strict_mapping(loader, node):
    loader.flatten_mapping(node)
    return _no_duplicate_keys(loader, node)


StrictLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _strict_mapping)


def load_credentials(args):
    """Las credenciales, resueltas por el ÚNICO sitio que sabe hacerlo.

    Antes cada herramienta aceptaba sus propios nombres y aplicaba su propio
    orden; eso es justo lo que permitía que el lector llevara meses sin usar el
    fichero que parecía estar usando. `tools/entorno.py` resuelve fichero >
    entorno una vez para todo el framework, y su error dice qué falta y dónde se
    declara en vez de devolver un 401.
    """
    return entorno.api(args.entorno)


def journal_append(path, event):
    """Best effort, and never fatal: a broken journal must not break a read."""
    if not path:
        return
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), **event}) + "\n")
        os.chmod(path, 0o600)
    except Exception as exc:  # observability must not change the outcome
        print(f"pve_read.py: journal write failed: {exc}", file=sys.stderr)


def journal_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def revision(cwd):
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=cwd, text=True,
                              capture_output=True, timeout=10).stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def declared(manifest):
    """The guests layer 1 manages. pve_config_targets is deliberately NOT read.

    Parsed with StrictLoader, so a duplicated key (the fingerprint of a
    half-deleted entry) stops the run instead of silently reconfiguring the guest
    above it, and every entry is required to carry its identity.
    """
    try:
        data = declaracion.leer_manifiesto(manifest, loader=lambda fh: yaml.load(fh, Loader=StrictLoader))
    except yaml.YAMLError as exc:
        sys.exit(f"pve_read.py: {manifest} is not a valid declared state: {exc}")
    guests = []
    for kind, key, default_key, identity in (("lxc", "pve_containers", "pve_defaults", "hostname"),
                                             ("qemu", "pve_vms", "pve_vm_defaults", "name")):
        defaults = data.get(default_key) or {}
        for item in data.get(key) or []:
            if not isinstance(item, dict) or "vmid" not in item:
                sys.exit(f"pve_read.py: every entry of {key} needs a vmid; found {item!r}. "
                         "A half-deleted entry is not state — delete the whole entry or none of it.")
            spec = {**defaults, **item}
            if not spec.get(identity):
                sys.exit(f"pve_read.py: {key} entry vmid {item['vmid']} declares no {identity}, "
                         "which is the identity the platform is matched against. Nothing was changed.")
            guests.append({"kind": kind, "vmid": item.get("vmid"), "spec": spec,
                           "identifier": spec.get("hostname") or spec.get("name")})
    return data, guests


def read_one(session, base, kind, vmid):
    """Config + status, or exists=false when PVE says the config file is not there."""
    out = {"exists": False, "config": {}, "status": "", "kind": kind, "error": None}
    try:
        r = session.get(f"{base}/{kind}/{vmid}/config", timeout=30)
        if r.status_code == 500 and "does not exist" in r.text:
            return out
        if r.status_code >= 400:
            out["error"] = f"config HTTP {r.status_code}"
            return out
        out["config"] = r.json().get("data") or {}
        out["exists"] = True
        s = session.get(f"{base}/{kind}/{vmid}/status/current", timeout=30)
        out["status"] = ((s.json().get("data") or {}).get("status", "")
                         if s.status_code < 400 else f"HTTP {s.status_code}")
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def platform_facts(session, base, node, data, guests):
    """Node online, storages active, declared templates and ISOs present.

    One call each, plus one content listing per storage actually referenced. The
    point is that these checks stop costing an Ansible task per guest.
    """
    facts = {"node_online": False, "storages_active": {}, "templates_present": {},
             "isos_present": {}, "errors": []}
    try:
        nodes = session.get("https://" + base.split("//")[1].split("/")[0] + "/api2/json/nodes",
                            timeout=30).json().get("data") or []
        facts["node_online"] = any(
            n.get("node") == node and n.get("status") == "online" for n in nodes)
    except Exception as exc:
        facts["errors"].append(f"nodes: {type(exc).__name__}: {exc}")

    try:
        st = session.get(f"{base}/storage", timeout=30).json().get("data") or []
        for s in st:
            facts["storages_active"][s.get("storage")] = bool(s.get("active"))
    except Exception as exc:
        facts["errors"].append(f"storage: {type(exc).__name__}: {exc}")

    # Which storages hold what we must verify: templates for containers, ISOs
    # and disks for VMs.
    wanted = {}
    for g in guests:
        spec = g["spec"]
        if g["kind"] == "lxc":
            st_name, volid = spec.get("template_storage"), spec.get("template")
            if st_name and volid:
                wanted.setdefault((st_name, "vztmpl"), set()).add(volid)
            if spec.get("storage"):
                facts["storages_active"].setdefault(spec["storage"], None)
        else:
            for key, value in (spec.get("ide") or {}).items():
                m = ISO_RE.search(str(value))
                if m:
                    st_name = m.group(1)
                    volid = str(value).split(",")[0].strip()
                    wanted.setdefault((st_name, "iso"), set()).add(volid)
            for key in ("ide", "scsi", "sata", "virtio"):
                for value in (spec.get(key) or {}).values():
                    m = VOLID_RE.match(str(value))
                    if m:
                        facts["storages_active"].setdefault(m.group(1), None)

    listing = {}
    for (st_name, content), volids in wanted.items():
        if content == "vztmpl" and facts["storages_active"].get(st_name) is not None:
            pass
        try:
            r = session.get(f"{base}/storage/{st_name}/content?content={content}", timeout=30)
            available = {c.get("volid") for c in (r.json().get("data") or [])}
        except Exception as exc:
            facts["errors"].append(f"content {st_name}/{content}: {type(exc).__name__}: {exc}")
            available = set()
        listing[(st_name, content)] = available
        for volid in volids:
            if content == "vztmpl":
                facts["templates_present"][volid] = volid in available
            else:
                facts["isos_present"][volid] = volid in available
    return facts


def pool_facts(session, api, poolid, declared_vmids):
    """El Resource Pool del laboratorio: existe, y quién está dentro (ADR 0008).

    Dos llamadas como mucho: la lista de pools dice si el nuestro existe, y el
    detalle dice los miembros. Sin `lab_pool` declarado no hay pool que buscar y
    se dice con un error en vez de inventarse uno.

    Devuelve `faltan` (los declarados que el pool no tiene) y `extra` (los que el
    pool tiene y la declaración no conoce). Son las dos listas que hacen falta:
    una la converge `apply`, la otra la denuncia `guests`.
    """
    declarados = sorted(int(v) for v in declared_vmids)
    facts = {"name": poolid or None, "exists": False, "members": [], "faltan": declarados,
             "extra": [], "comment": None, "error": None}
    if not poolid:
        facts["error"] = "la declaración no declara `lab_pool`: no sé qué pool es suyo"
        return facts
    try:
        lista = session.get(f"{api}/pools", timeout=30)
        if lista.status_code >= 400:
            facts["error"] = f"pools HTTP {lista.status_code}"
            return facts
        if poolid not in {p.get("poolid") for p in (lista.json().get("data") or [])}:
            return facts
        facts["exists"] = True
        r = session.get(f"{api}/pools/{poolid}", timeout=30)
        if r.status_code >= 400:
            facts["error"] = f"pool HTTP {r.status_code}"
            return facts
        data = r.json().get("data") or {}
        facts["comment"] = data.get("comment")
        dentro = {int(m["vmid"]) for m in (data.get("members") or []) if m.get("vmid") is not None}
        facts["members"] = sorted(dentro)
        facts["faltan"] = sorted(set(declarados) - dentro)
        facts["extra"] = sorted(dentro - set(declarados))
    except Exception as exc:
        facts["error"] = f"{type(exc).__name__}: {exc}"
    return facts


def main():
    ap = argparse.ArgumentParser(description="Read the declared state, every guest, and the platform facts.")
    ap.add_argument("--manifest", required=True, help="declared-state file (labs/<nombre>/<nombre>.yml)")
    ap.add_argument("--entorno", help="el entorno de la máquina (secrets.yaml)")
    ap.add_argument("--journal", help="append run_start/run_end markers here")
    ap.add_argument("--playbook", default="unknown")
    ap.add_argument("--phase", default="read", choices=["read", "verify"])
    ap.add_argument("--no-platform", action="store_true", help="skip the platform prerequisite facts")
    args = ap.parse_args()

    creds = load_credentials(args)
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(args.manifest)))
    data, guests = declared(args.manifest)
    node = data.get("pve_node", "")

    size_before = journal_size(args.journal) if args.journal else 0
    if args.phase == "read":
        journal_append(args.journal, {
            "event": "run_start", "playbook": args.playbook,
            "revision": revision(repo_root),
            "guests": [f"{g['kind']}:{g['vmid']}" for g in guests],
        })

    session = requests.Session()
    session.headers.update({
        "Authorization": f"PVEAPIToken={creds['token_id']}={creds['token_secret']}"
    })
    # Validate TLS with the provided CA, exactly like the Ansible modules do.
    session.verify = creds["ca_path"]
    api = f"https://{creds['host']}:{creds['port']}/api2/json"
    base = f"{api}/nodes/{node}"

    result, errors = {}, []
    for g in guests:
        live = read_one(session, base, g["kind"], g["vmid"])
        if live["error"]:
            errors.append({"vmid": g["vmid"], "kind": g["kind"], "error": live["error"]})
        result[str(g["vmid"])] = live

    facts = {"node_online": None, "storages_active": {}, "templates_present": {},
             "isos_present": {}, "errors": []}
    pool = {"name": data.get("lab_pool"), "exists": None, "members": [], "faltan": [],
            "extra": [], "comment": None, "error": None}
    if not args.no_platform:
        facts = platform_facts(session, base, node, data, guests)
        errors.extend(facts.pop("errors", []))
        pool = pool_facts(session, api, data.get("lab_pool"),
                          [g["vmid"] for g in guests])
        if pool["error"]:
            errors.append({"pool": pool["name"], "error": pool["error"]})

    if args.phase == "verify":
        journal_append(args.journal, {
            "event": "run_end", "playbook": args.playbook,
            "verified": [f"{g['kind']}:{g['vmid']}" for g in guests],
        })

    print(json.dumps({
        "node": node,
        "revision": revision(repo_root),
        "journal_size_before": size_before,
        "journal_size_after": journal_size(args.journal) if args.journal else 0,
        "guests": result,
        "platform": facts,
        "pool": pool,
        "errors": errors,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
