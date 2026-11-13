# Decisiones (ADR)

Un ADR registra UNA decisión y su porqué, en el momento en que se toma. Son la única
documentación de prosa que **no se genera**, y a propósito: no son estado del laboratorio,
son historia de sus decisiones. Se **citan** desde el código y los documentos; no se copian.

## Cuándo escribir uno

Cuando la decisión es **transversal** (afecta a varios ficheros o a cómo se trabaja) y su
porqué no tiene un único sitio natural junto al código. El porqué de una implementación
concreta va en el **comentario del fichero**, no aquí.

## Formato

`NNNN-titulo-corto.md`, numerado, nunca se renumera. Un ADR aceptado **no se edita**: si
cambia la decisión, se escribe uno nuevo que lo **sustituye** y se anota en `Sustituye a`.

Secciones fijas: Estado · Fecha · (Sustituye a) · Contexto · Decisión · Consecuencias ·
Dónde se aplica.

## Índice

- [0001 — El hipervisor se gobierna SOLO por su API](0001-solo-api.md)
- [0002 — Por qué existe el bootstrap](0002-bootstrap-existe.md)
- [0003 — La ruta por defecto del DHCP de fábrica se purga con un reinicio](0003-reinicio-purga-ruta-dhcp.md)
- [0004 — Un invitado del laboratorio se reconoce por su etiqueta, no por su VMID](0004-invitado-por-etiqueta.md) *(sustituido por [0008](0008-pool-por-laboratorio.md))*
- [0005 — El número de un invitado se compone (laboratorio, sede, clase, índice)](0005-numero-compuesto.md) *(el par de cifras del laboratorio, sustituido por [0008](0008-pool-por-laboratorio.md))*
- [0006 — El vocabulario de etiquetas: cuatro, y el laboratorio con su nombre](0006-vocabulario-etiquetas.md) *(la cuarta etiqueta, sustituida por [0008](0008-pool-por-laboratorio.md))*
- [0007 — El código de sede: familia e índice](0007-codigo-de-sede.md)
- [0008 — El laboratorio se agrupa por su Resource Pool, y su cifra es una](0008-pool-por-laboratorio.md)
