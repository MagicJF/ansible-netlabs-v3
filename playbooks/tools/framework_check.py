#!/usr/bin/env python3
# PROPÓSITO: la prueba del propio marco: ¿sigue comportándose como un sistema convergente?
# INVARIANTES: una pasada sobre un lab ya convergido no cambia NADA; y el lab VUELVE a
#   converger tras inyectarle deriva.
# LÍMITES: una regresión en cualquiera de las dos propiedades produce una pasada VERDE.
# VER: es la comprobación del marco.
"""The framework's own test: does it still behave like a convergent system?

Two properties hold this framework up, and both are easy to lose without
noticing, because a regression in either one still produces a green run:

  1. A run over an already-converged lab changes NOTHING. If a role starts
     reporting `changed` every time, the run is still green and the property is
     gone — and with it the only cheap signal that the declaration is the truth.
  2. A run COVERS every declared guest. With `serial`, one guest that fails its
     reachability check stops the remaining batches, and the recap simply lists
     fewer hosts: a failure that looks like a faster run.

  `invariant` runs a verb twice and asserts both, using Ansible's own JSON
  callback rather than parsing the human recap, and comparing the two host sets
  rather than trusting a count.

  `drill` proves the framework can still SEE and REPAIR a difference, which is
  the one thing no amount of `changed=0` can prove:

      preflight -> no DRIFT
      mutate one guest out of band, through the PVE API
      preflight -> that guest must report DRIFT
      apply     -> must change something and fail nothing
      preflight -> no DRIFT again

  The mutation is a `description` on a container: the engine compares it, it
  needs no restart, and the declaration converges it back — so the drill is its
  own cleanup and leaves the lab exactly as it found it.

Run it from anywhere:  python3 playbooks/tools/framework_check.py invariant
                       python3 playbooks/tools/framework_check.py drill

  `plan` es la única que no necesita el laboratorio: renderiza la plantilla del
  plan del rol RouterOS y comprueba, equipo por equipo, que crea las reglas en
  el ORDEN declarado, que no propone nada cuando ya está convergido, que borra
  solo lo que sobra y que no toca lo que el propio equipo creó. Se puede correr
  siempre — es la que protege el único sitio donde el orden decide el
  comportamiento.
"""

import argparse
import difflib
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import sys
from typing import NoReturn

import requests
import yaml

# La herramienta hermana que resuelve la declaración (una sola vez, para todas).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import declaracion  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# La topología viva se resuelve por `labs/active`, que es un enlace al laboratorio
# que se está operando. HERMES_LAB permite apuntar a OTRO sin tocar el enlace: es
# lo que hace posible validar un laboratorio nuevo ANTES de activarlo.
LAB = os.environ.get("HERMES_LAB", "labs/active")
MANIFEST = os.path.join(REPO, LAB, "inventory/group_vars/all.yml")
ENTORNO = os.path.join(REPO, "playbooks/vars/entorno.yml")
# La declaración de RouterOS vive en los valores por defecto del rol: la lista de
# menús que el framework reclama como suyos es lo que da contra qué comparar.
ROUTEROS_DEFAULTS = os.path.join(REPO, "configure/roles/routeros/defaults/main.yml")
# Where this script's own runs log. They must not share logs/ansible.log: the
# JSON callback is orders of magnitude larger than the human output, and mixing
# the two is what made that file unreadable. See run_verb().
FRAMEWORK_LOG = os.path.join(REPO, "logs/framework-check.log")


def manifiesto():
    """El manifiesto con sus referencias ya resueltas (ver tools/declaracion.py).

    Una ficha no lleva la direccion dentro: CITA la tabla (`lab_sede[1].mgmt.rt`)
    y Ansible la renderiza al usarla. Sin resolverla, el mapa de destinos saldria
    con la plantilla y `agree` denunciaria un desfase que no existe. La
    resolucion vive en `declaracion.cargar`, compartida con las demas
    herramientas: un solo sitio que tocar cuando aparezca otra variable derivada.
    """
    return declaracion.cargar(MANIFEST)

# `141: IN SYNC | exists` / `142: DRIFT | ...` — the line both verbs print per
# guest. The drill reads the framework's own verdict instead of re-deriving it.
_VERDICT = re.compile(r"^(\d+): (IN SYNC|DRIFT)\b", re.MULTILINE)


def say(message):
    print(message, flush=True)


def fail(message) -> NoReturn:
    say(f"\nFAIL: {message}")
    sys.exit(1)


def run_verb(verb):
    """Run a verb and return (returncode, {host: recap}, [task messages]).

    The JSON callback is used instead of the human recap on purpose: the recap is
    a formatted table that a count can be read out of but a host LIST cannot be
    trusted from, and telling "the guest was skipped" apart from "the guest was
    never in the play" is exactly what this test is for.
    """
    env = dict(os.environ)
    env["ANSIBLE_STDOUT_CALLBACK"] = "json"
    env["ANSIBLE_LOAD_CALLBACK_PLUGINS"] = "1"
    # Do NOT inherit the human run log. The JSON callback emits megabytes per run,
    # and this script already reads that output from stdout — so letting it land
    # in logs/ansible.log (append-only, never rotated by Ansible) is how that file
    # reached 78 MB, 99% of it machine output nobody reads. Send it to its own
    # file instead: the human log stays readable, and a failed run is still on
    # disk to debug. The file is covered by pve_log_retention like the others.
    env["ANSIBLE_LOG_PATH"] = FRAMEWORK_LOG
    proc = subprocess.run(
        ["ansible-playbook", verb], cwd=REPO, env=env, capture_output=True, text=True
    )
    start = proc.stdout.find("{")
    if start < 0:
        fail(f"`ansible-playbook {verb}` produced no JSON at all. stderr:\n{proc.stderr[-2000:]}")
    try:
        data = json.loads(proc.stdout[start:])
    except json.JSONDecodeError as exc:
        fail(f"could not parse the JSON callback output of {verb}: {exc}")

    recap, messages = {}, []
    # ansible-core 2.19 puts the run's recap at the TOP level of the callback
    # output; older versions nested it per play. Read both, so the check does not
    # silently see an empty recap on one of them — which is exactly how it failed
    # the first time it was written.
    for source in [data.get("stats") or {}] + [p.get("stats") or {} for p in data.get("plays") or []]:
        for host, stats in source.items():
            recap[host] = stats
    for play in data.get("plays") or []:
        for task in play.get("tasks") or []:
            for result in (task.get("hosts") or {}).values():
                messages.extend(_messages_in(result))
    if not recap:
        fail(
            f"`ansible-playbook {verb}` ran but its recap is empty, so nothing can be "
            f"asserted about host coverage. The callback output did not carry a per-host "
            f"recap where this script looks for it."
        )
    return proc.returncode, recap, messages


def assert_clean(recap, label, allow_changes):
    """A run is clean when nothing failed, nothing was unreachable, and — for a
    run over an already-converged lab — nothing changed."""
    problems = []
    for host in sorted(recap):
        stats = recap[host]
        if stats.get("unreachable"):
            problems.append(f"{host}: {stats['unreachable']} unreachable")
        if stats.get("failures"):
            problems.append(f"{host}: {stats['failures']} failure(s)")
        if not allow_changes and stats.get("changed"):
            problems.append(
                f"{host}: {stats['changed']} change(s) on a run that should have changed nothing"
            )
    if problems:
        fail(f"{label} is not clean:\n  " + "\n  ".join(problems))
    say(f"  ok  {label}: {len(recap)} host(s), "
        f"{'changes allowed' if allow_changes else 'changed=0'}, no failures")


def _messages_in(result):
    """Every message a task result carries, including its per-item ones.

    A task with `loop` does NOT put its message at the top of the result: it
    nests one result per item under `results`. A check that only reads the top
    level therefore finds nothing at all for exactly the tasks that report per
    guest — which is how the drill failed the first time it was run.
    """
    if not isinstance(result, dict):
        return []
    found = [str(result["msg"])] if result.get("msg") else []
    for item in result.get("results") or []:
        if isinstance(item, dict) and item.get("msg"):
            found.append(str(item["msg"]))
    return found


def drift_verdicts(messages):
    return {vmid: verdict for vmid, verdict in _VERDICT.findall("\n".join(messages))}


def invariant(verb):
    say(f"== invariant: `{verb}` twice ==")
    say(f"  run 1/2 (this one is allowed to change things)")
    rc, first, _ = run_verb(verb)
    if rc != 0:
        fail(f"{verb} exited {rc} on the first run")
    assert_clean(first, "run 1", allow_changes=True)

    say(f"  run 2/2 (this one must change nothing)")
    rc, second, _ = run_verb(verb)
    if rc != 0:
        fail(f"{verb} exited {rc} on the second run")
    assert_clean(second, "run 2", allow_changes=False)

    if set(first) != set(second):
        only_first = sorted(set(first) - set(second))
        only_second = sorted(set(second) - set(first))
        fail(
            f"the two runs did not cover the same hosts.\n"
            f"  only in run 1: {only_first or '(none)'}\n"
            f"  only in run 2: {only_second or '(none)'}\n"
            f"A host that disappears from the second recap was dropped, not converged."
        )
    say(f"  ok  both runs covered the same {len(first)} host(s)")

    # Do not claim more than was checked. A verb whose play runs on the control
    # node only (apply.yml, preflight.yml) has no guests in its recap, so the
    # coverage assertion above is vacuous for it — and a run that quietly stopped
    # short would look identical. Say so instead of printing a PASS that reads as
    # broader than it is.
    if set(first) <= {"localhost", "127.0.0.1"}:
        say(
            f"  note this verb's play targets the control node, so its recap cannot show "
            f"whether every declared guest was covered. For that, run the verb whose play "
            f"targets the guests:\n"
            f"       python3 playbooks/tools/framework_check.py invariant --verb configure/site.yml"
        )
    say("\nPASS: the verb is convergent" +
        ("" if set(first) <= {"localhost", "127.0.0.1"} else " and covers every host it claims to") +
        ".")
    return 0


def _api():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import entorno as _entorno

    creds = _entorno.api()
    session = requests.Session()
    session.verify = creds["ca_path"] or True
    session.headers["Authorization"] = (
        f"PVEAPIToken={creds['token_id']}={creds['token_secret']}"
    )
    return session, f"https://{creds['host']}:{creds['port']}/api2/json"


def drill(verb, preflight):
    say("== drill: can the framework still SEE a difference, and REPAIR it? ==")

    manifest = yaml.safe_load(open(MANIFEST)) or {}
    node = manifest.get("pve_node", "")
    containers = [c for c in (manifest.get("pve_containers") or []) if c.get("vmid")]
    if not containers:
        fail("the declared state has no containers to drill with")
    victim = containers[0]["vmid"]
    session, base = _api()

    say(f"  1. {preflight} (expect no DRIFT)")
    rc, _, messages = run_verb(preflight)
    if rc != 0:
        fail(f"{preflight} exited {rc} before the drill even started")
    verdicts = drift_verdicts(messages)
    if not verdicts:
        fail(
            "no per-guest verdict was found in the preflight output, so the drill cannot "
            "tell DRIFT from IN SYNC. Did the verb stop reporting per guest?"
        )
    if "DRIFT" in verdicts.values():
        fail(
            f"the lab already reports DRIFT before the drill: "
            f"{sorted(k for k, v in verdicts.items() if v == 'DRIFT')}. "
            f"Converge it first — a drill that starts dirty proves nothing."
        )
    say(f"     ok  {len(verdicts)} guest(s), all IN SYNC")

    stamp = f"drift injected by framework_check.py at {os.getpid()}"
    say(f"  2. mutate vmid {victim} out of band (description)")
    # PUT, not POST. PVE updates a container's config with PUT and a VM's with
    # POST — the same conceptual operation, two different verbs — and POST on an
    # LXC answers 501 "Method not implemented".
    response = session.put(
        f"{base}/nodes/{node}/lxc/{victim}/config", data={"description": stamp}, timeout=30
    )
    if response.status_code != 200:
        fail(f"the out-of-band mutation was refused: HTTP {response.status_code} {response.text[:200]}")

    say(f"  3. {preflight} (vmid {victim} must now report DRIFT)")
    rc, _, messages = run_verb(preflight)
    if rc != 0:
        fail(f"{preflight} exited {rc} on the dirty lab; it should report drift, not die")
    verdicts = drift_verdicts(messages)
    if verdicts.get(str(victim)) != "DRIFT":
        fail(
            f"the framework did NOT notice the drift it was just handed: vmid {victim} "
            f"reports {verdicts.get(str(victim))!r}. The declared state has stopped being the "
            f"authority for that guest."
        )
    say(f"     ok  vmid {victim} reports DRIFT")

    say(f"  4. {verb} (must repair it)")
    rc, recap, _ = run_verb(verb)
    if rc != 0:
        fail(f"{verb} exited {rc} while converging the injected drift")
    assert_clean(recap, "converge", allow_changes=True)
    changed = sum(s.get("changed", 0) for s in recap.values())
    if changed == 0:
        fail("apply reported no change at all, so it did not repair the drift it had just seen")
    say(f"     ok  repaired ({changed} change(s) reported)")

    say(f"  5. {preflight} (expect no DRIFT again)")
    rc, _, messages = run_verb(preflight)
    if rc != 0:
        fail(f"{preflight} exited {rc} after the repair")
    verdicts = drift_verdicts(messages)
    dirty = sorted(k for k, v in verdicts.items() if v == "DRIFT")
    if dirty:
        fail(f"still DRIFT after converging: {dirty}")
    say(f"     ok  {len(verdicts)} guest(s), all IN SYNC")

    say("\nPASS: the framework sees an out-of-band change and converges it back.")
    return 0


LABCHECK = os.path.join(REPO, "playbooks/tools/lab-check.sh")


# ---------------------------------------------------------------------------
# `agree`: la comprobación que SÍ puede encontrar lo que falta.
#
# El mapa de lab-check.sh es una copia a mano de parte de la declaración, y por
# eso puede desincronizarse sin que nada lo note: el script no puede detectar
# que su propia lista está mal, porque la lista es su ENTRADA. Un test que sólo
# pregunta por las direcciones que ya tiene nunca echa en falta ninguna — y esa
# fue exactamente la forma del último error: una dirección que era el VMID del
# invitado y no su IP.
#
# La cura es no comparar elemento a elemento, sino CONJUNTOS: derivar de la
# declaración qué direcciones DEBEN existir, derivar del mapa cuáles se van a
# probar, y quedarse con lo que falta en cada lado. La ausencia es el dato.
# ---------------------------------------------------------------------------
def declared_addresses():
    """Las direcciones que la declaración dice que hay. La fuente de verdad."""
    m = manifiesto()
    out = {}
    for c in m.get("pve_containers", []):
        cfg = c.get("config") or {}
        if "bootstrap" in cfg:
            net0 = (c.get("netif") or {}).get("net0", "")
            ip = re.search(r"\bip=([\d.]+)/", net0)
            if ip:
                out[c["hostname"]] = ip.group(1)
        elif "site" in c and c.get("address"):
            out[c["hostname"]] = c["address"]
    for v in m.get("pve_vms", []):
        if not v.get("chr"):
            continue
        ros = (v.get("config") or {}).get("routeros") or {}
        for a in ros.get("addresses", []):
            if a.get("interface") == "ether1":
                out[v["name"]] = a["address"].split("/")[0]
    return out


def _red_operador():
    """La red del segundo segmento de gestión (OOB), o None si no se declara.

    Ese segmento NO es del dominio de producción. En un despliegue físico es una
    isla aparte —su propio switch, su propio DHCP— que se alcanza desde el lado
    del operador (consola, VPN), no desde una workstation. Por eso las estaciones
    no lo prueban: lo prueba el operador, y lo que sí se prueba desde producción
    es justo lo contrario, que NO lleguen.
    """
    m = manifiesto()
    mgmt2 = m.get("lab_mgmt2")
    red = mgmt2.get("red") if isinstance(mgmt2, dict) else None
    if not red:
        return None
    try:
        return ipaddress.ip_network(red, strict=False)
    except ValueError:
        return None


def _vantage(ip):
    """`operator` si la dirección es del segmento OOB; `stations` en cualquier otro caso."""
    red = _red_operador()
    if red is None:
        return "stations"
    try:
        return "operator" if ipaddress.ip_address(ip) in red else "stations"
    except ValueError:
        return "stations"


def declared_targets():
    """El mapa del lab derivado de la declaración: nombre, dirección, sede y tipo.

    Es la lista que el playbook entrega a `lab-check.sh` como fichero. Se deriva en vez de
    escribirse a mano porque la lista es la ENTRADA del propio test: si se
    mantiene a mano, añadir un invitado deja el test ciego a él y nada lo nota.
    El tipo sale del nombre (pc/sw/rt/fw) y la sede del campo `site` declarado.

    `vantage` separa los dos mundos: `stations` lo prueban las workstations en su
    mapa; `operator` vive en el segmento de gestión OOB y NO entra en ese mapa —
    las estaciones deben comprobar que no llegan, y el operador que sí.
    """
    m = manifiesto()
    out = []
    for c in m.get("pve_containers", []):
        cfg = c.get("config") or {}
        if "bootstrap" in cfg:
            net0 = (c.get("netif") or {}).get("net0", "")
            ip = re.search(r"\bip=([\d.]+)/", net0)
            if ip:
                out.append({"name": c["hostname"], "ip": ip.group(1),
                            "site": 0, "kind": "boot", "vantage": "stations"})
        elif "site" in c and c.get("address"):
            # `site` se declara como "sede1"/"sede2"/"sede3"; el mapa usa el
            # DIGITO porque es el que ata la estación a su puerta y su tránsito.
            m_site = re.search(r"(\d+)", str(c["site"]))
            out.append({"name": c["hostname"], "ip": c["address"],
                        "site": int(m_site.group(1)) if m_site else 0, "kind": "pc",
                        "vantage": _vantage(c["address"])})
    for v in m.get("pve_vms", []):
        if not v.get("chr"):
            continue
        ros = (v.get("config") or {}).get("routeros") or {}
        ip = None
        for a in ros.get("addresses", []):
            if a.get("interface") == "ether1":
                ip = a["address"].split("/")[0]
        if not ip:
            continue
        nombre = v["name"]
        kind = "sw" if nombre.startswith("sw-") else "rt" if nombre.startswith("rt-") else "fw"
        # La sede del equipo de red se queda en 0 A PROPÓSITO: su dirección de
        # gestión vive en la LAN COMPARTIDA del nodo (todos los equipos del lab
        # cuelgan de ella), así que la separación de la política es entre las LANs
        # de sede —las estaciones— y no entre los planos de gestión.
        out.append({"name": nombre, "ip": ip, "site": 0, "kind": kind,
                    "vantage": _vantage(ip)})
    return out


def mapped_addresses():
    """Las direcciones que el script probará, derivadas de la declaración.

    Ya NO se leen del script: el script no lleva topología dentro. El mapa que
    el playbook le entrega se genera con `_labmap_block()`, así que se compara
    contra ESA función —la fuente única— y no contra una copia incrustada.
    """
    out = {}
    for line in _labmap_block().splitlines():
        for mm in re.finditer(r"([\w-]+) ([\d.]+) \d+ \w+", line):
            out[mm.group(1)] = mm.group(2)
    return out


def mapped_oob():
    """Los destinos OOB que las estaciones deben NO alcanzar, de la declaración."""
    out = {}
    for line in _oob_block().splitlines():
        for mm in re.finditer(r"([\w-]+) ([\d.]+)", line):
            out[mm.group(1)] = mm.group(2)
    return out


def agree():
    say("== agree: el mapa del propio test contra la declaración ==")
    decl = declared_addresses()
    mapped = mapped_addresses()
    oob = mapped_oob()
    red = _red_operador()

    def es_op(a):
        if red is None:
            return False
        try:
            return ipaddress.ip_address(a) in red
        except ValueError:
            return False

    op_decl = {n: a for n, a in decl.items() if es_op(a)}
    est_decl = {n: a for n, a in decl.items() if not es_op(a)}
    say(f"  la declaración declara {len(decl)} direcciones: {len(est_decl)} las prueban "
        f"las estaciones, {len(op_decl)} el operador (segmento OOB)")

    by_addr = {a: n for n, a in est_decl.items()}
    seen = {a: n for n, a in mapped.items()}
    missing = {a: n for a, n in by_addr.items() if a not in seen}
    extra = {a: n for a, n in seen.items() if a not in by_addr}
    for a, n in sorted(missing.items()):
        say(f"  FALTA en el mapa : {a:<15} ({n}) — declarado, y el script no lo prueba")
    for a, n in sorted(extra.items()):
        say(f"  SOBRA en el mapa : {a:<15} ({n}) — el script prueba algo que nadie declara")

    # El lado del operador es un test NEGATIVO desde las estaciones: tienen que
    # estar en el bloque OOB para vigilar que NO se llega, y fuera del mapa LAB.
    oob_by_addr = {a: n for n, a in op_decl.items()}
    oob_seen = {a: n for n, a in oob.items()}
    oob_missing = {a: n for a, n in oob_by_addr.items() if a not in oob_seen}
    oob_extra = {a: n for a, n in oob_seen.items() if a not in oob_by_addr}
    for a, n in sorted(oob_missing.items()):
        say(f"  FALTA en OOB     : {a:<15} ({n}) — es del operador y la estación no lo vigila")
    for a, n in sorted(oob_extra.items()):
        say(f"  SOBRA en OOB     : {a:<15} ({n}) — vigila algo que nadie declara")
    dobles = [a for a in seen if a in oob_seen]
    for a in sorted(dobles):
        say(f"  EN LOS DOS MUNDOS: {a:<15} — no puede ser destino de estación Y de operador")

    # La POLÍTICA: una pareja denegada que cita una sede que no existe no separa nada,
    # y en el mapa quedaría como un destino que nunca se prueba.
    ids = {int(s["id"]) for s in (manifiesto().get("lab_sites") or [])}
    malas = []
    for p in re.findall(r"(\d+)-(\d+)", _deny_block()):
        a, b = int(p[0]), int(p[1])
        if a not in ids or b not in ids:
            malas.append(f"{a}-{b}")
    for p in malas:
        say(f"  POLÍTICA ROTA    : la pareja {p} cita una sede que la declaración no tiene")
    if malas:
        fail("la política de alcance cita sedes inexistentes")
    if missing or extra or oob_missing or oob_extra or dobles:
        fail("el mapa del test y la declaración no dicen lo mismo")
    say("\nPASS: el test prueba exactamente lo que la declaración declara — las\n"
        "      estaciones su mundo (y que NO llegan al OOB), el operador el segmento OOB.")
    return 0


# --- lo que la declaración no cubre -----------------------------------------
# Los roles convergen lo que la declaración DICE y lo verifican releyéndolo. Eso
# prueba la dirección de ida: lo declarado está. No prueba la de vuelta: si algo
# apareció en el equipo que nadie declaró —un servicio que volvió a abrirse, un
# usuario, un trabajo programado, un cliente DHCP—, el run sale verde igual.
#
# El export de RouterOS lo ve. `POST /rest/export` escribe en el equipo un fichero
# con su configuración desplegada y `GET /rest/file/<f>` lo devuelve entero. Y hay
# un detalle que lo hace especialmente útil: un export NO verboso sólo escribe lo
# que NO es el valor de fábrica, así que es, en sí mismo, la lista de todo lo que
# alguien cambió en ese equipo. Comparado por MENÚS contra los que la declaración
# declara como suyos, señala exactamente lo que hay y nadie reclamó.
#
# Se compara por menús y no línea a línea a propósito: el export es un script
# generado (por la API los `yes/no` salen como `true/false`), así que la línea no
# es una unidad comparable; el menú sí.
def _menu_counts(export):
    """{'ip/address': 3, ...} — los menús del export y cuántas entradas llevan."""
    out = {}
    actual = None
    for line in export.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("/"):
            actual = line.lstrip("/").replace(" ", "/")
            out.setdefault(actual, 0)
        elif actual is not None:
            out[actual] += 1
    return {m: n for m, n in out.items() if n}


def routeros_export():
    say("== export: qué hay en los equipos de red que la declaración no menciona ==")
    manifest = manifiesto()
    defaults = yaml.safe_load(open(ROUTEROS_DEFAULTS)) or {}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import entorno as _entorno

    user = defaults.get("routeros_user", "admin")
    password = _entorno.maquina().get("pve_routeros_password", "")
    scheme = defaults.get("routeros_scheme", "http")
    port = defaults.get("routeros_port", 80)
    declared = {t["path"] for t in (defaults.get("routeros_tables") or [])}
    allowed = {m for m in (defaults.get("routeros_undeclared_allowed") or [])}
    forbidden = {m for m in (defaults.get("routeros_forbidden_menus") or [])}

    # Los equipos y su dirección de gestión salen de la declaración: la PRIMERA
    # entrada de `addresses` es la de administración (las demás van a interfaces de
    # datos y pueden traer plantillas, que aquí no se pueden resolver).
    devices = []
    for v in (manifest.get("pve_vms") or []):
        ros = ((v.get("config") or {}).get("routeros") or {})
        addrs = ros.get("addresses") or []
        if not addrs:
            continue
        host = str(addrs[0].get("address", "")).split("/")[0]
        if not host or "{{" in host:
            continue
        devices.append((ros.get("identity") or v.get("name") or str(v.get("vmid")), host))
    if not devices:
        fail("la declaración no tiene ningún equipo RouterOS con dirección de gestión")

    say(f"  {len(devices)} equipo(s) declarados, {len(declared)} menú(s) que la declaración reclama")
    session = requests.Session()
    session.auth = (user, password)
    desconocidos = []
    prohibidos = []

    for name, host in devices:
        base = f"{scheme}://{host}:{port}/rest"
        nombre_fichero = "framework-check.rsc"
        try:
            r = session.post(f"{base}/export", json={"file": nombre_fichero}, timeout=30)
            r.raise_for_status()
            r = session.get(f"{base}/file/{nombre_fichero}", timeout=30)
            r.raise_for_status()
            # La respuesta NO es el texto del fichero: el REST de RouterOS lo
            # devuelve como objeto JSON y el script viaja dentro de `contents`. Leer
            # `.text` tal cual no encuentra ni un menú — y contar cero de cero da
            # verde sin haber mirado nada, que es la peor forma de tener una
            # comprobación. Comprobado contra un equipo real, no deducido.
            try:
                cuerpo = r.json()
                export = cuerpo.get("contents", "") if isinstance(cuerpo, dict) else ""
            except ValueError:
                export = r.text
            if not export.strip():
                fail(f"{name} ({host}): el export volvió vacío, así que no hay nada que comparar")
        except Exception as exc:
            fail(f"{name} ({host}): no se pudo leer el export ({type(exc).__name__}: {exc})")
        finally:
            try:
                session.post(f"{base}/file/remove", json={"numbers": nombre_fichero}, timeout=20)
            except Exception:
                pass

        menus = _menu_counts(export)
        if not menus:
            # Una comprobación que no encuentra nada que comparar no ha comprobado
            # nada: falla, en vez de dar verde.
            fail(f"{name} ({host}): el export no tenía ni un menú con contenido")
        say(f"\n  {name} ({host}): {len(menus)} menú(s) con contenido")
        for m in sorted(menus):
            if m in declared:
                marca = "declarado"
            elif m in allowed:
                marca = "admitido"
            elif m in forbidden:
                marca = "PROHIBIDO"
                prohibidos.append((name, m))
            else:
                marca = "NO DECLARADO"
                desconocidos.append((name, m))
            say(f"    {m:<36} {menus[m]:>3} entrada(s)   {marca}")

    if prohibidos:
        say("")
        for name, m in prohibidos:
            say(f"  PROHIBIDO y presente : {m:<30} en {name}")
        fail("hay un menú que la declaración prohíbe y el equipo tiene")
    if desconocidos:
        say("")
        for name, m in desconocidos:
            say(f"  sin declarar : {m:<36} en {name}")
        fail(
            "hay menús con contenido que la declaración no reclama ni admite. O son "
            "configuración que alguien puso fuera del framework, o son menús que la "
            "declaración debería reclamar. Añádelos a `routeros_undeclared_allowed` "
            "si son esperados, o investiga de dónde salieron."
        )
    say(f"\nPASS: los {len(devices)} equipos sólo tienen lo que la declaración declara o admite.")
    return 0


# ---------------------------------------------------------------------------
# plan: la lógica del plan del rol RouterOS, probada SIN tocar ningún equipo
# ---------------------------------------------------------------------------
_PLAN_CAMPOS = ("chain", "action", "in-interface", "out-interface", "connection-state",
                "src-address", "dst-address", "comment")


def _plan_firma(regla):
    """Firma de una regla, con las claves normalizadas: la DECLARACIÓN las
    escribe en snake_case (`in_interface`) y el plan las emite en kebab-case
    (`in-interface`), así que hay que compararlas ya traducidas."""
    normal = {k.replace("_", "-"): v for k, v in regla.items()}
    return tuple(normal.get(c) for c in _PLAN_CAMPOS)


def plan_check():
    """El plan del rol RouterOS, probado sin red, sin credenciales y sin equipo.

    Renderiza la MISMA plantilla que usa el rol (`plan.j2`, no una copia) y
    comprueba, sobre los once equipos de red declarados, cuatro cosas:

      1. Equipo VACÍO      — el plan crea exactamente las reglas declaradas, y
                             **en el orden declarado**. El filtrado es
                             posicional: un plan que las creara desordenadas
                             dejaría un firewall que filtra otra cosa.
      2. Ya CONVERGIDO     — el plan sale vacío. Es la idempotencia, la
                             propiedad que nadie nota cuando se pierde.
      3. Una regla SOBRANTE— se borra solo esa, y no se toca ninguna otra.
      4. Una regla DINÁMICA (creada por el propio equipo) — ni se toca.

    Es la comprobación que se puede correr siempre, y la que protege el único
    sitio de este laboratorio donde el orden decide el comportamiento.
    """
    import copy

    import jinja2

    man = yaml.safe_load(open(MANIFEST))
    defaults = yaml.safe_load(open(ROUTEROS_DEFAULTS))
    plantilla = os.path.join(REPO, "configure/roles/routeros/templates/plan.j2")

    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    # `flatten`, `to_json` y `from_json` son filtros de Ansible, no de Jinja2
    # puro, y el plan los usa. Se replican para poder renderizar la plantilla tal
    # cual la usa el rol, sin sacarla de su sitio.
    env.filters["flatten"] = lambda x: [i for s in x for i in (s if isinstance(s, list) else [s])]
    env.filters["to_json"] = lambda x: json.dumps(x)
    env.filters["from_json"] = lambda x: json.loads(x)
    # `zip` tampoco es de Jinja2 puro: es un filtro de Ansible. La tabla de sedes
    # se indexa por id con `dict(ids | zip(sedes))`, asi que aqui hace falta.
    env.filters["zip"] = lambda a, b: list(zip(a, b))
    tpl = env.from_string(open(plantilla).read())

    # Las variables DERIVADAS de nivel raiz (hoy `lab_sede`, que indexa la tabla
    # de sedes por id) llegan de PyYAML como texto con Jinja sin resolver. Se
    # resuelven aqui, en orden de dependencia, para que el contexto con el que se
    # renderiza la plantilla tenga valores REALES y no la cadena "{{ ... }}".
    # Sin esto, `lab_sede[1].puerta` indexa la cadena por caracter y el plan
    # revienta con "'str object' has no attribute 'puerta'".
    # Ansible devuelve TIPOS NATIVOS de Jinja (un `{{ dict(...) }}` es un dict,
    # no su representacion como texto). Por eso la resolucion usa un entorno
    # nativo: con el entorno normal, `lab_sede` quedaria siendo una cadena y
    # `lab_sede[1]` indexaria el CARACTER 1 en vez de la sede 1.
    import jinja2.nativetypes
    nenv = jinja2.nativetypes.NativeEnvironment(undefined=jinja2.StrictUndefined)
    nenv.filters.update(env.filters)
    ctx = dict(man)
    for _ in range(4):
        pendiente = [k for k, v in ctx.items()
                     if isinstance(v, str) and "{{" in v]
        if not pendiente:
            break
        for k in pendiente:
            try:
                ctx[k] = nenv.from_string(ctx[k]).render(**ctx)
            except Exception:
                pass  # se queda sin resolver; lo denunciara el render que la use
    ctx["routeros_disabled_services"] = defaults["routeros_disabled_services"]

    def declarado(equipo):
        g = [v for v in man["pve_vms"] if v["name"] == equipo][0]
        limpio = copy.deepcopy(g["config"]["routeros"])
        # El bloque `leases` lleva una sustitución de regex que aqui no hace
        # falta (no probamos DHCP) y que Jinja no debe compilar.
        for srv in limpio.get("dhcp_servers") or []:
            srv.pop("leases", None)
        return json.loads(env.from_string(json.dumps(limpio)).render(**ctx))

    def plan(ros, cfg, identidad=""):
        return json.loads(tpl.render(l2_config={"routeros": cfg}, ros=ros,
                                     ros_identity_name=identidad, **ctx))

    def vivo(cfg, extra=None):
        """Lo que un equipo ya convergido respondería, en kebab-case."""
        v = {"identity": {"name": cfg["identity"]}}
        for menu, clave in (("filter", "firewall_filter"), ("nat", "firewall_nat")):
            filas = []
            for i, r in enumerate((cfg.get("firewall") or {}).get(menu) or []):
                fila = {"chain": r["chain"], "action": r["action"],
                        ".id": "*%s%d" % (clave[-1], i)}
                for origen, destino in (("connection_state", "connection-state"),
                                        ("in_interface", "in-interface"),
                                        ("out_interface", "out-interface"),
                                        ("src_address", "src-address"),
                                        ("dst_address", "dst-address"),
                                        ("comment", "comment")):
                    if origen in r:
                        fila[destino] = r[origen]
                filas.append(fila)
            v[clave] = filas
        if extra:
            v["firewall_filter"] = v["firewall_filter"] + extra
        return v

    vacias = {k: [] for k in ("identity", "services", "bridges", "bridge_ports", "addresses",
                              "routes", "firewall_filter", "firewall_nat", "dhcp_clients",
                              "pools", "dhcp_servers", "dhcp_networks", "dhcp_leases")}
    equipos = [v["name"] for v in man["pve_vms"]]
    fallos = []

    say("El plan del rol RouterOS, renderizado con la plantilla del rol (%d equipos)"
        % len(equipos))
    for equipo in equipos:
        cfg = declarado(equipo)
        filtro = (cfg.get("firewall") or {}).get("filter") or []
        nat = (cfg.get("firewall") or {}).get("nat") or []
        ops = lambda p: [o for o in p if "firewall" in o["path"]]  # noqa: E731

        # 1) vacio: crea todo, y en el orden declarado
        p1 = ops(plan(copy.deepcopy(vacias), cfg))
        if len(p1) != len(filtro) + len(nat):
            fallos.append("%s: equipo vacio -> %d llamadas, esperaba %d"
                          % (equipo, len(p1), len(filtro) + len(nat)))
        else:
            creadas = [_plan_firma(o["body"]) for o in p1 if "filter" in o["path"]]
            if creadas != [_plan_firma(r) for r in filtro]:
                fallos.append("%s: no crea las reglas en el ORDEN declarado" % equipo)

        # 2) convergido: no debe proponer nada
        p2 = ops(plan(dict(vacias) | vivo(cfg), cfg, identidad=cfg["identity"]))
        if p2:
            fallos.append("%s: no es idempotente -> %s" % (equipo, json.dumps(p2)))

        # 3) una sobrante, y una dinamica que no es nuestra
        sucio = dict(vacias) | vivo(cfg, extra=[{"chain": "input", "action": "accept",
                                                 ".id": "*dyn", "dynamic": "true"}])
        sucio["firewall_filter"] = sucio["firewall_filter"] + [
            {"chain": "forward", "action": "accept", ".id": "*sobra"}]
        p3 = ops(plan(sucio, cfg, identidad=cfg["identity"]))
        if len(p3) != 1 or p3[0]["method"] != "DELETE" \
                or p3[0]["path"] != "ip/firewall/filter/*sobra":
            fallos.append("%s: no borra solo lo que sobra -> %s" % (equipo, json.dumps(p3)))

        say("  %-14s %2d de filtrado, %d de NAT: crea en orden, idempotente y limpia la sobrante"
            % (equipo, len(filtro), len(nat)))

    if fallos:
        fail("el plan del rol RouterOS:\n  - " + "\n  - ".join(fallos))
    say("\nPASS: el plan crea en orden, no propone nada cuando ya esta, borra solo lo")
    say("      sobrante y no toca lo dinamico. Sin red ni credenciales: %d equipos."
        % len(equipos))
    return 0


# ---------------------------------------------------------------------------
# notas: la nota HTML de cada invitado contra la declaración que la genera
# ---------------------------------------------------------------------------
def _patas_de(g, tipo):
    """Las patas declaradas, leídas por CLAVE y no por posición.

    Una LXC declara la MAC en `hwaddr=` y una VM en `virtio=`; el bootstrap no
    declara ninguna de las dos. Un patrón con el orden fijo las confunde.
    """
    campo = g.get("netif") if tipo == "LXC" else g.get("net")
    out = []
    for k, v in (campo or {}).items():
        d = dict(x.split("=", 1) for x in v.split(",") if "=" in x)
        out.append({
            "pata": k,
            "bridge": d.get("bridge"),
            "mac": d.get("hwaddr") or d.get("virtio"),
        })
    return out


_NOTA_FILA = re.compile(
    r"<tr><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td><td>(.*?)</td></tr>")


def notas_check():
    """La nota y las etiquetas de cada invitado, contra la declaración.

    Sin red, sin equipo y sin credenciales. Comprueba lo que la nota CUENTA
    contra lo que la declaración DICE: es la dirección que ningún verbo puede
    probar, porque una nota que nombra otro puerto que el declarado sigue siendo
    HTML perfectamente válido y nadie lo notaría hasta necesitarla.

    Por invitado, seis cosas:
      1. una fila por pata declarada, con su bridge y su MAC
      2. en un cable punto a punto, que el vecino nombrado sea el otro extremo
      3. en el segmento COMPARTIDO (la red de gestión), que NO nombre un vecino
         único: ahí cuelgan las patas de administración de todos los equipos
      4. que no se invente una MAC donde la declaración no declara ninguna
      5. que las etiquetas sean exactamente las tres: quién, qué y dónde (de qué
         laboratorio lo dice su Resource Pool, no una etiqueta: ADR 0008)
      6. que ninguna nota se haya quedado con una referencia Jinja sin resolver

    Y una cosa más, que es la regla: que NINGÚN invitado guarde `description` ni
    `tags` en la declaración. Son derivados y se calculan (aquí y en el
    despliegue, con el mismo generador); guardarlos era tener una caché dentro de
    la fuente de verdad, y una caché dentro de la fuente de verdad se queda vieja
    sin decirlo.
    """
    say("== notas: la nota de cada invitado contra la declaración ==")
    # La declaración RESUELTA: el `net0` de un invitado es una plantilla
    # (`bridge={{ lab_mgmt2.bridge }}`) y la nota lleva el valor ya renderizado.
    # Comparando contra el texto crudo, la nota y la declaración "discrepan" siempre.
    man = manifiesto()
    invitados = ([(c, "LXC", c["hostname"]) for c in man["pve_containers"]]
                 + [(v, "CHR", v["name"]) for v in man["pve_vms"]])

    guardados = [n for g, _t, n in invitados if "description" in g or "tags" in g]
    if guardados:
        for n in guardados:
            say(f"  {n}: declara `description`/`tags`, que son DERIVADOS de la declaración")
        fail(f"{len(guardados)} invitado(s) guardan algo derivado en la declaración: "
             "la nota y las etiquetas se CALCULAN, no se almacenan")

    # Se generan aquí con el MISMO generador que usa el despliegue
    # (filter_plugins/notas.py -> playbooks/tools/pve_notas.py), así que lo que
    # esta comprobación aprueba es exactamente lo que PVE va a recibir.
    sys.path.insert(0, os.path.join(REPO, "playbooks", "tools"))
    import pve_notas as _notas  # noqa: E402
    # El manifiesto ENTERO: el generador deduce la identidad de las direcciones
    # declaradas (`lab_mgmt_otros`, `lab_mgmt2`, `lab_sites[].mgmt`…), así que un
    # subconjunto lo dejaría sin poder resolver el borde, la infra y el segmento OOB.
    _notas.man = man
    _notas.preparar()
    generadas = {e["vmid"]: {"description": _notas.html(e), "tags": _notas.tags_de(e)}
                 for e in _notas.todos(_notas.man)}

    cables = {}
    for g, tipo, nombre in invitados:
        for p in _patas_de(g, tipo):
            cables.setdefault(p["bridge"], []).append((nombre, p["pata"], p["mac"]))

    # El vocabulario válido sale de la DECLARACIÓN: los tags que la declaración pone
    # a cada invitado (`pve_defaults`/`pve_vm_defaults`), los códigos de sitio que
    # declara (`lab_sites[].codigo` y `lab_sedes_extra`) y los cinco papeles. No se re-deriva
    # la identidad —eso ya lo hace el generador—: aquí se comprueba la FORMA de las
    # etiquetas y que cada valor pertenezca al vocabulario declarado.
    marcas = set()
    for _clave in ("pve_defaults", "pve_vm_defaults"):
        marcas |= {str(t) for t in ((man.get(_clave) or {}).get("tags") or [])}
    sitios_ok = ({str(s.get("codigo")).lower() for s in (man.get("lab_sites") or [])}
                 | {str(k).lower() for k in (man.get("lab_sedes_extra") or {})})
    roles_ok = {"workstation", "switch", "router", "firewall", "bootstrap"}

    fallos = []
    for g, tipo, nombre in sorted(invitados, key=lambda x: x[0]["vmid"]):
        desc = generadas[g["vmid"]]["description"]
        if "{{" in desc or "{%" in desc:
            fallos.append(f"{nombre}: la nota se quedó con una referencia Jinja sin resolver")
        live = [t.strip() for t in generadas[g["vmid"]]["tags"] if t and t.strip()]
        if len(live) != 3:
            fallos.append(f"{nombre}: {len(live)} etiqueta(s); deben ser TRES "
                          f"(quién lo gestiona, qué es y dónde está): de qué laboratorio "
                          f"es un invitado lo dice su Resource Pool, no una etiqueta")
        else:
            if live[0] not in marcas:
                fallos.append(f"{nombre}: la etiqueta {live[0]!r} no está entre las "
                              f"declaradas {sorted(marcas)}")
            if live[1] not in roles_ok:
                fallos.append(f"{nombre}: el papel {live[1]!r} no está en {sorted(roles_ok)}")
            if live[2] not in sitios_ok:
                fallos.append(f"{nombre}: el sitio {live[2]!r} no está entre los "
                              f"declarados {sorted(sitios_ok)}")
        blk = re.search(r"<b>CONEXIONES</b>\s*<table>(.*?)</table>", desc, re.S)
        if not blk:
            fallos.append(f"{nombre}: la nota no tiene tabla de conexiones")
            continue
        celdas = _NOTA_FILA.findall(blk.group(1))
        mias = _patas_de(g, tipo)
        if len(celdas) != len(mias):
            fallos.append(f"{nombre}: {len(celdas)} fila(s) en la nota, "
                          f"{len(mias)} pata(s) declarada(s)")
        for (pata, _boca, bridge, mac, vecino), p in zip(celdas, mias):
            b = bridge.replace("<code>", "").replace("</code>", "")
            n_mac = mac.replace("<code>", "").replace("</code>", "")
            if b != p["bridge"]:
                fallos.append(f"{nombre} {pata}: la nota dice {b}, la declaración {p['bridge']}")
            if (p["mac"] or "—") != n_mac:
                fallos.append(f"{nombre} {pata}: la nota dice MAC {n_mac}, "
                              f"la declaración {p['mac'] or 'ninguna'}")
            patas = cables.get(p["bridge"], [])
            if len(patas) > 2:
                if not vecino.startswith("segmento compartido"):
                    fallos.append(f"{nombre} {pata}: {p['bridge']} lleva {len(patas)} patas "
                                  f"(segmento compartido) y la nota nombra un vecino único: {vecino!r}")
            else:
                otros = [x[0] for x in patas if x[0] != nombre]
                if len(otros) != 1 or vecino.split()[0] != otros[0]:
                    fallos.append(f"{nombre} {pata}: la nota dice {vecino!r} y el otro "
                                  f"extremo es {otros[0] if otros else '—'}")

    for f in fallos:
        say("  " + f)
    if fallos:
        fail(f"{len(fallos)} desacuerdo(s) entre las notas y la declaración")
    say(f"  {len(invitados)} invitados: una fila por pata, su bridge y su MAC, el vecino "
        "real de cada cable punto a punto,\n  el segmento de gestión contado como lo que "
        "es, y las tres etiquetas (quién, qué, dónde).")
    say("\nPASS: las notas no contradicen a la declaración.")
    return 0


TOPOLOGY_START = "# >>> TOPOLOGY"
TOPOLOGY_END = "# <<< TOPOLOGY"


def _topology_data():
    """La forma de la topología: quién es el hub, cada sede y el router de cada una.

    El hub es la sede cuyo firewall termina el borde y tiene una boca por cada
    enlace WAN. Las demás son spokes: su firewall termina UN enlace hacia el hub.
    Eso no se deduce del direccionamiento, se declara con `lab_hub`.
    """
    m = manifiesto()
    hub = int(m.get("lab_hub", 1))
    sites = {int(s["id"]): s for s in m.get("lab_sites", [])}
    # El router de cada sede sale de la DECLARACION (`lab_sites[].mgmt.rt`), no
    # del nombre del equipo: el mini lo llama `rt-u1` y el patron `rt-s<N>-` no
    # casaba, asi que `RT` salia VACIO y el test perdia la puerta de su sede.
    routers = {}
    for sid, s in sites.items():
        mgmt = s.get("mgmt") or {}
        if mgmt.get("rt"):
            routers[sid] = str(mgmt["rt"])
    # Respaldo: si una sede no declara su router en `mgmt.rt`, se busca un CHR
    # cuyo nombre empiece por `rt-s<sede>-`.
    for v in m.get("pve_vms", []):
        if not v.get("chr"):
            continue
        mm = re.match(r"rt-s(\d+)-", v["name"])
        if not mm:
            continue
        sid = int(mm.group(1))
        if sid in routers:
            continue
        for a in ((v.get("config") or {}).get("routeros") or {}).get("addresses", []):
            if a.get("interface") == "ether1":
                routers[sid] = a["address"].split("/")[0]
    return hub, sites, routers


def _topology_block():
    """El bloque GW/RT/HOP: puertas, routers de gestión y saltos predichos.

    Los saltos se DERIVAN de la forma declarada en vez de escribirse a mano por
    par de sedes. El camino de A a B es: puerta de A, el firewall de A, el otro
    extremo del enlace WAN (el del hub si A es spoke, el del spoke si B es
    spoke), y el router de B. Cuatro saltos entre sedes; uno solo hacia la
    gestión. Con dos sedes más, esto sigue siendo el mismo código.
    """
    hub, sites, routers = _topology_data()
    gw = " ".join(f"{s} {sites[s]['puerta']}" for s in sorted(sites))
    rt = " ".join(f"{s} {routers[s]}" for s in sorted(routers))
    filas = []
    for a in sorted(sites):
        # Hacia la red de gestión: el paquete sólo cruza el router de A.
        filas.append(f"{a}-0 {sites[a]['puerta']}")
        for b in sorted(sites):
            if a == b:
                filas.append(f"{a}-{b}")
                continue
            ta, tb = sites[a]["transito"], sites[b]["transito"]
            if a == hub:
                # El hub entrega en el extremo SPOKE del enlace de B.
                saltos = [sites[a]["puerta"], ta["fw"], sites[b]["wan"]["spoke"], tb["rt"]]
            elif b == hub:
                # El spoke entrega en el extremo HUB de su propio enlace.
                saltos = [sites[a]["puerta"], ta["fw"], sites[a]["wan"]["hub"], tb["rt"]]
            else:
                # Spoke a spoke: sube al hub por su enlace y baja por el del otro.
                saltos = [sites[a]["puerta"], ta["fw"], sites[a]["wan"]["hub"],
                          sites[b]["wan"]["spoke"], tb["rt"]]
            filas.append(f"{a}-{b} " + " ".join(saltos))
    return 'GW="' + gw + '"\nRT="' + rt + '"\nHOP="' + "\n".join(filas) + '"'


LABMAP_START = "# >>> LABMAP"
LABMAP_END = "# <<< LABMAP"
OOB_START = "# >>> OOB"
OOB_END = "# <<< OOB"


def _labmap_block():
    """El bloque `LAB=` que el playbook entrega como fichero, derivado del manifiesto.

    Se agrupa por tipo y se ordena por nombre para que dos generaciones seguidas
    den el MISMO texto: si el orden bailara, el fichero pareceria cambiado sin
    que nada haya cambiado de verdad. SOLO van los destinos `stations`: el
    segmento OOB no es de las estaciones y se vigila aparte (bloque OOB).
    """
    orden = {"pc": 0, "sw": 1, "rt": 2, "fw": 3, "boot": 4}
    destinos = sorted((d for d in declared_targets() if d.get("vantage") != "operator"),
                      key=lambda x: (orden.get(x["kind"], 9), x["name"]))
    lineas, primera = [], True
    for d in destinos:
        trozo = f"{d['name']} {d['ip']} {d['site']} {d['kind']}"
        if primera:
            lineas.append(f'LAB="{trozo}"')
            primera = False
        else:
            lineas.append(f'LAB="$LAB;{trozo}"')
    return "\n".join(lineas)


def _oob_block():
    """El bloque `OOB=` que el playbook entrega como fichero: qué NO debe alcanzar.

    Es la cara negativa del mismo mapa. Los destinos del segmento de gestión OOB
    no son del dominio de producción: en un despliegue físico son una isla. Las
    estaciones comprueban que NO llegan; el operador comprueba que sí. Se genera
    igual que LAB, y por la misma razón: una lista a mano se queda ciega.
    """
    destinos = sorted((d for d in declared_targets() if d.get("vantage") == "operator"),
                      key=lambda x: x["name"])
    if not destinos:
        return '# (la declaracion no tiene destinos en el segmento de gestion OOB)'
    lineas, primera = [], True
    for d in destinos:
        trozo = f"{d['name']} {d['ip']}"
        if primera:
            lineas.append(f'OOB="{trozo}"')
            primera = False
        else:
            lineas.append(f'OOB="$OOB;{trozo}"')
    return "\n".join(lineas)


def _deny_block():
    """El bloque `DENY=` que el playbook entrega como fichero: qué parejas de sede NO
    deben cruzarse.

    Es la cara negativa del mapa (como OOB) GENERALIZADA: la separación no se cablea en
    el test, la declara el laboratorio en `lab_policy`. El test la convierte en una
    prueba que espera que el destino NO conteste. Sin esto, un laboratorio cuyo punto es
    la separación se verificaría al revés: daría por bueno lo que hay que impedir.
    """
    m = manifiesto()
    deny = ((m.get("lab_policy") or {}).get("deny")) or []
    if not deny:
        return '# (la declaración no declara parejas de sede que no deban cruzarse)'
    pares, motivos = [], []
    for d in deny:
        for a in (d.get("from") or []):
            for b in (d.get("to") or []):
                pares.append(f"{int(a)}-{int(b)}")
                motivos.append(f"{int(a)}-{int(b)}: {d.get('why', '')}".rstrip(": "))
    return 'DENY="' + ";".join(pares) + '"\nDENY_WHY="' + ";".join(motivos) + '"'


def _reescribe(texto, marca, nuevo):
    """Sustituye lo que hay entre los marcadores por `nuevo`. Devuelve (texto, igual)."""
    ini, fin = texto.find(marca[0]), texto.find(marca[1])
    if ini < 0 or fin < 0:
        fail(f"lab-check.sh no tiene los marcadores {marca[0]}; no se puede regenerar")
    actual = texto[ini + len(marca[0]):fin].strip("\n")
    if actual == nuevo:
        return texto, True
    return texto[:ini + len(marca[0])] + "\n" + nuevo + "\n" + texto[fin:], False


def labmap(check=False, emit=False):
    """Emite el mapa de ESTE laboratorio y, con --check, vigila que el script no
    lleve topología dentro.

    El mapa (LAB, OOB, GW, RT y HOP) se deriva de la declaración y el playbook lo
    entrega al script como FICHERO. Antes se incrustaba en lab-check.sh; eso
    convertía al script en una copia de la topología del laboratorio activo y lo
    dejaba ciego al laboratorio que se estaba operando (medido: el mini se negó a
    medir porque su dirección no estaba en el mapa del grande). El script es
    lógica; la topología es un dato que se pasa.
    """
    say("== labmap: el mapa de este laboratorio, derivado de la declaración ==")
    if check:
        texto = open(LABCHECK, encoding="utf-8").read()
        incrustado = [m for m in (LABMAP_START, OOB_START, TOPOLOGY_START) if m in texto]
        if incrustado:
            fail(f"lab-check.sh lleva topología incrustada ({', '.join(incrustado)}); "
                 "el mapa debe venir como fichero, no escrito dentro")
        say("  el script no lleva topología incrustada: el mapa se pasa como fichero")
        say("\nPASS: el script no lleva el mapa dentro; el mapa se deriva de la declaración.")
        return 0
    print("\n".join([_labmap_block(), _oob_block(), _deny_block(), _topology_block()]))
    return 0


def nuevo_lab(nombre, desde=None, activar=False):
    """Crea un laboratorio nuevo copiando uno existente, listo para editar.

    Un laboratorio no se escribe desde cero: se COPIA uno que funciona y se
    cambia lo que hace distinto. Copiar arrastra lo que de verdad cuesta acertar
    —los cables, los bridges, las direcciones coherentes— y deja el trabajo en
    editar la topología, no en reconstruir el andamiaje.
    """
    import shutil

    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", nombre):
        fail(f"nombre inválido: {nombre!r}. Minúsculas, dígitos y guiones.")
    origen = desde or "labs/active"
    origen_real = os.path.realpath(os.path.join(REPO, origen))
    if not os.path.isdir(origen_real):
        fail(f"el laboratorio de origen no existe: {origen}")
    destino = os.path.join(REPO, "labs", nombre)
    if os.path.exists(destino):
        fail(f"ya existe labs/{nombre}")

    say(f"== nuevo-lab: {nombre} a partir de {os.path.relpath(origen_real, REPO)} ==")
    shutil.copytree(origen_real, destino)
    # El nombre del laboratorio aparece en las notas de los invitados; se corrige
    # la RUTA, no el nombre del equipo, para no tocar ningún hostname.
    manifiesto = os.path.join(destino, "inventory/group_vars/all.yml")
    texto = open(manifiesto, encoding="utf-8").read()
    origen_rel = os.path.relpath(origen_real, REPO).replace(os.sep, "/")
    texto = texto.replace(f"{origen_rel}/inventory/group_vars/all.yml",
                          f"labs/{nombre}/inventory/group_vars/all.yml")
    open(manifiesto, "w", encoding="utf-8").write(texto)

    say(f"  copiado en labs/{nombre}")
    say("\n  Para validarlo SIN activarlo (no toca el laboratorio vivo):")
    say(f"    HERMES_LAB=labs/{nombre} python3 playbooks/tools/framework_check.py agree")
    say(f"    HERMES_LAB=labs/{nombre} python3 playbooks/tools/framework_check.py plan")
    say(f"    HERMES_LAB=labs/{nombre} python3 playbooks/tools/framework_check.py notas")
    say("\n  Edita su manifiesto y su hosts.yml, y cuando cuadre:")
    if activar:
        enlace = os.path.join(REPO, "labs/active")
        if os.path.islink(enlace):
            os.unlink(enlace)
        os.symlink(nombre, enlace)
        say(f"  labs/active -> {nombre}  (hecho)")
    else:
        say(f"    ln -sfn {nombre} labs/active   # o repite con --activar")
    say("\nPASS: laboratorio creado. El motor no ha cambiado: sólo la topología.")
    return 0


# ── La puerta única de la API ────────────────────────────────────────────────
# El framework tiene UNA forma de hablar con Proxmox y RouterOS: `ansible.builtin.uri`
# dentro de un rol/play. Ese transporte queda anotado y entra en el diario. Escaparse
# del framework (requests/urllib/curl desde un script suelto) se permite sólo para
# comprobaciones rápidas en depuración: no puede ser la vía normal, porque entonces
# nadie sabe qué se tocó ni queda registro. Cuando un patrón se repite, se integra.
_HTTP_LIBS = re.compile(
    r"^\s*(?:import|from)\s+"
    r"(requests|urllib|urllib2|urllib3|http\.client|httplib|proxmoxer|librouteros)\b",
    re.MULTILINE)
# `curl` en un script es la otra forma de saltarse el framework sin que se vea.
_CURL = re.compile(r"(?<![\w.-])curl\b")
# Y tocar a pelo la dirección/el camino de las APIs delata la intención directa.
_API_SIGNS = re.compile(r":8006\b|/api2/json|/rest/ip\b|/rest/system\b")
_ESCANEO = (".py", ".sh", ".yml", ".yaml", ".j2")


def _puertas_api():
    """Los únicos sitios con permiso para hablar HTTP con las APIs.

    La puerta ES la metodología: lo que no está aquí pasa por `ansible.builtin.uri`,
    que es transporte anotado y registrado en `logs/pve-api.jsonl`. Una llamada
    fuera de aquí se ve; luego se decide si se mueve dentro o si está justificada.
    """
    return (
        os.path.join(REPO, "playbooks", "tools"),    # la capa por lotes (Python)
        os.path.join(REPO, "playbooks", "tracing"),  # el trazador (sitecustomize)
    )


def api_check():
    """Comprueba que sólo la capa habla HTTP con las APIs.

    Recorre el repo y denuncia cualquier fichero fuera de la puerta que importe una
    biblioteca HTTP, invoque `curl` o contenga el camino de las APIs. Los textos de
    documentación no cuentan: sólo código ejecutable. Es la ley que hace cumplir la
    regla del framework: la API se toca por la puerta, o no se toca.
    """
    puertas = tuple(os.path.abspath(p) for p in _puertas_api())
    # `.ansible/` guarda las colecciones que este marco usa, instaladas DENTRO del
    # repositorio para que un clon nuevo no dependa del home. Su código no es
    # nuestro código: que hable HTTP es su trabajo, no una puerta que nos saltemos.
    saltar = {".git", "logs", "__pycache__", "labs", "node_modules", ".venv", "venv", ".ansible"}
    offenders = []
    for raiz, dirs, ficheros in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in saltar]
        if "reports" in raiz or raiz.endswith("docs"):
            continue
        for nombre in ficheros:
            if not nombre.endswith(_ESCANEO):
                continue
            ruta = os.path.abspath(os.path.join(raiz, nombre))
            if ruta.startswith(puertas):
                continue
            try:
                texto = open(ruta, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            motivos = []
            if nombre.endswith((".py", ".sh")) and _HTTP_LIBS.search(texto):
                motivos.append("importa una biblioteca HTTP")
            if nombre.endswith((".sh",)) and _CURL.search(texto):
                motivos.append("usa curl")
            # El camino de la API sólo delata cuando está en un script ejecutable:
            # un .yml que declara `api_port: 8006` es el framework configurándose,
            # no un atajo. Ahí el endpoint es la declaración, no una llamada suelta.
            if nombre.endswith((".py", ".sh")) and _API_SIGNS.search(texto):
                motivos.append("lleva el camino de la API")
            if motivos:
                offenders.append((os.path.relpath(ruta, REPO), motivos))

    if offenders:
        for ruta, motivos in offenders:
            say(f"  {ruta}: {', '.join(motivos)}")
        fail(
            f"{len(offenders)} fichero(s) hablan con la API fuera de la puerta "
            f"({os.path.relpath(puertas[0], REPO)}/*). Múevelo dentro del framework "
            "(ansible.builtin.uri) o justifícalo; la API no se toca a mano.")
    say(f"PASS: la API sólo se toca por la puerta; {len(_puertas_api())} puertas, 0 fugas")


def _punteros(texto):
    """Los enlaces markdown de un documento que apuntan a una ruta del repo.

    Un documento que explica un MECANISMO no debe repetirlo: apunta al fichero que
    lo explica (su comentario de cabecera). Un puntero a una ruta que ya no existe
    es una instruccion que lleva a tocar lo que no es, y se detecta sin leer prosa.
    Se ignoran los enlaces externos (http/https/mailto) y los anclajes internos.
    """
    import re
    fuera = []
    for m in re.finditer(r"\[[^\]]*\]\(([^)]+)\)", texto):
        t = m.group(1).strip()
        if not t or t.startswith("#"):
            continue
        if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", t):  # esquema: http:, mailto:…
            continue
        fuera.append(t)
    return fuera


def _documentos_rastreables():
    """Los documentos donde vive un puntero: los generados + los de prosa del repo.

    No se rastrean los comentarios del código: el puntero va del DOC al CÓDIGO, así
    que la pregunta «¿quién cita esta ruta?» se responde mirando los documentos.
    """
    fuera = ["README.md", "EL-LABORATORIO.md", ".hermes.md"]
    d = os.path.join(REPO, "docs")
    if os.path.isdir(d):
        for raiz, _dirs, ficheros in os.walk(d):
            for f in ficheros:
                if f.endswith(".md"):
                    fuera.append(os.path.relpath(os.path.join(raiz, f), REPO))
    return [f for f in fuera if os.path.exists(os.path.join(REPO, f))]


def refs(ruta=None):
    """Índice inverso: qué documentos citan una ruta (o el mapa puntero -> documentos).

    Un puntero va del documento al código. Al cambiar un fichero de mecanismo hay que
    saber qué documentos lo citan, y eso no lo dice el fichero: lo dice el conjunto.
    `framework_check.py refs playbooks/apply.yml` lista los documentos que lo nombran.
    Sin argumento, imprime el mapa de todos los destinos enlazados.
    """
    docs = _documentos_rastreables()
    if ruta is None:
        say("== refs: mapa puntero -> documentos ==")
        mapa = {}
        for f in docs:
            for t in _punteros(open(os.path.join(REPO, f), encoding="utf-8").read()):
                objetivo = t.split("#", 1)[0]
                mapa.setdefault(objetivo, []).append(f)
        for objetivo in sorted(mapa):
            say(f"  {objetivo}  <-  {', '.join(sorted(set(mapa[objetivo])))}")
        return 0
    objetivo = ruta.lstrip("./")
    say(f"== refs: quién cita «{objetivo}» ==")
    hallado = False
    for f in docs:
        for n, linea in enumerate(open(os.path.join(REPO, f), encoding="utf-8"), 1):
            if objetivo in linea:
                hallado = True
                say(f"  {f}:{n}: {linea.strip()[:120]}")
    if not hallado:
        say("  (ningún documento cita esa ruta)")
    return 0


def routeros_check():
    """Tras converger, NINGÚN equipo puede quedar con una ruta por defecto DINÁMICA.

    Un CHR nace con un cliente DHCP de fábrica cuyo lease instala `0.0.0.0/0 via …`
    dinámica. Compite con la ruta declarada (mismo distance) y el balanceo ECMP manda
    la mitad del tráfico de vuelta por la puerta de gestión — alcance parcial cross-sede.
    El rol la purga con un reinicio controlado (ADR 0003). Esto lo COMPRUEBA: si algún
    equipo conserva esa ruta después de un `site`, el ADR 0003 ha dejado de cumplirse.
    """
    say("== routeros: ningún equipo con ruta por defecto DINÁMICA (ADR 0003) ==")
    manifest = manifiesto()
    defaults = yaml.safe_load(open(ROUTEROS_DEFAULTS)) or {}
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import entorno as _entorno

    user = defaults.get("routeros_user", "admin")
    password = _entorno.maquina().get("pve_routeros_password", "")
    scheme = defaults.get("routeros_scheme", "http")
    port = defaults.get("routeros_port", 80)

    # La PRIMERA entrada de `addresses` es la de gestión; las demás pueden traer
    # plantillas, que aquí no se resuelven.
    devices = []
    for v in (manifest.get("pve_vms") or []):
        ros = ((v.get("config") or {}).get("routeros") or {})
        addrs = ros.get("addresses") or []
        if not addrs:
            continue
        host = str(addrs[0].get("address", "")).split("/")[0]
        if not host or "{{" in host:
            continue
        devices.append((ros.get("identity") or v.get("name") or str(v.get("vmid")), host))
    if not devices:
        fail("la declaración no tiene ningún equipo RouterOS con dirección de gestión")

    session = requests.Session()
    session.auth = (user, password)
    culpables, inalcanzables = [], []
    for name, host in devices:
        base = f"{scheme}://{host}:{port}/rest"
        try:
            r = session.get(f"{base}/ip/route", timeout=15)
            r.raise_for_status()
            rutas = r.json()
        except Exception as e:
            inalcanzables.append((name, host, type(e).__name__))
            continue
        # La ruta del lease lleva `dhcp: "true"`; una ruta CONECTADA dinámica no tiene
        # dst 0.0.0.0/0, así que el filtro por destino ya la excluye.
        dyn = [x for x in rutas
               if str(x.get("dst-address", "")) == "0.0.0.0/0"
               and str(x.get("dhcp", "")).lower() == "true"]
        if dyn:
            culpables.append((name, host, [str(x.get("gateway", "?")) for x in dyn]))

    if inalcanzables:
        for n, h, e in inalcanzables:
            say(f"  INALCANZABLE: {n} ({h}) — {e}")
        fail("no se pudo comprobar algún equipo RouterOS; revisa la ruta de control")
    if culpables:
        for n, h, gws in culpables:
            say(f"  RUTA DINÁMICA: {n} ({h}) via {', '.join(gws)}")
        fail("algún equipo conserva la ruta por defecto dinámica del DHCP de fábrica (ADR 0003)")
    say(f"  {len(devices)} equipo(s): ninguno con ruta por defecto dinámica")
    say("\nPASS: la ruta del DHCP de fábrica está purgada en todos los equipos (ADR 0003).")
    return 0


def _labs_declarados():
    """[(nombre, ruta_manifest)] de todos los laboratorios, menos el enlace `active`."""
    raiz = os.path.join(REPO, "labs")
    out = []
    for nombre in sorted(os.listdir(raiz)):
        ruta = os.path.join(raiz, nombre)
        if os.path.islink(ruta):      # `active` es un enlace a uno de los laboratorios
            continue
        p = os.path.join(ruta, "inventory", "group_vars", "all.yml")
        if os.path.isfile(p):
            out.append((nombre, p))
    return out


def _lab_set(ruta):
    """(vmids declarados, el Resource Pool del laboratorio)."""
    d = yaml.safe_load(open(ruta)) or {}
    vmids = set()
    for clave in ("pve_containers", "pve_vms"):
        for it in (d.get(clave) or []):
            if isinstance(it, dict) and it.get("vmid") is not None:
                vmids.add(int(it["vmid"]))
    return vmids, d.get("lab_pool")


def guests_check():
    """La plataforma no tiene invitados del lab fuera de la declaración.

    «Del laboratorio» lo dice su Resource Pool, NO una etiqueta (ADR 0008): el pool
    es lo que PVE enseña en su árbol y lo único que la plataforma puede hacer
    cumplir, así que la pregunta y la respuesta están en el mismo sitio. Un invitado
    del host (hermesagent, caddy, netbox) no está en ningún pool de laboratorio y
    queda fuera del juicio, y no hace falta adivinar por rango de VMID —que se
    solaparía entre laboratorios— ni por lista escrita a mano, que envejece.
    """
    say("== guests: ningún invitado del lab fuera de la declaración ==")
    labs = _labs_declarados()
    if not labs:
        fail("no hay ningún laboratorio declarado en labs/")
    union, pools, por_lab = set(), {}, {}
    for nombre, ruta in labs:
        vmids, poolid = _lab_set(ruta)
        if not poolid:
            fail(f"el laboratorio «{nombre}» no declara lab_pool: sin pool no hay "
                 f"forma de reconocer sus invitados (docs/decisiones/0008)")
        if poolid in pools:
            fail(f"«{nombre}» y «{pools[poolid]}» declaran el MISMO pool {poolid!r}: "
                 f"los invitados de uno se leerían como los del otro")
        pools[poolid] = nombre
        union |= vmids
        por_lab[nombre] = vmids

    # El laboratorio ACTIVO es el que se está operando, y eso lo dice `LAB`, que
    # respeta HERMES_LAB: leer el manifiesto de uno y exigir los invitados del
    # enlace `active` es juzgar a un laboratorio con el censo de otro.
    activo = os.path.basename(os.path.realpath(os.path.join(REPO, LAB)))

    # Una sola lectura dice tres cosas de cada invitado: quién es, de qué tipo y en
    # qué pool está. `cluster/resources` es del datacenter entero, así que también
    # se ve un invitado del laboratorio que hubiera aparecido en otro nodo.
    session, base = _api()
    r = session.get(f"{base}/cluster/resources?type=vm", timeout=30)
    r.raise_for_status()
    plataforma, del_lab = {}, {}
    for g in r.json().get("data") or []:
        if g.get("vmid") is None:
            continue
        vmid = int(g["vmid"])
        poolid = str(g.get("pool") or "")
        plataforma[vmid] = {"name": g.get("name"), "kind": g.get("type"), "pool": poolid}
        if poolid in pools:
            del_lab[vmid] = plataforma[vmid]

    extras = sorted(v for v in del_lab if v not in union)
    faltan = sorted(v for v in por_lab.get(activo, set()) if v not in plataforma)

    say(f"  {len(labs)} laboratorio(s), {len(union)} invitado(s) declarados; "
        f"{len(plataforma)} en la plataforma, {len(del_lab)} del lab")
    for v in extras:
        g = del_lab[v]
        say(f"  EXTRA: {g['kind']} {v} «{g['name']}» está en el pool {g['pool']!r} "
            f"({pools[g['pool']]}) pero ningún laboratorio lo declara")
    for v in faltan:
        say(f"  FALTA: el laboratorio «{activo}» declara {v} y no está en la plataforma")
    if extras or faltan:
        fail(f"{len(extras)} invitado(s) sin declarar y {len(faltan)} declarado(s) ausente(s)")
    say(f"PASS: los {len(del_lab)} invitados del lab están declarados y no falta ninguno "
        f"(lab activo «{activo}»).")
    return 0


MANIFIESTO_REFS = os.path.join(REPO, "docs", ".refs-revisado.json")


def _sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


def _resolver(doc, objetivo):
    """Resuelve el destino de un puntero a una ruta del repo, o None si no existe.

    El enlace es relativo al DOCUMENTO: los de la raíz usan rutas desde la raíz, los de
    `docs/decisiones/` desde su carpeta. Se prueban las dos.
    """
    if not objetivo:
        return None
    for cand in (os.path.join(os.path.dirname(doc), objetivo), objetivo):
        cand = os.path.normpath(cand)
        if os.path.exists(os.path.join(REPO, cand)):
            return cand
    return None


def _citas_por_doc():
    """{doc: [rutas citadas]} — el destino de cada puntero de cada documento, deduplicado."""
    out = {}
    for doc in _documentos_rastreables():
        texto = open(os.path.join(REPO, doc), encoding="utf-8").read()
        citados = []
        for t in _punteros(texto):
            r = _resolver(doc, t.split("#", 1)[0])
            if r and r not in citados:
                citados.append(r)
        out[doc] = sorted(citados)
    return out


def refs_sellar(docs=None):
    """Sella las citas actuales: «estos documentos están revisados CONTRA este código».

    El sello no juzga la prosa —eso no lo ve un check—: fija el punto de referencia. Cuando
    el fichero citado cambie, `caducidad` dirá qué documentos toca revisar; tras revisarlos
    (cambiando la frase o confirmando que sigue siendo cierta) se vuelve a sellar. `docs`
    vacío sella todos; una lista sella sólo esos (para no borrar el aviso del resto).
    """
    actual = _citas_por_doc()
    manif = json.load(open(MANIFIESTO_REFS, encoding="utf-8")) if os.path.exists(MANIFIESTO_REFS) else {}
    sellados = []
    for doc, citas in actual.items():
        if docs and doc not in docs:
            continue
        manif[doc] = {c: _sha256(os.path.join(REPO, c)) for c in citas}
        sellados.append(doc)
    for doc in list(manif):                       # poda: documentos que ya no existen
        if doc not in actual:
            del manif[doc]
    os.makedirs(os.path.dirname(MANIFIESTO_REFS), exist_ok=True)
    with open(MANIFIESTO_REFS, "w", encoding="utf-8") as f:
        json.dump(manif, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    say(f"== refs --sellar: {len(sellados)} documento(s) sellados contra el código actual ==")
    for doc in sellados:
        say(f"  {doc}: {len(manif[doc])} cita(s)")
    return 0


def caducidad_check():
    """Dice CUÁNDO revisar un documento, no sólo dónde: el código citado se ha movido.

    `refs` responde «qué documentos citan este fichero» cuando eres tú quien cambia el
    código. Esto es el complemento: compara el hash actual de cada fichero citado con el
    que quedó grabado al sellar, y avisa de los documentos que citan algo que cambió desde
    su última revisión. La prosa no se puede comprobar; lo que SÍ se puede es saber que ha
    dejado de estar revisada. Convierte «acuérdate de mirar» en un hecho del repo.
    """
    say("== caducidad: documentos que citan código cambiado desde su última revisión ==")
    if not os.path.exists(MANIFIESTO_REFS):
        fail("no hay docs/.refs-revisado.json; siémbralo con `framework_check.py refs --sellar`")
    manif = json.load(open(MANIFIESTO_REFS, encoding="utf-8"))
    actual = _citas_por_doc()

    sin_sello, caducados, nuevas, huerfanas = [], [], [], []
    for doc, citas in actual.items():
        reg = manif.get(doc)
        if reg is None:
            sin_sello.append(doc)
            continue
        for c in citas:
            if c not in reg:
                nuevas.append((doc, c))
            elif _sha256(os.path.join(REPO, c)) != reg[c]:
                caducados.append((doc, c))
        for c in reg:
            if c not in citas:
                huerfanas.append((doc, c))

    for doc in sin_sello:
        say(f"  SIN SELLO: {doc} no está en el manifiesto")
    for doc, c in nuevas:
        say(f"  CITA NUEVA: {doc} cita {c}, sin sellar")
    for doc, c in caducados:
        say(f"  CADUCADO: {doc} cita {c}, que cambió desde su última revisión")
    for doc, c in huerfanas:
        say(f"  HUÉRFANA: {doc} ya no cita {c} pero sigue sellada")

    problemas = len(sin_sello) + len(nuevas) + len(caducados) + len(huerfanas)
    if problemas:
        say("")
        fail(f"{problemas} aviso(s). Revisa esos documentos y vuelve a sellar "
             f"(`framework_check.py refs --sellar [documento…]`). No es que la prosa esté "
             f"mal: es que ha dejado de estar revisada.")
    say(f"PASS: los {len(actual)} documento(s) con punteros están sellados contra el código actual.")
    return 0


def docs_check():
    """Los documentos del repositorio, contra la declaración que los genera.

    Un documento escrito a mano es una segunda fuente de verdad, y la que nadie
    relee: acaba nombrando un puerto que ya no existe o un invitado que se fue.
    Aquí se compara el documento en disco con su RENDER: si difieren, o alguien
    editó el documento (que se genera), o cambió la declaración y no se regeneró.
    """
    import documentos as _doc
    say("== docs: los documentos contra la declaración ==")
    ctx = _doc.contexto(manifiesto())
    malos = []
    for plantilla, salida in _doc.DOCUMENTOS:
        nuevo = _doc.render(plantilla, ctx)
        ruta = os.path.join(REPO, salida)
        actual = open(ruta, encoding="utf-8").read() if os.path.exists(ruta) else None
        if actual != nuevo:
            malos.append(salida)
            say(f"  DESFASADO : {salida} — no es el render de docs/{plantilla}")
        else:
            say(f"  al día    : {salida}")
    if malos:
        fail("hay documentos que no son el render de la declaración; "
             "ejecuta `python3 playbooks/tools/documentos.py`")
    # --- punteros: el doc apunta al código que explica el mecanismo ----------
    rotos = []
    for salida in _documentos_rastreables():
        ruta = os.path.join(REPO, salida)
        if not os.path.exists(ruta):
            continue
        for t in _punteros(open(ruta, encoding="utf-8").read()):
            if _resolver(salida, t.split("#", 1)[0]) is None:
                rotos.append((salida, t))
    if rotos:
        for salida, t in rotos:
            say(f"  PUNTERO ROTO: {salida} -> {t}")
        fail("hay documentos que apuntan a rutas que no existen; "
             "un puntero roto lleva a tocar lo que no es")
    say("  punteros  : todas las rutas citadas por los documentos existen")
    say("\nPASS: los documentos son el render de la declaración, no una copia a mano.")
    return 0



def _codigo_numero(codigo, familias):
    """El valor numérico del código de sede: familia (posición + 1) * 10 + índice.

    El código son DOS letras: la primera es la FAMILIA, cuya POSICIÓN en
    `lab_familias` da la decena; la segunda, minúscula, el índice dentro de ella
    (`a`=1). Así `Ca`=11, `Sa`=21, `Sb`=22, `Ia`=31, `Ga`=41, `Ba`=51.
    """
    letras = [f["letra"] for f in familias]
    return (letras.index(codigo[0]) + 1) * 10 + (ord(codigo[1].lower()) - ord("a") + 1)


def numeracion_check():
    """El número de cada invitado se compone de su declaración, y su nombre lo espeja.

    Un VMID de 7 cifras es L SS CC II: laboratorio (UNA cifra), sede, clase, índice.
    La sede se declara como dos letras —la familia (`lab_familias`) y su índice
    minúscula— y su POSICIÓN en la tabla da la decena; la clase como un número de la
    tabla `lab_clases`; el nombre se compone como `L-SS-token-II`. El check no adivina
    nada: comprueba que el número y el nombre de la MISMA declaración se componen de
    la misma forma. Si un invitado se numera a mano y se desvía, aquí se ve.
    """
    say("== numeracion: el numero y el nombre de cada invitado ==")
    man = manifiesto()
    lab = man.get("lab_numero")
    if lab is None:
        say("  SKIP: este laboratorio no declara lab_numero (migracion pendiente)")
        return 0
    if not re.fullmatch(r"[1-9]", str(lab)):
        fail(f"lab_numero es UNA cifra de 1 a 9 (la L del numero; ver docs/decisiones/0008): "
             f"{lab!r}")
    familias = man.get("lab_familias") or []
    if not familias:
        fail("este laboratorio no declara lab_familias: el codigo de sede no se puede leer")
    sedes = {s.get("codigo"): s for s in man.get("lab_sites", []) if s.get("codigo")}
    sedes.update({c: {"codigo": c} for c in (man.get("lab_sedes_extra") or {})})
    clases = {int(k): v for k, v in (man.get("lab_clases") or {}).items()}
    sede_por_numero = {_codigo_numero(c, familias): c for c in sedes}
    invitados = list(man.get("pve_containers") or []) + list(man.get("pve_vms") or [])
    errores = []
    for g in invitados:
        vmid = g.get("vmid")
        nombre = g.get("hostname") or g.get("name")
        if vmid is None or not nombre:
            errores.append(f"invitado sin vmid o nombre: {g}")
            continue
        cifras = str(vmid)
        if len(cifras) != 7:
            errores.append(f"{nombre}: vmid {vmid} no tiene 7 cifras")
            continue
        ll, ss, cc, ii = cifras[0:1], cifras[1:3], cifras[3:5], cifras[5:7]
        if ll != str(lab):
            errores.append(f"{nombre}: vmid {vmid} empieza por {ll}, no por el laboratorio {lab}")
        if int(ss) not in sede_por_numero:
            errores.append(f"{nombre}: vmid {vmid} usa la sede {ss}, que no esta declarada")
            continue
        if int(cc) not in clases:
            errores.append(f"{nombre}: vmid {vmid} usa la clase {cc}, que no esta declarada")
            continue
        token = clases[int(cc)]["token"]
        esperado = f"{ll}-{sede_por_numero[int(ss)]}-{token}-{ii}"
        if nombre != esperado:
            errores.append(f"{nombre}: el nombre no espeja el numero (esperado {esperado})")
    for e in errores:
        say(f"  DESFASE: {e}")
    if errores:
        fail(f"{len(errores)} invitado(s) con numero o nombre que no cuadran con el esquema")
    say(f"PASS: los {len(invitados)} invitados de este laboratorio tienen numero y nombre coherentes.")
    return 0


def pool_check():
    """El Resource Pool de cada laboratorio: lo declara, se llama como su carpeta, no se comparte.

    El pool es la identidad del laboratorio en la plataforma (ADR 0008), así que su
    nombre se puede comprobar sin tocar la plataforma: que el laboratorio lo declare,
    que sea `lab-<nombre de su carpeta>` (el pool dice QUÉ laboratorio es, y la
    carpeta es lo que nombra al laboratorio dentro del repo: son el mismo nombre, y
    aquí se exige que lo sean) y que ningún otro laboratorio declare el mismo. Dos
    laboratorios con el mismo poolid harían que los invitados de uno se leyeran como
    los del otro, que es exactamente lo que el pool viene a evitar.
    """
    say("== pool: el Resource Pool de cada laboratorio ==")
    labs = _labs_declarados()
    if not labs:
        fail("no hay ningún laboratorio declarado en labs/")
    vistos, errores = {}, []
    for nombre, ruta in labs:
        _vmids, poolid = _lab_set(ruta)
        esperado = f"lab-{nombre}"
        if not poolid:
            errores.append(f"{nombre}: no declara lab_pool")
            continue
        poolid = str(poolid)
        if not re.fullmatch(r"lab-[a-z0-9][a-z0-9._-]*", poolid):
            errores.append(f"{nombre}: lab_pool {poolid!r} no tiene forma de poolid: minúsculas, "
                           f"dígitos, guion, más y punto, y sin espacios (ver docs/decisiones/0008)")
        if poolid != esperado:
            errores.append(f"{nombre}: lab_pool es {poolid!r} y se espera {esperado!r}: "
                           f"el pool de un laboratorio se llama como su carpeta")
        if poolid in vistos:
            errores.append(f"{nombre}: comparte el pool {poolid!r} con el laboratorio "
                           f"«{vistos[poolid]}»")
        vistos[poolid] = nombre
    for e in errores:
        say(f"  DESFASE: {e}")
    if errores:
        fail(f"{len(errores)} laboratorio(s) con un Resource Pool que no cuadra")
    say(f"PASS: los {len(labs)} laboratorios tienen su pool y no lo comparte ninguno: "
        f"{', '.join(sorted(vistos))}.")
    return 0


def main():
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    sub = parser.add_subparsers(dest="mode")
    inv = sub.add_parser("invariant", help="run a verb twice; the second run must change nothing")
    inv.add_argument("--verb", default="playbooks/apply.yml")
    drl = sub.add_parser("drill", help="inject drift, watch preflight see it and apply repair it")
    drl.add_argument("--verb", default="playbooks/apply.yml")
    drl.add_argument("--preflight", default="playbooks/preflight.yml")
    sub.add_parser("agree", help="the check's own map must match the declaration")
    sub.add_parser("export", help="los equipos de red sólo tienen lo que la declaración declara")
    sub.add_parser("plan", help="el plan del rol RouterOS: sin red, sin equipo, sin credenciales")
    sub.add_parser("notas", help="la nota HTML y las etiquetas de cada invitado, contra la declaración")
    nl = sub.add_parser("nuevo-lab", help="crear un laboratorio nuevo copiando uno existente")
    nl.add_argument("nombre", help="nombre del laboratorio nuevo (labs/<nombre>)")
    nl.add_argument("--desde", help="laboratorio de origen (por defecto: labs/active)")
    nl.add_argument("--activar", action="store_true",
                    help="reapuntar labs/active al laboratorio nuevo")
    lm = sub.add_parser("labmap", help="emitir el mapa de este laboratorio (derivado de la declaración)")
    lm.add_argument("--check", action="store_true",
                    help="verificar que el script no lleva topología incrustada")
    lm.add_argument("--emit", action="store_true",
                    help="imprimir el mapa en stdout, sin escribir en lab-check.sh")
    sub.add_parser("api", help="la API sólo se toca por la puerta (tools/ + uri), no a mano")
    sub.add_parser("docs", help="los documentos son el render de la declaración, no copia a mano")
    sub.add_parser("routeros", help="ningún equipo con ruta por defecto dinámica tras converger (ADR 0003)")
    sub.add_parser("guests", help="la plataforma no tiene invitados del lab fuera de la declaración")
    rf = sub.add_parser("refs", help="índice inverso de citas; con --sellar, fija el punto de revisión")
    rf.add_argument("ruta", nargs="?", default=None)
    rf.add_argument("--sellar", nargs="*", default=None,
                    help="sella las citas actuales (sin nombres: todos los documentos)")
    sub.add_parser("caducidad", help="documentos que citan código cambiado desde su última revisión")
    sub.add_parser("numeracion", help="el numero y el nombre de cada invitado se componen igual")
    sub.add_parser("pool", help="el Resource Pool de cada laboratorio: declarado, propio y sin compartir")
    args = parser.parse_args()

    if args.mode == "invariant":
        return invariant(args.verb)
    if args.mode == "drill":
        return drill(args.verb, args.preflight)
    if args.mode == "agree":
        return agree()
    if args.mode == "export":
        return routeros_export()
    if args.mode == "plan":
        return plan_check()
    if args.mode == "notas":
        return notas_check()
    if args.mode == "labmap":
        return labmap(args.check, args.emit)
    if args.mode == "nuevo-lab":
        return nuevo_lab(args.nombre, args.desde, args.activar)
    if args.mode == "api":
        return api_check()
    if args.mode == "docs":
        return docs_check()
    if args.mode == "routeros":
        return routeros_check()
    if args.mode == "guests":
        return guests_check()
    if args.mode == "refs":
        if args.sellar is not None:
            return refs_sellar(args.sellar or None)
        return refs(args.ruta)
    if args.mode == "numeracion":
        return numeracion_check()
    if args.mode == "pool":
        return pool_check()
    if args.mode == "caducidad":
        return caducidad_check()
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
