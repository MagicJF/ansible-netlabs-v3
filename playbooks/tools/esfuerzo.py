#!/usr/bin/env python3
"""Genera ESFUERZO.md: cuanto trabajo costo poner el laboratorio en pie.

Dos registros, dos alcances distintos, y conviene saber por que:

  logs/pve-api.jsonl  el trazador. Registra cada llamada HTTP que pasa por
                      `requests`: eso es TODA la capa 1 (Proxmox, via proxmoxer)
                      y las herramientas sueltas. NO registra al rol RouterOS,
                      porque `ansible.builtin.uri` va por urllib, no por
                      requests. De aqui salen las tablas de Proxmox.

  logs/ansible.log    el log humano de Ansible, con marca de tiempo en cada
                      linea y el resultado de cada tarea. El rol RouterOS
                      imprime su plan **call by call**, y sus lecturas salen una
                      linea por tabla, asi que de aqui salen las tablas de
                      RouterOS y todas las de trabajo (tareas por anfitrion).

Uso:
    python3 playbooks/tools/esfuerzo.py            # escribe ESFUERZO.md
    python3 playbooks/tools/esfuerzo.py --stdout   # y ademas lo imprime
"""
import argparse
import collections
import datetime
import json
import os
import re
import sys

import yaml

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JOURNAL = os.path.join(RAIZ, "logs", "pve-api.jsonl")
ANSI = os.path.join(RAIZ, "logs", "ansible.log")
SALIDA = os.path.join(RAIZ, "ESFUERZO.md")

LINEA = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3}) ")
RECAP = re.compile(r"^(\S+)\s*:\s*ok=(\d+)\s+changed=(\d+)\s+unreachable=(\d+)\s+failed=(\d+)\s+skipped=(\d+)")
RESULT = re.compile(r"^(ok|changed|failed|fatal|skipping|unreachable|included): \[([^\]]+)\]")
ITEM = re.compile(r"=> \(item=([^)]*)\)")
PLAY = re.compile(r"PLAY \[(.*?)\]")
TASK = re.compile(r"TASK \[(.*?)\]")
MSG = re.compile(r'"msg": "((?:GET|PUT|POST|PATCH|DELETE) /rest/[^ "\\]+)')
LECTURA = "Read every table the declaration can touch"
PID = re.compile(r"^p=(\d+) ")


def miles(n):
    return "{:,}".format(int(n)).replace(",", ".")


def tst(s):
    if not s:
        return None
    for f in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.datetime.strptime(s, f)
        except ValueError:
            pass
    return None


# ------------------------------------------------------------------ nombres --
def nombres():
    man = yaml.safe_load(open(os.path.join(RAIZ, "inventory", "group_vars", "all.yml")))
    nom, tipo = {}, {}
    for g in man["pve_containers"]:
        nom[int(g["vmid"])] = g["hostname"]
        tipo[int(g["vmid"])] = "LXC"
    for g in man["pve_vms"]:
        nom[int(g["vmid"])] = g["name"]
        tipo[int(g["vmid"])] = "CHR"
    ip = {}
    for g in man["pve_vms"]:
        for a in g["config"]["routeros"]["addresses"]:
            if a["interface"] == "ether1":
                ip[a["address"].split("/")[0]] = g["name"]
    ip.setdefault("10.10.10.41", "infra-bootstrap")
    return man, nom, tipo, ip


# ------------------------------------------------------ el log de Ansible ----
def leer_ansible():
    """Devuelve los verbos. Cada verbo se separa por el PID del proceso principal
    (cada `ansible-playbook` es un proceso y escribe su propio log), que es mas
    robusto que cortar por los recuentos: dos verbos seguidos dejan dos recuentos
    pegados y un corte por 'PLAY RECAP' los confunde.

    Dentro de cada verbo:
       - recaps: por anfitrion, ok/changed/failed/skipped
       - ejec:   por anfitrion, cuantas tareas se le ejecutaron
       - ros_leidos / ros_escritos: llamadas a la API REST del equipo
       - span:   por anfitrion, cuando empezo y acabo su parte
    """
    crudo = []
    for l in open(ANSI, errors="replace"):
        m = LINEA.match(l)
        if not m:
            crudo.append((None, None, l.rstrip("\n")))
            continue
        resto = l[m.end():]
        mp = PID.match(resto)
        pid = mp.group(1) if mp else None
        txt = re.sub(r"^p=\d+ u=\S+ n=ansible \w+\| ", "", resto)
        crudo.append((m.group(1), pid, txt.rstrip("\n")))

    # Cortar por PID, conservando el orden.
    grupos, actual = [], None
    for ts, pid, txt in crudo:
        if pid is None:
            if actual is not None:
                actual["lineas"].append((ts, txt))
            continue
        if actual is None or actual["pid"] != pid:
            actual = dict(pid=pid, lineas=[])
            grupos.append(actual)
        actual["lineas"].append((ts, txt))

    verbos = []
    for g in grupos:
        lin = g["lineas"]
        recaps = {}
        for ts, txt in lin:
            m = RECAP.match(txt)
            if m:
                recaps[m.group(1)] = dict(ok=int(m.group(2)), changed=int(m.group(3)),
                                          unreachable=int(m.group(4)), failed=int(m.group(5)),
                                          skipped=int(m.group(6)))
        if not recaps:
            continue  # no es un verbo: es un pase auxiliar (inventario, lint...)
        ts_ini = next((t for t, _ in lin if t), None)
        ts_fin = next((t for t, _ in reversed(lin) if t), None)
        ejec = collections.Counter()
        plays = []
        ros_leidos = collections.Counter()
        ros_escritos = collections.Counter()
        span = {}
        tarea, host = "", None
        for ts, txt in lin:
            t = TASK.match(txt)
            if t:
                tarea = t.group(1)
                continue
            p = PLAY.match(txt)
            if p:
                plays.append(p.group(1))
                continue
            r = RESULT.match(txt)
            if r:
                host = r.group(2)
                if ts:
                    span.setdefault(host, [ts, ts])
                    span[host][1] = ts
                if LECTURA in tarea:
                    it = ITEM.search(txt)
                    if it:
                        ros_leidos[(host, it.group(1))] += 1
                ejec[host] += 1
                continue
            m = MSG.search(txt)
            if m and "Show every call" in tarea and host:
                partes = m.group(1).split()
                ep = partes[1].replace("/rest/", "") if len(partes) > 1 else m.group(1)
                ros_escritos[(host, partes[0], ep)] += 1
        verbos.append(dict(ini=ts_ini, fin=ts_fin, plays=plays, recaps=recaps,
                           ejec=ejec, ros_leidos=ros_leidos, ros_escritos=ros_escritos,
                           span=span))
    verbos.sort(key=lambda v: v["ini"] or "")
    return verbos


def etiqueta(v):
    ps = " | ".join(v["plays"])
    if "Report what would change" in ps:
        return "capa 1: preflight"
    if "Converge every guest declared" in ps:
        return "capa 1: apply"
    if "Destroy one guest" in ps:
        return "remove (baja deliberada)"
    if "speak their own API" in ps:
        return "configure: converge RouterOS"
    if "inside of every managed guest" in ps:
        return "configure: converge contenedores"
    if "tunnel" in ps.lower():
        return "connect (tunel)"
    return (v["plays"][0][:34] if v["plays"] else "sin nombre")


def duracion(v):
    a, b = tst(v["ini"]), tst(v["fin"])
    return (b - a).total_seconds() if a and b else None


# ------------------------------------------------------------- el journal ----
def leer_journal(nom, ip, verbos):
    pve, pve_s = collections.Counter(), collections.Counter()
    nod, nod_s = collections.Counter(), collections.Counter()
    ros, ros_s = collections.Counter(), collections.Counter()
    metodos, estados = collections.Counter(), collections.Counter()
    total, total_s = 0, 0.0
    tramos = [(tst(v["ini"]), tst(v["fin"]), i) for i, v in enumerate(verbos)]
    por_verbo, seg_verbo = collections.Counter(), collections.Counter()

    for l in open(JOURNAL, errors="replace"):
        l = l.strip()
        if not l:
            continue
        try:
            d = json.loads(l)
        except ValueError:
            continue
        if d.get("event") != "api_call":
            continue
        u = d.get("url", "")
        met, s = (d.get("method") or "").upper(), float(d.get("seconds") or 0)
        total += 1
        total_s += s
        metodos[met] += 1
        estados[d.get("status")] += 1
        ts = tst((d.get("ts") or "").replace("T", " ").split("+")[0])
        if ts:
            for a, b, i in tramos:
                if a and b and a <= ts <= b:
                    por_verbo[i] += 1
                    seg_verbo[i] += s
                    break
        if ":8006" in u:
            mm = re.match(r"/api2/json/nodes/[^/]+/(?:lxc|qemu)/(\d+)/(.*)", u.split(":8006", 1)[1])
            if mm:
                ep = mm.group(2)
                ep = "tasks/<tipo>" if ep.startswith("tasks/UPID") else ep
                g = nom.get(int(mm.group(1)), mm.group(1))
                pve[(g, ep)] += 1
                pve_s[(g, ep)] += s
            else:
                ep = re.sub(r"UPID:[^\s\"]+", "UPID:<id>", u.split(":8006", 1)[1])
                nod[ep] += 1
                nod_s[ep] += s
        else:
            mip = re.search(r"//([\d.]+)", u)
            if not mip:
                continue
            g = ip.get(mip.group(1), mip.group(1))
            p = re.sub(r"//[\d.]+", "", u).replace("http:/", "").replace("https:/", "")
            p = re.sub(r"/rest/(ip/firewall/(?:filter|nat))/[^/]+.*", r"/rest/\1", p)
            ros[(g, p)] += 1
            ros_s[(g, p)] += s
    return dict(pve=pve, pve_s=pve_s, nod=nod, nod_s=nod_s, ros=ros, ros_s=ros_s,
                metodos=metodos, estados=estados, total=total, total_s=total_s,
                por_verbo=por_verbo, seg_verbo=seg_verbo)


def universo(man):
    """Elementos declarados por equipo de red: el techo de lo que una
    convergencia puede escribir si todo estuviera en deriva."""
    out = {}
    for g in man["pve_vms"]:
        ros = g["config"]["routeros"]
        n = len(ros.get("addresses") or []) + len(ros.get("routes") or [])
        for b in ros.get("bridges") or []:
            n += 1 + len(b.get("ports") or [])
        n += len(ros.get("dhcp_servers") or []) + len(ros.get("pools") or [])
        n += len(ros.get("leases") or [])
        for t in ("filter", "nat"):
            n += len((ros.get("firewall") or {}).get(t) or [])
        out[g["name"]] = n
    return out


# ------------------------------------------------------------------- salida --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stdout", action="store_true")
    args = ap.parse_args()

    man, nom, tipo, ip = nombres()
    verbos = leer_ansible()
    j = leer_journal(nom, ip, verbos)
    uni = universo(man)

    h_ejec, h_ok, h_ch, h_fa, h_sk = (collections.Counter() for _ in range(5))
    for v in verbos:
        for h, n in v["ejec"].items():
            h_ejec[h] += n
        for h, r in v["recaps"].items():
            h_ok[h] += r["ok"]
            h_ch[h] += r["changed"]
            h_fa[h] += r["failed"]
            h_sk[h] += r["skipped"]

    ros_lec, ros_esc = collections.Counter(), collections.Counter()
    for v in verbos:
        for (h, t), n in v["ros_leidos"].items():
            ros_lec[h] += n
        for (h, m, e), n in v["ros_escritos"].items():
            ros_esc[h] += n
    ros_por_ep = collections.Counter()
    for v in verbos:
        for (h, t), n in v["ros_leidos"].items():
            ros_por_ep[("GET", t)] += n
        for (h, m, e), n in v["ros_escritos"].items():
            # El id interno de una entrada (`*4`) no aporta nada al recuento:
            # se normaliza para que las cinco lineas del mismo menu se sumen.
            ros_por_ep[(m, re.sub(r"\*[0-9A-Fa-f]+$", "<id>", e))] += n

    convergencias = [i for i, v in enumerate(verbos) if etiqueta(v) == "configure: converge RouterOS"]
    dur_total = sum(d for d in (duracion(v) for v in verbos) if d)
    tot_ejec = sum(h_ejec.values())
    tot_ros = sum(ros_lec.values()) + sum(ros_esc.values())

    L = []
    A = L.append
    A("# Cuánto trabajo costó poner el laboratorio en pie")
    A("")
    A("> Este documento **no está escrito a mano**: lo genera")
    A("> `playbooks/tools/esfuerzo.py` contando los registros que el propio motor")
    A("> escribe mientras trabaja. Volver a generarlo es un comando, así que las")
    A("> cifras se pueden auditar y refrescar en cualquier momento:")
    A(">")
    A("> ```bash")
    A("> python3 playbooks/tools/esfuerzo.py")
    A("> ```")
    A("")
    A("Las cifras son de la puesta en marcha del laboratorio v2 (2026-11-08).")
    A("")
    A("## De dónde salen los números")
    A("")
    A("| Registro | Qué guarda | Para qué sirve aquí |")
    A("| --- | --- | --- |")
    A("| `logs/pve-api.jsonl` | cada llamada HTTP que pasa por `requests`, con método, ruta, estado y **segundos** | **Proxmox**: la capa 1 va por proxmoxer y queda entera |")
    A("| `logs/ansible.log` | cada resultado de tarea, por anfitrión, con marca de tiempo | **RouterOS** y **trabajo**: el rol imprime su plan y sus lecturas |")
    A("")
    A("**Por qué no sale todo del trazador.** El trazador se engancha a")
    A("`requests.Session.request`, y el rol RouterOS habla por `ansible.builtin.uri`,")
    A("que va por `urllib`. Así que el diario tiene **toda** la capa 1 y **ninguna**")
    A("llamada del rol. No es un fallo del rol: es el alcance de la herramienta, y por")
    A("eso el lado RouterOS se cuenta del log, donde el rol imprime cada llamada que")
    A("hace (`Report the plan, call by call`) y cada tabla que lee.")
    A("")
    A("## Resumen")
    A("")
    A("- **%s verbos** ejecutados, con **%s ejecuciones de tarea** repartidas entre"
      % (miles(len(verbos)), miles(tot_ejec)))
    A("  **%d anfitriones**." % len(h_ejec))
    A("- **%s llamadas al API de Proxmox** medidas con el trazador, que suman"
      % miles(j["total"]))
    A("  **%.1f minutos** de espera dentro de la API." % (j["total_s"] / 60))
    A("- **%s llamadas al API de RouterOS** contadas en el log: %s de lectura y %s de"
      % (miles(tot_ros), miles(sum(ros_lec.values())), miles(sum(ros_esc.values()))))
    A("  escritura. Los once equipos se gobiernan por REST, sin SSH.")
    A("- **%d convergencias completas** del laboratorio, más los verbos de capa 1."
      % len(convergencias))
    A("- Tiempo de reloj de todos los verbos: **%.1f minutos**." % (dur_total / 60))
    A("")
    A("## Los verbos, uno a uno")
    A("")
    A("| # | inicio | dur. | verbo | anfitriones | llamadas PVE | RouterOS | ok | chg | fail |")
    A("| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
    for i, v in enumerate(verbos, 1):
        d = duracion(v)
        t = collections.Counter()
        for r in v["recaps"].values():
            for k, n in r.items():
                t[k] += n
        nros = sum(v["ros_leidos"].values()) + sum(v["ros_escritos"].values())
        A("| %d | %s | %s | %s | %d | %s | %s | %d | %d | %d |" % (
            i, (v["ini"] or "?")[11:19], ("%.0f s" % d) if d is not None else "?",
            etiqueta(v), len(v["recaps"]), miles(j["por_verbo"][i]), miles(nros),
            t["ok"], t["changed"], t["failed"]))
    A("")
    A("## API de Proxmox")
    A("")
    A("### Por invitado")
    A("")
    A("| invitado | tipo | llamadas | segundos |")
    A("| --- | --- | ---: | ---: |")
    agg, agg_s = collections.Counter(), collections.Counter()
    for (g, ep), k in j["pve"].items():
        agg[g] += k
        agg_s[g] += j["pve_s"][(g, ep)]
    for g, k in agg.most_common():
        vm = next((v for v, n in nom.items() if n == g), None)
        A("| `%s` | %s | %d | %.1f |" % (g, tipo.get(vm, "-"), k, agg_s[g]))
    A("| **total** | | **%s** | **%.1f** |" % (miles(sum(agg.values())), sum(agg_s.values())))
    A("")
    A("### Por endpoint")
    A("")
    A("| endpoint | llamadas | segundos |")
    A("| --- | ---: | ---: |")
    ea, ea_s = collections.Counter(), collections.Counter()
    for (g, ep), k in j["pve"].items():
        ea[ep] += k
        ea_s[ep] += j["pve_s"][(g, ep)]
    for ep, k in ea.most_common():
        A("| `%s` | %d | %.1f |" % (ep, k, ea_s[ep]))
    A("")
    A("### Sin invitado: el motor y el nodo")
    A("")
    A("| endpoint | llamadas | segundos |")
    A("| --- | ---: | ---: |")
    for ep, k in j["nod"].most_common():
        A("| `%s` | %d | %.1f |" % (ep[:78], k, j["nod_s"][ep]))
    A("")
    A("## API de RouterOS")
    A("")
    A("Los once equipos de red se gobiernan **solo** por su API REST (HTTP en el")
    A("puerto 80). Cada convergencia lee cada tabla declarada y escribe únicamente lo")
    A("que difiere, así que el grueso son lecturas y las escrituras son la excepción —")
    A("que es exactamente lo que debe pasar cuando el estado ya es el declarado.")
    A("")
    A("### Por equipo")
    A("")
    A("| equipo | lecturas | escrituras | total | tiempo en convergir | elementos declarados |")
    A("| --- | ---: | ---: | ---: | ---: | ---: |")
    equipos = sorted(set(ros_lec) | set(ros_esc) | set(uni),
                     key=lambda h: -(ros_lec[h] + ros_esc[h]))
    for h in equipos:
        seg = 0.0
        for v in verbos:
            if h in v["span"]:
                a, b = tst(v["span"][h][0]), tst(v["span"][h][1])
                if a and b:
                    seg += (b - a).total_seconds()
        A("| `%s` | %d | %d | %d | %.0f s | %d |" % (
            h, ros_lec[h], ros_esc[h], ros_lec[h] + ros_esc[h], seg, uni.get(h, 0)))
    A("| **total** | **%s** | **%s** | **%s** | | |" % (
        miles(sum(ros_lec.values())), miles(sum(ros_esc.values())), miles(tot_ros)))
    A("")
    A("La última columna es lo que el manifiesto declara para ese equipo: el techo de")
    A("lo que una convergencia puede llegar a escribir si todo estuviera en deriva.")
    A("")
    A("### Por endpoint")
    A("")
    A("| método | endpoint | llamadas |")
    A("| --- | --- | ---: |")
    for (m, ep), k in ros_por_ep.most_common():
        A("| `%s` | `/%s` | %d |" % (m, ep, k))
    A("")
    A("### Las escrituras, una a una")
    A("")
    A("| método | endpoint | llamadas | qué escribe |")
    A("| --- | --- | ---: | --- |")
    QUE = {
        "ip/firewall/filter": "una regla de filtrado del perímetro",
        "ip/service/<id>": "apagar un servicio que no debe escuchar (http, api, telnet…)",
        "ip/route/add": "una ruta (la puerta de enlace o la ruta a otra sede)",
        "ip/address": "una dirección IP",
        "interface/bridge/port": "meter una pata en el puente (un puerto del switch)",
        "system/identity/set": "el nombre del equipo",
        "execute": "el export de comprobación del estado",
        "ip/dhcp-server/lease": "una reserva DHCP atada a una MAC",
        "interface/bridge": "el puente de un switch",
        "ip/pool": "el rango de direcciones que reparte un router",
        "ip/dhcp-server/network": "la red que anuncia el DHCP",
        "ip/dhcp-server": "el propio servidor DHCP de la sede",
        "ip/firewall/nat": "una regla de NAT (solo el firewall de borde)",
    }
    for (m, ep), k in sorted(((k, v) for k, v in ros_por_ep.items() if k[0] != "GET"),
                             key=lambda x: -x[1]):
        A("| `%s` | `/%s` | %d | %s |" % (m, ep, k, QUE.get(ep, "")))
    A("")
    A("## Las estaciones de trabajo")
    A("")
    A("No hay API que llamar: Ansible **entra por SSH** y ejecuta módulos dentro. Por")
    A("eso lo que se cuenta son ejecuciones de tarea, que es la unidad real de trabajo.")
    A("")
    A("| anfitrión | ejecuciones | ok | changed | failed | skipped |")
    A("| --- | ---: | ---: | ---: | ---: | ---: |")
    for h in sorted(h_ejec, key=lambda h: (not h.startswith("pc-"), -h_ejec[h])):
        A("| `%s` | %d | %d | %d | %d | %d |" % (h, h_ejec[h], h_ok[h], h_ch[h], h_fa[h], h_sk[h]))
    A("")
    A("## Tiempos totales")
    A("")
    A("| Qué | Cuánto |")
    A("| --- | --- |")
    A("| Verbos ejecutados | %d |" % len(verbos))
    A("| Tiempo de reloj de los verbos | %.1f min |" % (dur_total / 60))
    A("| Llamadas al API de Proxmox | %s |" % miles(j["total"]))
    A("| Espera dentro del API de Proxmox | %.1f min (%.0f s) |" % (j["total_s"] / 60, j["total_s"]))
    A("| Llamadas al API de RouterOS | %s |" % miles(tot_ros))
    A("| Ejecuciones de tarea | %s |" % miles(tot_ejec))
    A("| Convergencias completas | %d |" % len(convergencias))
    A("")
    A("| método HTTP al API de Proxmox | llamadas |")
    A("| --- | ---: |")
    for m, k in j["metodos"].most_common():
        A("| `%s` | %d |" % (m, k))
    A("")
    A("| estado | llamadas |")
    A("| --- | ---: |")
    for s, k in sorted(j["estados"].items(), key=lambda x: -x[1]):
        A("| %s | %d |" % (s, k))
    A("")
    A("## Estimación del esfuerzo")
    A("")
    A("### Lo que cuesta UNA convergencia completa")
    A("")
    if convergencias:
        i = convergencias[-1]
        v = verbos[i]
        lec = sum(v["ros_leidos"].values())
        esc = sum(v["ros_escritos"].values())
        A("La última (%s, del %s), que no cambió nada y por tanto es la lectura entera:"
          % (etiqueta(v), (v["ini"] or "?")[11:19]))
        A("")
        A("| | llamadas |")
        A("| --- | ---: |")
        A("| Lecturas (cada tabla declarada, por equipo) | %s |" % miles(lec))
        A("| Escrituras (solo lo que difería) | %s |" % miles(esc))
        A("| **total** | **%s** |" % miles(lec + esc))
        A("")
    A("### El total de la puesta en marcha")
    A("")
    media = (sum(ros_lec.values()) + sum(ros_esc.values())) / max(len(convergencias), 1)
    A("| Vía | Llamadas medidas |")
    A("| --- | ---: |")
    A("| API de Proxmox (trazador, capa 1 completa) | %s |" % miles(j["total"]))
    A("| API de RouterOS (log, todos los verbos) | %s |" % miles(tot_ros))
    A("| **total de llamadas a APIs** | **%s** |" % miles(j["total"] + tot_ros))
    A("| Ejecuciones de tarea (capa 2, por SSH) | %s |" % miles(tot_ejec))
    A("| **suma de operaciones contables** | **%s** |" % miles(j["total"] + tot_ros + tot_ejec))
    A("")
    A("Reparto del trabajo de RouterOS entre los %d verbos que lo tocaron: una media"
      % len(convergencias))
    A("de **%.0f llamadas por convergencia**, sobre once equipos." % media)
    A("")
    A("## Qué NO mide este documento")
    A("")
    A("- **No mide trabajo humano.** Mide trabajo de máquina, que es lo único que se")
    A("  puede contar sin preguntar.")
    A("- **Las llamadas del rol RouterOS no están en el diario**, porque el trazador")
    A("  cubre `requests` y el rol va por `urllib`. Se cuentan del log, que sí las")
    A("  imprime una a una: por eso el detalle por endpoint existe, pero no lleva")
    A("  segundos por llamada (solo el tiempo total por equipo).")
    A("- **Los segundos de Proxmox son espera de la API, no de la tarea.** Un módulo")
    A("  que corre dentro de un invitado tarda lo que tarde el invitado, y eso no")
    A("  cruza ninguna API: se cuenta como ejecución, no como segundo.")
    A("- **Los verbos fallidos cuentan igual.** Un `apply` que falla a mitad sigue")
    A("  gastando llamadas, y aquí aparecen: son parte del coste real de dejar el")
    A("  laboratorio en pie.")

    texto = "\n".join(L) + "\n"
    open(SALIDA, "w").write(texto)
    if args.stdout:
        sys.stdout.write(texto)
    else:
        print("escrito %s (%d líneas)" % (SALIDA, len(L)))


if __name__ == "__main__":
    main()
