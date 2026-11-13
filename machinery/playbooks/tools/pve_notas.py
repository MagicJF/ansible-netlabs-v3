#!/usr/bin/env python3
# PROPÓSITO: derivar de la declaración las notas HTML y las etiquetas de cada invitado
#   (lo que PVE enseña en su interfaz).
# INVARIANTES: `description` y `tags` se GENERAN, no se escriben a mano; se escriben DE
#   VUELTA en el manifiesto.
# LÍMITES: una comprobación que valide el CONTENIDO de la nota no detecta que el texto
#   guardado no sea ya el render — el desfase pasa en verde.
# VER: `framework_check.py notas`.
# ===========================================================================
# pve_notas.py — las notas de los invitados, derivadas de la declaración.
#
# Qué hace: reescribe en labs/netlab-v2/netlab-v2.yml las dos cosas que PVE
# enseña en su interfaz y que hasta ahora se escribían a mano:
#   * description — la nota HTML (tablas, diagrama de posición, intención)
#   * tags        — tres y ni una más: quién lo gestiona, qué es y dónde está.
#                   De qué laboratorio es un invitado lo dice el Resource Pool
#                   del laboratorio, no una etiqueta (ADR 0008).
#
# Por qué se genera y no se escribe a mano: la nota cuenta cables, direcciones,
# rutas y reglas. Todo eso YA está en el manifiesto. Escribirlo dos veces
# significa que un día la nota dirá "ether2" y la declaración "ether3", y nadie
# sabrá cuál de las dos miente. Aquí la nota se DERIVA: no puede contradecir a
# la declaración porque sale de ella.
#
# Cómo se lee:
#   * La tabla de conexiones lee los cables reales: un bridge con exactamente
#     dos patas enchufadas es un cable punto a punto. La otra pata se nombra
#     igual que en el invitado vecino, no se adivina.
#   * El bloque RouterOS está escrito con referencias ({{ lab_tr1_fw }}), que
#     es la única verdad del manifiesto. Para la nota se RENDERIZAN con el
#     mismo motor que usa el rol y con `undefined` estricto, para que una
#     referencia rota salte aquí y no se cuele en la interfaz de PVE.
#   * La sede se deduce del NOMBRE ('...-s1-...'), nunca de los tags: este
#     mismo script reescribe los tags y una segunda pasada ya no llevaría
#     'sede1/2/3', con lo que todos los invitados caían en 'infra' y el
#     diagrama de posición desaparecía sin dar ningún error.
#
# Es una BIBLIOTECA: no escribe nada. La nota y las etiquetas se CALCULAN en el
# momento de usarlas — las llama `machinery/filter_plugins/notas.py` desde la
# construcción de la especificación efectiva (apply.yml / preflight.yml) — así
# que no queda ningún derivado guardado dentro de la declaración.
#
# Uso (inspección):  python3 machinery/playbooks/tools/pve_notas.py [--vmid NNNN] [ruta-del-manifiesto]
# ===========================================================================
import copy
import ipaddress
import json
import os
import re
import sys

import jinja2
import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
POR_DEFECTO = os.path.join(AQUI, "..", "..", "..", "labs", "active")
sys.path.insert(0, AQUI)
import declaracion  # noqa: E402

# El manifiesto con sus referencias RESUELTAS: la tabla de sedes se cita en las
# fichas (`lab_sede[1].mgmt.rt`) y aqui hacen falta los valores. La resolucion es
# la misma que usan el resto de herramientas (tools/declaracion.py).
#
# `man` es un global porque las funciones de render lo consultan (los cables, las
# sedes). El FILTRO de Ansible se lo inyecta ya resuelto desde el play, sin leer
# ficheros; solo la CLI lo carga de disco. Por eso la carga es PEREZOSA: importar
# este módulo no puede tener efectos — el filtro lo importa en cada ejecución.
man = None


def cargar(ruta=None):
    """Carga el manifiesto resuelto en el global `man` y lo devuelve."""
    global man
    man = declaracion.cargar(ruta or os.path.normpath(POR_DEFECTO))
    preparar()
    return man

ENV = jinja2.Environment(undefined=jinja2.StrictUndefined)


def ros_de(g):
    """El bloque RouterOS con sus referencias ya resueltas."""
    crudo = copy.deepcopy(g["config"]["routeros"])
    # Las reservas llevan una sustitución de regex que no hace falta para la
    # nota (sólo se leen nombre, interfaz y rango) y que Jinja no debe compilar.
    for srv in crudo.get("dhcp_servers") or []:
        srv.pop("leases", None)
    return json.loads(ENV.from_string(json.dumps(crudo)).render(**dict(man)))


# Las sedes salen de la TABLA del manifiesto (`lab_sites`), no de un diccionario
# escrito a mano: anadir una sede es anadir una entrada, y ni la nota ni las
# etiquetas se resienten. `tag` es el valor de la etiqueta de PVE (el color lo
# fija `pve_tag_style`), `nombre` el nombre corto y `etiqueta` como se dice en
# prosa. El hub se declara aparte (`lab_hub`) porque la topologia no es plana.
#
# Se calculan en `preparar()` y no al importar: dependen del manifiesto, que
# unas veces llega de disco (la CLI) y otras inyectado por el play (el filtro).
SEDES = {}
HUB = 1
SITIO = {}
NOMBRE_SITIO = {}
EXTRA = {}


# El papel de sitio: de qué parte de la topología cuelga un invitado. La primera
# letra de cada familia es la de su nombre (I=infraestructura, G=gestión, B=borde).
FAMILIA_DE_CLASE = {"infra": "I", "gestion": "G", "borde": "B"}


def clase_sitio(sede, rol):
    """'sede' | 'infra' | 'gestion' | 'borde' — de dónde cuelga el invitado."""
    if sede:
        return "sede"
    return {"bootstrap": "infra", "switch": "gestion", "firewall": "borde"}.get(rol)


def preparar():
    """Recalcula lo que depende del manifiesto. Hay que llamarla tras fijarlo."""
    global SEDES, HUB, SITIO, NOMBRE_SITIO, CABLES, SEDE_POR_NOMBRE, \
        ROL_POR_NOMBRE, SITIO_POR_NOMBRE, CLASE_POR_NOMBRE, EXTRA, BORDE_FW
    SEDES = {int(s["id"]): s for s in (man.get("lab_sites") or [])}
    HUB = int(man.get("lab_hub") or 1)
    # La etiqueta de sitio es el CÓDIGO de la sede (familia + índice, 'Ca', 'Sa'…),
    # el mismo que llevan su nombre y su número: no hay una palabra aparte.
    SITIO = {"sede%d" % i: s.get("codigo") for i, s in SEDES.items()}
    NOMBRE_SITIO = {"sede%d" % i: (s.get("etiqueta") or s.get("nombre"))
                    for i, s in SEDES.items()}
    # Las familias que no alojan estaciones (infraestructura, gestión, borde) se
    # declaran por su CÓDIGO en `lab_sedes_extra`; la primera letra es la familia.
    EXTRA = {c[0]: c for c in (man.get("lab_sedes_extra") or {})}
    CABLES = cables(man)
    # La identidad de cada invitado se resuelve UNA vez desde la declaración y se
    # reparte en mapas: el nombre sólo hace de clave.
    ident = {e["n"]: identidad_de(e) for e in todos(man)}
    SEDE_POR_NOMBRE = {n: s for n, (s, _r) in ident.items()}
    ROL_POR_NOMBRE = {n: r for n, (_s, r) in ident.items()}
    CLASE_POR_NOMBRE = {n: clase_sitio(s, r) for n, (s, r) in ident.items()}
    SITIO_POR_NOMBRE = {
        n: (SITIO[s] if s else EXTRA.get(FAMILIA_DE_CLASE.get(CLASE_POR_NOMBRE[n])))
        for n, (s, _r) in ident.items()}
    BORDE_FW = next((n for n, c in CLASE_POR_NOMBRE.items() if c == "borde"), None)


def rol(n):
    """El papel de un invitado, por la DECLARACIÓN (no por el prefijo del nombre)."""
    return ROL_POR_NOMBRE.get(n)


def todos(man):
    out = []
    for g in man["pve_containers"]:
        out.append(dict(n=g["hostname"], vmid=g["vmid"], tipo="LXC", g=g))
    for g in man["pve_vms"]:
        out.append(dict(n=g["name"], vmid=g["vmid"], tipo="CHR", g=g))
    return out


def _en_red(ip, red):
    """¿La dirección cae dentro de la red declarada? Como DIRECCIÓN, no como texto."""
    try:
        return ipaddress.ip_address(ip) in ipaddress.ip_network(red, strict=False)
    except (ValueError, TypeError):
        return False


def _dir_gestion(e):
    """La dirección de gestión DECLARADA: el contenedor en `address`, el CHR en `ether1`."""
    g, tipo = e["g"], e["tipo"]
    if tipo == "LXC":
        if g.get("address"):
            return g["address"]
        mm = re.search(r"\bip=([\d.]+)/", (g.get("netif") or {}).get("net0", ""))
        return mm.group(1) if mm else None
    for a in ((g.get("config") or {}).get("routeros") or {}).get("addresses", []):
        if a.get("interface") == "ether1":
            return a["address"].split("/")[0]
    return None


def identidad_de(e):
    """(sede 'sedeN'|None, rol) leídos de la DECLARACIÓN, no del nombre.

    La sede sale de las direcciones que la declaración ya fija: sus redes
    (`lab_sites[].red` para las estaciones, `.mgmt` para los equipos de red), el
    borde y la infraestructura por `lab_mgmt_otros`, y el segundo segmento de
    gestión por `lab_mgmt2`. Antes salía del NOMBRE (`-sN-`, prefijos `pc-/sw-/`),
    un esquema que un laboratorio con otra convención (mini: `pc-u1-01`) no sigue;
    además los tags los reescribe este mismo script, así que no servían de fuente.
    """
    d = _dir_gestion(e)
    otros = man.get("lab_mgmt_otros") or {}
    mgmt2 = man.get("lab_mgmt2") or {}
    if d:
        if otros.get("borde") and d == otros["borde"]:
            return None, "firewall"
        if otros.get("infra") and d == otros["infra"]:
            return None, "bootstrap"
        if mgmt2.get("red") and _en_red(d, mgmt2["red"]):
            return None, "switch"
    for i, s in SEDES.items():
        m = s.get("mgmt") or {}
        if d:
            if d == m.get("rt"):
                return "sede%d" % i, "router"
            if d == m.get("fw"):
                return "sede%d" % i, "firewall"
            if d in (m.get("sw") or []):
                return "sede%d" % i, "switch"
            if s.get("red") and _en_red(d, s["red"]):
                return "sede%d" % i, "workstation"
    return None, None


def sede_de(e):
    """La sede declarada del invitado (por su dirección), no la que sugiera el nombre."""
    return SEDE_POR_NOMBRE.get(e["n"])


def sitio_de(e):
    """Dónde está: el CÓDIGO de su sede, o el de su familia si no cuelga de ninguna."""
    return SITIO_POR_NOMBRE.get(e["n"])


# ---------------------------------------------------------------- los cables --
def patas_de(g, tipo):
    """Las patas de un invitado, sin depender del ORDEN de las claves.

    El bootstrap declara `name=eth0,bridge=vmbr1,gw=...,ip=...` y no lleva
    `hwaddr`; un patrón con el orden fijo (`name,bridge,hwaddr`) no lo casaba, y
    su pata desaparecía de la nota y del recuento del segmento de gestión. Las
    claves se leen por nombre, no por posición.
    """
    campo = g.get("netif") if tipo == "LXC" else g.get("net")
    out = []
    for k, v in (campo or {}).items():
        d = dict(x.split("=", 1) for x in v.split(",") if "=" in x)
        out.append({
            "pata": k,
            "boca": d.get("name") if tipo == "LXC" else "ether%d" % (int(k[3:]) + 1),
            "bridge": d.get("bridge"),
            # Una LXC declara la MAC en `hwaddr=`; una VM la declara en `virtio=`
            # (el modelo de la tarjeta y la MAC en la misma clave).
            "mac": d.get("hwaddr") or d.get("virtio"),
        })
    return out


def cables(man):
    """bridge -> [(invitado, netX, nombre de la boca, mac)]"""
    e = {}
    todos_los = ([(c, "LXC", c["hostname"]) for c in man["pve_containers"]]
                 + [(v, "CHR", v["name"]) for v in man["pve_vms"]])
    for g, tipo, nombre in todos_los:
        for p in patas_de(g, tipo):
            e.setdefault(p["bridge"], []).append((nombre, p["pata"], p["boca"], p["mac"]))
    return e


# Se calcula en preparar(): depende del manifiesto.
CABLES = []


def punta_de(nombre, bridge):
    """Quién hay al otro extremo de un cable.

    En un cable punto a punto es un nombre concreto, y la nota lo nombra. En un
    SEGMENTO compartido —la red de gestión, a la que se enchufan las patas de
    administración de todos los equipos de red— no hay "otro extremo": nombrar
    uno solo de los doce sería mentir, y la nota presentaría un cable directo
    que no existe. Ahí se dice lo que es.
    """
    patas = CABLES.get(bridge, [])
    otras = [x for x in patas if x[0] != nombre]
    if len(patas) > 2:
        return "segmento compartido (%d patas)" % len(patas)
    if not otras:
        return "—"
    return "%s %s" % (otras[0][0], otras[0][2])


# ------------------------------------------------------------- el camino ------
def camino_de(sede):
    """El camino de una estación hasta internet, derivado de la declaración.

    La FORMA la da la topología declarada, que no es plana: el hub es la sede
    cuyo firewall termina el borde y las demás son spokes. La estación sale por
    su switch, su router y su firewall; si su sede NO es el hub, cruza antes el
    firewall del hub; y de ahí al firewall de borde. Los NOMBRES salen de la
    declaración, no de una lista escrita a mano, así que una sede nueva aparece
    aquí sin tocar esto.

    El camino se midió en vivo con traceroute en la puesta en marcha: coincide
    con el que implica la topología, y esa coincidencia es lo que se comprueba.
    """
    if not sede:
        return []
    sid = int(sede.replace("sede", ""))

    def equipo(side, r):
        """El nombre del primer invitado de esa sede con ese papel — por la declaración."""
        pref = "sede%d" % side
        for e in todos(man):
            if SEDE_POR_NOMBRE.get(e["n"]) == pref and ROL_POR_NOMBRE.get(e["n"]) == r:
                return e["n"]
        return None

    pc = equipo(sid, "workstation")
    sw, rt, fw = equipo(sid, "switch"), equipo(sid, "router"), equipo(sid, "firewall")
    if not all((pc, sw, rt, fw)):
        return []
    camino = [pc, sw, rt, fw]
    if sid != HUB:
        fw_hub = equipo(HUB, "firewall")
        if fw_hub:
            camino.append(fw_hub)
    return camino + [BORDE_FW or "el firewall de borde", "internet"]


SEDE_POR_NOMBRE = {}
ROL_POR_NOMBRE = {}
SITIO_POR_NOMBRE = {}
CLASE_POR_NOMBRE = {}
BORDE_FW = None


def diagrama(e):
    """La posición del invitado en el camino, con su nombre marcado."""
    n = e["n"]
    if CLASE_POR_NOMBRE.get(n) == "borde":
        cadena = camino_de("sede%d" % HUB)
    elif ROL_POR_NOMBRE.get(n) == "bootstrap":
        return ("<pre>\n"
                "  %s ── %s (red de gestión) ──▶ todos los equipos\n"
                "     «ESTE»            da la PRIMERA dirección a cada uno, una vez\n"
                "</pre>" % (n, man.get("lab_mgmt_bridge", "la red de gestión")))
    else:
        cadena = camino_de(SEDE_POR_NOMBRE.get(n))
    if not cadena:
        return ""
    trozos = []
    for x in cadena:
        trozos.append("<b>%s</b> «ESTE»" % x if x == n else x)
    return "<pre>" + "  ──▶  ".join(trozos) + "</pre>"


# ------------------------------------------------------------ el HTML ---------
def tabla(filas, cabecera=None):
    out = ["<table>"]
    if cabecera:
        out.append(" <tr>" + "".join("<th>%s</th>" % c for c in cabecera) + "</tr>")
    for f in filas:
        out.append(" <tr>" + "".join("<td>%s</td>" % c for c in f) + "</tr>")
    out.append("</table>")
    return out


def html(e):
    g, n = e["g"], e["n"]
    tipo_txt = ("Contenedor LXC (Debian 13, sin privilegios)" if e["tipo"] == "LXC"
                else "Máquina virtual (RouterOS CHR)")
    st = sitio_de(e)
    cl = CLASE_POR_NOMBRE.get(n)
    sede = SEDE_POR_NOMBRE.get(n)
    L = []
    A = L.append

    # --- cabecera
    if rol(n) == "workstation":
        A("<b>%s</b> — workstation de %s. Un PC de usuario: toma su dirección por "
          "DHCP y <b>no tiene ninguna vía de gestión</b>." % (n, NOMBRE_SITIO.get(sede, "el laboratorio")))
    elif rol(n) == "switch":
        donde = ("el switch de acceso de %s" % NOMBRE_SITIO[sede]) if sede \
            else "el switch del segundo segmento de gestión (OOB)"
        A("<b>%s</b> — %s. Conmuta y nada más: "
          "<b>no enruta, no filtra y no da DHCP</b>." % (n, donde))
    elif rol(n) == "router":
        A("<b>%s</b> — router de %s. Es la <b>puerta de enlace y el servidor DHCP</b> "
          "de su LAN, y conoce las demás sedes." % (n, NOMBRE_SITIO.get(sede, "el laboratorio")))
    elif rol(n) == "firewall":
        A("<b>%s</b> — firewall %s. <b>Filtra el perímetro</b>%s." % (
            n, "de borde" if cl == "borde" else "de " + NOMBRE_SITIO.get(sede, "una sede"),
            " y es el único que hace NAT hacia internet" if cl == "borde" else ""))
    else:
        A("<b>%s</b> — herramienta de despliegue. Da a cada equipo de red su "
          "<b>primera</b> dirección y no interviene en nada más." % n)

    # --- identidad
    A("")
    A("<b>IDENTIDAD</b>")
    filas = [["vmid", str(e["vmid"])],
             ["Tipo", tipo_txt],
             ["Dónde", NOMBRE_SITIO.get(sede, "la red de gestión") if cl == "sede"
              else {"infra": "la red de gestión",
                    "gestion": "el segundo segmento de gestión (OOB)",
                    "borde": "el borde de la empresa"}.get(cl, "—")],
             ["Rol", rol(n)],
             ["Tags", " ".join("<code>%s</code>" % t for t in tags_de(e))]]
    L += tabla(filas)

    # --- conexiones
    A("")
    A("<b>CONEXIONES</b>")
    filas = []
    sus_bridges = []
    for p in patas_de(g, e["tipo"]):
        sus_bridges.append(p["bridge"])
        filas.append([p["pata"], p["boca"], "<code>%s</code>" % p["bridge"],
                      "<code>%s</code>" % p["mac"] if p["mac"] else "—",
                      punta_de(n, p["bridge"])])
    L += tabla(filas, ["Pata", "Interfaz", "Cable (bridge)", "MAC", "Al otro extremo"])
    A("")
    compartidos = [b for b in sus_bridges if len(CABLES.get(b, [])) > 2]
    if compartidos:
        A("Cada cable es un <b>bridge de Proxmox sin puerto físico</b>: un segmento de "
          "capa 2. Este invitado tiene una pata en un <b>segmento compartido</b> "
          "(<code>%s</code>), donde no hay un \"otro extremo\" único: ahí cuelgan las "
          "patas de administración de todos los equipos de red. Sus demás cables son "
          "punto a punto, con exactamente dos patas. Nada en el invitado sabe quién "
          "está al otro lado: lo aprende, igual que el hardware real."
          % ", ".join(compartidos))
    else:
        A("Cada cable es un <b>bridge de Proxmox sin puerto físico</b>: un segmento de "
          "capa 2 al que se enchufan exactamente estas dos patas. Nada en el invitado "
          "sabe quién está al otro lado: lo aprende, igual que el hardware real.")

    # --- direccionamiento / configuración
    A("")
    if e["tipo"] == "LXC":
        A("<b>CÓMO ESTÁ DIRIGIDA</b>")
        L += tabla([["Dirección", "%s — <b>por DHCP</b>, reserva atada a su MAC" % g.get("address")],
                    ["Se la da", "el <b>router de su sede</b> (no el switch ni el firewall): es "
                                 "su puerta, así que está en su mismo segmento, que es donde "
                                 "tiene que estar quien reparte el DHCP"],
                    ["Puerta de enlace", "la del router de su sede (.1 de su red)"],
                    ["Vía de gestión", "<b>ninguna.</b> Un PC de una empresa no se administra "
                                       "por una conexión entrante"]])
    else:
        ros = ros_de(g)
        A("<b>CONFIGURACIÓN DECLARADA (RouterOS)</b>")
        filas = []
        for a in ros.get("addresses") or []:
            filas.append([a["interface"], a["address"]])
        L += tabla(filas, ["Interfaz", "Dirección de gestión"])
        for b in ros.get("bridges") or []:
            A("")
            A("Puente <code>%s</code> con las bocas %s. <b>Sin dirección</b>: eso es lo que "
              "lo hace un switch y no un router." % (b["name"], ", ".join(b["ports"])))
        if ros.get("dhcp_servers"):
            A("")
            A("<b>Servidor DHCP de su sede</b>")
            for s in ros["dhcp_servers"]:
                L += tabla([["Nombre", s.get("name")],
                            ["Interfaz", s.get("interface")],
                            ["Rango que reparte", s.get("address_pool")],
                            ["Red de la LAN", s.get("network")],
                            ["Puerta de enlace que anuncia", s.get("gateway")],
                            ["DNS que anuncia", s.get("dns_server")],
                            ["Reservas", "una por workstation de la sede, atada a su MAC"]])
        if ros.get("routes"):
            A("")
            A("<b>Rutas</b>")
            L += tabla([[str(r.get("dst_address")), "vía %s" % r.get("gateway")] for r in ros["routes"]],
                       ["Destino", "Por dónde"])
        fw = (ros.get("firewall") or {})
        if fw.get("filter") or fw.get("nat"):
            A("")
            A("<b>Filtrado y NAT</b>")
            L += tabla([["Reglas de filtrado", "%d (el orden importa: decide qué se acepta)"
                         % len(fw.get("filter") or [])],
                        ["Reglas de NAT", "%d" % len(fw.get("nat") or [])]])

    # --- diagrama
    d = diagrama(e)
    if d:
        A("")
        A("<b>DÓNDE ESTÁ</b>")
        A(d)
        A("El camino está <b>medido</b> con traceroute desde una estación, no dibujado: "
          "es el que sigue un paquete de verdad.")

    # --- intención
    A("")
    A("<b>POR QUÉ ASÍ</b>")
    if rol(n) == "workstation":
        A("<ul>")
        A("<li><b>Una sola NIC y ninguna de gestión.</b> Así se hace en una empresa: el PC "
          "tiene un cable, y la administración de parque es un agente que <i>sale</i> hacia "
          "fuera. Por eso este invitado no aparece en el diario de la API como destino.</li>")
        A("<li><b>Su dirección vive en la declaración, no en el equipo.</b> El <code>address:</code> "
          "de su ficha <i>es</i> la reserva que el router deriva: no hay dos sitios donde se "
          "puedan desincronizar.</li>")
        A("</ul>")
    elif rol(n) == "switch":
        A("<ul>")
        A("<li><b>Sin dirección en el puente.</b> Un switch con dirección en el puente "
          "empieza a enrutar, y la topología deja de ser la del diagrama <i>sin que nada "
          "falle</i>. Su dirección vive sólo en su pata de gestión.</li>")
        A("<li><b>Pero esa pata SÍ lleva puerta de enlace</b>, apuntando al router de su "
          "sede. Sin ella el switch recibe los pings y no puede contestarlos.</li>")
        A("</ul>")
    elif rol(n) == "router":
        A("<ul>")
        A("<li><b>Da el DHCP de su LAN porque es su puerta, y quien reparte tiene que estar "
          "en el segmento de sus clientes:</b> el DHCP es una difusión de capa 2 y no cruza un "
          "router. Un <i>relay</i> (<code>ip helper-address</code>) valdría igual y dejaría el "
          "servidor en otro sitio —también es real, pero es el modelo de empresa; este es el de "
          "rama pequeña, donde puerta y servidor son el mismo equipo—. Por eso la LAN cuelga de "
          "él y el firewall se pone después, de cara a la WAN.</li>")
        A("<li><b>El reparto es jerárquico:</b> la central conoce las dos redes remotas y las "
          "delegaciones salen por su firewall. Añadir una sede es una entrada y una ruta.</li>")
        A("</ul>")
    elif rol(n) == "firewall":
        A("<ul>")
        A("<li><b>El orden de las reglas es el que filtra</b>, así que la verificación "
          "relee la tabla y comprueba el orden, no sólo el conjunto.</li>")
        if cl == "borde":
            A("<li><b>Es el único que hace NAT</b> (masquerade). Dentro de la empresa las "
              "direcciones son reales: por eso hay rutas de vuelta y no traducciones anidadas.</li>")
            A("<li><b>Su pata exterior sale por la red de gestión</b> y el proveedor es el host. "
              "Ningún invitado va en el bridge público del nodo, así que nada queda expuesto.</li>")
        else:
            A("<li><b>Deja hablar a sus bocas exteriores entre sí.</b> Sin esas reglas, el "
              "tráfico de una delegación hacia el borde entra por una boca y muere en el "
              "<code>drop</code>: lo destapó la prueba de conectividad, no la lectura del fichero.</li>")
        A("</ul>")
    else:
        A("<ul>")
        A("<li><b>Hace un solo trabajo y por eso existe.</b> La primera dirección de un CHR "
          "llega por una difusión, y el túnel de gestión es un enlace de capa 3, así que tiene "
          "que haber algo EN su segmento que se la dé. No sirve el servidor DHCP del host, que "
          "está ahí mismo: su oferta llega con el checksum de UDP sin resolver y el kernel del "
          "CHR la descarta. Después no vuelve a intervenir.</li>")
        A("</ul>")

    return "\n".join(L)


def tags_de(e):
    """Tres etiquetas y ni una más: quién lo gestiona, qué es y dónde está.

    De qué laboratorio es un invitado NO se pregunta por etiqueta: lo dice el
    Resource Pool PROPIO del laboratorio, que PVE enseña en su árbol junto al
    invitado (ADR 0008). Una etiqueta más sería una segunda respuesta a la misma
    pregunta, y dos respuestas se contradicen el día que una cambie.

    En MINÚSCULAS, y no por gusto de estilo: la etiqueta de PVE es un identificador,
    y PVE lo normaliza a minúsculas al guardarlo (creado con `Ca`, su API
    devuelve `ca` — medido: el `create` responde 200 y la relectura viene
    abajo). Una etiqueta declarada en mayúsculas no converge nunca: el motor la
    reescribe en cada pasada y la verificación la da por desajustada. El código de
    sede (`Ca`) sigue así en el NOMBRE y en la prosa; lo que se publica como
    etiqueta va en minúsculas. El esquema que cita el ADR 0006 ya lo decía: sólo
    minúsculas, dígitos, guion, más y punto.

    El papel y la sede salen de la DECLARACIÓN; si un invitado aún no
    resuelve (dirección plantillada sin renderizar), se omite la etiqueta en vez de
    devolver None: una lista con None revienta el `sort` del motor y tumba el
    preflight de TODOS los laboratorios, no sólo el de ese invitado.
    """
    return [str(t).lower() for t in ("ansible", rol(e["n"]), sitio_de(e)) if t]


# ------------------------------------------------------------------- CLI -
# Inspección: imprime lo que PVE enseñará para un invitado (o para todos). Sirve
# para leer la nota sin abrir la interfaz de Proxmox; no escribe nada.
def main(argv):
    args = list(argv[1:])
    vmid = None
    if "--vmid" in args:
        i = args.index("--vmid")
        vmid = int(args[i + 1])
        del args[i:i + 2]
    cargar(args[0] if args else None)
    for e in todos(man):
        if vmid is not None and e["vmid"] != vmid:
            continue
        print("=== %s (%s)  etiquetas: %s" % (e["n"], e["vmid"], ", ".join(tags_de(e))))
        print(html(e))
        print()


if __name__ == "__main__":
    main(sys.argv)
