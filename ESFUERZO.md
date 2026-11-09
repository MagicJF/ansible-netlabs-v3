# Cuánto trabajo costó poner el laboratorio en pie

> Este documento **no está escrito a mano**: lo genera
> `playbooks/tools/esfuerzo.py` contando los registros que el propio motor
> escribe mientras trabaja. Volver a generarlo es un comando, así que las
> cifras se pueden auditar y refrescar en cualquier momento:
>
> ```bash
> python3 playbooks/tools/esfuerzo.py
> ```

Las cifras son de la puesta en marcha del laboratorio v2 (2026-11-08).

## De dónde salen los números

| Registro | Qué guarda | Para qué sirve aquí |
| --- | --- | --- |
| `logs/pve-api.jsonl` | cada llamada HTTP que pasa por `requests`, con método, ruta, estado y **segundos** | **Proxmox**: la capa 1 va por proxmoxer y queda entera |
| `logs/ansible.log` | cada resultado de tarea, por anfitrión, con marca de tiempo | **RouterOS** y **trabajo**: el rol imprime su plan y sus lecturas |

**Por qué no sale todo del trazador.** El trazador se engancha a
`requests.Session.request`, y el rol RouterOS habla por `ansible.builtin.uri`,
que va por `urllib`. Así que el diario tiene **toda** la capa 1 y **ninguna**
llamada del rol. No es un fallo del rol: es el alcance de la herramienta, y por
eso el lado RouterOS se cuenta del log, donde el rol imprime cada llamada que
hace (`Report the plan, call by call`) y cada tabla que lee.

## Resumen

- **23 verbos** ejecutados, con **4.510 ejecuciones de tarea** repartidas entre
  **21 anfitriones**.
- **1.757 llamadas al API de Proxmox** medidas con el trazador, que suman
  **10.7 minutos** de espera dentro de la API.
- **1.578 llamadas al API de RouterOS** contadas en el log: 1.352 de lectura y 226 de
  escritura. Los once equipos se gobiernan por REST, sin SSH.
- **5 convergencias completas** del laboratorio, más los verbos de capa 1.
- Tiempo de reloj de todos los verbos: **49.2 minutos**.

## Los verbos, uno a uno

| # | inicio | dur. | verbo | anfitriones | llamadas PVE | RouterOS | ok | chg | fail |
| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 19:38:47 | 12 s | capa 1: preflight | 1 | 78 | 0 | 18 | 0 | 0 |
| 2 | 19:39:02 | 88 s | capa 1: apply | 1 | 23 | 0 | 27 | 1 | 0 |
| 3 | 20:15:12 | 12 s | capa 1: preflight | 1 | 533 | 0 | 18 | 0 | 0 |
| 4 | 20:16:20 | 669 s | capa 1: apply | 1 | 14 | 0 | 30 | 5 | 1 |
| 5 | 20:35:27 | 23 s | remove (baja deliberada) | 1 | 14 | 0 | 21 | 1 | 0 |
| 6 | 20:35:51 | 23 s | remove (baja deliberada) | 1 | 14 | 0 | 21 | 1 | 0 |
| 7 | 20:36:15 | 23 s | remove (baja deliberada) | 1 | 13 | 0 | 21 | 1 | 0 |
| 8 | 20:36:38 | 22 s | remove (baja deliberada) | 1 | 6 | 0 | 21 | 1 | 0 |
| 9 | 20:37:00 | 14 s | remove (baja deliberada) | 1 | 15 | 0 | 21 | 1 | 0 |
| 10 | 20:37:15 | 24 s | remove (baja deliberada) | 1 | 0 | 0 | 21 | 1 | 0 |
| 11 | 20:38:02 | 2 s | sin nombre | 1 | 36 | 0 | 21 | 1 | 0 |
| 12 | 20:40:27 | 10 s | capa 1: apply | 1 | 0 | 0 | 10 | 0 | 1 |
| 13 | 20:46:44 | 0 s | sin nombre | 1 | 0 | 0 | 23 | 3 | 1 |
| 14 | 20:48:34 | 17 s | sin nombre | 2 | 0 | 0 | 39 | 8 | 1 |
| 15 | 20:49:05 | 133 s | configure: converge contenedores | 3 | 0 | 0 | 44 | 2 | 1 |
| 16 | 20:51:39 | 354 s | configure: converge RouterOS | 14 | 0 | 476 | 338 | 11 | 1 |
| 17 | 21:07:10 | 192 s | configure: converge RouterOS | 9 | 0 | 212 | 215 | 1 | 1 |
| 18 | 21:10:57 | 414 s | configure: converge RouterOS | 21 | 43 | 301 | 378 | 9 | 0 |
| 19 | 21:18:26 | 12 s | capa 1: apply | 1 | 121 | 0 | 10 | 0 | 1 |
| 20 | 21:19:29 | 48 s | capa 1: apply | 1 | 0 | 0 | 28 | 1 | 0 |
| 21 | 21:29:09 | 428 s | configure: converge RouterOS | 21 | 0 | 303 | 378 | 1 | 0 |
| 22 | 21:38:56 | 0 s | Layer 2 - build the target invento | 1 | 0 | 0 | 0 | 0 | 1 |
| 23 | 21:39:35 | 430 s | configure: converge RouterOS | 21 | 0 | 286 | 376 | 0 | 0 |

## API de Proxmox

### Por invitado

| invitado | tipo | llamadas | segundos |
| --- | --- | ---: | ---: |
| `fw-s1-perim` | CHR | 20 | 11.0 |
| `fw-s2-perim` | CHR | 20 | 10.9 |
| `fw-s3-perim` | CHR | 20 | 10.9 |
| `fw-wan-edge` | CHR | 20 | 11.2 |
| `rt-s2-edge` | CHR | 20 | 11.4 |
| `rt-s3-edge` | CHR | 20 | 10.9 |
| `sw-s1-acc-01` | CHR | 19 | 16.4 |
| `sw-s2-acc-01` | CHR | 19 | 13.3 |
| `sw-s3-acc-01` | CHR | 19 | 13.4 |
| `rt-s1-core` | CHR | 19 | 14.0 |
| `sw-s1-acc-02` | CHR | 17 | 10.3 |
| `infra-bootstrap` | LXC | 14 | 15.1 |
| `pc-s1-01` | LXC | 13 | 3.0 |
| `pc-s1-02` | LXC | 13 | 3.0 |
| `pc-s1-03` | LXC | 13 | 3.4 |
| `pc-s1-04` | LXC | 13 | 3.0 |
| `pc-s2-01` | LXC | 13 | 3.0 |
| `pc-s2-02` | LXC | 13 | 3.1 |
| `pc-s3-01` | LXC | 13 | 3.0 |
| `pc-s3-02` | LXC | 13 | 3.0 |
| `167` | - | 6 | 1.3 |
| `131` | - | 6 | 1.3 |
| `150` | - | 6 | 1.3 |
| `151` | - | 6 | 1.3 |
| `152` | - | 6 | 1.3 |
| `153` | - | 6 | 1.3 |
| `154` | - | 6 | 1.3 |
| `155` | - | 6 | 1.3 |
| `156` | - | 6 | 1.3 |
| `157` | - | 6 | 1.3 |
| `143` | - | 6 | 1.3 |
| `160` | - | 6 | 1.1 |
| `161` | - | 6 | 1.1 |
| `162` | - | 6 | 1.1 |
| `163` | - | 6 | 1.1 |
| `164` | - | 6 | 1.1 |
| `165` | - | 6 | 1.1 |
| `166` | - | 6 | 1.1 |
| **total** | | **439** | **195.2** |

### Por endpoint

| endpoint | llamadas | segundos |
| --- | ---: | ---: |
| `config` | 243 | 53.4 |
| `status/current` | 190 | 139.8 |
| `status/shutdown` | 6 | 1.9 |

### Sin invitado: el motor y el nodo

| endpoint | llamadas | segundos |
| --- | ---: | ---: |
| `/api2/json/nodes/Proxmox/tasks/UPID:<id>` | 355 | 85.4 |
| `/api2/json/version` | 128 | 15.9 |
| `/api2/json/nodes` | 39 | 4.1 |
| `/api2/json/cluster/resources` | 34 | 2.6 |
| `/api2/json/nodes/Proxmox/qemu` | 18 | 4.3 |
| `/api2/json/nodes/Proxmox/storage` | 10 | 3.2 |
| `/api2/json/nodes/Proxmox/storage/local/content?content=vztmpl` | 10 | 3.0 |
| `/api2/json/nodes/Proxmox/storage/local/content` | 9 | 6.9 |
| `/api2/json/nodes/Proxmox/lxc` | 9 | 3.1 |
| `/api2/json/nodes/Proxmox/startall` | 5 | 1.7 |
| `/api2/json/nodes/Proxmox/qemu/1101` | 1 | 0.3 |
| `/api2/json/nodes/Proxmox/qemu/2101` | 1 | 0.3 |
| `/api2/json/nodes/Proxmox/qemu/3101` | 1 | 0.3 |
| `/api2/json/nodes/Proxmox/qemu/9101` | 1 | 0.3 |
| `/api2/json/nodes/Proxmox/qemu/1201` | 1 | 0.3 |
| `/api2/json/nodes/Proxmox/qemu/2201` | 1 | 0.3 |
| `/api2/json/nodes/Proxmox/qemu/3201` | 1 | 0.3 |

## API de RouterOS

Los once equipos de red se gobiernan **solo** por su API REST (HTTP en el
puerto 80). Cada convergencia lee cada tabla declarada y escribe únicamente lo
que difiere, así que el grueso son lecturas y las escrituras son la excepción —
que es exactamente lo que debe pasar cuando el estado ya es el declarado.

### Por equipo

| equipo | lecturas | escrituras | total | tiempo en convergir | elementos declarados |
| --- | ---: | ---: | ---: | ---: | ---: |
| `fw-s1-perim` | 130 | 63 | 193 | 91 s | 27 |
| `rt-s1-core` | 130 | 20 | 150 | 70 s | 8 |
| `rt-s3-edge` | 130 | 16 | 146 | 67 s | 6 |
| `rt-s2-edge` | 130 | 16 | 146 | 67 s | 6 |
| `sw-s1-acc-01` | 130 | 13 | 143 | 67 s | 7 |
| `sw-s2-acc-01` | 130 | 12 | 142 | 70 s | 6 |
| `sw-s1-acc-02` | 130 | 12 | 142 | 66 s | 6 |
| `sw-s3-acc-01` | 130 | 12 | 142 | 69 s | 6 |
| `fw-s3-perim` | 104 | 21 | 125 | 61 s | 15 |
| `fw-s2-perim` | 104 | 21 | 125 | 61 s | 15 |
| `fw-wan-edge` | 104 | 20 | 124 | 60 s | 14 |
| **total** | **1.352** | **226** | **1.578** | | |

La última columna es lo que el manifiesto declara para ese equipo: el techo de
lo que una convergencia puede llegar a escribir si todo estuviera en deriva.

### Por endpoint

| método | endpoint | llamadas |
| --- | --- | ---: |
| `GET` | `/system/identity` | 104 |
| `GET` | `/ip/service` | 104 |
| `GET` | `/interface/bridge` | 104 |
| `GET` | `/interface/bridge/port` | 104 |
| `GET` | `/ip/address` | 104 |
| `GET` | `/ip/route` | 104 |
| `GET` | `/ip/firewall/filter` | 104 |
| `GET` | `/ip/firewall/nat` | 104 |
| `GET` | `/ip/dhcp-client` | 104 |
| `GET` | `/ip/pool` | 104 |
| `GET` | `/ip/dhcp-server` | 104 |
| `GET` | `/ip/dhcp-server/network` | 104 |
| `GET` | `/ip/dhcp-server/lease` | 104 |
| `PUT` | `/ip/firewall/filter` | 67 |
| `PATCH` | `/ip/service/<id>` | 55 |
| `POST` | `/ip/route/add` | 32 |
| `PUT` | `/ip/address` | 15 |
| `PUT` | `/interface/bridge/port` | 13 |
| `POST` | `/system/identity/set` | 11 |
| `POST` | `/execute` | 11 |
| `PUT` | `/ip/dhcp-server/lease` | 8 |
| `PUT` | `/interface/bridge` | 4 |
| `PUT` | `/ip/pool` | 3 |
| `PUT` | `/ip/dhcp-server/network` | 3 |
| `PUT` | `/ip/dhcp-server` | 3 |
| `PUT` | `/ip/firewall/nat` | 1 |

### Las escrituras, una a una

| método | endpoint | llamadas | qué escribe |
| --- | --- | ---: | --- |
| `PUT` | `/ip/firewall/filter` | 67 | una regla de filtrado del perímetro |
| `PATCH` | `/ip/service/<id>` | 55 | apagar un servicio que no debe escuchar (http, api, telnet…) |
| `POST` | `/ip/route/add` | 32 | una ruta (la puerta de enlace o la ruta a otra sede) |
| `PUT` | `/ip/address` | 15 | una dirección IP |
| `PUT` | `/interface/bridge/port` | 13 | meter una pata en el puente (un puerto del switch) |
| `POST` | `/system/identity/set` | 11 | el nombre del equipo |
| `POST` | `/execute` | 11 | el export de comprobación del estado |
| `PUT` | `/ip/dhcp-server/lease` | 8 | una reserva DHCP atada a una MAC |
| `PUT` | `/interface/bridge` | 4 | el puente de un switch |
| `PUT` | `/ip/pool` | 3 | el rango de direcciones que reparte un router |
| `PUT` | `/ip/dhcp-server/network` | 3 | la red que anuncia el DHCP |
| `PUT` | `/ip/dhcp-server` | 3 | el propio servidor DHCP de la sede |
| `PUT` | `/ip/firewall/nat` | 1 | una regla de NAT (solo el firewall de borde) |

## Las estaciones de trabajo

No hay API que llamar: Ansible **entra por SSH** y ejecuta módulos dentro. Por
eso lo que se cuenta son ejecuciones de tarea, que es la unidad real de trabajo.

| anfitrión | ejecuciones | ok | changed | failed | skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `pc-s1-01` | 29 | 32 | 1 | 2 | 42 |
| `pc-s1-02` | 21 | 24 | 1 | 0 | 42 |
| `pc-s1-03` | 21 | 24 | 1 | 0 | 42 |
| `pc-s1-04` | 21 | 24 | 1 | 0 | 42 |
| `pc-s2-01` | 21 | 24 | 1 | 0 | 42 |
| `pc-s2-02` | 21 | 24 | 1 | 0 | 42 |
| `pc-s3-01` | 21 | 24 | 1 | 0 | 42 |
| `pc-s3-02` | 21 | 24 | 1 | 0 | 42 |
| `localhost` | 1178 | 458 | 17 | 5 | 94 |
| `fw-s1-perim` | 400 | 136 | 4 | 1 | 31 |
| `rt-s1-core` | 305 | 122 | 1 | 0 | 48 |
| `rt-s2-edge` | 277 | 122 | 1 | 0 | 48 |
| `rt-s3-edge` | 277 | 122 | 1 | 0 | 48 |
| `fw-s2-perim` | 254 | 106 | 1 | 0 | 30 |
| `fw-s3-perim` | 254 | 106 | 1 | 0 | 30 |
| `sw-s1-acc-01` | 251 | 122 | 1 | 0 | 48 |
| `sw-s1-acc-02` | 249 | 122 | 1 | 0 | 48 |
| `sw-s2-acc-01` | 249 | 122 | 1 | 0 | 48 |
| `sw-s3-acc-01` | 249 | 122 | 1 | 0 | 48 |
| `fw-wan-edge` | 248 | 106 | 1 | 0 | 30 |
| `infra-bootstrap` | 143 | 113 | 10 | 1 | 52 |

## Tiempos totales

| Qué | Cuánto |
| --- | --- |
| Verbos ejecutados | 23 |
| Tiempo de reloj de los verbos | 49.2 min |
| Llamadas al API de Proxmox | 1.757 |
| Espera dentro del API de Proxmox | 10.7 min (640 s) |
| Llamadas al API de RouterOS | 1.578 |
| Ejecuciones de tarea | 4.510 |
| Convergencias completas | 5 |

| método HTTP al API de Proxmox | llamadas |
| --- | ---: |
| `GET` | 1701 |
| `POST` | 38 |
| `PUT` | 11 |
| `DELETE` | 7 |

| estado | llamadas |
| --- | ---: |
| 200 | 1616 |
| None | 78 |
| 500 | 63 |

## Estimación del esfuerzo

### Lo que cuesta UNA convergencia completa

La última (configure: converge RouterOS, del 21:39:35), que no cambió nada y por tanto es la lectura entera:

| | llamadas |
| --- | ---: |
| Lecturas (cada tabla declarada, por equipo) | 286 |
| Escrituras (solo lo que difería) | 0 |
| **total** | **286** |

### El total de la puesta en marcha

| Vía | Llamadas medidas |
| --- | ---: |
| API de Proxmox (trazador, capa 1 completa) | 1.757 |
| API de RouterOS (log, todos los verbos) | 1.578 |
| **total de llamadas a APIs** | **3.335** |
| Ejecuciones de tarea (capa 2, por SSH) | 4.510 |
| **suma de operaciones contables** | **7.845** |

Reparto del trabajo de RouterOS entre los 5 verbos que lo tocaron: una media
de **316 llamadas por convergencia**, sobre once equipos.

## Qué NO mide este documento

- **No mide trabajo humano.** Mide trabajo de máquina, que es lo único que se
  puede contar sin preguntar.
- **Las llamadas del rol RouterOS no están en el diario**, porque el trazador
  cubre `requests` y el rol va por `urllib`. Se cuentan del log, que sí las
  imprime una a una: por eso el detalle por endpoint existe, pero no lleva
  segundos por llamada (solo el tiempo total por equipo).
- **Los segundos de Proxmox son espera de la API, no de la tarea.** Un módulo
  que corre dentro de un invitado tarda lo que tarde el invitado, y eso no
  cruza ninguna API: se cuenta como ejecución, no como segundo.
- **Los verbos fallidos cuentan igual.** Un `apply` que falla a mitad sigue
  gastando llamadas, y aquí aparecen: son parte del coste real de dejar el
  laboratorio en pie.
