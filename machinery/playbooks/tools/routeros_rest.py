"""La puerta REST a RouterOS, compartida por las herramientas del marco.

PROPÓSITO: un solo sitio donde vive cómo se LEE un menú de RouterOS por su API REST y
con qué credenciales, para que `routeros_wait.py` y `routeros_ready.py` no mantengan
dos copias que puedan desfasarse.

INVARIANTES:
- La API de RouterOS se toca por REST sobre HTTP básico (`requests`), NUNCA por SSH ni
  por la API binaria de TCP/8728.
- Las credenciales salen del entorno de ESTA máquina (`secrets.yaml`) y de los defaults
  del rol RouterOS: una sola fuente para las dos puertas.

LÍMITES: aquí sólo se LEE (GET). Escribir es del rol, con `ansible.builtin.uri`.

VER: docs/decisiones/0002-bootstrap-existe.md; la puerta de la API la vigila
`machinery/playbooks/tools/framework_check.py api`.
"""
from __future__ import annotations

import os

import yaml

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
ENTORNO = os.path.join(RAIZ, "secrets.yaml")
ROUTEROS_DEFAULTS = os.path.join(RAIZ, "machinery/configure/roles/routeros/defaults/main.yml")


def credenciales():
    """(usuario, clave, esquema, puerto): del entorno de la máquina y del rol."""
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
