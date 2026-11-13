<!-- GENERADO por machinery/playbooks/tools/documentos.py desde labs/netlab-v2.yml.
     No editar a mano: edita la plantilla docs/laboratorio.md.j2 y regenera. -->
# El laboratorio: una empresa de tres sedes

Este repositorio despliega un laboratorio de red que simula **una empresa de tres sedes**. No es un dibujo cómodo: está
construido para comportarse como hardware de verdad, y todo lo que hay dentro
—máquinas, cables, direcciones, rutas, reglas de firewall— vive declarado en un
solo fichero.

Todo se gobierna **exclusivamente por la API HTTPS de Proxmox**: ningún playbook
entra por SSH en el hipervisor, y ningún equipo de red se toca por SSH ni por el
puerto binario de RouterOS. Los 12 equipos de red se configuran por su **API
REST**.

---

## La topología

21 invitados. El camino de un paquete dentro de una sede es siempre el mismo:

```
   pc  ──▶  sw  ──▶  rt  ──▶  fw  ──▶  WAN
   │        │        │        │
   │        │        │        └─ el firewall filtra el PERÍMETRO
   │        │        └────────── el router es la PUERTA y el DHCP de su LAN
   │        └─────────────────── el switch sólo conmuta
   └──────────────────────────── el PC recibe su dirección por DHCP
```

```
  LA CENTRAL
    1-Ca-pc-10      workstation vmid 1119110 · gestión 10.11.0.11
    1-Ca-pc-11      workstation vmid 1119111 · gestión 10.11.0.12
    1-Ca-pc-12      workstation vmid 1119112 · gestión 10.11.0.13
    1-Ca-pc-13      workstation vmid 1119113 · gestión 10.11.0.14
    1-Ca-swac-10    switch      vmid 1111110 · gestión 10.10.10.11
    1-Ca-swac-11    switch      vmid 1111111 · gestión 10.10.10.12
    1-Ca-rtco-10    router      vmid 1112110 · gestión 10.10.10.21
    1-Ca-fwpe-10    firewall    vmid 1118110 · gestión 10.10.10.31
  LA DELEGACIÓN 2
    1-Sa-pc-10      workstation vmid 1219110 · gestión 10.12.0.11
    1-Sa-pc-11      workstation vmid 1219111 · gestión 10.12.0.12
    1-Sa-swac-10    switch      vmid 1211110 · gestión 10.10.10.13
    1-Sa-rtbo-10    router      vmid 1212210 · gestión 10.10.10.22
    1-Sa-fwpe-10    firewall    vmid 1218110 · gestión 10.10.10.32
  LA DELEGACIÓN 3
    1-Sb-pc-10      workstation vmid 1229110 · gestión 10.13.0.11
    1-Sb-pc-11      workstation vmid 1229111 · gestión 10.13.0.12
    1-Sb-swac-10    switch      vmid 1221110 · gestión 10.10.10.14
    1-Sb-rtbo-10    router      vmid 1222210 · gestión 10.10.10.23
    1-Sb-fwpe-10    firewall    vmid 1228110 · gestión 10.10.10.33
  SIN SEDE (la red de gestión, su segundo segmento OOB, el borde y la infraestructura)
    1-Ga-swge-10    switch      vmid 1411210 · gestión 10.20.20.11
    1-Ba-fwbo-10    firewall    vmid 1518210 · gestión 10.10.10.34
    1-Ia-boot-10    bootstrap   vmid 1317110 · gestión 10.10.10.41
```

Leído en palabras:

- **En la central** hay 2 switches de acceso unidos por un **troncal** (por eso
  sus 4 PCs comparten una sola red), un router que es la puerta de esa LAN y
  conoce todas las sedes, y **2 firewalls**: el de su sede, que la separa de la
  WAN, y el de **borde**, que es el único que sale a internet.
- **En cada una de las demás sedes** hay un switch (sus PCs), un router (puerta y DHCP de
  su LAN) y un firewall, que es la boca de la sede hacia fuera.
- **Todo el tráfico entre sedes pasa por la central**, y el de una sede
  hacia internet cruza su firewall, la WAN y el firewall de la central antes
  de llegar al de borde.

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

Y hay una razón para que el DHCP lo sirva el router y no el firewall, aunque no es
una ley física sino la consecuencia de **una elección**: el DHCP es un **broadcast
de capa 2** y no cruza un router, así que quien reparte tiene que estar **en el
mismo segmento** que sus clientes —o, si el servidor vive en otro sitio, un
**relay** (`ip helper-address`) que lo reenvíe desde ese segmento—. Este
laboratorio elige el modelo de **rama pequeña**: la puerta de enlace y el servidor
son el mismo equipo, así que la LAN cuelga de su router y el firewall se pone
**después**, de cara a la WAN. Con un servidor central y un relay el firewall
podría ir en medio; también es real, sólo que no es éste. (La v1 tenía el firewall
entre el switch y el router y el DHCP en el firewall: era válido, con el router de
relay. Se cambió por **elegir este modelo**, no porque aquél no pudiera funcionar.)

---

## Qué es cada pieza

La numeración tiene cuatro dígitos y se lee de un vistazo: **`STNN`**, donde `S`
es la sede, `T` el tipo de equipo y `NN` el índice.

| | S = sede | | T = tipo |
|---|---|---|---|
| `0` | infraestructura | `1` | firewall |
| `1` | central | 2 | router |
| `2` | delegacion-2 | 3 | switch |
| `3` | delegacion-3 | 4 | workstation |
| `9` | borde | `9` | servicio |

Así `1301` es "central, switch, el primero" y `1401` "central, workstation, la primera". No hay que consultar nada para saber qué es una máquina y dónde está.

| Máquina | VMID | Tipo | Función | Dirección |
|---|---|---|---|---|
| `1-Ca-pc-10` | 1119110 | LXC | workstation de la central: PC de usuario, sin vía de gestión | `10.11.0.11` |
| `1-Ca-pc-11` | 1119111 | LXC | workstation de la central: PC de usuario, sin vía de gestión | `10.11.0.12` |
| `1-Ca-pc-12` | 1119112 | LXC | workstation de la central: PC de usuario, sin vía de gestión | `10.11.0.13` |
| `1-Ca-pc-13` | 1119113 | LXC | workstation de la central: PC de usuario, sin vía de gestión | `10.11.0.14` |
| `1-Sa-pc-10` | 1219110 | LXC | workstation de la delegación 2: PC de usuario, sin vía de gestión | `10.12.0.11` |
| `1-Sa-pc-11` | 1219111 | LXC | workstation de la delegación 2: PC de usuario, sin vía de gestión | `10.12.0.12` |
| `1-Sb-pc-10` | 1229110 | LXC | workstation de la delegación 3: PC de usuario, sin vía de gestión | `10.13.0.11` |
| `1-Sb-pc-11` | 1229111 | LXC | workstation de la delegación 3: PC de usuario, sin vía de gestión | `10.13.0.12` |
| `1-Ca-swac-10` | 1111110 | CHR | switch de la central | `10.10.10.11` |
| `1-Ca-swac-11` | 1111111 | CHR | switch de la central | `10.10.10.12` |
| `1-Ga-swge-10` | 1411210 | CHR | switch de la red de gestión | `10.20.20.11` |
| `1-Sa-swac-10` | 1211110 | CHR | switch de la delegación 2 | `10.10.10.13` |
| `1-Sb-swac-10` | 1221110 | CHR | switch de la delegación 3 | `10.10.10.14` |
| `1-Ca-rtco-10` | 1112110 | CHR | router de la central | `10.10.10.21` |
| `1-Sa-rtbo-10` | 1212210 | CHR | router de la delegación 2 | `10.10.10.22` |
| `1-Sb-rtbo-10` | 1222210 | CHR | router de la delegación 3 | `10.10.10.23` |
| `1-Ba-fwbo-10` | 1518210 | CHR | **firewall de borde**: el único que sale a internet y el único que hace NAT | `10.10.10.34` |
| `1-Ca-fwpe-10` | 1118110 | CHR | firewall de la central | `10.10.10.31` |
| `1-Sa-fwpe-10` | 1218110 | CHR | firewall de la delegación 2 | `10.10.10.32` |
| `1-Sb-fwpe-10` | 1228110 | CHR | firewall de la delegación 3 | `10.10.10.33` |
| `1-Ia-boot-10` | 1317110 | LXC | bootstrap de la red de gestión | `10.10.10.41` |

Los **12 equipos de red** son **RouterOS CHR** (la versión virtual de RouterOS).
Las **8 workstations** y el bootstrap son **contenedores LXC** de Debian.

---

## El direccionamiento

| Qué | Red | Puerta de enlace |
|---|---|---|
| Red de gestión (patas de administración) | `10.10.10.0/24` | `10.10.10.1` (el host Proxmox) |
| Segundo segmento de gestión (OOB) | `10.20.20.0/24` | `10.20.20.1` (el host Proxmox) |
| LAN de la central | `10.11.0.0/24` | `10.11.0.1` (1-Ca-rtco-10) |
| Tránsito router ↔ su firewall (la central) | `10.21.0.0/30` | router `10.21.0.2` ↔ firewall `10.21.0.1` |
| LAN de la delegación 2 | `10.12.0.0/24` | `10.12.0.1` (1-Sa-rtbo-10) |
| Tránsito router ↔ su firewall (la delegación 2) | `10.22.0.0/30` | router `10.22.0.2` ↔ firewall `10.22.0.1` |
| LAN de la delegación 3 | `10.13.0.0/24` | `10.13.0.1` (1-Sb-rtbo-10) |
| Tránsito router ↔ su firewall (la delegación 3) | `10.23.0.0/30` | router `10.23.0.2` ↔ firewall `10.23.0.1` |
| Enlace WAN la central ↔ la delegación 2 | `10.99.1.0/30` | `1-Ca-fwpe-10` `10.99.1.1` ↔ `1-Sa-fwpe-10` `10.99.1.2` |
| Enlace WAN la central ↔ la delegación 3 | `10.99.2.0/30` | `1-Ca-fwpe-10` `10.99.2.1` ↔ `1-Sb-fwpe-10` `10.99.2.2` |
| Tránsito de borde | `10.29.0.0/30` | `1-Ca-fwpe-10` `10.29.0.1` ↔ `1-Ba-fwbo-10` `10.29.0.2` |

Las direcciones de gestión se asignan **por bloques de función** dentro de
`10.10.10.0/24`, y el bloque de cada función sale de las direcciones
que la declaración ya tiene: `.11-.14` switches, `.21-.23` routers, `.31-.34` firewalls, `.41` infraestructura.
(La regla de la v1 —"el último octeto es el VMID"— no cabe con cuatro dígitos, y
ese `/24` no se puede ampliar sin reconfigurar el host, que no se toca.)

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

Medido, no supuesto: desde `1-Ba-fwbo-10` responde `1.1.1.1`; desde la
LAN de la central y desde las demás sedes se llega a internet; y una
workstation resuelve DNS y abre TCP/443 hacia fuera.

---

## Por dónde va un paquete

Una workstation de la central hablando con una de la delegación 2:
```
  1-Ca-pc-10 ──(10.11.0.1)──▶ 1-Ca-rtco-10 ──(10.21.0.1)──▶ 1-Ca-fwpe-10 ──(10.99.1.2)──▶ 1-Sa-fwpe-10 ──(10.12.0.11)──▶ 1-Sa-pc-10

  La respuesta vuelve por donde vino.
```
Destino: la delegación 2 (10.12.0.0/24), a través del enlace WAN `10.99.1.0/30`.

Y entre dos sedes que no son la central, el paquete **pasa por la central**, que es lo que
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
   CAPA 1 — LA FORMA (API HTTPS de Proxmox)         CAPA 2 — LA CONFIGURACIÓN (dentro de cada invitado)

     los 19 segmentos (un cable cada uno)            RouterOS ← su API REST HTTP
     las 8 workstations                              · puentes y puertos
     los 12 equipos de red                           · direcciones IP
     1-Ia-boot-10                                    · servidores DHCP por sede
                                                     · rutas entre sedes
                                                     · FIREWALL y NAT
     └── declara la FORMA, nunca la toca ────────┘
```

- **La capa 1** crea las máquinas y los cables. No entra en ninguna.
- **La capa 2** entra en los invitados y los configura. En un RouterOS es
  **siempre** por su API REST, con `ansible.builtin.uri`: nada de SSH, nada del
  puerto binario 8728.

Un mismo fichero, `labs/netlab-v2.yml`, declara **todo**.

---

## Cómo se despliega

Un laboratorio **desde cero** necesita este orden, y cada paso existe por una
razón física:

```bash
# 1. la forma: los 21 invitados, y la energía del bootstrap (orden 1) y de los
#    equipos de red (orden 2). Las estaciones NO se encienden todavía: su router
#    aún no sirve DHCP, y una workstation no reintenta — encenderla ahora la
#    dejaría sin dirección hasta reiniciarla a mano. El verbo lo dice, nombra lo
#    que aplaza y termina en rojo POR ESO, no por un desajuste.
ansible-playbook machinery/playbooks/apply.yml

# 2. el bootstrap sirve: es quien da la PRIMERA dirección a los equipos de red
#    (un CHR reintenta su primer DHCP, así que la coge en cuanto sirve).
ansible-playbook machinery/configure/site.yml --limit localhost,infra-bootstrap

# 3. los equipos de red, y con ellos el DHCP de cada sede. Las estaciones se quedan
#    FUERA solas: el verbo pregunta por API si su sede sirve DHCP y no exige alcance
#    a lo que este mismo orden impide que esté en pie. Lo dice al hacerlo, con los
#    nombres, para que no parezca que se ha olvidado de ellas.
ansible-playbook machinery/configure/site.yml

# 4. ya con el DHCP de las sedes en pie, apply enciende las estaciones: piden su
#    dirección y la obtienen a la primera. Y verifica la capa 1 completa, que
#    ahora sí está completa.
ansible-playbook machinery/playbooks/apply.yml

# 5. con las estaciones alcanzables, se configura su interior
ansible-playbook machinery/configure/site.yml
```

El orden y sus verbos se explican en la cabecera de cada uno:
[`machinery/playbooks/apply.yml`](machinery/playbooks/apply.yml) y
[`machinery/configure/site.yml`](machinery/configure/site.yml); aquí sólo se cuenta el orden.

**El alcance no se le exige a quien este orden impide estar en pie.** La capa 2
pregunta lo mismo que la capa 1 —¿sirve ya la sede su DHCP?— y salta a las estaciones
que todavía no pueden existir, diciendo cuáles y por qué. Por eso el paso 3 no
necesita ningún apaño para esquivarlas: lo hace el verbo. Y `lab-check` NO las salta
—su razón de ser es probarlas—, pero su error dice la verdad («su sede todavía no
sirve DHCP», no «concede la clave»), que es la diferencia entre mandar a alguien a
arreglar lo que no está roto y decirle qué falta.

**Por qué el paso 1 no puede terminar en verde.** `apply.yml` converge el estado
declarado o falla, y el estado declarado pide los 21 invitados en pie. Un arranque
en frío que deja 8 estaciones sin encender no ha convergido, así que el verbo
**falla** — pero falla nombrando lo aplazado y el paso que falta, en vez de esperar
300 s a un DHCP que sabe que aún no sirve. Ese rojo es la respuesta correcta a un
paso que todavía no puede completarse.

En un laboratorio ya montado, `machinery/configure/site.yml` o `apply.yml` sobre un estado
convergido **no cambian nada** (`changed=0`), y esa es la garantía central del
repositorio.

> **Un paso que la API no puede dar.** El extremo del túnel de gestión vive en el
> host Proxmox, y la API no puede configurar el host (sería ejecutar código en el
> hipervisor). Se pega **una vez** con `machinery/playbooks/tools/wg_endpoint_setup.sh`,
> pasándole las redes de las sedes como último argumento. Es el único paso manual.

---

## Cómo se verifica

`machinery/playbooks/tools/lab-check.sh` se ejecuta **dentro de cualquiera de las 8
workstations** y comprueba contra todos los demás equipos del laboratorio:

| | Qué comprueba | Dureza |
|---|---|---|
| **alcance** | ¿contesta? | dura |
| **primer salto** | ¿el primer salto es la puerta de enlace que le toca? | dura |
| **camino** | ¿los saltos intermedios son los que predice la topología? | hallazgo |
| **OOB** | ¿**no** llega al segmento de gestión? (la isla no se toca desde aquí) | dura |

El mismo fichero sirve para todas: mira su propia dirección, deduce en qué sede
está y quién debe ser su puerta de enlace.

La prueba **OOB** va al revés que las demás: se espera que **falle**. El segundo
segmento de gestión (`10.20.20.0/24`, donde vive `1-Ga-swge-10`) no es del dominio de
producción —en un montaje físico es una isla con su propio switch y su propio DHCP—,
así que una workstation no debe alcanzarlo. El test lo comprueba desde las estaciones
(que **no** llegan) y desde el operador (que **sí** llega, por el túnel), que es lo
fiel a lo que te encontrarías con hierro.

---

## Lo que se ve en la interfaz de Proxmox

Cada invitado lleva **tres etiquetas y ni una más**: quién lo gestiona (`ansible`), qué
es (`firewall`, `router`, `switch`, `workstation`, `bootstrap`) y dónde está
(`Ca`, `Sa`, `Sb`, `Ia`, `Ga`, `Ba`). Nada de vocabulario que no responda a una de
esas tres preguntas.

De qué laboratorio es un invitado **no se pregunta por etiqueta**: lo dice su Resource
Pool, `lab-netlab-v2` en el árbol de Proxmox, que tiene dentro exactamente los
invitados que la declaración declara y deja fuera a los del host
([ADR 0008](docs/decisiones/0008-pool-por-laboratorio.md)). Un invitado del laboratorio
que se quede fuera de su pool es un invitado huérfano: `apply` lo devuelve a su sitio y
`guests` denuncia lo que esté dentro sin que ningún laboratorio lo declare.

Esas etiquetas están **coloreadas en el datacenter** (opción `tag-style`, declarada en
`pve_tag_style` y convergida por `apply.yml`). El color dice dos cosas sin abrir nada: el
**rojo** es "gestionado por este repositorio", y el resto agrupa por función y por sede.
PVE guarda las etiquetas ordenadas alfabéticamente; el motor compara **conjuntos
ordenados**, así que el orden en que se declaren no produce deriva.

La **nota** de cada máquina no es un adorno: es HTML y se **deriva** de la propia
declaración (`machinery/filter_plugins/notas.py`, con el generador de
`machinery/playbooks/tools/pve_notas.py`) en el momento de desplegarla; **no está guardada en el
manifiesto**, porque una copia guardada es una caché dentro de la fuente de verdad y un
día se queda vieja sin decirlo. Lleva la tabla de conexiones (qué pata
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
`machinery/playbooks/tools/esfuerzo.py` a partir de esos dos registros, así que se puede
volver a generar y auditar cuando haga falta.

## Lo que este laboratorio NO es

- **El contenedor `1-Ia-boot-10` no es un equipo de la empresa simulada.** Es
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
`remove`, `machinery/configure/site`— compara lo declarado con lo que hay en la plataforma y
aplica **sólo la diferencia**; si no hay diferencia, no toca nada y lo dice.
