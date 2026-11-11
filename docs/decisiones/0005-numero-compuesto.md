# 0005 — El número de un invitado se compone: laboratorio, sede, clase e índice

- Estado: propuesta
- Fecha: 2026-11-11

## Contexto
La numeración de CUATRO dígitos `STNN` (sede, tipo de equipo, índice) nació cuando el
marco era UN laboratorio. En cuanto el marco pasa a ser una fábrica de laboratorios,
se rompe por tres sitios, los tres medidos:

- **Se queda corta por arriba.** Un dígito de sede son diez sedes y uno de tipo son diez
  tipos. Un laboratorio multi-inquilino ya usa tres sedes y varios papeles; no hay margen.
- **No dice de qué laboratorio es el invitado.** `2401` existe en netlab-v2 (estación de
  la delegación 2) y en la banda 2xxx de mini; el nombre `infra-bootstrap` se repite en
  todos. Es la raíz de la colisión que la ADR 0004 resolvió a posteriori etiquetando.
- **El nombre contradice al número.** El número lee `S T NN` (sede primero); el nombre
  (`sw-s1-acc-01`) lee tipo, sede, papel, índice. Dos formas de lo mismo, en órdenes
  distintos, y ninguna derivable de la otra.

## Decisión
El número de un invitado pasa a OCHO dígitos, en CUATRO campos de dos:

    LL SS TT NN

**Ningún campo empieza por cero** (todos valen 10..99). Un campo con cero inicial se lee
como un índice disfrazado (`08`), y la regla es que ninguna parte del número parezca lo
que no es.

- **LL — laboratorio.** Dos dígitos, **desde 10**. El laboratorio tiene además un nombre:
  `10 netlab-v2`, `11 mini`, `12 coworking`.
- **SS — sede.** Dos dígitos que se LEEN como dos letras, con `A=1 … I=9` (`AA`=11,
  `AB`=12, `AC`=13, `AF`=16, `AI`=19, `BA`=21, `II`=99). La letra J NO se usa: no hay
  cero en una sede, que es justo lo que se pide. Noventa sedes.
- **TT — clase.** Dos dígitos, **agrupados por familia**: la decena dice la familia y la
  unidad la variante dentro de ella. Una clase describe el tipo de equipo y el papel
  juntos (un firewall perimetral no es «firewall» más «perimetral»: es una clase).
- **NN — índice.** Dos dígitos, dentro de sede y clase, desde 10.

El **nombre espeja el número**, en el mismo orden:

    <LL>-<SS como letras>-<clase como token>-<NN>        p. ej.  10-AB-swac-10

| Número   | Nombre        | Qué es                                     |
|----------|---------------|--------------------------------------------|
| 10121110 | 10-AB-swac-10 | lab 10, sede 12 (central), switch acceso 1º |
| 10128110 | 10-AB-fwpe-10 | lab 10, sede 12 (central), firewall perime. |
| 10168210 | 10-AF-fwbo-10 | lab 10, sede 16 (borde), firewall de borde  |

## Tabla de sedes (A=1 … I=9; J no se usa)
| Código | Nº | Sede                          |
|--------|----|-------------------------------|
| AA     | 11 | infraestructura (no es sede)  |
| AB     | 12 | central / principal           |
| AC     | 13 | delegación 2                  |
| AD     | 14 | delegación 3                  |
| AE     | 15 | gestión (segmento OOB)        |
| AF     | 16 | borde                         |
| AG     | 17 | edificio                      |
| AH     | 18 | inquilino A                   |
| AI     | 19 | inquilino B                   |

## Tabla de clases (decena = familia, unidad = variante)
Familias: **1x** conmutación · **2x** enrutamiento · **8x** seguridad · **9x** puestos ·
**7x** apoyo · **3x–6x** reservado.

| Nº | Token | Clase                    |
|----|-------|--------------------------|
| 11 | swac  | switch de acceso         |
| 12 | swge  | switch de gestión        |
| 13 | swco  | switch de núcleo         |
| 21 | rtco  | router de núcleo         |
| 22 | rtbo  | router de borde          |
| 71 | boot  | bootstrap (sala de partos)|
| 81 | fwpe  | firewall perimetral      |
| 82 | fwbo  | firewall de borde        |
| 91 | pc    | estación de trabajo      |

## Consecuencias
- Dos laboratorios no pueden pisarse: el prefijo de laboratorio separa sus números y sus
  nombres aunque la sede y la clase coincidan.
- Un invitado nuevo no se numera a mano: se compone de su laboratorio, su sede, su clase y
  su índice, todos declarados.
- El número deja de ser un dato suelto que hay que recordar y pasa a ser una lectura.
- **Se renumeran los tres laboratorios existentes** (VMIDs, nombres, MACs, bridges). Es un
  cambio destructivo en la plataforma: el invitado que cambia de VMID se recrea.

## Dónde se aplica
El inventario de cada laboratorio (`lab_numero`, `lab_sites[].codigo`, `lab_clases`); el
scaffold `framework_check.py nuevo-lab`; los generadores `documentos.py` y `pve_notas.py`;
y la prosa del laboratorio (`docs/laboratorio.md.j2`).
