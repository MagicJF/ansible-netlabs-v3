#!/usr/bin/env python3
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
import re

import jinja2
import jinja2.nativetypes
import yaml


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
    return yaml.safe_load(open(ruta, encoding="utf-8")) or {}


def _resolver(x, env, ctx):
    if isinstance(x, str):
        try:
            return env.from_string(x).render(**ctx)
        except Exception:
            return x  # se queda como estaba; lo denunciará quien la use
    if isinstance(x, dict):
        return {k: _resolver(v, env, ctx) for k, v in x.items()}
    if isinstance(x, list):
        return [_resolver(v, env, ctx) for v in x]
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
    """El manifiesto con sus referencias resueltas a VALORES."""
    env = entorno()
    man = crudo(ruta)
    return _resolver(man, env, contexto(man, env))
