# 0006 — El vocabulario de etiquetas: cuatro, y el laboratorio con su nombre

- Estado: aceptada
- Fecha: 2026-11-12

## Contexto

Hasta ahora cada invitado llevaba tres etiquetas y ni una más: quién lo gestiona
(`ansible-managed`), qué es (`firewall`, `router`, `switch`, `workstation`,
`bootstrap`) y dónde está (`Ca`, `Sa`, `Sb`, `borde`, `infra` — ahora el código de
sede; ver [ADR 0007](0007-codigo-de-sede.md)). Con dos
laboratorios conviviendo en el mismo nodo, esas tres preguntas no bastan: en el
árbol del datacenter no hay forma de decir a qué laboratorio pertenece un
invitado. Además, `ansible-managed` se lee como un adjetivo de la herramienta y
no como el nombre de la etiqueta: sobra el sufijo.

## Decisión

El vocabulario sube a cuatro etiquetas, y ni una más:

1. **`ansible`** — quién lo gestiona (antes `ansible-managed`).
2. **el rol** — qué es: `firewall`, `router`, `switch`, `workstation`, `bootstrap`.
3. **el código de la sede** — dónde está: `Ca`, `Sa`, `Sb`, `Ia`, `Ga`, `Ba`
   (la familia y su índice; ver [ADR 0007](0007-codigo-de-sede.md)).
4. **`Lab-<numero>`** — de qué laboratorio: `Lab-10`, `Lab-11`, `Lab-12`.

El número es el `lab_numero` de la declaración. El tag lleva **guion y no
espacio**: PVE valida el tag con `[a-z0-9_][a-z0-9_\-\+\.]*` (pve-common,
JSONSchema) y un espacio lo rechaza con «invalid characters in tag»; por eso
`Lab 10` no existe como etiqueta y `Lab-10` sí. La lista base
(`pve_defaults.tags`, `pve_vm_defaults.tags`, `pve_chr_defaults.tags`) sigue
siendo el marcador de la declaración; lo que se publica en cada invitado es la
lista derivada, no la base.

## Consecuencias

- El árbol de PVE dice de un vistazo a qué laboratorio pertenece cada invitado.
- `framework_check.py notas` exige exactamente cuatro etiquetas y comprueba que
  la cuarta sea la del `lab_numero` declarado; un laboratorio sin `lab_numero`
  falla en voz alta en vez de publicar `Lab-None`.
- La paleta de color (`pve_tag_style.colors`) gana una entrada por laboratorio
  (`Lab-10:827717:ffffff`), para que la etiqueta del laboratorio no dependa del
  color por defecto que PVE le asigne.
- Si el datacenter tiene `allowed-tags`, hay que añadir `Lab-<numero>` allí: la
  tarea de estilo de etiquetas no puede crear la lista.

## Dónde se aplica

`filter_plugins/notas.py` y `playbooks/tools/pve_notas.py` (la derivación, con
`lab_numero`); `playbooks/apply.yml` y `playbooks/preflight.yml` (el
`lab_numero` que llega al filtro); `framework_check.py notas` (el chequeo); los
`pve_tag_style.colors` de cada laboratorio; y la prosa de `docs/README.md.j2` y
`docs/laboratorio.md.j2`.
