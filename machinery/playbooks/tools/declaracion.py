#!/usr/bin/env python3
# PROPÓSITO: cargar la declaración del laboratorio con sus referencias `{{ }}` resueltas.
# INVARIANTES: una ficha CITA la tabla del manifiesto, no lleva la dirección dentro; quien
#   lea el YAML en crudo encuentra plantillas donde espera direcciones.
# LÍMITES: el fallo por referencias sin resolver no siempre es ruidoso (el mapa sale con
#   `{{ … }}` y `agree` denuncia un desfase que no existe).
# VER: `framework_check.py agree`.
# ===========================================================================
# declaracion.py — la declaración del laboratorio, con sus referencias resueltas.
#
# Por qué existe: una ficha NO lleva la dirección dentro; CITA la tabla del
# manifiesto (`lab_sede[1].mgmt.rt`, `lab_mgmt_otros.infra`) y Ansible la
# renderiza al usarla. Una herramienta que lea el YAML en crudo se encuentra
# plantillas donde espera direcciones, y el fallo no siempre es ruidoso: el mapa
# de destinos sale con `{{ ... }}` y `agree` denuncia un desfase que no existe.
#
# Aquí se replica ese render UNA vez, para todas: `cargar()` devuelve el
# manifiesto con los valores reales. El día que aparezca otra variable derivada
# hay un solo sitio que tocar. Se replica con entorno NATIVO (un `{{ dict(...) }}`
# es un dict, no su representación como texto) y con los filtros de Ansible que
# la declaración usa, para no tener que sacarla de su sitio.
# ===========================================================================
import json
import os
import re

import jinja2
import jinja2.nativetypes
import yaml

# La raíz del repositorio —para encontrar `labs/defaults.yml`—, subiendo desde
# `machinery/playbooks/tools/`: tools -> playbooks -> machinery -> repo.
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def entorno():
    """El entorno con los filtros de Ansible que la declaración usa."""
    env = jinja2.nativetypes.NativeEnvironment(undefined=jinja2.StrictUndefined)
    env.filters["flatten"] = lambda x: [i for s in x
                                        for i in (s if isinstance(s, list) else [s])]
    env.filters["to_json"] = json.dumps
    env.filters["from_json"] = json.loads
    env.filters["zip"] = lambda a, b: list(zip(a, b))
    env.filters["regex_replace"] = lambda v, pat, repl: re.sub(pat, repl, str(v))
    return env


def crudo(ruta):
    """El manifiesto tal cual, sin resolver: para quien reescribe el fichero."""
    return leer_manifiesto(ruta)


def _resolver(x, env, ctx, _prof=0):
    """Resuelve en CASCADA, que es como renderiza Ansible.

    Un valor no se queda resuelto por renderizar su propia cadena: el `hosts` del
    bootstrap es una plantilla que LEE `pve_vms`, y las direcciones de `pve_vms`
    son a su vez plantillas contra la tabla de sedes. Con una sola pasada, la
    lista de reservas salía con `{{ lab_sede[1].mgmt.sw[0] }}` dentro — y una
    reserva DHCP con una plantilla es una reserva que no concede nada.
    """
    if _prof > 6:
        return x
    if isinstance(x, str):
        try:
            r = env.from_string(x).render(**ctx)
        except Exception:
            return x  # se queda como estaba; lo denunciará quien la use
        # Sólo se sigue si el resultado TODAVÍA es una plantilla: si no, un texto
        # sin Jinja se renderizaría a sí mismo para siempre.
        if isinstance(r, str) and ("{{" in r or "{%" in r):
            return _resolver(r, env, ctx, _prof + 1)
        if isinstance(r, (list, dict)):
            return _resolver(r, env, ctx, _prof + 1)
        return r
    if isinstance(x, dict):
        return {k: _resolver(v, env, ctx, _prof) for k, v in x.items()}
    if isinstance(x, list):
        return [_resolver(v, env, ctx, _prof) for v in x]
    return x


def contexto(man, env=None):
    """El contexto con las variables DERIVADAS de nivel raíz ya resueltas.

    `lab_sede` llega como el texto "{{ dict(...) }}": sin resolverlo, `lab_sede[1]`
    indexa la CADENA por caracter y el render revienta con «'str object' has no
    attribute 'puerta'». Se resuelven primero, en orden de dependencia.
    """
    env = env or entorno()
    ctx = dict(man)
    for _ in range(4):
        pendiente = [k for k, v in ctx.items() if isinstance(v, str) and "{{" in v]
        if not pendiente:
            break
        for k in pendiente:
            try:
                ctx[k] = env.from_string(ctx[k]).render(**ctx)
            except Exception:
                pass
    return ctx


def cargar(ruta):
    """El manifiesto con sus referencias resueltas a VALORES.

    POR CAPAS, y no es un lujo: hay plantillas que LEEN otras plantillas. El
    `segments` del bootstrap mira el `net0` de cada VM para saber en que bridge
    tiene su gestion, y ese `net0` es a su vez una plantilla (`bridge={{ ... }}`).
    Con una sola pasada el contexto le da la plantilla sin resolver, ninguna
    reserva casa, y el resultado es una lista VACIA — que no revienta, que es lo
    peligroso. Se renderiza, se mete lo renderizado en el contexto, y se repite.
    """
    env = entorno()
    raw = crudo(ruta)
    ctx = dict(contexto(raw, env))
    for _ in range(3):
        ctx = {**ctx, **_resolver(raw, env, ctx)}
    return _resolver(raw, env, ctx)


# ---------------------------------------------------------------------------
# Fusión con `labs/defaults.yml` (shadowing). Ver `fusionar`.
# ---------------------------------------------------------------------------
def fusionar(base, propio):
    """`propio` ENCIMA de `base`, en profundidad (shadowing).

    Lo que el laboratorio no escribe, lo pone el default; los diccionarios se funden
    clave a clave, para que declarar `pve_defaults: {memory: 4096}` cambie SÓLO la
    memoria y conserve el resto. Las listas y los escalares se sustituyen enteros:
    una lista no se puede entremezclar sin inventar un orden que nadie declaró.
    """
    if isinstance(base, dict) and isinstance(propio, dict):
        out = dict(base)
        for k, v in propio.items():
            out[k] = fusionar(base[k], v) if k in base else v
        return out
    return propio


def leer_manifiesto(ruta, loader=yaml.safe_load):
    """Un manifiesto de laboratorio YA FUNDIDO con `labs/defaults.yml`.

    TODO el que lea una declaración pasa por aquí: un lector que se saltara la fusión
    vería un laboratorio al que le faltan claves sin que nada avisara — y con
    `undefined` estricto eso no es un error ruidoso, es una variable vacía.
    """
    with open(ruta, encoding="utf-8") as fh:
        propio = loader(fh) or {}
    with open(os.path.join(_REPO, "machinery", "defaults.yml"), encoding="utf-8") as fh:
        base = yaml.safe_load(fh) or {}
    return fusionar(base, propio)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="La declaración, fundida con labs/defaults.yml.")
    ap.add_argument("--fundir", help="manifiesto del laboratorio")
    ap.add_argument("--salida", help="dónde dejar el YAML fundido (para Ansible)")
    a = ap.parse_args()
    if a.fundir and a.salida:
        datos = leer_manifiesto(a.fundir)
        with open(a.salida, "w", encoding="utf-8") as fh:
            yaml.safe_dump(datos, fh, sort_keys=False, allow_unicode=True, width=1000)
        print(f"{a.fundir} + labs/defaults.yml -> {a.salida}")
