#!/usr/bin/env python3
# PROPÓSITO: decir si el DHCP que va a servir a las estaciones está EN PIE (sólo lectura).
# INVARIANTES: no basta con que un equipo «funcione» (puentes/rutas) —un router recién
#   importado no tiene configuración y ese examen lo daría por bueno—; se pregunta por el
#   DHCP y su reserva.
# VER: decide si las estaciones pueden encenderse; lo usa `apply.yml`.
"""¿Está en pie el DHCP que va a responder a las estaciones? Sólo lectura.

Por qué existe, y por qué no vale `routeros_wait.py`: aquél dice si un equipo de
red "funciona" (puentes en marcha, rutas activas) mirando lo que el equipo TIENE.
Un router recién importado no tiene configuración ninguna, así que ese examen no
encuentra nada que reprocharle y lo daría por bueno. Este contesta la pregunta
contraria, y es la que decide si una estación puede encenderse:

    ¿está ya en pie el DHCP de la sede al que va a pedirle su dirección?

Una workstation NO reintenta: su cliente DHCP pide al arrancar, se rinde y no
vuelve a preguntar. Si la enciendes antes de que su router sirva, se queda sin
dirección hasta que alguien la reinicie — y ese "alguien la reinicie" era el paso
que este laboratorio tenía que dar a mano. Aquí se comprueba, contra lo DECLARADO
y contra el equipo vivo, que quien tiene que responderle ya lo haría:

  - el servidor DHCP de la sede existe y está encendido, y
  - escucha en la interfaz que declara, y
  - su pozo existe, y
  - existe la reserva de ESTA estación (su MAC, con su dirección declarada).

Un CHR es distinto y por eso no pasa por aquí: su cliente de primer arranque
reintenta para siempre, así que se le puede encender y dejar pidiendo.

Sólo lee: no escribe una sola línea en ningún equipo.

    routeros_ready.py [--manifest RUTA] [--json]

Sale 0 cuando el DHCP de TODAS las estaciones está en pie, 1 diciendo cuál falta
y por qué, y 2 si se usa mal.
"""

import argparse
import ast
import json
import re
import os
import sys

import jinja2
import requests
import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
POR_DEFECTO = os.path.join(RAIZ, "labs/active/inventory/group_vars/all.yml")
ENTORNO = os.path.join(RAIZ, "playbooks/vars/entorno.yml")
ROUTEROS_DEFAULTS = os.path.join(RAIZ, "configure/roles/routeros/defaults/main.yml")

sys.path.insert(0, AQUI)
import declaracion  # noqa: E402


def credenciales():
    """Las mismas que usa el rol RouterOS: una sola fuente para las dos puertas."""
    valores = yaml.safe_load(open(ROUTEROS_DEFAULTS)) or {}
    clave = ""
    if os.path.exists(ENTORNO):
        clave = (yaml.safe_load(open(ENTORNO)) or {}).get("pve_routeros_password", "")
    return (valores.get("routeros_user", "admin"), clave,
            valores.get("routeros_scheme", "http"), valores.get("routeros_port", 80))


def leer(sesion, base, menu):
    """Las entradas de un menú del equipo, o None si no se puede leer."""
    try:
        r = sesion.get(f"{base}/rest/{menu}", timeout=8)
        if r.status_code != 200:
            return None
        datos = r.json()
        return datos if isinstance(datos, list) else datos.get("data", [])
    except Exception:
        return None


# La plantilla de `leases` usa piezas de Ansible que Jinja2 no trae de fábrica
# (el test `match`, por ejemplo, para quedarse con la MAC virtio de cada
# estación). Se añaden aquí, mínimas, y sólo las que la plantilla necesita: si
# alguna vez usa otra, el error lo dirá con su nombre.
ENV = jinja2.Environment(undefined=jinja2.StrictUndefined)
ENV.tests["match"] = lambda v, pat: bool(re.match(pat, str(v)))
ENV.tests["search"] = lambda v, pat: bool(re.search(pat, str(v)))


def reservas(srv, man):
    """Las reservas declaradas de un servidor DHCP, con su plantilla RESUELTA.

    En la declaración, `leases` no es una lista: es una plantilla Jinja que se
    construye recorriendo las estaciones de la sede (su dirección y su MAC). Ansible
    la evalúa cuando el play la usa, así que el rol la ve ya como lista; aquí se lee
    el fichero en crudo y hay que resolverla.

    No vale serializar el bloque entero y renderizarlo — es lo que hace `pve_notas`
    y por eso BORRA este campo: `json.dumps` deja los saltos de línea escapados y
    Jinja revienta al compilar. Se renderiza sólo la plantilla y se evalúa su
    salida, que es un literal Python (comillas simples), no JSON.
    """
    l = srv.get("leases")
    if isinstance(l, str):
        l = ast.literal_eval(ENV.from_string(l).render(**dict(man)))
    return l or []


def encargos(man):
    """Qué router tiene que servir a qué estación, sacado de la declaración.

    Se lee del ROUTER y no de la estación: el router declara sus servidores DHCP
    y, dentro de cada uno, las reservas con la MAC y la dirección de cada
    workstation de su sede. La lista de "quién le responde" ya está escrita una
    vez, así que aquí sólo se recorre.
    """
    fuera = []
    for v in man["pve_vms"]:
        cfg = (v.get("config") or {}).get("routeros") or {}
        if not cfg.get("dhcp_servers"):
            continue

        direcciones = cfg.get("addresses") or []
        if not direcciones:
            continue
        mgmt = direcciones[0]["address"].split("/")[0]
        for s in cfg["dhcp_servers"]:
            for l in reservas(s, man):
                fuera.append({
                    "router": v["name"],
                    "mgmt": mgmt,
                    "hostname": l.get("comment") or l["mac_address"],
                    "address": l["address"],
                    "mac": l["mac_address"],
                    "servidor": s["name"],
                    "interfaz": s.get("interface", ""),
                    "pozo": s.get("address_pool", ""),
                })
    return fuera


def revisar(encargo, sesion, base):
    """Los problemas que impiden que ese DHCP responda a esa estación."""
    servidores = leer(sesion, base, "ip/dhcp-server")
    if servidores is None:
        return ["el equipo no contesta su API"]
    pozos = leer(sesion, base, "ip/pool")
    if pozos is None:
        return ["no se pudieron leer los pozos del equipo"]
    reservas = leer(sesion, base, "ip/dhcp-server/lease")
    if reservas is None:
        return ["no se pudieron leer las reservas del equipo"]

    problemas = []
    suyo = [s for s in servidores if s.get("name") == encargo["servidor"]]
    if not suyo:
        problemas.append(f"el servidor DHCP {encargo['servidor']} no existe todavía")
    else:
        s = suyo[0]
        if str(s.get("disabled", "false")).lower() == "true":
            problemas.append(f"el servidor DHCP {encargo['servidor']} está apagado")
        if encargo["interfaz"] and s.get("interface") != encargo["interfaz"]:
            problemas.append(f"el servidor DHCP {encargo['servidor']} no escucha "
                             f"en {encargo['interfaz']}")
        pozo = s.get("address-pool") or encargo["pozo"]
        if pozo and pozo not in {p.get("name") for p in pozos}:
            problemas.append(f"el pozo {pozo} no existe")

    mia = [l for l in reservas
           if l.get("mac-address", "").upper() == encargo["mac"].upper()]
    if not mia:
        problemas.append(f"no hay reserva para la MAC {encargo['mac']}")
    elif mia[0].get("address", "").split("/")[0] != encargo["address"]:
        problemas.append(f"la reserva de esa MAC da {mia[0].get('address')}, "
                         f"no {encargo['address']}")
    return problemas


def main():
    ap = argparse.ArgumentParser(
        description="¿Está en pie el DHCP que va a responder a cada estación?")
    ap.add_argument("--manifest", default=POR_DEFECTO,
                    help="state file (labs/active/inventory/group_vars/all.yml)")
    ap.add_argument("--json", action="store_true", help="salida legible por máquina")
    args = ap.parse_args()

    man = declaracion.cargar(args.manifest)
    todos = encargos(man)
    usuario, clave, esquema, puerto = credenciales()

    por_router = {}
    for e in todos:
        por_router.setdefault(e["mgmt"], []).append(e)

    resultados = []
    for mgmt, suyos in sorted(por_router.items()):
        base = f"{esquema}://{mgmt}:{puerto}"
        sesion = requests.Session()
        sesion.auth = (usuario, clave)
        for e in suyos:
            resultados.append({**e, "problemas": revisar(e, sesion, base)})

    malos = [r for r in resultados if r["problemas"]]
    if args.json:
        print(json.dumps({"listo": not malos, "estaciones": resultados}, ensure_ascii=False))
    else:
        for r in resultados:
            print(f"  {'OK  ' if not r['problemas'] else 'NO  '}{r['hostname']:<12} "
                  f"{r['address']:<14} via {r['router']} ({r['servidor']})")
            for p in r["problemas"]:
                print(f"        - {p}")
        if malos:
            print(f"FALLO: {len(malos)} de {len(resultados)} estaciones no tienen todavía "
                  f"quién les responda.")
        else:
            print(f"OK: las {len(resultados)} estaciones tienen su DHCP en pie.")
    return 1 if malos else 0


if __name__ == "__main__":
    sys.exit(main())
