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

- **41 verbos** ejecutados, con **2.967 ejecuciones de tarea** repartidas entre
  **22 anfitriones**.
- **622 llamadas al API de Proxmox** medidas con el trazador, que suman
  **4.1 minutos** de espera dentro de la API.
- **333 llamadas al API de RouterOS** contadas en el log: 326 de lectura y 7 de
  escritura. Los once equipos se gobiernan por REST, sin SSH.
- **9 convergencias completas** del laboratorio, más los verbos de capa 1.
- Tiempo de reloj de todos los verbos: **38.7 minutos**.

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
| 22 | 18:08:20 | 46 s | capa 1: apply | 1 | 170 | 0 | 19 | 0 | 1 |
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
| `/api2/json/version` | 73 | 34.9 |
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
| `sw-mgmt-01` | 40 | 7 | 47 | 270 s | 2 |
| `rt-s3-edge` | 26 | 0 | 26 | 11 s | 6 |
| `sw-s1-acc-02` | 26 | 0 | 26 | 12 s | 6 |
| `fw-s3-perim` | 26 | 0 | 26 | 11 s | 15 |
| `fw-wan-edge` | 26 | 0 | 26 | 11 s | 14 |
| `rt-s2-edge` | 26 | 0 | 26 | 12 s | 6 |
| `sw-s3-acc-01` | 26 | 0 | 26 | 12 s | 6 |
| `fw-s2-perim` | 26 | 0 | 26 | 12 s | 15 |
| `sw-s2-acc-01` | 26 | 0 | 26 | 12 s | 6 |
| `sw-s1-acc-01` | 26 | 0 | 26 | 12 s | 7 |
| `rt-s1-core` | 26 | 0 | 26 | 12 s | 8 |
| `fw-s1-perim` | 26 | 0 | 26 | 12 s | 27 |
| **total** | **326** | **7** | **333** | | |

La última columna es lo que el manifiesto declara para ese equipo: el techo de
lo que una convergencia puede llegar a escribir si todo estuviera en deriva.

### Por endpoint

| método | endpoint | llamadas |
| --- | --- | ---: |
| `GET` | `/ip/dhcp-server/lease` | 26 |
| `GET` | `/system/identity` | 25 |
| `GET` | `/ip/service` | 25 |
| `GET` | `/interface/bridge` | 25 |
| `GET` | `/interface/bridge/port` | 25 |
| `GET` | `/ip/address` | 25 |
| `GET` | `/ip/route` | 25 |
| `GET` | `/ip/firewall/filter` | 25 |
| `GET` | `/ip/firewall/nat` | 25 |
| `GET` | `/ip/dhcp-client` | 25 |
| `GET` | `/ip/pool` | 25 |
| `GET` | `/ip/dhcp-server` | 25 |
| `GET` | `/ip/dhcp-server/network` | 25 |
| `PATCH` | `/ip/service/<id>` | 5 |
| `POST` | `/system/identity/set` | 1 |
| `POST` | `/execute` | 1 |

### Las escrituras, una a una

| método | endpoint | llamadas | qué escribe |
| --- | --- | ---: | --- |
| `PATCH` | `/ip/service/<id>` | 5 | apagar un servicio que no debe escuchar (http, api, telnet…) |
| `POST` | `/system/identity/set` | 1 | el nombre del equipo |
| `POST` | `/execute` | 1 | el export de comprobación del estado |

## Las estaciones de trabajo

No hay API que llamar: Ansible **entra por SSH** y ejecuta módulos dentro. Por
eso lo que se cuenta son ejecuciones de tarea, que es la unidad real de trabajo.

| anfitrión | ejecuciones | ok | changed | failed | skipped |
| --- | ---: | ---: | ---: | ---: | ---: |
| `pc-s1-01` | 13 | 14 | 0 | 0 | 14 |
| `pc-s1-02` | 13 | 14 | 0 | 0 | 14 |
| `pc-s1-03` | 13 | 14 | 0 | 0 | 14 |
| `pc-s1-04` | 13 | 14 | 0 | 0 | 14 |
| `pc-s2-01` | 13 | 14 | 0 | 0 | 14 |
| `pc-s2-02` | 13 | 14 | 0 | 0 | 14 |
| `pc-s3-01` | 13 | 14 | 0 | 0 | 14 |
| `pc-s3-02` | 13 | 14 | 0 | 0 | 14 |
| `localhost` | 2064 | 425 | 10 | 12 | 75 |
| `infra-bootstrap` | 161 | 121 | 5 | 5 | 62 |
| `sw-mgmt-01` | 94 | 39 | 1 | 1 | 12 |
| `fw-s1-perim` | 55 | 26 | 0 | 0 | 8 |
| `rt-s1-core` | 53 | 24 | 0 | 0 | 10 |
| `fw-s2-perim` | 53 | 26 | 0 | 0 | 8 |
| `fw-s3-perim` | 53 | 26 | 0 | 0 | 8 |
| `fw-wan-edge` | 52 | 26 | 0 | 0 | 8 |
| `rt-s2-edge` | 49 | 24 | 0 | 0 | 10 |
| `rt-s3-edge` | 49 | 24 | 0 | 0 | 10 |
| `sw-s1-acc-01` | 45 | 24 | 0 | 0 | 10 |
| `sw-s1-acc-02` | 45 | 24 | 0 | 0 | 10 |
| `sw-s2-acc-01` | 45 | 24 | 0 | 0 | 10 |
| `sw-s3-acc-01` | 45 | 24 | 0 | 0 | 10 |

## Tiempos totales

| Qué | Cuánto |
| --- | --- |
| Verbos ejecutados | 41 |
| Tiempo de reloj de los verbos | 38.7 min |
| Llamadas al API de Proxmox | 622 |
| Espera dentro del API de Proxmox | 4.1 min (248 s) |
| Llamadas al API de RouterOS | 333 |
| Ejecuciones de tarea | 2.967 |
| Convergencias completas | 9 |

| método HTTP al API de Proxmox | llamadas |
| --- | ---: |
| `GET` | 607 |
| `PUT` | 13 |
| `POST` | 2 |

| estado | llamadas |
| --- | ---: |
| 200 | 590 |
| None | 18 |
| 401 | 9 |
| 500 | 5 |

## Estimación del esfuerzo

### Lo que cuesta UNA convergencia completa

La última (configure: converge RouterOS, del 19:31:56), que no cambió nada y por tanto es la lectura entera:

| | llamadas |
| --- | ---: |
| Lecturas (cada tabla declarada, por equipo) | 312 |
| Escrituras (solo lo que difería) | 0 |
| **total** | **312** |

### El total de la puesta en marcha

| Vía | Llamadas medidas |
| --- | ---: |
| API de Proxmox (trazador, capa 1 completa) | 622 |
| API de RouterOS (log, todos los verbos) | 333 |
| **total de llamadas a APIs** | **955** |
| Ejecuciones de tarea (capa 2, por SSH) | 2.967 |
| **suma de operaciones contables** | **3.922** |

Reparto del trabajo de RouterOS entre los 9 verbos que lo tocaron: una media
de **37 llamadas por convergencia**, sobre once equipos.

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
