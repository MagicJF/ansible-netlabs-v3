#!/bin/bash
# =============================================================================
# lab-check.sh — el MISMO script para las OCHO workstations del lab de 3 sedes.
#
# No se configura ni se le pasa nada: mira su PROPIA dirección, deduce en qué
# sede está y quién es su puerta de enlace, y comprueba que la red se comporta
# como la topología dice. Se ejecuta igual en pc-s1-01 que en pc-s3-02.
#
# Por cada uno de los otros 19 dispositivos del lab:
#   1 ALCANCE      ¿contesta?  (el último salto del traceroute es el destino)
#   2 PRIMER SALTO ¿el primer salto es MI puerta de enlace declarada?
#   3 CAMINO       ¿los saltos intermedios son los que predice la topología?
#
# 1 y 2 son duros: un fallo ahí es un fallo real. El 3 es un HALLAZGO — si
# difiere, imprime esperado y obtenido para analizarlo, no para darlo por roto.
# =============================================================================
set -u

# --- el mapa del lab: nombre, dirección, sede (0 = red de gestión), tipo -----
# GENERADO desde la declaración. No se edita a mano: la lista es la ENTRADA de
# este test, así que una lista escrita a mano se queda ciega a los invitados que
# se añaden después y nada lo detecta. Se regenera con:
#     python3 playbooks/tools/framework_check.py labmap
# >>> LABMAP
LAB="pc-s1-01 10.11.0.11 1 pc"
LAB="$LAB;pc-s1-02 10.11.0.12 1 pc"
LAB="$LAB;pc-s1-03 10.11.0.13 1 pc"
LAB="$LAB;pc-s1-04 10.11.0.14 1 pc"
LAB="$LAB;pc-s2-01 10.12.0.11 2 pc"
LAB="$LAB;pc-s2-02 10.12.0.12 2 pc"
LAB="$LAB;pc-s3-01 10.13.0.11 3 pc"
LAB="$LAB;pc-s3-02 10.13.0.12 3 pc"
LAB="$LAB;sw-s1-acc-01 10.10.10.11 0 sw"
LAB="$LAB;sw-s1-acc-02 10.10.10.12 0 sw"
LAB="$LAB;sw-s2-acc-01 10.10.10.13 0 sw"
LAB="$LAB;sw-s3-acc-01 10.10.10.14 0 sw"
LAB="$LAB;rt-s1-core 10.10.10.21 0 rt"
LAB="$LAB;rt-s2-edge 10.10.10.22 0 rt"
LAB="$LAB;rt-s3-edge 10.10.10.23 0 rt"
LAB="$LAB;fw-s1-perim 10.10.10.31 0 fw"
LAB="$LAB;fw-s2-perim 10.10.10.32 0 fw"
LAB="$LAB;fw-s3-perim 10.10.10.33 0 fw"
LAB="$LAB;fw-wan-edge 10.10.10.34 0 fw"
LAB="$LAB;infra-bootstrap 10.10.10.41 0 boot"
# <<< LABMAP

# --- la topología: quién es quién y por dónde se cruza -----------------------
# GENERADO desde la declaración. No se edita a mano: las puertas, los routers de
# gestión y los saltos de cada par de sedes se derivan de `lab_sites` y `lab_hub`.
# Se regenera con:  python3 playbooks/tools/framework_check.py labmap
#
# La LAN de la sede cuelga de su ROUTER (el router es la puerta y el servidor
# DHCP) y el FIREWALL se interpone entre el router y la WAN. Por eso el tránsito
# entre sedes tiene CUATRO saltos: entra y sale por dos firewalls además de los
# dos routers. El hub es la sede cuyo firewall termina el borde; las demás son
# spokes con UN enlace hacia el hub.
# >>> TOPOLOGY
GW="1 10.11.0.1 2 10.12.0.1 3 10.13.0.1"
RT="1 10.10.10.21 2 10.10.10.22 3 10.10.10.23"
HOP="1-0 10.11.0.1
1-1
1-2 10.11.0.1 10.21.0.1 10.99.1.2 10.22.0.2
1-3 10.11.0.1 10.21.0.1 10.99.2.2 10.23.0.2
2-0 10.12.0.1
2-1 10.12.0.1 10.22.0.1 10.99.1.1 10.21.0.2
2-2
2-3 10.12.0.1 10.22.0.1 10.99.1.1 10.99.2.2 10.23.0.2
3-0 10.13.0.1
3-1 10.13.0.1 10.23.0.1 10.99.2.1 10.21.0.2
3-2 10.13.0.1 10.23.0.1 10.99.2.1 10.99.1.2 10.22.0.2
3-3"
# <<< TOPOLOGY

gw_of() { printf '%s\n' "$GW" | awk -v s="$1" '{for(i=1;i<=NF;i+=2) if($i==s){print $(i+1); exit}}'; }
rt_of() { printf '%s\n' "$RT" | awk -v s="$1" '{for(i=1;i<=NF;i+=2) if($i==s){print $(i+1); exit}}'; }
es_mi_puerta() { [ "$1" = "$MY_GW" ] || [ "$1" = "$(rt_of "$MY_SITE")" ]; }

# esperado <sede mía> <sede destino> -> saltos intermedios que predice la
# topología. El destino NUNCA va aquí: el último salto del traceroute ES el
# destino y se comprueba aparte, como prueba de alcance.
esperado() {
  printf '%s\n' "$HOP" | awk -v k="$1-$2" '$1==k {if (NF==1) {print ""; exit}; sub(/^[^ ]+ /,""); print; exit}'
}

# Permite cargar sólo las funciones para probarlas:  LABCHECK_LIB=1 . lab-check.sh
[ "${LABCHECK_LIB:-}" = "1" ] && return 0 2>/dev/null

# --- ¿quién soy? ------------------------------------------------------------
MY_IP="${LABCHECK_MY_IP:-$(ip -4 -o addr show dev eth0 2>/dev/null | awk '{print $4}' | cut -d/ -f1)}"
[ -z "$MY_IP" ] && MY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
ME=$(echo "$LAB"      | tr ';' '\n' | awk -v ip="$MY_IP" '$2==ip {print $1}')
MY_SITE=$(echo "$LAB" | tr ';' '\n' | awk -v ip="$MY_IP" '$2==ip {print $3}')

if [ -z "$ME" ]; then
  echo "!! Mi dirección es '$MY_IP' y no está en el mapa del lab."
  echo "   Este script es para las 8 workstations; ejecútalo dentro de una."
  exit 2
fi

MY_GW=$(gw_of "$MY_SITE")
MY_HOST=$(hostname 2>/dev/null)
DEF_GW=$(ip route show default 2>/dev/null | awk '/^default/ {print $3; exit}')

echo "=== LAB-CHECK - $ME ($MY_IP) - sede $MY_SITE ==="
if [ "$MY_HOST" = "$ME" ]; then
  printf '  %-12s %-14s %s\n' hostname "$MY_HOST" "OK (coincide con la IP)"
else
  printf '  %-12s %-14s %s\n' hostname "$MY_HOST" "OJO: la IP dice que soy $ME"
fi
printf '  %-12s %-14s %s\n' "dirección" "$MY_IP" "la reservada en el mapa"
if [ "$DEF_GW" = "$MY_GW" ]; then
  printf '  %-12s %-14s %s\n' "puerta enf." "$DEF_GW" "OK (la declarada)"
else
  printf '  %-12s %-14s %s\n' "puerta enf." "${DEF_GW:-ninguna}" "OJO: esperaba $MY_GW"
fi
echo

# --- la prueba, destino a destino -------------------------------------------
printf '%-4s %-14s %-4s %-5s %-8s %-9s %-7s %s\n' DISPO DIRECCIÓN SEDE TIPO ALCANCE 1erSALTO CAMINO DETALLE
echo "---------------------------------------------------------------------------------------"

total=0; ok_reach=0; ok_first=0; ok_path=0; exempt=0
anomalias=""; por_tipo=""

while read -r name ip site kind; do
  [ -z "${ip:-}" ] && continue
  [ "$ip" = "$MY_IP" ] && continue                 # yo no me pruebo
  total=$((total + 1))

  exp=$(esperado "$MY_SITE" "$site")
  # Si el destino es mi propia puerta —su LAN o su gestión— no hay salto previo
  # que esperar: el traceroute la muestra a la vez como primer salto y destino.
  es_mi_puerta "$ip" && exp=""

  raw=$(timeout 20 traceroute -n -q 1 -w 1 -m 8 "$ip" 2>/dev/null)
  got=$(echo "$raw" | awk 'NR>1 && $2!="*" && $2!="" {print $2}')
  got_flat=$(echo $got)
  last=$(echo "$got" | tail -1)
  # `got` trae UNA DIRECCIÓN POR LÍNEA: hay que quitar la ÚLTIMA LÍNEA (el
  # destino) para quedarse con los intermedios. Un `awk` sobre la lista entera
  # ve NF=1 en cada línea y no recorta nada — devolvía siempre vacío.
  got_int=$(echo "$got" | head -n -1 | tr '\n' ' ' | sed 's/ *$//')

  # 1 — alcance
  if [ "$last" = "$ip" ]; then reach=OK; ok_reach=$((ok_reach + 1)); else reach=NO; fi

  # 2 — primer salto (no aplica si el destino es de mi sede o es mi puerta)
  if [ "$site" = "$MY_SITE" ] || es_mi_puerta "$ip"; then
    first="-"; exempt=$((exempt + 1))
  elif [ "$(echo $got | awk '{print $1}')" = "$MY_GW" ]; then
    first=OK; ok_first=$((ok_first + 1))
  else
    first=NO
  fi

  # 3 — camino (sólo si el destino contestó: si no, el traceroute se corta y los
  # saltos que faltan no son una discrepancia, son la consecuencia)
  if [ "$reach" = "NO" ]; then
    path="n/a"; det="sin respuesta ($got_flat)"
  elif [ "$(echo $exp)" = "$(echo $got_int)" ]; then
    path="="; ok_path=$((ok_path + 1)); det="$got_flat"
  else
    path="DIF"; det="esp[$exp] obt[$got_flat]"
  fi

  printf '%-4s %-14s %-4s %-5s %-8s %-9s %-7s %s\n' "$name" "$ip" "$site" "$kind" "$reach" "$first" "$path" "$det"
  if [ "$path" = "DIF" ]; then
    anomalias="${anomalias}${name}(${ip}) esp[${exp}] obt[${got_flat}]"$'\n'
  fi
  por_tipo="${por_tipo}${kind} ${reach}"$'\n'
done < <(echo "$LAB" | tr ';' '\n')

# --- resumen, y un bloque corto para pegar ----------------------------------
exigidos=$((total - exempt))
echo
echo "--- RESUMEN $ME ---"
printf '  alcance      : %d/%d destinos contestan\n' "$ok_reach" "$total"
printf '  primer salto : %d/%d por mi puerta (%d en mi propia sede exentos)\n' "$ok_first" "$exigidos" "$exempt"
printf '  camino       : %d/%d de los que contestan\n' "$ok_path" "$ok_reach"
for k in pc rt fw sw boot; do
  case "$k" in pc) lbl="workstations";; rt) lbl="routers     ";; fw) lbl="firewalls   ";; sw) lbl="switches    ";; boot) lbl="bootstrap   ";; esac
  tot=$(printf '%s' "$por_tipo" | awk -v k="$k" '$1==k' | wc -l)
  oks=$(printf '%s' "$por_tipo" | awk -v k="$k" '$1==k && $2=="OK"' | wc -l)
  [ "$tot" -gt 0 ] && printf '    %s : %d/%d contestan\n' "$lbl" "$oks" "$tot"
done
if [ -n "$anomalias" ]; then
  echo "  caminos distintos al predicho:"
  printf '%s' "$anomalias" | sed 's/^/    - /'
fi
# La nota sólo aparece si algo NO contestó. En un lab sano no hay nada que
# explicar, y una nota fija contradiría al propio resultado en cuanto los
# switches llevaran su puerta de enlace de gestión.
if [ "$ok_reach" != "$total" ]; then
  echo
  echo "  NOTA: lo que sale en NO suele ser falta de ruta de VUELTA, no de ida —"
  echo "  el paquete llega y la respuesta no encuentra por dónde salir. Es lo que"
  echo "  le pasaba a los switches antes de llevar puerta de enlace de gestión."
fi

echo
echo "### PEGA ESTO ###"
echo "ws=$ME ip=$MY_IP sede=$MY_SITE host=$MY_HOST gw=${DEF_GW:-ninguna}(esp $MY_GW)"
echo "alcance=$ok_reach/$total primer_salto=$ok_first/$exigidos camino=$ok_path/$ok_reach"
for k in pc rt fw sw boot; do
  tot=$(printf '%s' "$por_tipo" | awk -v k="$k" '$1==k' | wc -l)
  oks=$(printf '%s' "$por_tipo" | awk -v k="$k" '$1==k && $2=="OK"' | wc -l)
  [ "$tot" -gt 0 ] && echo "$k=$oks/$tot"
done
printf '%s' "$anomalias" | sed 's/^/ANOM /'
echo "### FIN ###"

# El código de salida sólo mira lo que DEBE funcionar: workstations, routers y
# firewalls. Los switches y el bootstrap son la excepción conocida.
malos=$(printf '%s' "$por_tipo" | awk '$1=="pc"||$1=="rt"||$1=="fw"' | grep -c NO)
[ "$malos" = "0" ] && [ "$ok_first" = "$exigidos" ] && exit 0 || exit 1
