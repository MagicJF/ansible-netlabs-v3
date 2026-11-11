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

- **LL — laboratorio.** Dos dígitos, **desde 10** (nunca con cero a la izquierda, para
  que el número no pierda cifras al leerse como entero). El laboratorio tiene además un
  nombre: `10 netlab-v2`, `11 mini`, `12 coworking`.
- **SS — sede.** Dos dígitos que se LEEN como dos letras `AA`..`JJ`, con `A=0 … J=9`
  (`AA`=00, `AF`=05, `AJ`=09, `BA`=10, `JJ`=99: cien sedes). La letra es la forma legible
  y el dígito la del número.
- **TT — clase.** Dos dígitos. La clase describe **el tipo de equipo y el papel juntos**
  (un firewall perimetral no es «firewall» más «perimetral»: es una clase). Cien clases.
- **NN — índice.** Dos dígitos, dentro de la sede y la clase.

El **nombre espeja el número**, en el mismo orden:

    <LL>-<SS como letras>-<clase como token>-<NN>        p. ej.  10-AB-swac-01

| Número   | Nombre          | Qué es                                   |
|----------|-----------------|------------------------------------------|
| 10010301 | 10-AB-swac-01   | lab 10, sede 01, switch de acceso, el 1º |
| 10010101 | 10-AB-fwpe-01   | lab 10, sede 01, firewall perimetral     |
| 10010109 | 10-AJ-fwbo-01   | lab 10, sede 09 (borde), firewall de borde |

## Tabla de sedes (A=0 … J=9)
| Código | Nº | Sede                          |
|--------|----|-------------------------------|
| AA     | 00 | infraestructura (no es sede)  |
| AB     | 01 | central / principal           |
| AC     | 02 | delegación 2                  |
| AD     | 03 | delegación 3                  |
| AE     | 04 | gestión (segmento OOB)        |
| AF     | 05 | (reserva)                     |
| AG     | 06 | edificio                      |
| AH     | 07 | inquilino A                   |
| AI     | 08 | inquilino B                   |
| AJ     | 09 | borde                         |

## Tabla de clases (tipo + papel)
| Nº | Token | Clase                    |
|----|-------|--------------------------|
| 01 | fwpe  | firewall perimetral      |
| 02 | fwbo  | firewall de borde        |
| 03 | rtco  | router de núcleo         |
| 04 | rtbo  | router de borde          |
| 05 | swac  | switch de acceso         |
| 06 | swco  | switch de núcleo         |
| 07 | swge  | switch de gestión        |
| 08 | pc    | estación de trabajo      |
| 09 | boot  | bootstrap (sala de partos) |

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
