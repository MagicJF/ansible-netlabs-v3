#!/usr/bin/env python3
# PROPÓSITO: renderizar los documentos con valores desde la declaración.
# INVARIANTES: un documento con nombres, direcciones o recuentos a mano es una SEGUNDA
#   fuente de verdad; los documentos con valores se RENDERIZAN desde el manifiesto.
# VER: `framework_check.py docs`.
# ===========================================================================
# documentos.py — los documentos del repositorio, renderizados desde la
#                 declaración.
#
# Por qué existe: un documento escrito a mano con nombres, direcciones y
# recuentos dentro es una SEGUNDA fuente de verdad, y la que nadie vuelve a
# mirar. En este repositorio la fuente es el manifiesto (`group_vars/all.yml`);
# así que los documentos con valores (este laboratorio, el README) se RENDERIZAN
# desde él con plantillas Jinja en `docs/`. Un documento no puede contradecir a
# la declaración porque sale de ella: si un día nombrara otro puerto, sería la
# plantilla la que está mal, y eso se ve en el diff de una regeneración.
#
# Lo que NO se genera: la prosa que explica y las reglas. Eso es criterio, no
# dato, y vive en la plantilla como texto. Lo que sí: cualquier VALOR —nombre de
# invitado, dirección, bridge, vmid, recuento, red— sale de la declaración.
#
# Uso:
#     python3 machinery/playbooks/tools/documentos.py            # regenera los documentos
#     python3 machinery/playbooks/tools/documentos.py --check    # falla si están desfasados
#     python3 machinery/playbooks/tools/documentos.py --lista    # qué se genera y de dónde
# ===========================================================================
import argparse
import os
import re
import sys

import ipaddress

import jinja2

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import declaracion  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(AQUI)))
LAB = "labs/active"
MANIFIESTO = os.path.join(REPO, LAB)
PLANTILLAS = os.path.join(REPO, "docs")

# (plantilla, salida). La salida es relativa a la raíz del repositorio.
DOCUMENTOS = [
    ("laboratorio.md.j2", "docs/EL-LABORATORIO.md"),
    ("README.md.j2", "docs/README.md"),
]

# El orden de los roles en las tablas: del que no enruta al que más hace.
ORDEN_ROL = {"workstation": 0, "switch": 1, "router": 2, "firewall": 3, "bootstrap": 4}


def _en_red(ip, red):
    """¿La dirección cae dentro de la red declarada? Se compara como DIRECCIÓN, no texto."""
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(red, strict=False)
    except (ValueError, TypeError):
        return False


def _dir_gestion(g, tipo):
    """La dirección de gestión DECLARADA: el contenedor en `address`, el CHR en `ether1`."""
    if tipo == "LXC":
        if g.get("address"):
            return g["address"]
        mm = re.search(r"\bip=([\d.]+)/", (g.get("netif") or {}).get("net0", ""))
        return mm.group(1) if mm else None
    for a in ((g.get("config") or {}).get("routeros") or {}).get("addresses", []):
        if a.get("interface") == "ether1":
            return a["address"].split("/")[0]
    return None


def _identidad(dir_gestion, man):
    """(sede, rol) leídos de la DECLARACIÓN, nunca del nombre.

    La sede y el papel de un invitado salen de las direcciones que la declaración ya
    fija: la sede, por sus redes (`lab_sites[].red` para las estaciones y `.mgmt` para
    los equipos de red); el borde y la infraestructura, por `lab_mgmt_otros`; y el
    segundo segmento de gestión, por `lab_mgmt2`. Así un laboratorio con otra
    convención de nombres —mini llama `pc-u1-01` y `rt-u1` a los suyos— se documenta
    igual, sin que el motor conozca ningún esquema de nombres.
    """
    sites = {int(s["id"]): s for s in man.get("lab_sites") or []}
    otros = man.get("lab_mgmt_otros") or {}
    mgmt2 = man.get("lab_mgmt2") or {}
    if dir_gestion:
        if otros.get("borde") and dir_gestion == otros["borde"]:
            return None, "firewall"
        if otros.get("infra") and dir_gestion == otros["infra"]:
            return None, "bootstrap"
        if mgmt2.get("red") and _en_red(dir_gestion, mgmt2["red"]):
            return None, "switch"
    for sid, s in sites.items():
        m = s.get("mgmt") or {}
        if dir_gestion:
            if dir_gestion == m.get("rt"):
                return sid, "router"
            if dir_gestion == m.get("fw"):
                return sid, "firewall"
            if dir_gestion in (m.get("sw") or []):
                return sid, "switch"
            if s.get("red") and _en_red(dir_gestion, s["red"]):
                return sid, "workstation"
    return None, None


def _clase_sitio(sede, rol):
    """De dónde cuelga: 'sede', 'infra', 'gestion' o 'borde' (por su sede y su papel)."""
    if sede is not None:
        return "sede"
    return {"bootstrap": "infra", "switch": "gestion", "firewall": "borde"}.get(rol)


def _sitio(sede, rol, por_id, man):
    """El CÓDIGO de sitio (familia + índice) de un invitado, de la declaración.

    El de una sede es su `codigo`; el de quien no cuelga de ninguna sale de
    `lab_sedes_extra` por su familia, según el papel.
    """
    if sede in por_id:
        return por_id[sede].get("codigo")
    extra = {c[0]: c for c in (man.get("lab_sedes_extra") or {})}
    return extra.get({"bootstrap": "I", "switch": "G", "firewall": "B"}.get(rol))


def _patas(g, tipo):
    """Las patas declaradas, leídas por CLAVE (la MAC va en hwaddr o en virtio)."""
    campo = g.get("netif") if tipo == "LXC" else g.get("net")
    out = []
    for k, v in (campo or {}).items():
        d = dict(x.split("=", 1) for x in v.split(",") if "=" in x)
        out.append({"pata": k,
                    "boca": d.get("name") if tipo == "LXC" else "ether%d" % (int(k[3:]) + 1),
                    "bridge": d.get("bridge"),
                    "mac": d.get("hwaddr") or d.get("virtio")})
    return out


def contexto(man):
    """Todo lo que las plantillas pueden citar, derivado de la declaración."""
    sedes = man["lab_sites"]
    ids = sorted(s["id"] for s in sedes)
    hub = int(man["lab_hub"])
    por_id = {s["id"]: s for s in sedes}
    hub_sede = por_id[hub]

    # --- los invitados: su identidad sale de la declaración, no del nombre
    invitados = []
    for c in man["pve_containers"]:
        d = _dir_gestion(c, "LXC")
        sede, r = _identidad(d, man)
        invitados.append({
            "n": c["hostname"], "vmid": c["vmid"], "tipo": "LXC",
            "rol": r, "sede": sede, "clase": _clase_sitio(sede, r),
            "sitio": _sitio(sede, r, por_id, man),
            "gestion": d, "direccion": d,
            "patas": _patas(c, "LXC"),
        })
    for v in man["pve_vms"]:
        d = _dir_gestion(v, "CHR")
        sede, r = _identidad(d, man)
        invitados.append({
            "n": v["name"], "vmid": v["vmid"], "tipo": "CHR",
            "rol": r, "sede": sede, "clase": _clase_sitio(sede, r),
            "sitio": _sitio(sede, r, por_id, man),
            "gestion": d, "direccion": d,
            "patas": _patas(v, "CHR"),
        })
    invitados.sort(key=lambda x: (ORDEN_ROL.get(x["rol"], 9), x["n"]))

    def de_rol(r):
        return [e for e in invitados if e["rol"] == r]

    def de_sede(e):
        return [x for x in invitados if x["sede"] == e]

    # --- la red de gestión, por bloques de función (derivados, no escritos)
    def bloque(prefijo_rol):
        base = man["lab_mgmt_network"].rsplit(".", 1)[0]
        der = sorted(int(e["gestion"].split(".")[-1]) for e in invitados
                     if e["rol"] == prefijo_rol and e["gestion"]
                     and e["gestion"].startswith(base))
        return der

    def bloque_txt(prefijo_rol):
        d = bloque(prefijo_rol)
        if not d:
            return "—"
        return ".%d" % d[0] if len(d) == 1 else ".%d-.%d" % (d[0], d[-1])

    corto = {s["id"]: s["etiqueta"].split(" (")[0] for s in sedes}

    def funcion(e):
        """Qué es un invitado, en una frase, derivado de su rol y su posición.

        La prosa del «qué es» es criterio, pero el SUJETO de la frase (qué rol,
        de qué sede, de qué tipo) es dato: se deriva para que añadir un invitado
        no deje una fila sin escribir.
        """
        if e["clase"] == "borde":
            return "firewall de **borde**: filtrado **y NAT** (el único que sale a internet)"
        if e["rol"] == "bootstrap":
            return "da a cada equipo de red su **primera** dirección, una vez"
        if e["sede"] is None and e["rol"] == "switch":
            return "switch del segundo segmento de gestión (OOB)"
        donde = corto[e["sede"]] if e["sede"] else "la red de gestión"
        if e["rol"] == "workstation":
            return "workstation de %s%s" % (donde, " (LXC)" if e["tipo"] == "LXC" else "")
        if e["rol"] == "switch":
            return "switch de acceso de %s" % donde
        if e["rol"] == "router":
            return "router de %s: puerta de la LAN **y servidor DHCP**" % donde
        if e["rol"] == "firewall":
            return "perímetro de %s: filtrado" % donde
        return e["rol"]

    def equipo(sid, rol_):
        """El nombre del primer invitado de esa sede con ese papel — por la declaración."""
        return next((x["n"] for x in invitados if x["sede"] == sid and x["rol"] == rol_), None)

    # Las dos piezas que no cuelgan de ninguna sede: el firewall de borde y el
    # switch del segundo segmento de gestión (OOB). Se RECONOCEN, no se nombran.
    borde_fw = next((x["n"] for x in invitados if x["clase"] == "borde"), None)
    mgmt_sw = next((x["n"] for x in invitados
                    if x["sede"] is None and x["rol"] == "switch"), None)

    # --- el camino de una sede hasta internet (equipos declarados, no nombres)
    def camino(sid):
        pc, sw, rt, fw = (equipo(sid, "workstation"), equipo(sid, "switch"),
                          equipo(sid, "router"), equipo(sid, "firewall"))
        if not all((pc, sw, rt, fw)):
            return []
        c = [pc, sw, rt, fw]
        if sid != hub:
            fh = equipo(hub, "firewall")
            if fh:
                c.append(fh)
        return c + [borde_fw or "el firewall de borde", "internet"]

    ctx = {
        "man": man,
        "man_rel": os.path.relpath(os.path.realpath(MANIFIESTO), REPO),
        # El nombre corto de una sede, para las frases compuestas: la etiqueta
        # llevaba «(sede N)» pegado y dentro de una tabla se lee mal.
        "corto": corto,
        "funcion": funcion,
        "bloque_txt": bloque_txt,
        "sedes": sedes, "hub": hub, "hub_sede": hub_sede,
        "codigos_extra": list(man.get("lab_sedes_extra") or {}),
        "sede_por_id": por_id,
        "invitados": invitados,
        "workstations": de_rol("workstation"),
        "chrs": de_rol("switch") + de_rol("router") + de_rol("firewall"),
        "equipos_red": [e for e in invitados if e["tipo"] == "CHR"],
        "bootstrap": de_rol("bootstrap"),
        "primer_pc": next((x for x in invitados
                           if x["rol"] == "workstation" and x["sede"] == hub), None),
        "lxc": [e for e in invitados if e["tipo"] == "LXC"],
        "de_rol": de_rol, "de_sede": de_sede,
        "equipo": equipo, "borde_fw": borde_fw, "mgmt_sw": mgmt_sw,
        "camino": camino, "bloque": bloque,
        "n_invitados": len(invitados),
        "n_equipos_red": len([e for e in invitados if e["tipo"] == "CHR"]),
        "n_workstations": len(de_rol("workstation")),
        "n_bridges": len(man["pve_bridges"]),
        "bridges_rango": (lambda b: (b[0], b[-1]))(
            sorted((x["iface"] for x in man["pve_bridges"]), key=lambda x: int(x[4:]))),
    }
    return ctx


def render(nombre_plantilla, ctx):
    ruta = os.path.join(PLANTILLAS, nombre_plantilla)
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        trim_blocks=True, lstrip_blocks=True, keep_trailing_newline=True)
    return env.from_string(open(ruta, encoding="utf-8").read()).render(**ctx)


def main():
    ap = argparse.ArgumentParser(
        description="Renderiza los documentos del repositorio desde la declaración.")
    ap.add_argument("--check", action="store_true",
                    help="no escribe; falla si algún documento no coincide con su render")
    ap.add_argument("--lista", action="store_true", help="qué se genera y de dónde")
    ap.add_argument("--lab", default="labs/active", help="laboratorio (labs/active o labs/<nombre>.yml)")
    args = ap.parse_args()
    global MANIFIESTO
    MANIFIESTO = os.path.join(REPO, args.lab)

    man = declaracion.cargar(MANIFIESTO)
    ctx = contexto(man)

    if args.lista:
        print("plantilla -> documento (desde %s)" % os.path.relpath(MANIFIESTO, REPO))
        for p, s in DOCUMENTOS:
            print("  docs/%-22s -> %s" % (p, s))
        return 0

    desfasados = []
    for plantilla, salida in DOCUMENTOS:
        nuevo = render(plantilla, ctx)
        ruta = os.path.join(REPO, salida)
        actual = open(ruta, encoding="utf-8").read() if os.path.exists(ruta) else None
        if actual == nuevo:
            print("  %-24s al día" % salida)
            continue
        desfasados.append(salida)
        if not args.check:
            with open(ruta, "w", encoding="utf-8") as fh:
                fh.write(nuevo)
            print("  %-24s regenerado" % salida)

    if args.check and desfasados:
        print("\nFAIL: %s no coincide(n) con su plantilla. Ejecuta `documentos.py` "
              "para regenerar." % ", ".join(desfasados))
        return 1
    print("\nPASS: los documentos son el render de la declaración." if not args.check
          else "\nPASS: los documentos coinciden con la declaración.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
