#!/usr/bin/env python3
# ===========================================================================
# pve_notas.py — las notas de los invitados, derivadas de la declaración.
#
# Qué hace: reescribe en inventory/group_vars/all.yml las dos cosas que PVE
# enseña en su interfaz y que hasta ahora se escribían a mano:
#   * description — la nota HTML (tablas, diagrama de posición, intención)
#   * tags        — tres y ni una más: quién lo gestiona, qué es y dónde está
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
# Reescribe el manifiesto POR TEXTO (no con PyYAML) para no perder ni un
# comentario, y es idempotente: la segunda pasada deja el fichero byte a byte
# igual. Se prueba así sobre una copia antes de tocar el original.
#
# Uso:  python3 playbooks/tools/pve_notas.py [ruta-del-manifiesto]
# ===========================================================================
import copy
import json
import os
import re
import sys

import jinja2
import yaml

AQUI = os.path.dirname(os.path.abspath(__file__))
POR_DEFECTO = os.path.join(AQUI, "..", "..", "inventory", "group_vars", "all.yml")
MAN = sys.argv[1] if len(sys.argv) > 1 else os.path.normpath(POR_DEFECTO)
man = yaml.safe_load(open(MAN))

ENV = jinja2.Environment(undefined=jinja2.StrictUndefined)


def ros_de(g):
    """El bloque RouterOS con sus referencias ya resueltas."""
    crudo = copy.deepcopy(g["config"]["routeros"])
    # Las reservas llevan una sustitución de regex que no hace falta para la
    # nota (sólo se leen nombre, interfaz y rango) y que Jinja no debe compilar.
    for srv in crudo.get("dhcp_servers") or []:
        srv.pop("leases", None)
    return json.loads(ENV.from_string(json.dumps(crudo)).render(**dict(man)))


ROLES = {"pc-": "workstation", "sw-": "switch", "rt-": "router", "fw-": "firewall"}
SITIO = {"sede1": "central", "sede2": "delegacion", "sede3": "delegacion"}
NOMBRE_SITIO = {"sede1": "la central (sede 1)", "sede2": "la delegación 2",
                "sede3": "la delegación 3"}


def rol(n):
    for p, r in ROLES.items():
        if n.startswith(p):
            return r
    return "bootstrap"


def todos(man):
    out = []
    for g in man["pve_containers"]:
        out.append(dict(n=g["hostname"], vmid=g["vmid"], tipo="LXC", g=g))
    for g in man["pve_vms"]:
        out.append(dict(n=g["name"], vmid=g["vmid"], tipo="CHR", g=g))
    return out


def sede_de(e):
    """La sede sale del NOMBRE ('...-s1-...'), no de los tags.

    Los tags los reescribe este mismo script, y en una segunda pasada ya no
    llevan 'sede1/2/3': todos los invitados caían en 'infra' y el diagrama de
    posición desaparecía sin dar ningún error. El nombre no cambia nunca.
    """
    n = e["n"]
    for i in ("1", "2", "3"):
        if "-s%s-" % i in n:
            return "sede" + i
    return None


def sitio_de(e):
    if e["n"] == "fw-wan-edge":
        return "borde"
    if e["n"].startswith("infra-"):
        return "infra"
    return SITIO.get(sede_de(e), "infra")


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


CABLES = cables(man)


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
    """El camino medido de una estación hasta internet, con los nombres reales.

    Medido con traceroute desde una estación: es el que sigue un paquete de
    verdad, no el que uno dibujaría. Las delegaciones cruzan la central antes
    del borde; es lo que devolvió la prueba, no lo que parecía lógico.
    """
    if sede == "sede1":
        return ["pc-s1-01", "sw-s1-acc-01", "rt-s1-core", "fw-s1-perim",
                "fw-wan-edge", "internet"]
    if sede == "sede2":
        return ["pc-s2-01", "sw-s2-acc-01", "rt-s2-edge", "fw-s2-perim",
                "fw-s1-perim", "fw-wan-edge", "internet"]
    if sede == "sede3":
        return ["pc-s3-01", "sw-s3-acc-01", "rt-s3-edge", "fw-s3-perim",
                "fw-s1-perim", "fw-wan-edge", "internet"]
    return []


SEDE_POR_NOMBRE = {e["n"]: sede_de(e) for e in todos(man)}


def diagrama(e):
    """La posición del invitado en el camino, con su nombre marcado."""
    n = e["n"]
    if n == "fw-wan-edge":
        cadena = camino_de("sede1")
    elif n.startswith("infra-"):
        return ("<pre>\n"
                "  infra-bootstrap ── vmbr1 (red de gestión) ──▶ todos los equipos\n"
                "     «ESTE»            da la PRIMERA dirección a cada uno, una vez\n"
                "</pre>")
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
    sede = SEDE_POR_NOMBRE.get(n)
    L = []
    A = L.append

    # --- cabecera
    if rol(n) == "workstation":
        A("<b>%s</b> — workstation de %s. Un PC de usuario: toma su dirección por "
          "DHCP y <b>no tiene ninguna vía de gestión</b>." % (n, NOMBRE_SITIO.get(sede, "el laboratorio")))
    elif rol(n) == "switch":
        A("<b>%s</b> — switch de acceso de %s. Conmuta y nada más: "
          "<b>no enruta, no filtra y no da DHCP</b>." % (n, NOMBRE_SITIO.get(sede, "el laboratorio")))
    elif rol(n) == "router":
        A("<b>%s</b> — router de %s. Es la <b>puerta de enlace y el servidor DHCP</b> "
          "de su LAN, y conoce las demás sedes." % (n, NOMBRE_SITIO.get(sede, "el laboratorio")))
    elif rol(n) == "firewall":
        A("<b>%s</b> — firewall %s. <b>Filtra el perímetro</b>%s." % (
            n, "de borde" if st == "borde" else "de " + NOMBRE_SITIO.get(sede, "una sede"),
            " y es el único que hace NAT hacia internet" if st == "borde" else ""))
    else:
        A("<b>%s</b> — herramienta de despliegue. Da a cada equipo de red su "
          "<b>primera</b> dirección y no interviene en nada más." % n)

    # --- identidad
    A("")
    A("<b>IDENTIDAD</b>")
    filas = [["vmid", str(e["vmid"])],
             ["Tipo", tipo_txt],
             ["Dónde", NOMBRE_SITIO.get(sede, "la red de gestión / borde") if st not in ("infra", "borde")
              else ("red de gestión" if st == "infra" else "el borde de la empresa")],
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
                    ["Se la da", "el <b>router de su sede</b> (no el switch ni el firewall): "
                                 "el DHCP es una difusión de capa 2 y el servidor tiene que "
                                 "estar en su mismo segmento"],
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
        A("<li><b>Da el DHCP de su LAN porque tiene que estar en su segmento.</b> El DHCP "
          "es una difusión de capa 2: un firewall de capa 3 en medio lo rompería. Por eso "
          "la LAN cuelga de él y el firewall se pone después, de cara a la WAN.</li>")
        A("<li><b>El reparto es jerárquico:</b> la central conoce las dos redes remotas y las "
          "delegaciones salen por su firewall. Añadir una sede es una entrada y una ruta.</li>")
        A("</ul>")
    elif rol(n) == "firewall":
        A("<ul>")
        A("<li><b>El orden de las reglas es el que filtra</b>, así que la verificación "
          "relee la tabla y comprueba el orden, no sólo el conjunto.</li>")
        if st == "borde":
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
          "llega por una difusión que no cruza un enlace de capa 3, así que tiene que haber "
          "algo en su mismo segmento que se la dé. Después no vuelve a intervenir.</li>")
        A("</ul>")

    return "\n".join(L)


def tags_de(e):
    """Tres etiquetas y ni una más: quien lo gestiona, qué es y dónde está."""
    return ["ansible-managed", rol(e["n"]), sitio_de(e)]


# --------------------------------------------------- reescribir el manifiesto -
texto = open(MAN).read()
lineas = texto.split("\n")

# Los límites de cada bloque: "  - vmid: NNNN" hasta el siguiente.
inicios = [i for i, l in enumerate(lineas) if re.match(r"^  - vmid: \d+$", l)]
bloques = []
for k, i in enumerate(inicios):
    fin = inicios[k + 1] if k + 1 < len(inicios) else len(lineas)
    bloques.append((i, fin))

cambios = 0
# En orden INVERSO: cada descripción se inserta desplazando líneas, y así los
# índices de los bloques que faltan por tratar (que están más arriba) siguen
# siendo válidos. En orden directo, la primera inserción desfasa todas las
# siguientes y la búsqueda del bloque empieza a fallar.
for e in reversed(todos(man)):
    html_txt = html(e)
    etiquetas = "[%s]" % ", ".join(tags_de(e))
    idx = [b for b in bloques
           if re.match(r"^    (hostname|name): %s$" % re.escape(e["n"]), lineas[b[0] + 1])]
    if not idx:
        sys.exit("no encuentro el bloque de " + e["n"])
    ini, fin = idx[0]
    # tags
    ti = [i for i in range(ini, fin) if re.match(r"^    tags: ", lineas[i])]
    if not ti:
        sys.exit("no encuentro tags de " + e["n"])
    lineas[ti[0]] = "    tags: %s" % etiquetas
    # description (bloque escalar)
    di = [i for i in range(ini, fin) if re.match(r"^    description:", lineas[i])]
    cuerpo = ["    description: |"] + ["      " + l for l in html_txt.split("\n")]
    if di:
        # La vieja se quita ENTERA: cabecera y todas las líneas más indentadas
        # que le siguen. Si sólo se quitara la cabecera, al reescribir quedarían
        # las dos versiones mezcladas — pasó de verdad en una segunda pasada.
        j = di[0] + 1
        while j < len(lineas) and (lineas[j].startswith("      ") or lineas[j].strip() == ""):
            j += 1
        del lineas[di[0]:j]
        for n_, l in enumerate(cuerpo):
            lineas.insert(di[0] + n_, l)
    else:
        # detrás de tags
        for n_, l in enumerate(cuerpo):
            lineas.insert(ti[0] + 1 + n_, l)
    cambios += 1

open(MAN, "w").write("\n".join(lineas))
print("reescritos %d invitados" % cambios)
