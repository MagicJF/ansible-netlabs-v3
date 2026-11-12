#!/usr/bin/env python3
# ===========================================================================
# notas.py — la nota HTML de cada invitado y sus cuatro etiquetas, como FILTRO.
#
# Qué es: el puente entre la declaración y las dos cosas que Proxmox enseña en
# su interfaz (`description` y `tags`). NO guarda nada: se calcula cada vez que
# se construye la especificación efectiva de un invitado.
#
# Por qué así: la nota cuenta cables, direcciones, rutas y reglas, y todo eso ya
# está en la declaración. Guardarla DENTRO del manifiesto era una copia de algo
# derivado de sí mismo — una caché en la fuente de verdad, que un día se queda
# vieja y entonces nadie sabe cuál de las dos miente (pasó: la nota de un
# invitado llevaba 53 líneas de retraso y el manifiesto no lo decía). Aquí se
# calcula en el momento de usarla, con los mismos valores que todo lo demás.
#
# Uso desde un play, dentro de la construcción de la especificación efectiva:
#   {% set notas = pve_containers | notas_map(pve_vms, lab_sites, lab_hub) %}
#   ... pve_defaults | combine(ficha) | combine(notas[ficha.vmid])
#
# El render vive en `playbooks/tools/pve_notas.py` (probado); aquí sólo se le
# inyecta el manifiesto resuelto que el play ya tiene en memoria, sin leer
# ficheros. Una sola implementación, y sin efectos al importar.
# ===========================================================================
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, os.path.join(RAIZ, "playbooks", "tools"))

import pve_notas as N  # noqa: E402


def notas_map(cts, vms=None, sites=None, hub=None, otros=None, mgmt2=None, lab_numero=None):
    """{vmid: {"description": <html>, "tags": [cuatro]}} de toda la declaración.

    Los argumentos son los que el render necesita: la lista de contenedores y de
    VMs (para saber quién es vecino de quién por los cables), la tabla de sedes
    con el hub (para el diagrama de posición y la sede) y el número declarado del
    laboratorio (`lab_numero`, para la etiqueta «Lab-NN»).
    """
    N.man = {
        "pve_containers": cts,
        "pve_vms": vms or [],
        "lab_sites": sites or [],
        "lab_hub": hub,
        "lab_mgmt_otros": otros or {},
        "lab_mgmt2": mgmt2 or {},
        "lab_numero": lab_numero,
    }
    N.preparar()
    out = {}
    for e in N.todos(N.man):
        out[e["vmid"]] = {"description": N.html(e), "tags": N.tags_de(e)}
    return out


class FilterModule(object):
    def filters(self):
        return {"notas_map": notas_map}
