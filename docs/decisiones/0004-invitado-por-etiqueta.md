# 0004 — Un invitado del laboratorio se reconoce por su etiqueta, no por su VMID

- Estado: aceptada
- Fecha: 2026-11-11

## Contexto
Para poder afirmar «la plataforma no tiene invitados del laboratorio fuera de la
declaración» hay que decidir primero qué invitado de la plataforma es «del laboratorio».
El **VMID no sirve**: sus rangos se solapan entre laboratorios — netlab-v2 declara 2401 y
2402 (estaciones de la delegación 2) y mini declara 2001, 2011 y 2021, todos en la banda
2xxx—, y la numeración tiene excepciones (901 para el bootstrap de netlab-v2, 4401 para su
switch de gestión). El **nombre tampoco**: `infra-bootstrap` existe en los dos
laboratorios. Y una lista de VMID escrita a mano sería otra copia que envejece en cuanto un
laboratorio crezca.

## Decisión
El discriminante es la **etiqueta que la propia declaración pone a todos sus invitados**
(`pve_defaults.tags` y `pve_vm_defaults.tags`, hoy `netlab` y `ansible`; ver
[ADR 0006](0006-vocabulario-etiquetas.md)). Un
invitado de la plataforma pertenece al laboratorio si lleva alguna de esas etiquetas; los
del host (100 hermesagent, 101 caddy, 105 netbox) no las llevan y quedan fuera del juicio.
`framework_check.py guests` compara entonces el conjunto declarado por TODOS los
laboratorios contra los invitados etiquetados de la plataforma: falla si hay uno
etiquetado sin declarar («extra») o si el laboratorio ACTIVO —el que apunta
`HERMES_LAB`, no el enlace `labs/active` si se está validando otro— declara una VMID ausente
(«falta»).

## Consecuencias
- El juicio se **deriva de la declaración**, no de una lista escrita a mano: si mañana un
  laboratorio añade otro marcador en sus `defaults`, el check lo recoge solo.
- Depende de que la etiqueta se aplique **al crear** el invitado. Un invitado del lab sin
  la etiqueta se vería como ajeno, y uno ajeno con la etiqueta se vería como del lab. Es el
  precio de reconocer por etiqueta en vez de por rango, y es el precio que se acepta.
- La comprobación cubre la **unión** de laboratorios para «extra» y el laboratorio
  **activo** para «falta».

## Dónde se aplica
El check `framework_check.py guests`
([`playbooks/tools/framework_check.py`](playbooks/tools/framework_check.py)); las etiquetas
se declaran en `pve_defaults` y `pve_vm_defaults` del inventario de cada laboratorio; y la
prosa en el README (plantilla `docs/README.md.j2`).
