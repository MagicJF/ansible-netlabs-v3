# 0002 — Por qué existe el bootstrap (y no es un segundo camino de configuración)

- Estado: aceptada
- Fecha: 2026-11-11

## Contexto
Un CHR recién importado arranca con un cliente DHCP en `ether1` y SIN dirección. Como VM no
puede tomar una del servidor DHCP del host: la oferta llega con un checksum UDP sin resolver
y el kernel del invitado la descarta. Sin dirección, su API REST no existe, así que no hay
con qué configurarlo.

## Decisión
Un contenedor (`infra-bootstrap`) entrega esa ÚNICA primera dirección, en el mismo segmento
que la pata de gestión del router, con dnsmasq atado a la MAC y
`ethtool -K eth0 tx off gso off tso off` (sin eso su propia oferta lleva el checksum roto).
Después de que el router toma la dirección, el contenedor no interviene nunca más: todo lo
demás es REST. Es un bootstrap, no una segunda vía de configuración.

## Consecuencias
- El defecto que bloquea al servidor del host es lo que lo hace determinista: el router ve
  una sola oferta, así que no hay carrera entre dos servidores DHCP.
- La oferta lleva la puerta por defecto (opción 3): sin ella el router no sabe volver fuera
  de su subred y su API no contesta al nodo de control (medido). Esa puerta es, además, el
  ORIGEN de la ruta dinámica del ADR 0003.

## Dónde se aplica
`configure/roles/bootstrap/`; prosa en `EL-LABORATORIO.md`; la sección «¿Se puede prescindir
del bootstrap?» de `.hermes.md`.
