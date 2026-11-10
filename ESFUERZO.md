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
| `logs/pve-api.jsonl` | cada llamada HTTP de las **dos** APIs, con un campo `api` para separarlas, y método, ruta, estado y **segundos** | **Proxmox**: la capa 1 va por proxmoxer, y aquí se leen SOLO esas |
| `logs/ansible.log` | cada resultado de tarea, por anfitrión, con marca de tiempo | **RouterOS** y **trabajo**: el rol imprime su plan y sus lecturas |

**Por qué dos fuentes.** El diario es uno para las dos APIs: el trazador engancha
`requests` (el módulo de Proxmox) **y** `urllib` (lo que usa `ansible.builtin.uri`,
o sea el rol RouterOS). Así que trae las dos, y aquí se separan por el campo `api`
—sin eso, las tablas de Proxmox contarían también las de RouterOS—. Las tablas de
Proxmox salen del diario. El lado RouterOS se cuenta del log de Ansible porque da
lo que el diario no da: el desglose por equipo × endpoint (el rol imprime
`Report the plan, call by call` y cada tabla que lee).

## Resumen

- **48 verbos** ejecutados, con **5.057 ejecuciones de tarea** repartidas entre
  **22 anfitriones**.
- **605 llamadas al API de Proxmox** medidas con el trazador, que suman
  **2.6 minutos** de espera dentro de la API.
- **964 llamadas al API de RouterOS** contadas en el log: 950 de lectura y 14 de
  escritura. Los once equipos se gobiernan por REST, sin SSH.
- El trazador anotó además **675 llamadas del lado RouterOS con sus segundos**
  (no son sólo convergencia: incluyen las pruebas de `lab-check`).
- **11 convergencias completas** del laboratorio, más los verbos de capa 1.
- Tiempo de reloj de todos los verbos: **54.6 minutos**.

## Los verbos, uno a uno

| # | inicio | dur. | verbo | anfitriones | llamadas PVE | RouterOS | ok | chg | fail |
| ---: | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 17:52:27 | 0 s | localhost | 1 | 0 | 0 | 0 | 0 | 1 |
| 2 | 17:52:30 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 3 | 17:52:37 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 4 | 17:52:47 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 5 | 17:53:01 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 6 | 17:53:07 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 7 | 17:53:08 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 8 | 17:53:18 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 9 | 17:53:22 | 1 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 10 | 17:53:23 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 11 | 17:53:35 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 12 | 17:53:35 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 13 | 17:53:52 | 0 s | localhost | 1 | 0 | 0 | 0 | 0 | 1 |
| 14 | 17:55:27 | 0 s | localhost | 1 | 0 | 0 | 0 | 0 | 1 |
| 15 | 17:55:28 | 0 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 16 | 17:55:36 | 1 s | localhost | 1 | 0 | 0 | 0 | 0 | 1 |
| 17 | 17:55:47 | 1 s | localhost | 1 | 0 | 0 | 1 | 0 | 0 |
| 18 | 17:55:48 | 0 s | localhost | 1 | 44 | 0 | 1 | 0 | 0 |
| 19 | 18:00:15 | 11 s | capa 1: apply | 1 | 44 | 0 | 7 | 0 | 1 |
| 20 | 18:02:45 | 13 s | capa 1: apply | 1 | 44 | 0 | 13 | 0 | 1 |
| 21 | 18:04:11 | 26 s | capa 1: apply | 1 | 53 | 0 | 22 | 2 | 1 |
| 22 | 18:08:20 | 46 s | capa 1: apply | 1 | 152 | 0 | 19 | 0 | 1 |
| 23 | 18:13:48 | 242 s | capa 1: apply | 1 | 0 | 0 | 31 | 4 | 1 |
| 24 | 18:32:07 | 4 s | Converge the control node's path i | 1 | 0 | 0 | 19 | 3 | 0 |
| 25 | 18:38:06 | 104 s | configure: converge RouterOS | 2 | 0 | 0 | 26 | 0 | 1 |
| 26 | 18:40:04 | 0 s | localhost | 1 | 0 | 0 | 0 | 0 | 1 |
| 27 | 18:40:23 | 0 s | localhost | 1 | 0 | 0 | 2 | 0 | 1 |
| 28 | 18:40:43 | 2 s | localhost | 1 | 0 | 0 | 12 | 0 | 0 |
| 29 | 18:42:24 | 2 s | localhost | 1 | 0 | 0 | 12 | 0 | 0 |
| 30 | 18:52:05 | 165 s | configure: converge RouterOS | 2 | 0 | 0 | 28 | 0 | 1 |
| 31 | 18:59:43 | 167 s | configure: converge RouterOS | 2 | 0 | 0 | 37 | 3 | 1 |
| 32 | 19:04:19 | 152 s | configure: converge RouterOS | 2 | 0 | 0 | 37 | 0 | 1 |
| 33 | 19:08:17 | 131 s | configure: converge RouterOS | 2 | 0 | 0 | 32 | 0 | 1 |
| 34 | 19:12:10 | 196 s | configure: converge RouterOS | 2 | 0 | 0 | 43 | 0 | 0 |
| 35 | 19:16:56 | 197 s | configure: converge RouterOS | 2 | 95 | 0 | 43 | 2 | 0 |
| 36 | 19:22:33 | 41 s | capa 1: apply | 1 | 0 | 0 | 32 | 1 | 0 |
| 37 | 19:25:50 | 352 s | configure: converge RouterOS | 2 | 0 | 21 | 37 | 1 | 1 |
| 38 | 19:31:56 | 433 s | configure: converge RouterOS | 22 | 0 | 312 | 402 | 0 | 0 |
| 39 | 19:41:25 | 12 s | lab-check - build the workstation  | 9 | 0 | 0 | 33 | 0 | 1 |
| 40 | 19:41:56 | 12 s | lab-check - build the workstation  | 9 | 0 | 0 | 34 | 0 | 0 |
| 41 | 19:42:51 | 12 s | lab-check - build the workstation  | 9 | 0 | 0 | 34 | 0 | 0 |
| 42 | 19:51:41 | 450 s | configure: converge RouterOS | 22 | 0 | 312 | 402 | 0 | 0 |
| 43 | 19:59:49 | 1 s | localhost | 1 | 1 | 0 | 2 | 0 | 0 |
| 44 | 20:00:00 | 1 s | localhost | 1 | 0 | 0 | 2 | 0 | 0 |
| 45 | 20:00:51 | 12 s | lab-check - build the workstation  | 9 | 0 | 0 | 34 | 0 | 0 |
| 46 | 20:22:58 | 456 s | configure: converge RouterOS | 22 | 0 | 319 | 404 | 1 | 0 |
| 47 | 20:31:10 | 16 s | lab-check - build the workstation  | 9 | 0 | 0 | 35 | 0 | 1 |
| 48 | 20:31:39 | 16 s | lab-check - build the workstation  | 9 | 0 | 0 | 37 | 0 | 0 |

## API de Proxmox

### Por invitado

| invitado | tipo | llamadas | segundos |
| --- | --- | ---: | ---: |
| `pc-s3-01` | LXC | 25 | 5.7 |
| `infra-bootstrap` | LXC | 24 | 10.2 |
| `pc-s1-01` | LXC | 24 | 5.5 |
| `pc-s1-02` | LXC | 24 | 5.5 |
| `pc-s1-03` | LXC | 24 | 5.5 |
| `pc-s1-04` | LXC | 24 | 5.6 |
| `pc-s2-01` | LXC | 24 | 5.5 |
| `pc-s2-02` | LXC | 24 | 5.6 |
| `pc-s3-02` | LXC | 24 | 5.5 |
| `rt-s1-core` | CHR | 24 | 5.0 |
| `rt-s2-edge` | CHR | 24 | 4.9 |
| `rt-s3-edge` | CHR | 24 | 5.5 |
| `sw-s1-acc-01` | CHR | 22 | 4.5 |
| `sw-s1-acc-02` | CHR | 22 | 4.5 |
| `sw-s2-acc-01` | CHR | 22 | 4.5 |
| `sw-s3-acc-01` | CHR | 22 | 4.5 |
| `fw-s1-perim` | CHR | 22 | 4.3 |
| `fw-s2-perim` | CHR | 22 | 4.3 |
| `fw-s3-perim` | CHR | 22 | 4.4 |
| `fw-wan-edge` | CHR | 22 | 4.4 |
| `sw-mgmt-01` | CHR | 12 | 5.9 |
| **total** | | **477** | **111.4** |

### Por endpoint

| endpoint | llamadas | segundos |
| --- | ---: | ---: |
| `config` | 254 | 59.4 |
| `status/current` | 223 | 52.0 |

### Sin invitado: el motor y el nodo

| endpoint | llamadas | segundos |
| --- | ---: | ---: |
| `/api2/json/version` | 74 | 35.1 |
| `/api2/json/nodes` | 16 | 2.6 |
| `/api2/json/nodes/Proxmox/storage` | 11 | 3.4 |
| `/api2/json/nodes/Proxmox/storage/local/content?content=vztmpl` | 11 | 3.2 |
| `/api2/json/cluster/resources` | 10 | 0.8 |
| `/api2/json/nodes/Proxmox/tasks/UPID:<id>` | 4 | 0.9 |
| `/api2/json/nodes/Proxmox/qemu` | 1 | 0.2 |
| `/api2/json/nodes/Proxmox/startall` | 1 | 0.3 |

## API de RouterOS

Los once equipos de red se gobiernan **solo** por su API REST (HTTP en el
puerto 80). Cada convergencia lee cada tabla declarada y escribe únicamente lo
que difiere, así que el grueso son lecturas y las escrituras son la excepción —
que es exactamente lo que debe pasar cuando el estado ya es el declarado.

### Por equipo

| equipo | lecturas | escrituras | total | tiempo en convergir | elementos declarados |
| --- | ---: | ---: | ---: | ---: | ---: |
| `sw-mgmt-01` | 92 | 7 | 99 | 296 s | 2 |
| `fw-wan-edge` | 78 | 7 | 85 | 40 s | 15 |
| `sw-s1-acc-01` | 78 | 0 | 78 | 39 s | 7 |
| `sw-s3-acc-01` | 78 | 0 | 78 | 38 s | 6 |
| `rt-s1-core` | 78 | 0 | 78 | 38 s | 8 |
| `fw-s2-perim` | 78 | 0 | 78 | 39 s | 15 |
| `fw-s3-perim` | 78 | 0 | 78 | 39 s | 15 |
| `fw-s1-perim` | 78 | 0 | 78 | 39 s | 27 |
| `rt-s2-edge` | 78 | 0 | 78 | 38 s | 6 |
| `rt-s3-edge` | 78 | 0 | 78 | 37 s | 6 |
| `sw-s1-acc-02` | 78 | 0 | 78 | 38 s | 6 |
| `sw-s2-acc-01` | 78 | 0 | 78 | 39 s | 6 |
| **total** | **950** | **14** | **964** | | |

La última columna es lo que el manifiesto declara para ese equipo: el techo de
lo que una convergencia puede llegar a escribir si todo estuviera en deriva.

### Por endpoint

| método | endpoint | llamadas |
| --- | --- | ---: |
| `GET` | `/ip/dhcp-server/lease` | 74 |
| `GET` | `/system/identity` | 73 |
| `GET` | `/ip/service` | 73 |
| `GET` | `/interface/bridge` | 73 |
| `GET` | `/interface/bridge/port` | 73 |
| `GET` | `/ip/address` | 73 |
| `GET` | `/ip/route` | 73 |
| `GET` | `/ip/firewall/filter` | 73 |
| `GET` | `/ip/firewall/nat` | 73 |
| `GET` | `/ip/dhcp-client` | 73 |
| `GET` | `/ip/pool` | 73 |
| `GET` | `/ip/dhcp-server` | 73 |
| `GET` | `/ip/dhcp-server/network` | 73 |
| `PUT` | `/ip/firewall/filter` | 7 |
| `PATCH` | `/ip/service/<id>` | 5 |
| `POST` | `/system/identity/set` | 1 |
| `POST` | `/execute` | 1 |

### Las escrituras, una a una

| método | endpoint | llamadas | qué escribe |
| --- | --- | ---: | --- |
| `PUT` | `/ip/firewall/filter` | 7 | una regla de filtrado del perímetro |
| `PATCH` | `/ip/service/<id>` | 5 | apagar un servicio que no debe escuchar (http, api, telnet…) |
| `POST` | `/system/identity/set` | 1 | el nombre del equipo |
| `POST` | `/execute` | 1 | el export de comprobación del estado |

## Las estaciones de trabajo

No hay API que llamar: Ansible **entra por SSH** y ejecuta módulos dentro. Por
eso lo que se cuenta son ejecuciones de tarea, que es la unidad real de trabajo.

| anfitrión | ejecuciones | ok | changed | failed | skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `pc-s1-01` | 33 | 36 | 0 | 0 | 42 |
| `pc-s1-02` | 33 | 36 | 0 | 0 | 42 |
| `pc-s1-03` | 33 | 36 | 0 | 0 | 42 |
| `pc-s1-04` | 33 | 36 | 0 | 0 | 42 |
| `pc-s2-01` | 33 | 36 | 0 | 0 | 42 |
| `pc-s2-02` | 33 | 36 | 0 | 0 | 42 |
| `pc-s3-01` | 33 | 36 | 0 | 0 | 42 |
| `pc-s3-02` | 33 | 36 | 0 | 0 | 42 |
| `localhost` | 2734 | 529 | 10 | 13 | 92 |
| `infra-bootstrap` | 231 | 165 | 5 | 5 | 82 |
| `sw-mgmt-01` | 182 | 85 | 1 | 1 | 34 |
| `fw-wan-edge` | 170 | 80 | 1 | 0 | 22 |
| `fw-s1-perim` | 165 | 78 | 0 | 0 | 24 |
| `rt-s1-core` | 159 | 72 | 0 | 0 | 30 |
| `fw-s2-perim` | 159 | 78 | 0 | 0 | 24 |
| `fw-s3-perim` | 159 | 78 | 0 | 0 | 24 |
| `rt-s2-edge` | 147 | 72 | 0 | 0 | 30 |
| `rt-s3-edge` | 147 | 72 | 0 | 0 | 30 |
| `sw-s1-acc-01` | 135 | 72 | 0 | 0 | 30 |
| `sw-s1-acc-02` | 135 | 72 | 0 | 0 | 30 |
| `sw-s2-acc-01` | 135 | 72 | 0 | 0 | 30 |
| `sw-s3-acc-01` | 135 | 72 | 0 | 0 | 30 |

## Tiempos totales

| Qué | Cuánto |
| --- | --- |
| Verbos ejecutados | 48 |
| Tiempo de reloj de los verbos | 54.6 min |
| Llamadas al API de Proxmox | 605 |
| Espera dentro del API de Proxmox | 2.6 min (158 s) |
| Llamadas al API de RouterOS | 964 |
| Ejecuciones de tarea | 5.057 |
| Convergencias completas | 11 |

| método HTTP al API de Proxmox | llamadas |
| --- | ---: |
| `GET` | 590 |
| `PUT` | 13 |
| `POST` | 2 |

| estado | llamadas |
| --- | ---: |
| 200 | 591 |
| 401 | 9 |
| 500 | 5 |

## Estimación del esfuerzo

### Lo que cuesta UNA convergencia completa

La última (configure: converge RouterOS, del 20:22:58), que no cambió nada y por tanto es la lectura entera:

| | llamadas |
| --- | ---: |
| Lecturas (cada tabla declarada, por equipo) | 312 |
| Escrituras (solo lo que difería) | 7 |
| **total** | **319** |

### El total de la puesta en marcha

| Vía | Llamadas medidas |
| --- | ---: |
| API de Proxmox (trazador, capa 1 completa) | 605 |
| API de RouterOS (log, todos los verbos) | 964 |
| **total de llamadas a APIs** | **1.569** |
| Ejecuciones de tarea (capa 2, por SSH) | 5.057 |
| **suma de operaciones contables** | **6.626** |

Reparto del trabajo de RouterOS entre los 11 verbos que lo tocaron: una media
de **88 llamadas por convergencia**, sobre once equipos.

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
