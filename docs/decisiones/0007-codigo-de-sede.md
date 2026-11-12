# 0007 — El código de sede: familia e índice

- Estado: aceptada
- Fecha: 2026-11-12
- Sustituye a: 0005 (la tabla de sedes y la lectura del campo `SS`)

## Contexto

La ADR 0005 fijó que la sede se escribe con dos letras y que **cada letra se lee
como su cifra alfabética** (`A`=1 … `I`=9, `AA`=11 … `II`=99). Eso ata el código al
orden del abecedario: la central salía `AB` (12) y las delegaciones `AC` (13) / `AD`
(14), así que el código no dice **qué** es la sede —hay que consultar la tabla— ni se
corresponde con su nombre. Quien lee la etiqueta en el árbol de PVE no sabe si `AC`
es «central» o «lo tercero».

## Decisión

El código de sede son **dos letras**: la primera es la **FAMILIA** —la INICIAL de su
nombre— y la segunda, **minúscula**, el **ÍNDICE** dentro de ella. El número que va
al vmid es la **DECENA** de la familia (su POSICIÓN en la tabla `lab_familias`) y la
unidad del índice (`a`=1, `b`=2…).

| Familia                 | Decena | Código | Nº  |
|-------------------------|--------|--------|-----|
| **C** — central         | 1x     | `Ca`   | 11  |
| **S** — sedes           | 2x     | `Sa`…  | 21… |
| **I** — infraestructura | 3x     | `Ia`   | 31  |
| **G** — gestión         | 4x     | `Ga`   | 41  |
| **B** — borde           | 5x     | `Ba`   | 51  |

Una tercera sede sería `Sc` (23), una cuarta `Sd` (24). Las familias se declaran, **en
orden**, en `lab_familias` (su posición es la decena); los códigos de sede en
`lab_sites[].codigo`; y los que no alojan estaciones —`Ia`, `Ga`, `Ba`— en
`lab_sedes_extra`. El nombre sigue espejando el número: `LL-SS-token-II`
(ej.: `10-Ca-swac-10` = `10111110`).

## Consecuencias

- La **etiqueta de sitio** (la tercera del invitado) es el MISMO código: nombre,
  número y etiqueta dicen lo mismo, con una diferencia que impone PVE: la etiqueta
  viaja en MINÚSCULAS (`ca`) porque PVE las normaliza al guardarlas, mientras el
  nombre conserva la caja (`11-Ca-rtco-10`). Ver la corrección del
  [ADR 0006](0006-vocabulario-etiquetas.md). El vocabulario lo fija la [ADR 0006](0006-vocabulario-etiquetas.md).
- Se **renumeraron** los tres laboratorios existentes (nombres y vmids): netlab-v2
  (central `Ca`, delegaciones `Sa`/`Sb`), coworking (edificio `Ca`, inquilinos
  `Sa`/`Sb`) y mini (su única sede, `Ca`). Cambiar un vmid obliga a **recrear** el
  invitado, así que un laboratorio en marcha (netlab-v2) se levanta de nuevo.
- El check `numeracion` deja de leer la cifra alfabética y lee la POSICIÓN de la
  familia —un dato de la declaración—, así que añadir una familia es una entrada y el
  check la recoge solo.

## Dónde se aplica

`lab_familias`, `lab_sites[].codigo` y `lab_sedes_extra` del inventario de cada
laboratorio; `playbooks/tools/pve_notas.py` (la etiqueta de sitio) y
`playbooks/tools/documentos.py`; `framework_check.py` (`numeracion` y `notas`); y la
prosa de `docs/laboratorio.md.j2`.
