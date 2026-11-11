# 0003 — La ruta por defecto que deja el DHCP de fábrica se purga con un reinicio

- Estado: aceptada
- Fecha: 2026-11-11

## Contexto
El lease DHCP del bootstrap (ADR 0002) instala en el router una ruta por defecto dinámica
`0.0.0.0/0 via 10.10.10.1`, con el mismo `distance` que la estática declarada. RouterOS hace
balanceo ECMP y manda la mitad de las respuestas por la puerta de gestión, lo que se
manifiesta como alcance parcial cross-sede. La convergencia desactiva el cliente DHCP, pero
NO borra esa ruta: la API se niega (`cannot modify dynamic route created by a different
owner`, medido). Se probó el borrado dentro del guion del router y el equipo se quedó SIN
dirección (API muda), porque no deja tocar la dirección dinámica heredada.

## Decisión
El rol `routeros` detecta esa ruta, reinicia el equipo UNA vez con el cliente ya
desactivado, espera a que vuelva y verifica que desapareció. Solo reinicia cuando la ruta
existe, así que un `site` posterior es idempotente. Si tras el reinicio la ruta siguiera
ahí, el `site` falla a propósito (sería un CHR que nace con el cliente activo). Se usan las
imágenes CHR de fábrica; no se fabrica ninguna ISO.

## Consecuencias
- Purga fiable sin tocar la imagen; el precio es un reinicio, una sola vez por equipo.
- La comprobación de ruta tolera un gemelo dinámico a propósito; el reinicio es lo que lo
  elimina.

## Dónde se aplica
`configure/roles/routeros/tasks/main.yml`; prosa en el README (plantilla `docs/README.md.j2`).
