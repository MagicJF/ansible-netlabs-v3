# Proxmox LXC y VM mediante Ansible

IaC declarativo para los contenedores LXC y las máquinas virtuales QEMU de Proxmox
VE, gobernado **enteramente por la API HTTPS**. Ningún playbook entra por SSH en
el hipervisor.

---

## El laboratorio: una empresa de tres sedes

Lo que este repositorio despliega es un laboratorio de red que simula **una
empresa con una central y dos delegaciones**: ocho workstations, **once equipos
de red** MikroTik (RouterOS) —cuatro switches, tres routers y cuatro firewalls— y
los cables que los unen, todo declarado en un solo fichero y gobernado
**exclusivamente por la API**.

```
        SEDE 1 — LA CENTRAL                      SEDE 2                SEDE 3
   ┌──────────────────────────────────┐    ┌───────────────┐    ┌───────────────┐
   │  pc-s1-01..04 (cuatro PCs)       │    │  pc-s2-01/02  │    │  pc-s3-01/02  │
   │       │        │                 │    │      │        │    │       │       │
   │  sw-s1-acc-01 ═══ sw-s1-acc-02   │    │ sw-s2-acc-01  │    │ sw-s3-acc-01  │
   │       │       (troncal)          │    │      │        │    │       │       │
   │       └───────────┬──────────────│    │      │        │    │       │       │
   │             rt-s1-core           │    │  rt-s2-edge   │    │  rt-s3-edge   │
   │                   │              │    │      │        │    │       │       │
   │             fw-s1-perim ─────────┼────┼─ fw-s2-perim  │    │  fw-s3-perim  │
   │                   │              │    │               │    │       │       │
   │             fw-wan-edge ────▶ internet (NAT)          │    │       │       │
   └──────────────────────────────────┘    └───────────────┘    └───────────────┘
                                        ╰── WAN 1 ──╯  ╰───── WAN 2 ─────╯
```

En una frase: **cuatro switches, tres routers y cuatro firewalls** RouterOS, y el
camino de un paquete dentro de una sede es **`pc → sw → rt → fw → WAN`**. Los
switches lo son por su configuración (patas de datos en un puente sin dirección,
lo que los distingue de un router). **El router es la puerta y el servidor DHCP de
su LAN**, no el switch ni el firewall: el DHCP es una difusión de capa 2, así que
quien reparte las direcciones tiene que estar en el mismo segmento que sus
clientes. Los firewalls **filtran el perímetro** y sólo el de borde hace **NAT**.
Las **ocho workstations no tienen ninguna vía de gestión** (una sola interfaz,
dirección por DHCP, como un PC de verdad), y la red se verifica **desde dentro de
los propios equipos**, que es como lo haría un ingeniero.

**Guía completa, en castellano: [`EL-LABORATORIO.md`](EL-LABORATORIO.md)** — la
topología explicada, el direccionamiento, por dónde va un paquete, las dos capas
del despliegue, el orden de montaje y cómo se verifica.

---

## Estructura

```text
inventory/group_vars/all.yml           # EL estado deseado — el único fichero que cambia por petición
ansible.cfg                            # pipelining, reutilización SSH, forks, rutas de plugins y log
.ansible-lint                          # las reglas de lint que se exigen, y por qué no las demás
playbooks/preflight.yml                # sólo lectura: comprobaciones de plataforma + declarado frente a vivo
playbooks/apply.yml                    # converge cada invitado declarado y luego verifica por la API
playbooks/connect.yml                  # converge el CAMINO del nodo de control hacia la LAN de invitados
playbooks/remove.yml                   # el destruir deliberado, se niega mientras el invitado siga declarado
playbooks/pve_engine.j2                # motor: análisis declarado-vs-vivo, como macros Jinja
playbooks/tasks/                       # motor: pasos compartidos (segmentos, importación de discos, energía, tags)
playbooks/tools/pve_read.py            # motor: lee todos los invitados + datos de plataforma en UN proceso
playbooks/tools/framework_check.py     # el test del propio marco: convergente, y ve el drift
playbooks/tools/pve_notas.py           # motor: genera la nota HTML y las etiquetas, desde la declaración
playbooks/tools/logs_prune.py          # motor: retención de logs/, la aplica cada verbo
playbooks/tools/esfuerzo.py            # genera ESFUERZO.md desde los registros reales
playbooks/tools/lab-check.sh           # verificación end-to-end de la red, desde dentro de una workstation
playbooks/tools/lab-check.yml          # la misma prueba, orquestada como playbook
playbooks/tools/pve_start_batch.py     # arranque por escalones contra la API
playbooks/tools/routeros_wait.py       # espera a que un equipo RouterOS termine de arrancar
playbooks/tools/segment_comments.py    # vuelca en los bridges del host la descripción de su cable
playbooks/tools/wg_endpoint_setup.sh   # capa 2: bootstrap del extremo del túnel, una vez en el host PVE
playbooks/tracing/sitecustomize.py     # motor: registra cada llamada HTTP a PVE
filter_plugins/pve.py                  # motor: filtros de canonicalización que usan las macros
filter_plugins/state.py                # motor: comprobaciones de referencias cruzadas del estado declarado
configure/audit.yml                    # capa 2: inspección de sólo lectura de un invitado
configure/site.yml                     # capa 2: converge el interior de los invitados gestionados
configure/tasks/                       # capa 2: construcción de destinos, política de acceso y el camino
configure/roles/<app>/                 # capa 2: un rol por aplicación, o por tipo de invitado
logs/                                  # registros de ejecución, diario de la API y su archivo (ignorado por git)
```

La **capa 1** es un motor fijo con cuatro verbos —`preflight` (sólo lectura),
`apply` (converge), `connect` (el camino) y `remove` (el destruir deliberado)—
leyendo todos el mismo estado declarado. Una petición de cambio es una edición de
`inventory/group_vars/all.yml` en una rama nueva, no un playbook nuevo: un
playbook por cambio dispersaría el estado real en ficheros que se pisan unos a
otros. **La rama se corta de `main` y se fusiona cuando el trabajo está
terminado** — `main` es donde vive lo acabado y sólo hay una. Cortar de la rama
anterior es cómo este repositorio llegó a acumular catorce ramas encadenadas con
`main` 43 commits por detrás: cada rama contenía la anterior, así que nunca hubo
nada en `main`. `connect` posee lo único que no es un invitado, el camino de red
del nodo de control hacia la LAN de invitados (ver [El camino por el que corre la
capa 2](#el-camino-por-el-que-corre-la-capa-2)); `remove` posee lo único que el
motor no hará por su cuenta (ver [Añadir y quitar un
invitado](#añadir-y-quitar-un-invitado)).

`group_vars/all.yml` es un *fichero* de group_vars, así que sus variables viven en
el nivel superior; anidarlas bajo una clave `all:` sólo define una variable
llamada `all` y rompe todas las referencias.

## Requisitos

- Ansible Core 2.17 o superior.
- La colección `community.proxmox` 2.1.0 (`ansible-galaxy collection install -r requirements.yml`).
- Las dependencias Python de la colección: `proxmoxer >= 2.3` y `requests` (`python3 -m pip install -r requirements.txt`).
- Un token de la API de Proxmox, disponible sólo en el entorno local o en Ansible Vault; nunca en el repositorio.
- Un certificado/CA de confianza para la API de PVE. Se apunta `PROXMOX_CA_PATH` a ese fichero local y `PROXMOX_HOST` a un nombre o IP presente en el SAN del certificado.

## Credenciales

Dos fuentes, en este orden de precedencia:

1. **`playbooks/vars/secrets.yml`** — valores escritos directamente. Los dos playbooks lo cargan en `pre_tasks` cuando el fichero existe, así que no hace falta preparar el entorno. **Está ignorado por git a propósito**: el repositorio es público y el token de PVE equivale a root y no caduca. El fichero se crea con permisos `0600`. No lo commitees ni copies su contenido a un fichero versionado, una issue o un mensaje de commit.
2. **Variables de entorno `PROXMOX_*`** — el respaldo, usado cuando el fichero no está. Es la vía preferible en cuanto se retire el hardcode temporal.

Para volver a credenciales sólo por entorno, borra `playbooks/vars/secrets.yml`; no hay que cambiar nada más.

Nunca commitees estos valores. Si el token llega a un fichero versionado o al remoto, rótalo de inmediato (el motor lee lo que haya en `secrets.yml`, así que rotar es editar una línea).

### Variables de entorno (vía de respaldo)

```text
PROXMOX_HOST=<nombre o IP del SAN de la API de PVE>
PROXMOX_TOKEN_ID=<usuario@realm!nombre-del-token>
PROXMOX_TOKEN_SECRET=<secreto del token>
PROXMOX_CA_PATH=<ruta al certificado/CA de confianza de PVE>
```

En este laboratorio el certificado incluye la IP pública de PVE como SAN; la
dirección de LAN `10.10.10.1` no está en ese certificado, así que usa un nombre o
IP que coincida con el SAN, o sustituye el certificado por uno que cubra el nombre
de la LAN.

## Cómo se ejecuta

```bash
python3 -m pip install -r requirements.txt
ansible-galaxy collection install -r requirements.yml
ansible-playbook --syntax-check playbooks/preflight.yml
ansible-playbook --syntax-check playbooks/apply.yml
ansible-playbook playbooks/preflight.yml   # sólo lectura: comprobaciones + qué cambiaría
ansible-playbook playbooks/apply.yml       # converge + verifica
ansible-playbook playbooks/connect.yml     # converge el camino que la capa 2 necesita (normalmente automático)
```

Para iterar de forma interactiva, el verbo es `apply`: lee el estado declarado,
aplica lo que difiere y vuelve a leer para verificar por la API en la misma
ejecución. Lanza `preflight` cuando sospeches drift, no como paso rutinario — ver
[Rendimiento y cómo iterar rápido](#rendimiento-y-cómo-iterar-rápido).

## El estado declarado

`inventory/group_vars/all.yml` contiene `pve_node`, un bloque `pve_defaults`,
`pve_containers` (los invitados LXC) y `pve_vms` (los invitados RouterOS CHR):
**los únicos invitados que este repositorio gestiona**. Un invitado ausente de esas
listas nunca se lee, se crea ni se modifica. Cualquier clave de `pve_defaults`
puede sobrescribirse por invitado.

El laboratorio v2 son **veinte invitados** — nueve contenedores y once VMs CHR —
numerados `STNN` (sede, tipo, índice):

| vmid | hostname | qué es |
| --- | --- | --- |
| 1401-1404 | `pc-s1-01`…`pc-s1-04` | las cuatro workstations de la central (LXC: 1 vCPU / 256 MiB / 4 GiB) |
| 2401-2402 | `pc-s2-01`, `pc-s2-02` | las workstations de la delegación 2 |
| 3401-3402 | `pc-s3-01`, `pc-s3-02` | las workstations de la delegación 3 |
| 901 | `infra-bootstrap` | da a cada equipo de red su **primera** dirección, una vez |
| 1301, 1302 | `sw-s1-acc-01`, `sw-s1-acc-02` | los dos switches de acceso de la central, unidos por un troncal |
| 2301 | `sw-s2-acc-01` | el switch de la delegación 2 |
| 3301 | `sw-s3-acc-01` | el switch de la delegación 3 |
| 1201, 2201, 3201 | `rt-s1-core`, `rt-s2-edge`, `rt-s3-edge` | los routers: puerta de la LAN **y servidor DHCP** |
| 1101, 2101, 3101 | `fw-s1-perim`, `fw-s2-perim`, `fw-s3-perim` | los perímetros de sede: filtrado |
| 9101 | `fw-wan-edge` | el firewall de borde: filtrado **y NAT** |

El manifiesto de la v1 llevaba una segunda lista, `pve_config_targets`: invitados
cuya **forma** no gestionaba pero cuyo **interior** sí. **La v2 no la usa como
fuente de verdad** — cada invitado que configura es uno que también declara. El
grupo sigue declarado vacío en `inventory/hosts.yml` por compatibilidad con los
playbooks de capa 2, que lo llenan con `add_host` desde la declaración; en la v2
no contiene nada. Lo que la v1 adoptaba queda fuera de la declaración, así que la
convergencia nunca lo lee, lo crea ni lo modifica.

Declarado por contenedor, heredado de `pve_defaults` salvo que se sobrescriba:

| Propiedad | Declarada como | La converge `apply.yml` |
| --- | --- | --- |
| `vmid`, `hostname` | identidad | no — cambiarlas significa "recrear" |
| `ostype` | `debian` | no — propiedad de creación |
| `storage`, `rootfs_size`, `template`, `template_storage` | `local-zfs`, 4-8 GiB, Debian 13 | no — creación; crecer el rootfs es irreversible |
| `unprivileged` | `true` | no — propiedad de creación |
| `cores`, `memory`, `swap`, `cpuunits` | 1-5, 512-2560 MiB, 256-896 MiB, 1024 | sí |
| `onboot` | `false` | sí |
| `status` | `stopped` por defecto, `started` por invitado | sí — el contenedor se para/arranca para coincidir |
| `cmode` | `shell` | sí |
| `timezone` | `host` | sí |
| `description` | nota HTML, **generada** por `playbooks/tools/pve_notas.py` | sí |
| `tags` | `[ansible-managed, <rol>, <sede>]` — tres, ni una más | sí |
| `features`, `startup` | `[]` (no deben existir) | sí — se borran si están |
| `netif` | `{}` por defecto; declarado por invitado | sí — se crean las interfaces declaradas y se borran las que no lo estén |
| `mounts`, `mount_devices` | `{}`, `[]` (no deben existir) | sí — se borran si están |
| `nameserver`, `searchdomain`, `hookscript` | `null` | sí — se borran si están |

**La ausencia es estado.** Un ajuste declarado como `null`/vacío no debe existir en
el contenedor, y el motor lo borra si está. Así es como se revierte una interfaz,
un montaje o una línea `features=` puesta a mano.

### Añadir y quitar un invitado

Añadir uno es: escribir la entrada, lanzar `apply` (la forma) y luego
`configure/site.yml` (el interior). Quitar uno son **dos pasos en este orden**,
porque el motor nunca destruye nada:

1. **Desdeclararlo** — borrar la entrada entera de `pve_containers` (o `pve_vms`)
   en una rama, commit y push. El siguiente `apply` deja de gestionarlo; el
   contenedor sigue corriendo, intacto.
2. **Destruirlo** deliberadamente — interfaz de PVE → *More → Destroy*, `pct
   destroy <vmid>` en el host, o `ansible-playbook playbooks/remove.yml -e
   hostname=<nombre> -e confirm=<nombre>`. `remove.yml` se niega mientras el
   invitado siga declarado, que es exactamente por qué el orden no es una
   preferencia.

Hacerlo al revés es cómo un invitado borrado vuelve: destruye uno que siga
declarado y el siguiente `apply` lo recrea.

**Borra la entrada entera, o nada de ella.** YAML se queda con el *último* valor de
una clave duplicada sin avisar, así que una entrada cuyas líneas de identidad se
borraron mientras su bloque `manage:`/`config:` seguía ahí no desaparece: se
engancha en silencio a la entrada de arriba y reconfigura **ese** invitado. Tres
guardián hacen que eso sea un fallo ruidoso en vez de uno silencioso:

- el lector parsea el estado declarado con un **cargador que rechaza claves
  duplicadas** y se detiene indicando la clave y la línea;
- cada entrada debe llevar su identidad (`vmid` más `hostname`/`name`), o la
  ejecución se niega;
- el **validador de estado** (`filter_plugins/state.py`) se niega ante un estado
  cuyas referencias no resuelven — una interfaz que el router no tiene, una ruta
  de extremo que el túnel no lleva, una reserva para una máquina que nadie declaró
  — antes de que ningún verbo lea o escriba nada. Ver [Comprobar el propio
  marco](#comprobar-el-propio-marco).

Nunca dejes una entrada de invitado comentada como borrador: coméntala *entera* o
bórrala, para que el fichero no guarde media entrada.

### Lo que no se declara aquí

Está deliberadamente fuera del fichero, no olvidado:

- `password` — un secreto de creación; ponerlo en Git es lo único peor que un secreto sin guardar. Inyéctalo desde un vault al crear si alguna vez hace falta.
- `pubkey` — PVE lo aplica sólo al crear, no lo reenvía al actualizar.
- `clone` / `clone_type` — una vía de creación alternativa, sin usar.
- `pool` — no hay pool en este nodo.
- `force`, `purge`, `destroy_unreferenced_disks` — banderas destructivas; el motor nunca las pone.
- claves crudas `lxc.*` (límites de cgroup, bind mounts) — el módulo de la colección no las expone.
- `cpus` (límite de CPU) — el módulo lo mapea a `cpuunits` al crear pero a `cpulimit` al actualizar, así que no puede tener un solo significado; declara `cpuunits`.

## VMs QEMU: los once equipos RouterOS

`pve_vm_defaults` + `pve_chr_defaults` + `pve_vms` declaran las VMs con una
diferencia estructural: **`proxmox_kvm` se niega a actualizar `net`, `scsi`,
`ide`, `sata`, `virtio`, `efidisk0` y `tpmstate0`** — actualizarlos puede
regenerar una MAC o recrear un disco y perder datos. Así que en una VM la red, los
discos y el CD-ROM son propiedades de *creación*, igual que `bios`, `machine`,
`scsihw` y `ostype`: drift en cualquiera de ellas hace que `apply.yml` falle para
esa VM con un mensaje explícito en vez de converger.

Se convergen en sitio: `cores`, `sockets`, `memory`, `cpu`, `vga`, `boot`,
`onboot`, `description`, `tags` y el estado de energía.

**Qué hace que un CHR sea un CHR** (`pve_chr_defaults`, heredado por los once):

| Clave | Valor | Por qué |
| --- | --- | --- |
| `machine` | `pc` | la imagen de RouterOS es de la era i440fx; con `q35` no arranca |
| `bios` | `seabios` | la imagen no trae arranque UEFI |
| `boot` | `order=scsi0` | arranca del disco importado, no del CD-ROM |
| `cloudinit` | `false` | RouterOS no ejecuta cloud-init: la clave no se inyecta así |
| `serial` / `vga` | `serial0: socket` / `serial0` | la consola útil es la serie |
| `scsi0` | `local-zfs:1` + `disk_import` | el disco nace de la imagen del fabricante |
| `cores` / `memory` | 1 / 256 MiB | un equipo de red por función no necesita más |
| `onboot` / `startup` | `true` / `order=2` | arrancan solos y en el escalón 2 |
| `manage` | `true` | capa 2 los configura por su API REST |

| VM | vmid | qué es |
| --- | --- | --- |
| `sw-s1-acc-01`, `sw-s1-acc-02` | 1301, 1302 | switches de acceso de la central |
| `sw-s2-acc-01`, `sw-s3-acc-01` | 2301, 3301 | switches de acceso de cada delegación |
| `rt-s1-core`, `rt-s2-edge`, `rt-s3-edge` | 1201, 2201, 3201 | routers: puerta de la LAN y servidor DHCP |
| `fw-s1-perim`, `fw-s2-perim`, `fw-s3-perim` | 1101, 2101, 3101 | firewalls de perímetro |
| `fw-wan-edge` | 9101 | firewall de borde con NAT |

Ojo con el bridge: `vmbr1` es la LAN interna (`10.10.10.0/24`) compartida con todos
los invitados del laboratorio, mientras que `vmbr0` es el bridge **público**
(`54.36.168.83/24` sobre `eno3`). Poner un invitado del laboratorio en `vmbr0` lo
expone a internet.

`preflight.yml` comprueba además que toda ISO que una VM declare esté realmente en
el nodo antes de crear nada. Una VM que **importa una imagen de fabricante** en vez
de construir un disco a partir de un tamaño es un caso especial: PVE acepta
`import-from` sólo al crear, así que `playbooks/tasks/disk_import.yml` hace crecer
el volumen importado después, y `apply` se niega en voz alta en vez de fingir que
puede adjuntar uno más tarde.

## Capa 2 — configurar el INTERIOR de un invitado

La capa 1 aprovisiona un invitado por la API de Proxmox. Esa API no puede ejecutar
nada dentro de un invitado: `POST /nodes/{node}/lxc/{vmid}/exec` responde **501
Method not implemented**. Así que un Caddyfile, una unidad de systemd o una tarea
programada quedan fuera del alcance de la capa 1 por construcción, y la capa 2
existe justo para esa frontera: llega al invitado por SSH y converge lo que corre
dentro.

La metodología, una línea por regla:

- **Un estado declarado, dos capas.** `inventory/group_vars/all.yml` sigue siendo
  la única fuente de verdad: la capa 1 lee la forma del invitado, la capa 2 lee su
  bloque `config:`. Las direcciones nunca se duplican — la capa 2 deriva el destino
  SSH de la declaración de la interfaz con el filtro `pve_declared_ipv4`, o del
  `address:` propio del invitado cuando su NIC es DHCP.
- **A un invitado se le configura por el protocolo que habla.** Casi todos son
  Linux, así que la capa 2 llega por SSH. Un invitado RouterOS no es un shell
  POSIX — el SSH aterriza en su CLI — así que declara `config.routeros` y se
  converge por su **API REST** con `ansible.builtin.uri`, desde el nodo de
  control, sin SSH. El `kind` del destino (`ssh` o `api`) se deriva del bloque que
  el invitado declara, y cada kind tiene su propio play, porque los dos no pueden
  compartir conexión.
- **Un invitado puede no tener `config:` en absoluto.** Las ocho workstations
  declaran sólo una forma: son PCs cuyo interior nadie configura, así que no son
  destinos de capa 2. Lo que necesitan —una dirección— se lo da el router, y el
  router la declara.
- **Lee antes de escribir.** `configure/audit.yml` inspecciona un invitado y no
  cambia nada. Lánzalo antes de declarar `manage: true` sobre un invitado que ya
  existe.
- **La convergencia es opt-in por invitado.** Un bloque `config:` más
  `manage: true` significa que la capa 2 posee el interior; `manage: false` (o
  ausente) significa sólo auditoría. Un invitado nunca se configura por accidente.
- **Cada capa verifica lo que declara.** La capa 1 vuelve a leer por la API. La capa
  2 valida dentro del invitado (`caddy validate`, `systemctl is-active`, los
  timers) *y* desde fuera (una petición HTTP que comprueba el estado y el cuerpo
  declarados).
- **El acceso tiene un sitio.** La capa 1 inyecta la clave de automatización **al
  nacer** (`pubkey` en `pve_defaults` — PVE la escribe en
  `/root/.ssh/authorized_keys` al crear y nunca la reenvía al actualizar). Para un
  invitado que ya existe, la clave se concede una vez desde la consola de PVE y la
  ejecución te dice el comando exacto, con la clave pública en el mensaje.
- **El camino también.** Una clave autoriza una conexión que ya llegó. Si el nodo de
  control no está conectado a la LAN de invitados, todos parecen inalcanzables y
  ninguna clave ayuda, así que la ruta se declara (`pve_tunnel`) y se converge —
  automáticamente, desde dentro de este mismo verbo, cuando ningún invitado
  responde en el :22.

```bash
ansible-playbook configure/audit.yml   # sólo lectura: qué hay dentro de cada destino
ansible-playbook configure/site.yml    # converge cada invitado declarado manage: true
```

### El camino por el que corre la capa 2

La API de PVE responde en la dirección pública desde cualquier sitio; los invitados
están en un bridge interno. Un nodo de control fuera de ese bridge no alcanza a
**ningún** invitado — lo que parece un fallo de autenticación y en realidad es una
ruta que falta. El marco lo anticipa: `pve_tunnel` declara el camino, y la capa 2
lo converge antes de necesitarlo.

`pve_tunnel` lo describe en el único fichero de estado declarado: nombre de la
interfaz, `endpoint` (`host:port`), la clave **pública** del extremo, la dirección
del túnel en este nodo, el prefijo de invitados que se enruta por él y dónde vive
la clave privada.

El túnel va al **host**, no a cada invitado: un solo par con `AllowedIPs` que cubra las
redes del laboratorio alcanza la **red de gestión** entera, así que un contenedor
creado mañana en ella es alcanzable en cuanto exista y no se configura nada por
invitado. Lo que la hace alcanzable es que el host enruta y hace NAT del subnet del
túnel hacia su bridge.

Una LAN de sede, en cambio, **queda detrás de su router**, y el nodo de control no
tiene ruta hasta ella. Medido en la v2, en vivo: `10.11.0.11` no contesta en el :22 y
por el `infra-bootstrap` como `ProxyJump` **sí**. El salto se escribe desde la
declaración —`configure/tasks/ssh_path.yml` lo deriva del invitado que declara
`config.bootstrap`— como un bloque `Host` por destino, porque `ProxyJump` necesita la
identidad de los DOS saltos y ssh no propaga el `-i` de la línea de comandos al host de
salto: con el bloque, la clave llega a los dos.

Una red que vive **detrás de un router dentro del laboratorio** necesita una cosa
más. El extremo alcanza al router —está en el bridge de invitados— pero no tiene
idea de dónde están las redes que hay detrás, así que sin una ruta el nodo de
control llega al router y nada más allá. `pve_tunnel.endpoint_routes` declara esas
rutas, y `wg_endpoint_setup.sh` las toma como último argumento para que vivan y
mueran con el túnel en vez de ser algo aparte que hay que mantener en sincronía. El
validador de estado se niega ante una ruta que no esté también en `guest_network`:
el extremo la tendría y el nodo de control nunca metería ese tráfico por el túnel.

Una cosa no está automatizada a propósito, y así debe quedarse: el extremo vive en
el host de Proxmox, y la única vía sólo-API para ejecutar código allí sería un
`hookscript` (root en el hipervisor, y los storages de este nodo ni siquiera
ofrecen el tipo de contenido `snippets` que hace falta). La API administra
invitados; no da una puerta trasera a root en el host. Así que el extremo es el
único paste versionado e idempotente que un operador ejecuta por laboratorio.

```bash
ansible-playbook playbooks/connect.yml   # converge el camino por su cuenta
```

`configure/site.yml` ejecuta el mismo fichero de tareas
(`configure/tasks/tunnel.yml`) automáticamente cuando su sonda no encuentra ningún
destino respondiendo en el :22, así que una ejecución normal se auto-repara: detecta
la ruta que falta → levanta la interfaz → espera el handshake → demuestra que la LAN
de invitados responde → converge los invitados. Si el camino ya está, no se toca
nada.

Las claves siguen la convención SSH: la mitad privada es un fichero fuera del
repositorio (generado en la primera ejecución si falta, nunca impreso), sólo viaja
la mitad pública, y `connect.yml` la imprime.

`preflight.yml` informa del camino —`up` o `DOWN`, y cuántos invitados responden en
el :22— sin cambiar nada, así que un problema de capa 2 se ve antes de lanzar el
verbo de configuración.

### Ejemplo trabajado: un servidor Caddy

Lo que el segundo verbo hace por invitado lo decide la declaración. Este es el
formato de un destino de capa 2 por SSH (es la **capacidad** del marco; en la v2
ningún invitado declara Caddy):

```yaml
  - vmid: 121
    hostname: caddy-lab
    cores: 1
    memory: 512
    netif:
      net0: "name=eth0,bridge=vmbr1,gw=10.10.10.1,ip=10.10.10.21/24,ip6=auto"
    manage: true                      # la capa 2 puede converger este invitado
    config:
      caddy:
        sites:
          - address: ":80"
            respond: "hola desde la capa 2 - caddy-lab"
            expect_body: "hola desde la capa 2 - caddy-lab"
          - address: ":8080"
            root: /srv/www
            file_server: true
            index_html: "contenido declarado en group_vars"
            expect_body: "contenido declarado"
        timers:
          - name: caddy-validate
            on_calendar: "daily"
            exec_start: "/usr/bin/caddy validate --config /etc/caddy/Caddyfile"
```

El rol instala Caddy desde el repositorio apt oficial (clave + fuente deb822, sin
`curl | bash`), renderiza el Caddyfile a partir de esos sitios con `validate:` para
que un fichero roto no llegue nunca al servicio en marcha, escribe el contenido
índice declarado, declara los trabajos periódicos como **timers de systemd** en vez
de crontabs, y luego lo demuestra: `caddy validate`, `systemctl is-active`, cada
timer declarado activo, y una sonda HTTP desde el nodo de control que comprueba el
estado y el cuerpo declarados.

Añadir otra aplicación es otro rol bajo `configure/roles/` y otro bloque bajo
`config:` — no otro repositorio, ni un script `curl | bash` que nadie puede diffear.

### Ejemplo trabajado: un servidor TiddlyWiki

Un invitado que declara una instancia de TiddlyWiki (también **capacidad** del
marco, **no** un invitado del laboratorio actual — la v2 no declara ninguno) lleva:

```yaml
    config:
      tiddlywiki:
        wiki_dir: /srv/tiddlywiki
        port: 8080
        version: "5.4.1"
        service_user: tiddlywiki
        listen_host: "0.0.0.0"
      http:
        - address: ":8080"
          expect_status: 200
          expect_body: "TiddlyWiki"
```

`apply` crea el invitado (que nace alcanzable por SSH gracias a `pubkey`), y
`configure/site.yml` instala Node.js, instala el motor con la versión fijada, lanza
`tiddlywiki /srv/tiddlywiki --init server` una vez, declara `tiddlywiki.service`
(`Restart=always`, `enabled`), y luego lo demuestra: el proceso vivo debe ser *esta*
carpeta de wiki en *este* puerto, el invitado debe responder HTTP 200, `anonymous`
y el nodo de control también deben obtener HTTP 200 con el cuerpo declarado. Un rol
se incluye sólo cuando el invitado declara su clave de configuración, así que un
invitado gestionado que no declare un bloque `caddy` nunca recibe Caddy.

Dos decisiones que conviene conocer:

- **El motor se instala desde el tarball oficial de npm, no por el paquete `npm` de
  Debian**, porque `apt install npm` en Debian 13 arrastra ~400 paquetes (la pila
  GTK/X, por sus dependencias de módulos) para un wiki que no necesita ninguno. El
  rol comprueba que el tarball no declare dependencias de ejecución, así que una
  versión futura que las gane falla en voz alta en vez de necesitar un gestor de
  paquetes en silencio.
- **La dirección de escucha se declara, no se pone por defecto.** La edición servidor
  de TiddlyWiki es escribible y sin autenticación, así que `listen_host` es una
  decisión de exposición explícita en el manifiesto y se espera que el invitado esté
  detrás de una red que no sea pública.

### La red de tres sedes, descrita en un solo fichero

El laboratorio declarado ahora es una red de empresa —una sede central y dos
delegaciones— y está ahí para ejercitar el marco con algo que **no** es una lista
plana de invitados idénticos:

```text
SEDE 1 (central)                     SEDE 2                SEDE 3
  pc-s1-01..04                       pc-s2-01/02           pc-s3-01/02
     │        │                          │                      │
  sw-s1-acc-01 ═══ sw-s1-acc-02     sw-s2-acc-01           sw-s3-acc-01
     │                                  │                      │
   rt-s1-core                       rt-s2-edge             rt-s3-edge
     │                                  │                      │
   fw-s1-perim ── WAN 1 ── fw-s2-perim │ ── WAN 2 ── fw-s3-perim
     │
   fw-wan-edge ──▶ internet (NAT)
```

**Once invitados RouterOS y ocho PCs**, todo en `inventory/group_vars/all.yml`:

- **Cuatro switches, y son L2 puros.** Meten sus patas de datos en un bridge de
  RouterOS y **no ponen ninguna dirección en él**. Eso es lo que los hace switches
  y no routers: su dirección vive sólo en su pata de gestión (`ether1` → `vmbr1`).
  Un switch con dirección en su bridge empieza a enrutar, y la topología deja de
  ser la del diagrama sin que nadie se entere.
- **Tres routers** que enrutan *y* sirven: la LAN de su sede en una pata —donde
  corren el **servidor DHCP** y sus reservas— y la WAN en otra. Son la puerta de la
  LAN, no el firewall, porque el DHCP es una difusión de capa 2 y su servidor tiene
  que estar en el mismo segmento que sus clientes. El diseño es **jerárquico** —el
  router de la central conoce las dos redes remotas y los de las delegaciones
  llevan una ruta por defecto a su firewall— así que añadir una cuarta sede es una
  entrada y una ruta, no una malla de ellas.
- **Cuatro firewalls** que filtran el perímetro y no enrutan nada entre sedes. El
  filtrado es **posicional** (el ORDEN de las reglas decide), así que la
  verificación lee la tabla de vuelta y comprueba el orden, no sólo el conjunto. El
  NAT vive sólo en `fw-wan-edge`: dentro de la empresa las direcciones son reales,
  que es por lo que existen las rutas de retorno y no se anida ninguna traducción.
  Y un firewall de sede debe permitir que sus patas **exteriores** hablen entre sí —
  así es como una delegación alcanza el borde, y omitirlo mete el tráfico saliente
  de la delegación directamente en el `drop`.
- **Ocho workstations, cada una un PC**: una sola NIC, **sin interfaz de gestión y
  sin bloque `config:` en absoluto**, así que la capa 2 nunca entra en ellas. Así se
  hace en una empresa: un escritorio tiene una interfaz, toma su dirección por DHCP,
  y la gestión de flota es un agente que llama HACIA FUERA, nunca una conexión
  entrante. Su dirección sale del router de su sede como reserva DHCP atada a su
  MAC, y el `address:` de su entrada **ES** esa reserva — el router la deriva de
  allí, así que las dos no pueden separarse.
- **La verificación no entra en ellas; viene de los routers**, que es como un
  ingeniero de red prueba una red: `/ping`, `/tool/traceroute`, `/ip/arp`,
  `/ip/dhcp-server/lease` y `/interface/bridge/host`. Como segunda vista
  independiente, la API de PVE lee las interfaces del propio contenedor
  (`GET /nodes/<node>/lxc/<id>/interfaces`) — esa es la vista del hipervisor, no una
  vía de gestión dentro del invitado. Se usaron las dos, y coinciden.

El direccionamiento, para que un lector pueda seguir los pings: gestión
`10.10.10.0/24` **en bloques por función** (`.11-.14` switches, `.21-.23` routers,
`.31-.34` firewalls, `.41` el bootstrap — la regla de la v1 "el último octeto es el
vmid" no cabe en cuatro dígitos), las sedes `10.11/10.12/10.13.0.0/24`, el tránsito
`router↔firewall` de cada sede como un `/30` (`10.21`, `10.22`, `10.23.0.0/30`), los
enlaces entre firewalls de sede como `/30`s (`10.99.1.0/30`, `10.99.2.0/30`) y el
tránsito de borde `10.29.0.0/30`. **Dieciocho bridges sin puertos** (`vmbr4`…`vmbr21`),
**uno por cable** — el nombre del bridge aparece literalmente en sus dos extremos, y
el validador de estado se niega ante un nombre citado pero nunca declarado, así que
una errata no puede producir un cable de un solo extremo.

**Un despliegue limpio deja las workstations sin dirección hasta que se reinician.**
Su cliente DHCP corre cuando se crea el contenedor, cuando el servidor DHCP de su
sede todavía no existe, y no reintenta para siempre. Los routers las sirven en
cuanto se convergen, y un reinicio las pone en su sitio — lo cual también es cierto
de los propios routers. El orden que funciona, y el que se midió de verdad, es:
`apply.yml` (crear y encender) → `configure/site.yml` (**equipos de red primero**,
porque las workstations dependen del DHCP de su router) → reiniciar las workstations
→ `configure/site.yml` otra vez (ahora su interior es alcanzable) → `apply.yml` (la
verificación de capa 1 cierra en `failed=0`).

### Lo que la API no puede hacer: la primera dirección de un router

Un CHR recién importado arranca con un cliente DHCP en `ether1` y **sin
dirección**, y como VM no puede tomar una del servidor DHCP del host: la oferta
llega con un checksum UDP sin resolver y el kernel del invitado la descarta. Sin
dirección su API no existe, así que no hay con qué configurarlo.

`infra-bootstrap` (vmid 901) es la máquina que entrega esa única dirección. Vive en
el mismo segmento que la pata de gestión del router y corre dnsmasq atado a esa MAC,
con `ethtool -K eth0 tx off gso off tso off` — sin lo cual su propia oferta llevaría
el mismo checksum roto.

El mismo defecto que bloquea al servidor del host es lo que hace esto determinista:
el router sólo ve esta única oferta, así que no hay carrera entre dos servidores
DHCP. Después de que el router haya tomado la dirección, el contenedor no interviene
nunca más — todo lo demás es REST. Es un bootstrap, no una segunda vía de
configuración.

### Por qué no los installers de community-scripts

Scripts como los de `community-scripts.org` corren en el **host de PVE como root**,
manejan `pct create` y luego `pct exec` dentro del invitado, y su vía de
"actualización" es `apt upgrade` más una descarga de release de GitHub. Son
imperativos sin estado declarado: nada que diffear, nada que verificar, y necesitan
el shell del host que este repositorio evita a propósito. Si alguna vez se usa uno,
que sea una vez a mano y que la capa 2 tome el interior después — nunca los dos a la
vez, o se pelean por los mismos ficheros.

## La clave al nacer, por defecto

Cada invitado que este motor crea nace con la clave de automatización ya puesta, sin
ningún paso manual:

- **Los contenedores** usan el parámetro `pubkey` de LXC en PVE. Es una propiedad de
  *creación*: PVE la escribe en `/root/.ssh/authorized_keys` al crear y el módulo
  nunca la reenvía al actualizar, así que la capa 1 puede ponerla y la capa 2
  (`configure/`) es lo que la verifica desde dentro.
- **Las VMs** no tienen equivalente, así que la misma clave viaja por cloud-init:
  `ciuser` más `sshkeys` y una unidad cloud-init (`<storage>:cloudinit`). Está
  activo por defecto (`pve_vm_defaults.cloudinit: true`) y se apaga por invitado para
  una imagen que no ejecute cloud-init. **Los once CHR lo apagan**
  (`pve_chr_defaults.cloudinit: false`): RouterOS no ejecuta cloud-init y su acceso
  es por la API REST, no por SSH.

La única fuente de la clave es el FICHERO de la clave, no una copia de su texto:
`pve_ssh_pubkey_path` apunta al `.pub` junto a la clave privada que usa
`configure/`, y `pve_defaults.pubkey` es un `lookup('file', ...)` del mismo. Un
invitado se descuelga con `pubkey: ""`.

Verificado de extremo a extremo: un invitado creado por `apply` respondió por SSH
como root al primer intento, con el marcador `# --- BEGIN PVE ---` y la clave de
automatización en `authorized_keys`.

## Rendimiento y cómo iterar rápido

Medido en el nodo de control del laboratorio (un contenedor en el propio host de
PVE, 4 vCPU, sin cuota de CPU):

| Medición | Resultado |
|---|---|
| Llamada a la API de PVE con `python-requests` | **15-80 ms** |
| Todas las lecturas de API de todos los invitados declarados, en **un** proceso Python | **0,34 s** |
| Esas mismas lecturas repartidas en una tarea de Ansible por invitado | ~48 s de puro overhead |
| `ansible --version` (sólo el arranque) | 3,9 s |
| Coste marginal por tarea (medido de 1 a 8 tareas) | ~3 s/tarea + ~9 s fijos |
| `apply` antes de consolidar, sin nada que cambiar | 219 s |
| **`apply` ahora, sin nada que cambiar** | **41 s** |
| **`preflight` ahora** | **30 s** |
| `apply` creando un invitado de principio a fin | 105 s |

Cómo se hizo, sin quitar ni una comprobación: **se eliminaron las fronteras de
ejecución, no la verificación.** Un proceso lector (`tools/pve_read.py`) hace todas
las lecturas de invitados *y* todos los prerrequisitos de plataforma (nodo en línea,
storage activo, plantilla presente, ISO presente) que antes costaban una tarea cada
uno. Una sola pasada de plantillado (macros de `pve_engine.j2`) analiza todos los
invitados, sustituyendo el bucle de `set_fact` por invitado que costaba una
ejecución de módulo por cada uno. Los marcadores del diario y la revisión de git se
mudaron al lector. Las cifras de las dos últimas ejecuciones salieron de la misma
batería de comprobaciones: los prerrequisitos de plataforma, la negativa ante
propiedades de creación, la comparación declarado-vs-vivo y la relectura
independiente de verificación siguen todas ahí.

Una ejecución de módulo de Ansible cuesta segundos aquí, así que **el tiempo de
ejecución es el número de ejecuciones de módulo, no el tamaño del trabajo.** Cada
iteración de un `loop` es una ejecución, y por eso una tarea que recorre cinco
invitados paga cinco veces. Esa es toda la palanca:

- **`apply` es el verbo de iteración.** Lee, aplica y verifica por la API en una sola ejecución.
- **Para iterar sobre UN invitado, `--limit` ya funciona — y es la única ejecución selectiva que sigue siendo honesta.** `ansible-playbook configure/site.yml --limit localhost,rt-s1-core` ejecuta el motor y converge exactamente ese invitado (medido: `rt-s1-core ok=24 changed=0`, mientras los plays de los demás informan `skipping: no hosts matched`). `localhost` es obligatorio, porque es el play que construye el inventario de destinos. Las etiquetas darían la misma comodidad invitando a ejecuciones que se saltan parte de la declaración de un invitado; un `--limit` nombra un invitado, y un invitado se converge entero o no se converge.
- **No vuelvas a ejecutar sólo para demostrar idempotencia.** `apply` ya relee e imprime la comparación declarado-vs-vivo; una segunda ejecución dobla el tiempo de reloj por información que ya tienes. Reserva la repetición para cambios que toquen propiedades de creación o energía.
- **La verificación no es lo que cuesta.** `validate:`, la sonda HTTP externa y el aserto del diario son casi gratis dentro de una tarea. Lo que cuesta es un segundo verbo, y una tarea —o una iteración de bucle— por elemento.

`ansible.cfg` ya lleva `pipelining`, reutilización de conexión SSH
(`ControlMaster`/`ControlPersist`), `forks = 20` y `display_skipped_hosts = False`.
Eso quita sólo el *establecimiento* SSH por tarea; no reduce los ~3 s de overhead de
Ansible/Python por ejecución, que es por lo que menos tareas y más gruesas siguen
siendo la palanca real.

Dos trampas de medición, ambas pisadas de verdad al construir esto:

- **`curl` miente sobre esta API.** Cada petición `curl` a `:8006` tarda un ~3,05 s
  constante de TTFB — con un token válido, con uno malo (401), con `--http1.1` y
  contra la IP pelada — mientras que `python-requests`, que es lo que usa Ansible,
  responde en 15-80 ms. Mide con el mismo cliente que usa el motor antes de concluir
  que la API es lenta.
- **Una ejecución no es "más rápida" si su resultado cambió.** Una mejora de 104 s a
  32 s resultó ser una ejecución que abortó pronto (`failed=1`) porque su invitado
  destino había sido borrado. Una aceleración sólo es una aceleración cuando el
  trabajo hecho y el resultado son idénticos.
- **Un bloque Jinja `{% %}` produce TEXTO, una sola expresión `{{ }}` conserva su
  tipo.** Las variables de tarea construidas con `{% set %}`/`{% for %}` vuelven como
  cadenas, así que `| length` cuenta caracteres y un aserto que compara una lista con
  `0` nunca pasa. Construye *listas* para los asertos desde una expresión `{{ }}` y
  *mensajes* desde los bloques de texto.
- **`for k, v in x | dict2items` está mal.** `dict2items` produce elementos, así que
  eso desestructura los nombres `key`/`value` del propio elemento y `v` se queda en
  la cadena `"value"`. Usa `x.items()`.

## Comprobar el propio marco

Existen **seis** comprobaciones, y cada una responde una pregunta que las otras no
pueden.

**El estado declarado tiene que tener sentido como un todo.** `filter_plugins/state.py`
valida las referencias cruzadas del manifiesto — que una interfaz de RouterOS exista,
que una ruta de extremo esté también en `guest_network`, que una reserva DHCP nombre
una máquina declarada, que un invitado no esté a la vez en `pve_containers` y en
`pve_config_targets` — y `playbooks/tasks/validate_state.yml` hace que AMBOS verbos
fallen por ello, antes de leer o escribir nada.

Esta es la comprobación de más valor, porque la plataforma no detecta una referencia
colgando: **RouterOS acepta una dirección sobre una interfaz que no existe y
simplemente no la crea.** La API responde 200, la ejecución sale verde, y al router le
falta la dirección en silencio. El fallo aparece dos capas más tarde, en una prueba de
conectividad, con la apariencia de un problema de red.

Las comprobaciones viven en un filtro y no dentro de `playbooks/tools/pve_read.py` a
propósito: el lector parsea el manifiesto en CRUDO, así que ve `"{{ lab_bridge_name }}"`
como una cadena literal y todo valor plantillado sería un falso positivo. Ansible
resuelve el Jinja antes de llamar a un filtro.

**¿Sigue siendo convergente?** `framework_check.py invariant` ejecuta un verbo dos
veces y exige que la segunda informa `changed=0` y cubra los mismos anfitriones. Lee
el callback JSON de Ansible en vez del recap humano, porque de una tabla formateada
puedes leer un recuento pero no fiarte de una LISTA de anfitriones — y distinguir "el
invitado se saltó" de "el invitado nunca estuvo en el play" es justo el punto. Usa
`--verb configure/site.yml` para la mitad de cobertura: los plays de `apply` y
`preflight` corren en el nodo de control, así que su recap no puede mostrar los
invitados, y el script lo dice en vez de reclamar una cobertura que no comprobó.

**¿Sigue viendo y reparando una diferencia?** `framework_check.py drill` muta un
invitado fuera de banda por la API de PVE y exige la secuencia completa: preflight
limpio → preflight informa DRIFT → apply lo repara → preflight limpio otra vez.
`changed=0` por sí solo no prueba ninguna de las dos mitades. La mutación es una
`description`, que la declaración vuelve a converger, así que el drill limpia tras de
sí.

**¿El mapa del test coincide con la declaración?** `framework_check.py agree`
comprueba que la lista de destinos que prueba la propia suite es exactamente la que
declara el manifiesto: si alguien añade un invitado y no lo añade a la prueba (o al
revés), falla. Una suite que prueba diecinueve de veinte sale verde y miente.

**¿Los equipos de red sólo tienen lo que la declaración declara?** `framework_check.py
export` lee el `export` de RouterOS de cada equipo y exige que no sobre nada: ni una
regla, ni una dirección, ni un pool que la declaración no declare. Es la mitad que
`apply` no puede ver, porque `apply` sólo escribe lo que declara y nunca se queja de
lo que sobra.

**¿El plan del rol RouterOS sigue haciendo lo que promete?** `framework_check.py plan`
no necesita laboratorio, ni credenciales, ni red: renderiza la plantilla del propio rol
(`plan.j2`) contra la declaración y exige, por equipo, que el plan cree las reglas **en
el orden declarado** sobre un equipo vacío, no proponga nada sobre uno ya convergido,
borre sólo la regla suelta y deje en paz la regla que el equipo creó por su cuenta. El
filtrado es posicional —el orden decide qué se acepta— así que "las reglas correctas"
no basta: tienen que crearse en el orden correcto. Es la comprobación que siempre puede
correr, y es la razón por la que las reglas salen en orden.

**¿La nota sigue diciendo la verdad?** `framework_check.py notas` tampoco necesita
laboratorio. La nota en la interfaz de PVE es HTML y está *generada* desde la
declaración (`pve_notas.py`), así que la comprobación lee las dos y exige que
coincidan: una fila por pata declarada con su bridge y su MAC, el vecino real en cada
cable punto a punto, el segmento de gestión compartido descrito como segmento
compartido en vez de nombrar un vecino de doce, y exactamente las tres etiquetas (quién
lo gestiona, qué es, dónde está). Nada más puede pillar esta clase de error: una nota
que nombra el puerto equivocado sigue siendo HTML perfectamente válido, y sólo se lee
el día que alguien se fía de ella.

**`ansible-lint` sigue en verde.** `.ansible-lint` fuerza las reglas que importan y
deja escrito por qué se saltan las demás. Un linter con hallazgos permanentes te enseña
a ignorarlo, que es peor que no tenerlo. Es un trinquete de convención, no una puerta de
corrección: no ve dentro de un `lookup('template')`, así que no pilla la clase de bug
que de verdad cuesta una ejecución aquí.

```bash
ansible-lint
python3 playbooks/tools/framework_check.py agree
python3 playbooks/tools/framework_check.py export
python3 playbooks/tools/framework_check.py plan
python3 playbooks/tools/framework_check.py notas
python3 playbooks/tools/framework_check.py invariant --verb configure/site.yml
python3 playbooks/tools/framework_check.py drill
```

## Cómo se comporta el motor

Los dos playbooks construyen un spec efectivo por invitado como
`pve_defaults | combine(entrada)`, leen cada invitado y los datos de plataforma en un
solo proceso, y analizan el conjunto entero en una sola pasada de plantillado
(`pve_engine.j2`), así que ya ninguna tarea tiene que correlacionarse con un
resultado de la API por índice.

**preflight.yml** (sólo lectura) comprueba que el nodo está en línea y, por
contenedor, que su storage de rootfs está activo y su plantilla presente; luego
imprime `declarado=… vivo=…`, lo que se escribiría, lo que se borraría, la transición
de energía y cualquier drift de creación, con cada contenedor marcado `IN SYNC` o
`DRIFT`.

**apply.yml** se niega ante drift de creación, crea los contenedores que no existen,
converge sólo los ajustes que de verdad difieren, converge el estado de energía y
luego relee cada contenedor y rederiva la comparación entera desde esa lectura
fresca. Un código de salida de tarea no se acepta como prueba. Los arranques van por
**escalones** (`pve_power_start_timeout`, `pve_power_gap_after`,
`pve_power_ready_timeout`): los equipos de red suben antes que las estaciones, con su
margen entre escalones.

La normalización es la parte sutil (`playbooks/pve_engine.j2`), porque PVE no guarda
los valores tal cual:

| Qué hace PVE | Cómo lo maneja el motor |
| --- | --- |
| reordena `tags` (`probe;manual` → `manual;probe`) | compara las etiquetas como conjunto ordenado |
| añade un salto de línea a `description` | compara recortado |
| reordena las propiedades dentro de un valor `netX`/`mpX` | canonicalizado por `pve_canon_attachments` |
| añade `hwaddr=…` y `type=veth` a un valor `netX` | descarta los dos, o cada ejecución haría PUT para siempre |
| resuelve la forma corta del volumen de un montaje (`local:5` → `local:167/vm-167-disk-0.raw` + `size=5G`) | compara el storage, el tamaño y la ruta del montaje |
| añade un `size=` a un CD-ROM (el tamaño del fichero, p. ej. `size=1666190K` para una ISO de 1,6 GB) | se ignora en adjuntos respaldados por ISO |
| mete la MAC generada de una NIC de VM dentro de la propiedad del modelo (`virtio=BC:24:…`) | compara `model=virtio`, la MAC se ignora |
| informa un contenedor en marcha como `running`, mientras el vocabulario de energía del módulo es `started` | compara la energía en el vocabulario de la API |
| devuelve números donde una plantilla produjo un int | fuerza `string` en los dos lados |

Sin esa normalización el motor informa drift fantasma y deja de ser idempotente.

Sólo las claves con drift se envían en la ruta de actualización:
`community.proxmox.proxmox` hace PUT de todos los parámetros que recibe, no sólo de
los que encontró distintos, así que enviar `disk`/`ostemplate`/`unprivileged` en una
actualización los escribiría a ciegas. `state=present` también exige `node` y
`hostname`, así que esos se envían siempre (hostname sin cambios).

`community.proxmox.proxmox` declara `supports_check_mode=False`: bajo `--check`
Ansible se salta la tarea mutante y no predice nada, así que `apply.yml` falla pronto
bajo check mode en vez de insinuar un dry-run. Usa `preflight.yml` para la vista no
mutante.

`apply.yml` es idempotente: cuando el estado vivo coincide con el declarado no
informa cambios y no cambia ningún `digest` de configuración. Cada ejecución hace una
llamada HTTPS por tarea y por contenedor contra el nodo.

## Registro y observabilidad de la API

Cada ejecución escribe bajo `logs/` (ignorado por git — describe infraestructura real
y este repositorio es público):

**`logs/ansible.log`** — la salida humana completa del play, anexada por Ansible
(`log_path` en `ansible.cfg`). Los resultados de las tareas de API quedan censurados
porque llevan `no_log`.

**`logs/framework-check.log`** — donde `playbooks/tools/framework_check.py` manda la
salida de los verbos que *él* ejecuta. No debe compartir el log humano: ese script
lanza un verbo con el callback JSON, que emite dos o tres órdenes de magnitud más
bytes que la salida humana, y mezclar los dos es cómo `ansible.log` llegó a **78 MB de
los cuales el 99,4% era salida de máquina que nadie lee**. En su propio fichero el
JSON queda en disco para depurar una comprobación fallida, y el log humano sigue
legible.

**`logs/pve-api.jsonl`** — el diario legible por máquina del tráfico que de verdad
cruzó el cable, un objeto JSON por línea:

```json
{"ts": "...", "event": "api_call", "method": "PUT", "url": "https://…/nodes/Proxmox/lxc/1401/config",
 "request_body": {"cores": 1, "delete": "net0", "tags": "ansible-managed;workstation;central", "hostname": "pc-s1-01"},
 "status": 200, "response_body": "{\"data\":null}", "seconds": 0.186, "pid": 2457156}
```

`event` es `run_start` (marca de tiempo, playbook, revisión de git, lista de
invitados), `tracer_armed` (escrito una vez por proceso de módulo — la prueba
por-proceso de que el trazador está vivo), `api_call`, `tracer_error` (un fallo dentro
del trazador, con la excepción), o `run_end`, así que un revisor puede agrupar las
llamadas de una ejecución y atarlas a una revisión de código.

**El trazador se comprueba, no se confía.** Nunca falla en silencio: un fallo de
escritura cae a un warning de módulo y un fallo de armado se registra como
`tracer_error`. Encima de eso, los dos playbooks comparan el tamaño del diario al
principio y al final de la ejecución y **hacen fallar la ejecución** si no creció, así
que un trazador que dejó de funcionar sin avisar no puede dejarte con logs vacíos.
`grep tracer_error logs/pve-api.jsonl` sin resultados es el aspecto de "la
observabilidad funciona".

Cómo se arma: los playbooks ponen `playbooks/tracing` en `PYTHONPATH` y definen
`PVE_HTTP_TRACE`. CPython importa `sitecustomize` de ahí al arrancar el intérprete,
así que el trazador está activo en cada proceso de módulo — los módulos no se tocan.
El envoltorio se sienta en `requests.Session.request`, que es lo que usa proxmoxer.

Lo que deliberadamente nunca registra: cabeceras de petición, así que el token de la
API nunca llega al fichero; los campos del cuerpo cuya nombre parezca un secreto
también se redactan. Verificado grepeando los ficheros buscando el token: cero
ocurrencias.

Cómo leerlo:

```bash
# todas las llamadas de una ejecución, en orden
python3 -c "
import json
for l in open('logs/pve-api.jsonl'):
    r = json.loads(l)
    print(r['ts'], r['event'], r.get('method',''), r.get('status',''), r.get('url','').split('/api2/json')[-1], r.get('request_body',''))"

# sólo las mutaciones, con la respuesta de PVE
grep '"method": "PUT"' logs/pve-api.jsonl | python3 -m json.tool --json-lines

# todo lo que PVE rechazó
grep -E '"status": 4[0-9][0-9]|"status": 5[0-9][0-9]' logs/pve-api.jsonl
```

### Cuánto costó

El diario y el log del play son también la materia prima de un relato **medido** de lo
que costó poner este laboratorio en pie: llamadas a la API por endpoint y por máquina,
ejecuciones de tarea por anfitrión y el tiempo de reloj de cada verbo. Se genera desde
esos registros, nunca escrito a mano — [`ESFUERZO.md`](ESFUERZO.md) más
`playbooks/tools/esfuerzo.py`.

### Retención

Ansible sólo **anexa** a su `log_path` — nunca lo rota — así que `logs/` es el único
directorio de este repositorio que crece solo. Está acotado por una política declarada
en vez de por un operador que se acuerde:

```yaml
pve_log_retention:
  live_max_mb: 8    # un fichero vivo por encima de esto se rota a logs/archive/ y se vacía
  keep_days: 14     # los archivos con más antigüedad se borran
  keep_count: 10    # ...y no se guardan más de estos, los más nuevos primero
```

**Cada verbo la aplica antes de hacer nada**, por `playbooks/tasks/prune_logs.yml`, así
que un laboratorio gobernado sólo por los verbos nunca necesita que nadie se acuerde.
El mismo script corre suelto para el caso contrario — nadie lanza el marco en días:

```bash
python3 playbooks/tools/logs_prune.py --dry-run   # dice qué haría, no cambia nada
python3 playbooks/tools/logs_prune.py             # lo hace
```

Cuatro cosas son deliberadas:

- **Copia al archivo y luego vacía el fichero vivo**, en vez de renombrarlo. Ansible
  mantiene el fichero de log abierto durante toda la ejecución, así que renombrar
  dejaría a Ansible escribiendo en el archivo mientras la ruta viva queda vacía. El
  diario se abre por escritura y toleraría un rename — los dos toman la misma ruta a
  propósito, un solo comportamiento que razonar.
- **El archivo más nuevo nunca se borra**, diga lo que diga `keep_count`: es el fichero
  al que alguien recurriría de verdad, y "guardar cero" no es una política.
- **Sólo borra ficheros que reconoce**, por prefijo contra los tres nombres vivos. Una
  herramienta de retención que borra por comodín en un directorio es cómo alguien
  pierde el único fichero que no era un log.
- **La tarea nunca informa `changed`.** La retención de logs no es convergencia, y la
  garantía central del marco —una ejecución sobre un laboratorio convergido no cambia
  nada— no debe depender de cuántos megabytes escribieron ejecuciones anteriores. Si el
  cambio se informara, la rotación se dispararía sola cada ~96 ejecuciones y la
  comprobación de invariante fallaría sin nada realmente mal, que es precisamente el
  falso positivo que enseña a un operador a ignorar la comprobación. Lo que importa se
  conserva: si el script no puede hacer su trabajo, la tarea falla por su código de
  salida.

La única fealdad, dicha para que nadie tenga que descubrirla: la rotación ocurre
mientras la ejecución en curso ya está anexando, así que la **cabecera del play de la
ejecución en curso aterriza al final del archivo**. Las ejecuciones ya terminadas se
archivan enteras, que es la parte que importa. Para rotar sin ninguna partición, lanza
el script entre ejecuciones.

El tope acota el fichero **entre** ejecuciones, no dentro de una: una ejecución pesada
puede escribir más de `live_max_mb` — un `drill` son cuatro verbos, y uno de ellos
escribe un log JSON de ~16 MB — y lo rota la comprobación del verbo siguiente. El tope
está en el estado estacionario, que es lo que crece sin uno.

El directorio `logs/` debe existir antes de que Ansible arranque (`log_path` no puede
crearlo), y por eso `logs/.gitkeep` está commiteado.

## Credenciales y limpieza

El token inicial del laboratorio se creó para `root@pam` con separación de privilegios
desactivada y sin caducidad, así que tiene privilegios de API equivalentes a root. Es
deliberadamente sobreprivilegiado para un MVP desechable: revócalo y crea un token
acotado antes de cualquier uso continuado. La clave SSH fue sólo para el
descubrimiento/bootstrap inicial; ningún playbook de infraestructura usa SSH.

Para quitar un invitado, **desdecláralo primero y destrúyelo después** — ver [Añadir y
quitar un invitado](#añadir-y-quitar-un-invitado). `ansible-playbook
playbooks/remove.yml -e hostname=<nombre> -e confirm=<nombre>` hace el segundo paso y
se niega mientras el invitado siga declarado. No quites recursos con comandos SSH, y no
destruyas un invitado que el manifiesto aún declara: el siguiente `apply` lo recrearía.
