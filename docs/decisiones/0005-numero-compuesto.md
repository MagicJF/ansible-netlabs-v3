# 0005 — El número de un invitado se compone (laboratorio, sede, clase, índice)

- Estado: aceptada
- Fecha: 2026-11-11

## Contexto
La numeración de CUATRO dígitos `STNN` nació para UN laboratorio y se rompe por tres
sitios, los tres medidos:

- **Se queda corta.** Un dígito de sede son diez sedes y un dígito de tipo son diez
  papeles; un laboratorio multi-inquilino ya usa tres sedes y varios papeles.
- **No dice de qué laboratorio es.** `2401` existe en netlab-v2 y la banda 2xxx la usa
  también mini; el nombre `infra-bootstrap` se repite. Es la colisión que la ADR 0004
  tuvo que resolver con una etiqueta.
- **El nombre contradice al número.** El número dice sede primero (`1301`) y el nombre
  dice tipo primero (`sw-s1-acc-01`). Dos órdenes para lo mismo.

## Decisión
El número tiene OCHO dígitos en CUATRO campos de dos: `LL SS CC II`.

- **Ningún campo empieza por cero.** Todos van de 10 en adelante. Un `01` en un campo
  se lee como un índice encubierto; el número no debe parecer lo que no es.
- **LL — laboratorio.** 10–99. El primero en crearse es el 10. Cada laboratorio tiene
  además un nombre: `10 netlab-v2`, `11 mini`, `12 coworking`.
- **SS — sede.** La sede se escribe con DOS LETRAS que se leen como sus dos cifras.
  `A`=1, `B`=2, `C`=3, `D`=4, `E`=5, `F`=6, `G`=7, `H`=8, `I`=9. La `J` no se usa: no
  hay cero en una sede. Por eso `AA`=11, `AB`=12, … `AI`=19, `BA`=21, … `II`=99.
  La letra es la vista legible; la cifra es la que va al número.
- **CC — clase.** 10–99. La decena es la FAMILIA y la unidad el PAPEL dentro de ella:
  `1x` conmutación, `2x` enrutamiento, `8x` seguridad, `9x` puestos, `7x` apoyo. Una
  clase describe el tipo y el papel JUNTOS: «switch de acceso» es una clase, no
  «switch» más «acceso».
- **II — índice.** 10–99. El primero de una clase en una sede es el 10.

El nombre espeja el número, mismo orden: `LL-SS-token-II`.

| Número   | Nombre        | Qué es                                      |
|----------|---------------|---------------------------------------------|
| 10121110 | 10-AB-swac-10 | lab 10, sede 12 (central), switch acceso 1º |
| 10128110 | 10-AB-fwpe-10 | lab 10, sede 12 (central), firewall perime. |
| 10168210 | 10-AF-fwbo-10 | lab 10, sede 16 (borde), firewall de borde  |

## Tabla de sedes
| Código | Nº | Sede                          |
|--------|----|-------------------------------|
| AA     | 11 | infraestructura               |
| AB     | 12 | central / principal           |
| AC     | 13 | delegación 2                  |
| AD     | 14 | delegación 3                  |
| AE     | 15 | gestión (OOB)                 |
| AF     | 16 | borde                         |
| AG     | 17 | edificio                      |
| AH     | 18 | inquilino A                   |
| AI     | 19 | inquilino B                   |

## Tabla de clases (decena = familia)
| Nº  | Token | Clase                     |
|-----|-------|---------------------------|
| 10  | sw    | switch (genérico)         |
| 11  | swac  | switch de acceso          |
| 12  | swge  | switch de gestión         |
| 13  | swco  | switch de núcleo          |
| 20  | rt    | router (genérico)         |
| 21  | rtco  | router de núcleo          |
| 22  | rtbo  | router de borde           |
| 71  | boot  | bootstrap (sala de partos)|
| 80  | fw    | firewall (genérico)       |
| 81  | fwpe  | firewall perimetral       |
| 82  | fwbo  | firewall de borde         |
| 90  | pc    | puesto (genérico)         |
| 91  | pcws  | estación de trabajo       |

## Consecuencias
- Dos laboratorios no pueden pisarse: el prefijo de laboratorio hace único el número y
  el nombre aunque la sede y la clase coincidan.
- El número deja de ser un valor que se recuerda y pasa a ser uno que se lee.
- Se renumeran los tres laboratorios existentes. Cambiar un VMID obliga a recrear el
  invitado, así que se empieza por el que no está desplegado (coworking) y se valida
  allí el esquema antes de tocar los que están en marcha.

## Dónde se aplica
El inventario de cada laboratorio (`lab_numero`, `lab_sites[].codigo`, `lab_clases`);
la herramienta de verificación de la numeración; y la prosa de `docs/laboratorio.md.j2`.
