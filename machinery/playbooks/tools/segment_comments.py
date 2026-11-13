#!/usr/bin/env python3
# PROPÓSITO: poner en el nodo los comentarios de cableado y crear los segmentos que
#   falten.
# INVARIANTES: el motor de aplicar sólo CREA segmentos (uno existente se deja igual, para
#   no cortar un laboratorio vivo); esto actualiza por API, el mismo camino que el motor.
# VER: ejecución directa.
"""Pone en el nodo los comentarios de cableado de la v2 y crea los segmentos
que falten.

Por qué existe: el motor de aplicar sólo CREA segmentos — uno que ya existe se
deja exactamente como está, a propósito, porque recrear un bridge bajo un
laboratorio vivo cortaría a sus invitados. Eso significa que el comentario de
vmbr4..vmbr17 seguiría diciendo "cable: ws1 eth0 <-> sw1 ether2" (el cableado
de la v1). Esto lo actualiza por API, que es el mismo camino que usa el motor.

Uso:
    segment_comments.py --dry-run     # sólo dice qué haría
    segment_comments.py               # lo hace y verifica
"""
import argparse
import os
import sys
import time

import requests
import yaml

# La ruta se DERIVA de la ubicacion del propio fichero, nunca se escribe a mano:
# una ruta absoluta codificada hace que la herramienta solo funcione en la
# maquina donde se escribio.
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MANIFEST = os.path.join(REPO, "labs/active")
ENTORNO = os.path.join(REPO, "secrets.yaml")


def session_and_node():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import entorno as _entorno

    creds = _entorno.api()
    s = requests.Session()
    s.headers.update({"Authorization": "PVEAPIToken=%s=%s" % (
        creds["token_id"], creds["token_secret"])})
    s.verify = creds["ca_path"]
    man = yaml.safe_load(open(MANIFEST))
    return s, "https://%s:%s/api2/json" % (creds["host"], creds["port"]), man["pve_node"], man


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-apply", action="store_true",
                    help="prepara los cambios pero NO recarga la red del nodo")
    args = ap.parse_args()

    s, base, node, man = session_and_node()
    declarados = man["pve_bridges"]

    live = s.get("%s/nodes/%s/network" % (base, node), timeout=30).json()["data"]
    por_iface = {i["iface"]: i for i in live}

    crear, comentar, ya_ok = [], [], []
    for b in declarados:
        actual = por_iface.get(b["iface"])
        if actual is None:
            crear.append(b)
        elif (actual.get("comments") or "").strip() != b["comments"].strip():
            comentar.append((b, (actual.get("comments") or "").strip()))
        else:
            ya_ok.append(b["iface"])

    print("segmentos declarados:", len(declarados))
    print("  ya correctos :", len(ya_ok), ya_ok)
    print("  hay que CREAR:", len(crear), [b["iface"] for b in crear])
    print("  comentario viejo -> nuevo:")
    for b, viejo in comentar:
        print("    %-8s %r  ->  %r" % (b["iface"], viejo, b["comments"]))
    if not crear and not comentar:
        print("\nNada que hacer: el nodo ya dice lo que la declaracion.")
        return 0

    if args.dry_run:
        print("\nSIMULACRO: no se ha tocado nada.")
        return 0

    for b in crear:
        r = s.post("%s/nodes/%s/network" % (base, node), data={
            "iface": b["iface"], "type": "bridge", "autostart": 1,
            "bridge_ports": "", "comments": b["comments"]}, timeout=30)
        r.raise_for_status()
        print("creado   :", b["iface"])
    for b, _viejo in comentar:
        # `type` no es opcional en el PUT de una interfaz, aunque ya exista:
        # sin él la API responde 400 "type: property is missing".
        r = s.put("%s/nodes/%s/network/%s" % (base, node, b["iface"]),
                  data={"type": "bridge", "comments": b["comments"]}, timeout=30)
        r.raise_for_status()
        print("comentado:", b["iface"])

    if args.no_apply:
        print("\nCambios PREPARADOS y sin aplicar (--no-apply).")
        print("El nodo los hará efectivos en el proximo apply de red:")
        print("  - desde la interfaz de Proxmox: boton 'Apply Configuration'")
        print("  - o con el motor: ansible-playbook machinery/playbooks/apply.yml")
        print("Se relee el nodo para dejar constancia de lo que queda pendiente.")
        live = s.get("%s/nodes/%s/network" % (base, node), timeout=30).json()["data"]
        pend = [i["iface"] for i in live if i.get("iface") in
                [b["iface"] for b in declarados] and not i.get("active")]
        print("  segmentos declarados que aun NO estan activos:", pend or "ninguno")
        return 0

    r = s.put("%s/nodes/%s/network" % (base, node), timeout=60)
    r.raise_for_status()
    upid = r.json()["data"]
    print("aplicando cambios de red (UPID %s)..." % upid)
    for _ in range(60):
        st = s.get("%s/nodes/%s/tasks/%s/status" % (base, node, upid), timeout=30).json()["data"]
        if st.get("status") == "stopped":
            print("apply terminado:", st.get("exitstatus"))
            break
        time.sleep(2)

    # Verificación: se relee el nodo y se compara con lo declarado.
    live = s.get("%s/nodes/%s/network" % (base, node), timeout=30).json()["data"]
    por_iface = {i["iface"]: i for i in live}
    malos = []
    for b in declarados:
        i = por_iface.get(b["iface"])
        if i is None or (i.get("comments") or "").strip() != b["comments"].strip():
            malos.append(b["iface"])
    inactivos = [b["iface"] for b in declarados
                 if not por_iface.get(b["iface"], {}).get("active")]
    con_puertos = [b["iface"] for b in declarados
                   if (por_iface.get(b["iface"], {}).get("bridge_ports") or "") != ""]
    print()
    print("VERIFICACION (releyendo el nodo):")
    print("  comentario incorrecto o ausente:", malos or "ninguno")
    print("  no activos                     :", inactivos or "ninguno")
    print("  con puertos (deben estar aislados):", con_puertos or "ninguno")
    return 1 if (malos or inactivos or con_puertos) else 0


if __name__ == "__main__":
    sys.exit(main())
