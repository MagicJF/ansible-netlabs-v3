# 0001 — El hipervisor se gobierna SOLO por su API

- Estado: aceptada
- Fecha: 2026-11-11

## Contexto
El framework administra invitados (VM/LXC) en un nodo Proxmox. Existe la tentación de
ejecutar cosas en el host (snippets, hookscripts, `pct exec`) para lo que la API no ofrece
directamente.

## Decisión
Toda interacción con Proxmox es por su API HTTPS/REST. Nunca snippets, hookscripts ni nada
que ejecute código como root en el hipervisor. Cuando algo solo se puede resolver en el host
(el extremo del túnel WireGuard), es un script versionado que el operador corre a mano UNA
vez, con el comando y la clave pública impresos en el mensaje de fallo.

## Consecuencias
- El token administra invitados; NO concede derecho a ejecutar como root en el host.
- Un requisito que parezca necesitar un hook se resuelve con un paso manual explícito.
- La API es la única puerta: si algo no se puede hacer por API, se dice, no se rodea.

## Dónde se aplica
Regla vinculante en `.hermes.md` («Regla absoluta»); la skill `devops-iac` la desarrolla.
