# 0008 — El laboratorio se agrupa por su Resource Pool, y su cifra es una

- Estado: aceptada
- Fecha: 2026-11-13
- Sustituye a: [0004](0004-invitado-por-etiqueta.md) (el invitado se reconocía por su etiqueta), [0005](0005-numero-compuesto.md) (el par de cifras del laboratorio) y [0006](0006-vocabulario-etiquetas.md) (la cuarta etiqueta del vocabulario)

## Contexto

Dos laboratorios conviviendo en el mismo nodo obligaron a meter el laboratorio dentro del
invitado, y se hizo con dos cosas a la vez: una cuarta etiqueta (`Lab-10`) y un par de
cifras delante del número (`10-AB-swac-10`). Las dos respondían a la misma pregunta —«¿de
qué laboratorio es este invitado?»— y ninguna la respondía desde donde se agrupa de
verdad. Proxmox ya sabe agrupar invitados: lo hace con los **Resource Pool**, que se ven
en el árbol del datacenter, se filtran, se facturan y distinguen un pool vacío de un pool
ausente. Una etiqueta, en cambio, es una marca que hay que creer: nadie comprueba que
diga la verdad, y el laboratorio pagaba por ella una entrada de color en
`pve_tag_style.colors`, una entrada más en `allowed-tags` y una segunda respuesta a una
pregunta que la plataforma puede contestar sola.

Y el par de cifras gastaba dos dígitos de un número que se lee de un vistazo: con el pool
diciendo a qué laboratorio pertenece cada invitado, la cifra solo tiene que evitar que dos
laboratorios se pisen en el mismo datacenter, y para eso una cifra basta.

## Decisión

1. **Cada laboratorio tiene su PROPIO Resource Pool**, declarado en el manifiesto como
   `lab_pool` y llamado como la carpeta del laboratorio (`lab-netlab-v2`, `lab-mini`,
   `lab-coworking`). Un invitado es del laboratorio **por estar dentro de su pool**, no
   por llevar una etiqueta: el pool es la respuesta, y es la que vive en la plataforma.
   El comentario del pool es el `lab_nombre` del laboratorio, para que el árbol de PVE
   diga qué es sin abrir el repositorio.
2. **El número de un invitado pasa a SIETE cifras, `L SS CC II`**: `L` el laboratorio, con
   UNA cifra (1..9). La sede, la clase y el índice no cambian (ADR 0005 sigue vigente en
   todo lo demás). Los laboratorios quedan: `netlab-v2` = 1, `mini` = 2, `coworking` = 3.
   El nombre espeja el número, como siempre: `1-Ca-swac-10`.
3. **El vocabulario de etiquetas vuelve a TRES y ni una más**: `ansible`, el rol y el
   código de sede. De qué laboratorio ya no se pregunta por etiqueta.
4. **El pool se crea si falta y NO se borra**: `apply` lo deja en pie (antes de crear sus
   invitados) y da de alta dentro lo que falte; `remove` retira los invitados declarados y
   deja el pool vacío. Borrar un pool es un acto deliberado y aparte, como borrar un
   bridge, y un pool vacío no molesta a nadie.
5. **Lo que el pool tenga de más no se toca**: `apply` no borra lo que no ha declarado, ni
   de un pool. Lo que sobre lo denuncia `guests`, que es el verbo que juzga lo que sobra.

## Consecuencias

- **Los invitados desplegados hay que recrearlos**: un VMID no se cambia en caliente, así
  que la renumeración de un laboratorio en marcha es un `remove` deliberado y su `apply`,
  empezando —como en el ADR 0005— por el laboratorio que no está desplegado.
- De qué laboratorio es un invitado deja de ser una etiqueta y pasa a ser su pool: un
  invitado del laboratorio que se quede fuera del pool es un invitado huérfano —existe,
  pero ningún laboratorio lo reconoce— y `apply` lo devuelve a su sitio.
- El `pve_tag_style.colors` de cada laboratorio pierde su entrada `lab-NN`, y
  `allowed-tags` (si el datacenter la usa) ya no necesita `lab-NN`. Las etiquetas
  publicadas bajan de cuatro a tres por invitado.
- `framework_check.py guests` lee el pool en vez de la etiqueta (una sola llamada a
  `cluster/resources` dice nombre, tipo y pool de cada invitado), y `framework_check.py
  pool` —nuevo, sin laboratorio ni credenciales— exige que cada manifiesto declare
  `lab_pool`, que se llame como su carpeta y que no lo comparta con otro laboratorio.
- `preflight` informa del estado del pool y `apply` lo converge; los dos leen el mismo
  dato del mismo sitio (`pve_read.py`), que es lo que impide que discrepen.
- El token de la API necesita `Pool.Allocate` en `/pool/<poolid>` (crear y dar de alta) y
  `Pool.Audit` (leer): la puerta de la API no cambia, pero el permiso es nuevo.

## Dónde se aplica

El `lab_pool` y la renumeración de `labs/*/inventory/group_vars/all.yml`;
`machinery/playbooks/tasks/pool.yml` y `machinery/playbooks/tasks/pool_members.yml` (lo crea y da de alta);
`machinery/playbooks/tasks/validate_state.yml` (que exista y esté bien declarado, en los dos
verbos); `machinery/playbooks/tools/pve_read.py` (el estado del pool, que informan y convergen);
`machinery/playbooks/apply.yml` y `machinery/playbooks/preflight.yml`; `machinery/playbooks/tools/framework_check.py`
(`guests` por pool, `notas` con tres etiquetas, `numeracion` con siete cifras, y el verbo
`pool`); `machinery/filter_plugins/notas.py` y `machinery/playbooks/tools/pve_notas.py` (la etiqueta del
laboratorio desaparece de la derivación); y la prosa de `docs/README.md.j2` y
`docs/laboratorio.md.j2`.
