# El laboratorio: una empresa de tres sedes

Este repositorio despliega un laboratorio de red que simula **una empresa
pequeña con una central y dos delegaciones**. No es un dibujo cómodo: está
construido para comportarse como hardware de verdad, y todo lo que hay dentro
—máquinas, cables, direcciones, rutas, reglas de firewall— vive declarado en un
solo fichero.

Todo se gobierna **exclusivamente por la API HTTPS de Proxmox**: ningún playbook
entra por SSH en el hipervisor, y ningún equipo de red se toca por SSH ni por el
puerto binario de RouterOS. Los once equipos de red se configuran por su **API
REST**.

---

## La topología

Veinte invitados. El camino de un paquete dentro de una sede es siempre el mismo:

```
   pc  ──▶  sw  ──▶  rt  ──▶  fw  ──▶  WAN
   │        │        │        │
   │        │        │        └─ el firewall filtra el PERÍMETRO
   │        │        └────────── el router es la PUERTA y el DHCP de su LAN
   │        └─────────────────── el switch sólo conmuta
   └──────────────────────────── el PC recibe su dirección por DHCP
```

```
        SEDE 1 — LA CENTRAL                    SEDE 2                 SEDE 3
   ┌──────────────────────────────────┐   ┌───────────────┐    ┌───────────────┐
   │  pc-s1-01..04  (cuatro PCs)      │   │  pc-s2-01/02  │    │  pc-s3-01/02  │
   │       │      │                   │   │      │        │    │       │       │
   │  sw-s1-acc-01 ═══ sw-s1-acc-02   │   │ sw-s2-acc-01  │    │ sw-s3-acc-01  │
   │       │        (troncal)         │   │      │        │    │       │       │
   │       └──────────┬───────────────│   │      │        │    │       │       │
   │             rt-s1-core           │   │  rt-s2-edge   │    │  rt-s3-edge   │
   │                  │               │   │      │        │    │       │       │
   │             fw-s1-perim ─────────┼───┼─ fw-s2-perim  │    │  fw-s3-perim  │
   │                  │               │   │               │    │       │       │
   │             fw-wan-edge ────▶ internet                │    │       │       │
   └──────────────────────────────────┘   └───────────────┘    └───────────────┘
                                        ╰── WAN 1 ──╯  ╰───── WAN 2 ─────╯
```

Leído en palabras:

- **En la central** hay dos switches de acceso unidos por un **troncal** (por eso
  sus cuatro PCs comparten una sola red), un router que es la puerta de esa LAN y
  conoce las tres sedes, y **dos firewalls**: el de su sede, que la separa de la
  WAN, y el de **borde**, que es el único que sale a internet.
- **En cada delegación** hay un switch (sus dos PCs), un router (puerta y DHCP de
  su LAN) y un firewall, que es la boca de la sede hacia fuera.
- **Todo el tráfico entre sedes pasa por la central**, y el de una delegación
  hacia internet cruza su firewall, la WAN y el firewall de la central antes de
  llegar al de borde.

---

## Por qué cada función es una máquina distinta

En la v1, cada sede tenía un router que lo hacía todo. Aquí **conmutar, enrutar y
filtrar son tres equipos**, y no es un capricho: es lo que hace que cada máquina
tenga una responsabilidad que se puede leer en su nombre.

| Función | Quién la ejerce | Qué NO hace |
|---|---|---|
| **Conmutar** (capa 2) | los switches (`sw-s*`) | no enruta, no filtra, no da DHCP |
| **Enrutar** dentro de la empresa | los routers (`rt-s*`) | no filtra |
| **Filtrar** el perímetro | los firewalls (`fw-*`) | no enruta entre sedes |

Y hay una razón **física** para que el DHCP lo sirva el router y no el firewall:
el DHCP es un **broadcast de capa 2**, así que quien reparte las direcciones tiene
que estar **en el mismo segmento** que sus clientes. Un firewall de capa 3 en
medio rompería el DHCP. Por eso la LAN de cada sede cuelga de su router y el
firewall se pone **después**, de cara a la WAN. (La v1 tenía el firewall entre el
switch y el router y el DHCP en el firewall; se corrigió por esto.)

---

## Qué es cada pieza

La numeración tiene cuatro dígitos y se lee de un vistazo: **`STNN`**, donde `S`
es la sede, `T` el tipo de equipo y `NN` el índice.

| | S = sede | | T = tipo |
|---|---|---|---|
| `0` | infraestructura | `1` | firewall |
| `1` | central | `2` | router |
| `2` | delegación 2 | `3` | switch |
| `3` | delegación 3 | `4` | workstation |
| `9` | borde | `9` | servicio |

Así `1301` es "sede 1, switch, el primero" y `1401` "sede 1, workstation, la
primera". No hay que consultar nada para saber qué es una máquina y dónde está.

| Máquina | VMID | Qué es | Gestión |
|---|---|---|---|
| `sw-s1-acc-01` / `-02` | 1301 / 1302 | los dos switches de acceso de la central (unidos por troncal) | `10.10.10.11` / `.12` |
| `sw-s2-acc-01` | 2301 | switch de la delegación 2 | `10.10.10.13` |
| `sw-s3-acc-01` | 3301 | switch de la delegación 3 | `10.10.10.14` |
| `rt-s1-core` | 1201 | router de la central; conoce las tres sedes | `10.10.10.21` |
| `rt-s2-edge` | 2201 | router de la delegación 2 | `10.10.10.22` |
| `rt-s3-edge` | 3201 | router de la delegación 3 | `10.10.10.23` |
| `fw-s1-perim` | 1101 | perímetro de la central (3 bocas: WAN 1, WAN 2, borde) | `10.10.10.31` |
| `fw-s2-perim` | 2101 | perímetro de la delegación 2 | `10.10.10.32` |
| `fw-s3-perim` | 3101 | perímetro de la delegación 3 | `10.10.10.33` |
| `fw-wan-edge` | 9101 | **firewall de borde**: el único que sale a internet, y el único que hace NAT | `10.10.10.34` |
| `pc-s1-01`…`04` | 1401-1404 | las cuatro workstations de la central | `10.11.0.11`…`.14` |
| `pc-s2-01/02` | 2401 / 2402 | las dos de la delegación 2 | `10.12.0.11`, `.12` |
| `pc-s3-01/02` | 3401 / 3402 | las dos de la delegación 3 | `10.13.0.11`, `.12` |
| `infra-bootstrap` | 901 | herramienta de despliegue: da su primera dirección a los equipos de red | `10.10.10.41` |

Los **once equipos de red** son **RouterOS CHR** (la versión virtual de RouterOS).
Las **ocho workstations** y el bootstrap son **contenedores LXC** de Debian.

---

## El direccionamiento

| Qué | Red | Puerta de enlace |
|---|---|---|
| Red de gestión (patas de administración) | `10.10.10.0/24` | `10.10.10.1` (el host Proxmox) |
| LAN de la central | `10.11.0.0/24` | `10.11.0.1` (rt-s1-core) |
| LAN de la delegación 2 | `10.12.0.0/24` | `10.12.0.1` (rt-s2-edge) |
| LAN de la delegación 3 | `10.13.0.0/24` | `10.13.0.1` (rt-s3-edge) |
| Tránsito router ↔ su firewall | `10.21/22/23.0.0/30` | router `.2` ↔ firewall `.1` |
| Enlace WAN central ↔ delegación 2 | `10.99.1.0/30` | fw-s1 `.1` ↔ fw-s2 `.2` |
| Enlace WAN central ↔ delegación 3 | `10.99.2.0/30` | fw-s1 `.1` ↔ fw-s3 `.2` |
| Tránsito de borde | `10.29.0.0/30` | fw-s1 `.1` ↔ fw-wan-edge `.2` |

Las direcciones de gestión se asignan **por bloques de función** dentro de
`10.10.10.0/24`: `.11-.19` switches, `.21-.29` routers, `.31-.39` firewalls,
`.41-.49` infraestructura. (La regla de la v1 —"el último octeto es el VMID"— no
cabe con cuatro dígitos, y ese `/24` no se puede ampliar sin reconfigurar el
host, que no se toca.)

Las workstations **no tienen dirección fija**: se la da por DHCP el **router de su
sede**, con una reserva atada a su MAC. La reserva no se escribe dos veces: el
router la **deriva** de la declaración de la propia workstation.

---

## La salida a internet

Este laboratorio **sí sale a internet**, y hay que decir cómo para que no parezca
magia:

- **El proveedor es el host Proxmox.** Es el único que tiene salida real, y vive
  en la red de gestión (`10.10.10.1`). No se inventa un segmento "ISP".
- **El firewall de borde** tiene su pata exterior ahí mismo y hace **NAT
  (masquerade)** para toda la empresa. Su ruta por defecto apunta al host.
- **Ningún invitado va en `vmbr0`** (el bridge público del nodo): la salida va por
  la red de gestión, así que **ninguna máquina del laboratorio queda expuesta** a
  internet directamente.
- **El NAT vive sólo en el borde.** Los firewalls de sede filtran pero no
  traducen: dentro de la empresa las direcciones son las reales, y por eso existen
  las rutas de vuelta y no hay traducciones anidadas.

Medido, no supuesto: desde `fw-wan-edge` responden `1.1.1.1` y `8.8.8.8`; desde la
LAN de la central y desde las dos delegaciones se llega a internet; y una
workstation resuelve DNS y abre TCP/443 hacia fuera.

---

## Por dónde va un paquete

Una workstation de la central hablando con una de la delegación 2:

```
  pc-s1-01          rt-s1-core          fw-s1-perim        fw-s2-perim       pc-s2-01
     │                  │                    │                 │                │
     │── 10.11.0.1 ────▶│                    │                 │                │
     │                  │── 10.21.0.1 ──────▶│                 │                │
     │                  │                    │── 10.99.1.2 ───▶│                │
     │                  │                    │                 │─ 10.12.0.11 ──▶│
     │◀────────────────── la respuesta vuelve por donde vino ─────────────────────│
```

Y entre las dos delegaciones, el paquete **pasa por la central**, que es lo que
dice la topología. Ese detalle es una señal de que esto es hardware real: **el
salto intermedio lo anuncia la interfaz del equipo que RECIBE el paquete**, no la
del que lo envía.

---

## Qué hace que esto se comporte como hardware de verdad

**1. Las workstations son PCs, no contenedores con una pata de gestión.** Cada
una tiene **una sola interfaz** —el cable RJ45— y **ninguna vía de gestión**. Es
como se hace en una empresa: un PC toma su dirección por DHCP y la gestión de
parque es un agente que **sale** hacia fuera, nunca una conexión entrante.

**2. Los switches son switches por su configuración, no por su nombre.** Ponen
sus patas de datos en un puente de RouterOS y **no le ponen dirección**. Eso es lo
que los distingue de un router: su dirección vive sólo en su pata de gestión. Un
switch con dirección en el puente empieza a enrutar y la topología deja de ser la
del dibujo **sin que nada falle** — el peor tipo de error, porque no se nota.

**3. Los switches llevan puerta de enlace de gestión.** Sin ella reciben los pings
de su sede y **no pueden contestarlos**: su tabla de rutas sólo conocería la red de
gestión y no sabría volver.

**4. La red se prueba desde dentro, como lo haría un ingeniero.** La verificación
sale de los propios equipos (ping, rutas, concesiones DHCP, reglas del firewall),
no de una vía de gestión metida en las workstations.

---

## Las dos capas

```
   CAPA 1 — LA FORMA                          CAPA 2 — LA CONFIGURACIÓN
   (API HTTPS de Proxmox)                     (dentro de cada invitado)

     los 18 segmentos (un cable cada uno)       RouterOS ← su API REST HTTP
     las 8 workstations                                · puentes y puertos
     los 11 equipos de red                             · direcciones IP
     infra-bootstrap                                   · servidores DHCP por sede
        │                                               · rutas entre sedes
        │                                               · FIREWALL y NAT
        └── declara la FORMA, nunca la toca ────────┘
```

- **La capa 1** crea las máquinas y los cables. No entra en ninguna.
- **La capa 2** entra en los invitados y los configura. En un RouterOS es
  **siempre** por su API REST, con `ansible.builtin.uri`: nada de SSH, nada del
  puerto binario 8728.

Un mismo fichero, `inventory/group_vars/all.yml`, declara **todo**.

---

## Cómo se despliega

Un laboratorio **desde cero** necesita este orden, y cada paso existe por una
razón física:

```bash
# 1. la forma: segmentos, workstations y equipos de red. Arranca por escalones
#    (bootstrap -> equipos de red -> workstations).
ansible-playbook playbooks/apply.yml

# 2. la configuración de los equipos de red (equipos de red PRIMERO: el DHCP de
#    una LAN lo sirve su router, así que las estaciones dependen de ellos).
ansible-playbook configure/site.yml

# 3. reiniciar las estaciones: se crearon antes de que su router sirviera DHCP,
#    así que su cliente se rindió. Con el router ya repartiendo, vuelven a pedir
#    su dirección y la obtienen.

# 4. ya con las estaciones alcanzables, se configura su interior
ansible-playbook configure/site.yml

# 5. y se cierra con la verificación de capa 1
ansible-playbook playbooks/apply.yml
```

En un laboratorio ya montado, `configure/site.yml` o `apply.yml` sobre un estado
convergido **no cambian nada** (`changed=0`), y esa es la garantía central del
repositorio.

> **Un paso que la API no puede dar.** El extremo del túnel de gestión vive en el
> host Proxmox, y la API no puede configurar el host (sería ejecutar código en el
> hipervisor). Se pega **una vez** con `playbooks/tools/wg_endpoint_setup.sh`,
> pasándole las redes de las sedes como último argumento. Es el único paso manual.

---

## Cómo se verifica

`playbooks/tools/lab-check.sh` se ejecuta **dentro de cualquiera de las ocho
workstations** y comprueba contra todos los demás equipos del laboratorio:

| | Qué comprueba | Dureza |
|---|---|---|
| **alcance** | ¿contesta? | dura |
| **primer salto** | ¿el primer salto es la puerta de enlace que le toca? | dura |
| **camino** | ¿los saltos intermedios son los que predice la topología? | hallazgo |

El mismo fichero sirve para las ocho: mira su propia dirección, deduce en qué sede
está y quién debe ser su puerta de enlace.

---

## Lo que se ve en la interfaz de Proxmox

Cada invitado lleva **tres etiquetas y ni una más**: quién lo gestiona (`ansible-managed`),
qué es (`firewall`, `router`, `switch`, `workstation`, `bootstrap`) y dónde está
(`central`, `delegacion`, `borde`, `infra`). Nada de vocabulario que no responda a una
de esas tres preguntas.

Esas etiquetas están **coloreadas en el datacenter** (opción `tag-style`, declarada en
`pve_tag_style` y convergida por `apply.yml`). El color dice dos cosas sin abrir nada: el
**rojo** es "gestionado por este repositorio", y el resto agrupa por función y por sede.
PVE guarda las etiquetas ordenadas alfabéticamente; el motor compara **conjuntos
ordenados**, así que el orden en que se declaren no produce deriva.

La **nota** de cada máquina no es un adorno: es HTML y se **genera desde la propia
declaración** con `playbooks/tools/pve_notas.py`. Lleva la tabla de conexiones (qué pata
va a qué bridge y con quién la comparte, incluidas las MAC), el direccionamiento, el
bloque RouterOS ya con sus referencias resueltas, el camino real hasta internet y **por
qué** cada pieza es como es. Como sale del manifiesto, no puede contradecirlo: si un día
la nota dijera otro puerto que la declaración, sería el generador el que estaría roto.

---

## Cuánto costó ponerlo en pie

Los dos registros que el motor escribe mientras trabaja —el **diario** de llamadas
HTTP y el **log** de Ansible— permiten contar el trabajo con números en vez de con
impresiones: cuántas llamadas se hicieron a cada API, por equipo y por endpoint,
cuántas tareas se ejecutaron en cada anfitrión y cuánto tardó cada verbo.

**[`ESFUERZO.md`](ESFUERZO.md)** tiene las tablas. No está escrito a mano: lo genera
`playbooks/tools/esfuerzo.py` a partir de esos dos registros, así que se puede
volver a generar y auditar cuando haga falta.

## Lo que este laboratorio NO es

- **El contenedor `infra-bootstrap` no es un equipo de la empresa simulada.** Es
  la herramienta que da a cada equipo de red su primera dirección, en la única
  ocasión en que no tiene ninguna (la petición DHCP de un RouterOS recién nacido
  es una difusión, y una difusión no cruza un enlace punto a punto). Una vez cada
  equipo la tiene, no interviene más.
- **No hay un segmento "ISP" simulado**: el proveedor es el host real, y la
  salida va por la red de gestión.
- **Los invitados que la v1 adoptaba no se recrean.** Quedan fuera de la
  declaración a propósito; la convergencia nunca borra, así que siguen corriendo
  hasta que alguien los retire a mano.

---

## Lo que hace el motor, en una frase

Declaras el estado deseado una vez. Cada verbo —`preflight`, `apply`, `connect`,
`remove`, `configure/site`— compara lo declarado con lo que hay en la plataforma y
aplica **sólo la diferencia**; si no hay diferencia, no toca nada y lo dice.
