#!/usr/bin/env python3
# PROPÓSITO: el entorno de esta máquina de control: un solo fichero, una sola verdad.
# INVARIANTES: todo lo que cambia de una máquina a otra se declara UNA vez en
#   `playbooks/vars/entorno.yml`; este módulo es el ÚNICO que sabe dónde está y cómo se
#   llama cada clave (y con qué nombres alternativos se acepta).
# VER: `entorno.py verificar` (lo corre `bin/lab` antes de cualquier verbo).
"""El entorno de esta máquina de control: un solo fichero, una sola verdad.

Todo lo que cambia de una máquina a otra —las credenciales de la API, su puerto,
la ruta de la clave de automatización, la del certificado, la del túnel y dónde
vive el `config` de ssh— se declara UNA vez, en `playbooks/vars/entorno.yml`.

Este módulo es el ÚNICO sitio que sabe dónde está ese fichero, cómo se llama cada
clave y con qué nombres alternativos se aceptan (las variables de entorno
`PROXMOX_*`, que son el respaldo). Los playbooks lo cargan con `include_vars`;
las herramientas lo leen importando esto. Así la precedencia es la misma en los
dos lados y no hay dos verdades que puedan desfasarse.

Por qué un fichero y no variables de entorno: un clon nuevo en otra máquina tiene
que poder arrancar sin que nadie recuerde exportar nada, y lo que hay que
declarar tiene que estar a la vista para poder revisarlo. Las variables siguen
valiendo como respaldo, para donde no se puede dejar un fichero en disco.

Verbos:
    entorno.py verificar              ¿está completo, con rutas que existen, 0600?
    entorno.py mostrar                lo que hay, con los secretos tapados
    entorno.py crear                  lo escribe desde la plantilla, 0600
    entorno.py crear --desde-secrets  migra el antiguo playbooks/vars/secrets.yml
    entorno.py ruta                   imprime la ruta del fichero (para scripts)
"""
from __future__ import annotations

import argparse
import os
import shlex
import stat
import subprocess
import sys

import yaml

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUTA = os.path.join(RAIZ, "playbooks", "vars", "entorno.yml")
PLANTILLA = os.path.join(RAIZ, "playbooks", "vars", "entorno.example.yml")
SECRETS_ANTIGUO = os.path.join(RAIZ, "playbooks", "vars", "secrets.yml")
MANIFIESTO = os.path.join(RAIZ, "labs", "active", "inventory", "group_vars", "all.yml")

# Lo que SIEMPRE tiene que estar, y qué es. El orden es el del fichero, para que
# el informe se lea en el mismo orden en que se escribe.
OBLIGATORIAS = (
    ("pve_api_host", "el nombre o IP de la API (el que está en el SAN del certificado)"),
    ("pve_api_port", "el puerto de la API (8006 es lo normal)"),
    ("pve_api_token_id", "el token entero, `usuario@realm!nombre`"),
    ("pve_api_token_secret", "el secreto del token"),
    ("pve_api_ca_path", "la ruta del certificado o CA con el que se valida la API"),
    ("pve_ssh_user", "el usuario con el que se entra por SSH a los invitados"),
    ("pve_ssh_key_path", "la ruta de la clave privada de automatización"),
    ("pve_ssh_config_path", "dónde escribe la capa 2 el camino SSH hacia los invitados"),
)
OPCIONALES = (
    ("pve_tunnel_key_path", "la clave privada del túnel de gestión (sólo si el laboratorio declara túnel)"),
    ("control_tmp_dir", "dónde deja Ansible sus ficheros de trabajo (vacío = su sitio habitual)"),
    ("pve_ssh_args_extra", "opciones EXTRA del cliente ssh de Ansible (vacío en una máquina sana)"),
    ("pve_routeros_password", "la contraseña de administración de RouterOS (vacía = la de fábrica)"),
)
# De estas claves del entorno salen variables de Ansible. `entorno.py env` las
# imprime para que bin/lab las exporte: así el mapa vive en UN sitio y no en el
# script de arranque.
EXPORTS = {
    "control_tmp_dir": ("ANSIBLE_LOCAL_TEMP", "ANSIBLE_REMOTE_TEMP"),
}
# Lo que no se imprime nunca tal cual.
SECRETAS = ("pve_api_token_secret",)

# Nombres que se aceptan para cada valor de la API: primero los del FICHERO, luego
# los del ENTORNO. Se declaran aquí y en ningún otro sitio — que cada herramienta
# inventara los suyos era justo lo que había que quitar de en medio.
ALIAS_API = {
    "host": ("pve_api_host", "PROXMOX_HOST"),
    "port": ("pve_api_port", "PROXMOX_PORT"),
    "token_id": ("pve_api_token_id", "PROXMOX_TOKEN_ID"),
    "token_secret": ("pve_api_token_secret", "PROXMOX_TOKEN_SECRET"),
    "ca_path": ("pve_api_ca_path", "PROXMOX_CA_PATH"),
}


class EntornoIncompleto(SystemExit):
    """Falta algo del entorno. El mensaje dice QUÉ y DÓNDE se declara.

    Hereda de SystemExit a propósito: una herramienta que no puede resolver sus
    credenciales no tiene nada que hacer salvo salir diciéndolo, y así el error
    que ve el operador no es un rastro de pila sino la frase que lo arregla.
    """


def _sin_rellenar(valor):
    """¿Sigue el marcador de la plantilla? Lo que hay que rellenar va entre <>, y
    esa marca distingue "sin rellenar" de "valor por defecto" (8006, root, ~/.ssh/config
    son respuestas legítimas, no restos). Sin esta distinción, un fichero perfecto
    saldría lleno de errores y el verificador no serviría para nada."""
    return str(valor).strip().startswith("<") and str(valor).strip().endswith(">")


def _exp(v):
    return os.path.expanduser(str(v)) if isinstance(v, str) else v


def leer(ruta=None):
    """El fichero del entorno como diccionario. {} si no existe (no se inventa)."""
    ruta = ruta or RUTA
    if not os.path.exists(ruta):
        return {}
    with open(ruta, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def maquina(ruta=None):
    """Todo lo declarado, con las rutas expandidas (para el `~` del config de ssh)."""
    return {k: _exp(v) for k, v in leer(ruta).items()}


def api(ruta=None):
    """Las cinco piezas de la API, resolviendo FICHERO > ENTORNO.

    Devuelve {host, port, token_id, token_secret, ca_path}. Si falta alguna de
    las imprescindibles, sale con un mensaje que nombra el fichero y la variable
    de entorno que la puede suplir: un clon nuevo tiene que fallar diciendo qué
    le falta, no con un 401 ni con un KeyError.
    """
    declarado = leer(ruta)
    salida = {}
    for clave, nombres in ALIAS_API.items():
        valor = None
        for nombre in nombres:                      # 1) el fichero
            if nombre in declarado and str(declarado[nombre]).strip():
                valor = declarado[nombre]
                break
        if valor is None:
            for nombre in nombres:                  # 2) el respaldo del entorno
                del_entorno = os.environ.get(nombre)
                if del_entorno and del_entorno.strip():
                    valor = del_entorno
                    break
        salida[clave] = valor

    try:
        salida["port"] = int(salida.get("port") or 8006)
    except (TypeError, ValueError):
        raise EntornoIncompleto(
            f"entorno.py: pve_api_port no es un número: {salida.get('port')!r} "
            f"(decláralo en {ruta or RUTA})")
    salida["ca_path"] = _exp(salida.get("ca_path"))

    faltan = [c for c in ("host", "token_id", "token_secret", "ca_path") if not salida.get(c)]
    if faltan:
        raise EntornoIncompleto(
            "entorno.py: faltan credenciales de la API de Proxmox: "
            + ", ".join(faltan)
            + f". Decláralas en {ruta or RUTA} (plantilla: {PLANTILLA}); como respaldo, "
            + "en las variables PROXMOX_HOST, PROXMOX_TOKEN_ID, PROXMOX_TOKEN_SECRET y "
            + "PROXMOX_CA_PATH.")
    return salida


def _tapado(clave, valor):
    if clave not in SECRETAS:
        return valor
    texto = str(valor)
    return (texto[:2] + "…" + texto[-2:]) if len(texto) > 6 else "…"


def _entorno_necesita_tunel(manifiesto=None):
    """¿El laboratorio declara un túnel? Sólo entonces hace falta su clave.

    Se lee el manifiesto en crudo a propósito: aquí sólo se mira si la clave está
    declarada, y resolver la declaración entera (con Jinja y referencias) es
    muchísimo más caro que esto.
    """
    manifiesto = manifiesto or MANIFIESTO
    if not os.path.exists(manifiesto):
        return False
    try:
        with open(manifiesto, encoding="utf-8") as fh:
            datos = yaml.safe_load(fh) or {}
    except Exception:
        return False
    tunel = datos.get("pve_tunnel") or {}
    return bool(isinstance(tunel, dict) and tunel.get("manage"))


def rastreado_por_git(ruta=None):
    """¿Git tiene el fichero en el índice? Que lo tenga es un incidente, no un aviso."""
    ruta = ruta or RUTA
    try:
        rel = os.path.relpath(ruta, RAIZ)
        res = subprocess.run(["git", "-C", RAIZ, "ls-files", "--error-unmatch", rel],
                             capture_output=True, text=True)
    except (OSError, ValueError):
        return False
    return res.returncode == 0


def verificar(ruta=None, manifiesto=None, detallado=False):
    """Comprueba que el entorno está completo y es utilizable.

    Devuelve (errores, avisos), dos listas de frases. Un error es algo que impide
    ejecutar; un aviso, algo que conviene saber. Nada se da por bueno por omisión.
    """
    ruta = ruta or RUTA
    errores, avisos = [], []

    if not os.path.exists(ruta):
        errores.append(
            f"no existe {ruta}. Créalo desde la plantilla: "
            f"`cp {os.path.relpath(PLANTILLA, RAIZ)} {os.path.relpath(ruta, RAIZ)}` y edítalo, "
            f"o migra lo que ya tengas con `entorno.py crear --desde-secrets`.")
        return errores, avisos

    declarado = leer(ruta)
    plantilla = leer(PLANTILLA)

    # 1) las claves obligatorias, presentes y sin el valor de la plantilla
    for clave, que_es in OBLIGATORIAS:
        if clave not in declarado or not str(declarado[clave]).strip():
            errores.append(f"falta `{clave}`: {que_es}")
        elif _sin_rellenar(declarado[clave]):
            errores.append(f"`{clave}` sigue sin rellenar ({declarado[clave]!r}): {que_es}")

    # 2) el puerto, que tiene que poder usarse como tal
    if "pve_api_port" in declarado:
        try:
            int(str(declarado["pve_api_port"]))
        except ValueError:
            errores.append(f"`pve_api_port` no es un número: {declarado['pve_api_port']!r}")

    # 3) los ficheros que el entorno nombra tienen que estar
    def exigir_fichero(clave, que_es, opcional=False):
        valor = declarado.get(clave)
        if not valor or _sin_rellenar(valor):
            return
        camino = _exp(valor)
        if not os.path.exists(camino):
            (avisos if opcional else errores).append(f"`{clave}` apunta a algo que no existe: {camino} ({que_es})")
        elif not os.access(camino, os.R_OK):
            errores.append(f"`{clave}` no se puede leer: {camino}")

    exigir_fichero("pve_api_ca_path", "el CA de la API")
    exigir_fichero("pve_ssh_key_path", "la clave de automatización")
    if declarado.get("pve_ssh_key_path"):
        publica = _exp(str(declarado["pve_ssh_key_path"]) + ".pub")
        if not os.path.exists(publica):
            errores.append(
                f"falta la clave PÚBLICA {publica}: se deriva de `pve_ssh_key_path`, y sin ella "
                f"no se puede inyectar en los invitados al nacer. Genérala con "
                f"`ssh-keygen -y -f {_exp(str(declarado['pve_ssh_key_path']))} > {publica}`.")
    necesita_tunel = _entorno_necesita_tunel(manifiesto)
    if necesita_tunel and not declarado.get("pve_tunnel_key_path"):
        errores.append("`pve_tunnel_key_path` falta: el laboratorio declara túnel de gestión "
                       "(`pve_tunnel.manage: true`) y es la clave con la que se levanta.")
    else:
        exigir_fichero("pve_tunnel_key_path", "la clave del túnel", opcional=not necesita_tunel)

    # 4) el config de ssh: no tiene que existir, pero su carpeta sí y escribible
    ssh_config = declarado.get("pve_ssh_config_path")
    if ssh_config:
        carpeta = os.path.dirname(_exp(ssh_config))
        if not os.path.isdir(carpeta):
            errores.append(f"`pve_ssh_config_path` apunta a una carpeta que no existe: {carpeta} "
                           f"(créala con `mkdir -p {carpeta}`: la capa 2 escribe ahí el salto)")
        elif not os.access(carpeta, os.W_OK):
            errores.append(f"la carpeta de `pve_ssh_config_path` no se puede escribir: {carpeta}")

    # 5) permisos y git: el token equivale a root y el repositorio es público
    modo = stat.S_IMODE(os.stat(ruta).st_mode)
    if modo & 0o077:
        errores.append(f"{ruta} tiene permisos {modo:04o}: cualquiera de la máquina puede leerlo. "
                       f"Es un token root-equivalente — ponlo en 0600 (`chmod 600`).")
    if rastreado_por_git(ruta):
        errores.append(f"{ruta} ESTÁ EN EL ÍNDICE DE GIT. El repositorio es público y ese fichero "
                       f"lleva un token root-equivalente: sácalo del índice (`git rm --cached`) y "
                       f"confirma que el patrón sigue en .gitignore.")

    # 6) lo opcional que falte: se dice sólo si se piden los detalles, porque el
    #    envoltorio verifica en CADA verbo y una línea de relleno en cada ejecución
    #    acaba enseñando a no leer la salida.
    if detallado:
        for clave, que_es in OPCIONALES:
            if not declarado.get(clave):
                avisos.append(f"opcional, sin declarar: `{clave}` — {que_es}")
    return errores, avisos


def _ssh_args_del_framework():
    """Las `ssh_args` que declara ansible.cfg. Se leen del INI tal cual: es la única
    copia que existe, y ansible-config las devuelve como una lista de Python que
    habría que re-parsear para nada."""
    import configparser

    # interpolation=None: el ControlPath de ansible.cfg lleva `%h-%p-%r`, y el
    # interpolador de configparser se lo come como si fuera una sustitución.
    cp = configparser.ConfigParser(interpolation=None)
    cp.read(os.path.join(RAIZ, "ansible.cfg"))
    return cp.get("ssh_connection", "ssh_args", fallback="").strip()


def exports(ruta=None):
    """Las variables de entorno de Ansible que salen del fichero, en sintaxis de shell.

    Se imprime sólo lo declarado, y con `printf`-able: bin/lab hace `eval` de esta
    salida. Una ruta con espacios o comillas no debe romper la línea.
    """
    declarado = maquina(ruta)
    for clave, nombres in EXPORTS.items():
        valor = declarado.get(clave)
        if not valor:
            continue
        for nombre in nombres:
            print(f"export {nombre}={shlex.quote(str(valor))}")

    # Las de ssh se COMPONEN: las del framework, más las que añada esta máquina.
    # Sin extra no se exporta nada y ansible.cfg sigue mandando, como siempre.
    extra = declarado.get("pve_ssh_args_extra")
    if extra:
        print(f"export ANSIBLE_SSH_ARGS={shlex.quote((_ssh_args_del_framework() + ' ' + str(extra)).strip())}")


def mostrar(ruta=None):
    """El entorno, con los secretos tapados. Sin `mostrar` no hay forma de revisarlo
    sin abrirlo entero, y abrirlo entero es cómo se acaba pegando un token en un chat."""
    declarado = leer(ruta)
    if not declarado:
        print(f"(no hay fichero en {ruta or RUTA})")
        return
    ancho = max(len(k) for k in declarado)
    for clave in declarado:
        print(f"  {clave.ljust(ancho)}  {_tapado(clave, declarado[clave])}")


def _valores_del_entorno():
    salida = {}
    for clave, nombres in ALIAS_API.items():
        for nombre in nombres:
            valor = os.environ.get(nombre)
            if valor and valor.strip():
                # el canónico del fichero, no el nombre de la variable
                salida[nombres[0]] = valor
                break
    if os.environ.get("PROXMOX_PORT"):
        salida["pve_api_port"] = os.environ["PROXMOX_PORT"]
    return salida


def valores_para_crear(desde_secrets=False, manifiesto=None):
    """Lo que se sabe, para no pedir a mano lo que ya está en la máquina."""
    valores = {}
    if desde_secrets and os.path.exists(SECRETS_ANTIGUO):
        with open(SECRETS_ANTIGUO, encoding="utf-8") as fh:
            valores.update(yaml.safe_load(fh) or {})
    for clave, valor in _valores_del_entorno().items():
        valores.setdefault(clave, valor)

    # El manifiesto todavía puede tener las rutas de las claves (es de donde se
    # están quitando): sirven para no transcribirlas.
    manifiesto = manifiesto or MANIFIESTO
    datos = {}
    if os.path.exists(manifiesto):
        try:
            with open(manifiesto, encoding="utf-8") as fh:
                datos = yaml.safe_load(fh) or {}
        except Exception:
            datos = {}
    publica = datos.get("pve_ssh_pubkey_path")
    if publica and not valores.get("pve_ssh_key_path"):
        valores["pve_ssh_key_path"] = str(publica)[:-4] if str(publica).endswith(".pub") else publica
    tunel = datos.get("pve_tunnel") or {}
    if isinstance(tunel, dict) and tunel.get("private_key_path") and not valores.get("pve_tunnel_key_path"):
        valores["pve_tunnel_key_path"] = tunel["private_key_path"]

    valores.setdefault("pve_api_port", 8006)
    valores.setdefault("pve_ssh_config_path", "~/.ssh/config")
    return valores


def crear(destino=None, desde_secrets=False, forzar=False, manifiesto=None):
    """Escribe el fichero del entorno a partir de la plantilla, con lo que ya se
    sepa de esta máquina. Sólo deja el fichero si sale con 0600."""
    destino = destino or RUTA
    if os.path.exists(destino) and not forzar:
        raise EntornoIncompleto(
            f"entorno.py: {destino} ya existe. Muévelo si quieres rehacerlo, o pasa --forzar "
            f"(y cuenta con perder lo que tuviera).")

    plantilla = leer(PLANTILLA)
    if not plantilla:
        raise EntornoIncompleto(f"entorno.py: no encuentro la plantilla en {PLANTILLA}")

    valores = valores_para_crear(desde_secrets=desde_secrets, manifiesto=manifiesto)
    salida = {}
    for clave in plantilla:                      # el orden es el de la plantilla
        salida[clave] = valores.get(clave, plantilla[clave])
    for clave, valor in valores.items():         # lo que se sepa y la plantilla no declare
        salida.setdefault(clave, valor)

    cabecera = (
        "# Generado por playbooks/tools/entorno.py — el entorno de ESTA máquina.\n"
        "# Git lo ignora a propósito (el token de PVE equivale a root y el repo es\n"
        "# público). Revísalo con `entorno.py mostrar` y valídalo con `entorno.py verificar`.\n"
    )
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(cabecera)
        yaml.safe_dump(salida, fh, sort_keys=False, allow_unicode=True, default_flow_style=False)
    os.chmod(destino, 0o600)
    return destino, [clave for clave, valor in salida.items() if _sin_rellenar(valor)]


def main(argv=None):
    ap = argparse.ArgumentParser(description="El entorno de la máquina de control (un solo fichero).")
    ap.add_argument("--entorno", help=f"fichero del entorno (por defecto {os.path.relpath(RUTA, RAIZ)})")
    ap.add_argument("--manifiesto", help="manifiesto del laboratorio (para saber si declara túnel)")
    sub = ap.add_subparsers(dest="verbo", required=True)
    p_ver = sub.add_parser("verificar", help="¿está completo y son válidas sus rutas?")
    p_ver.add_argument("--detallado", action="store_true", help="incluye las claves opcionales")
    sub.add_parser("mostrar", help="lo que hay, con los secretos tapados")
    sub.add_parser("ruta", help="imprime la ruta del fichero")
    p_crear = sub.add_parser("crear", help="escríbelo desde la plantilla (0600)")
    p_crear.add_argument("--desde-secrets", action="store_true",
                         help="migra el antiguo playbooks/vars/secrets.yml")
    p_crear.add_argument("--forzar", action="store_true", help="pisa el que haya")
    sub.add_parser("api", help="las credenciales resueltas (tapadas), para depurar")
    sub.add_parser("env", help="las variables de Ansible que salen del fichero, para bin/lab")

    args = ap.parse_args(argv)

    if args.verbo == "ruta":
        print(args.entorno or RUTA)
        return 0
    if args.verbo == "mostrar":
        mostrar(args.entorno)
        return 0
    if args.verbo == "env":
        exports(args.entorno)
        return 0
    if args.verbo == "api":
        creds = api(args.entorno)
        ancho = max(len(k) for k in creds)
        for clave, valor in creds.items():
            print(f"  {clave.ljust(ancho)}  {_tapado('pve_api_token_secret' if clave == 'token_secret' else clave, valor)}")
        return 0
    if args.verbo == "crear":
        destino, pendientes = crear(args.entorno, desde_secrets=args.desde_secrets,
                                    forzar=args.forzar, manifiesto=args.manifiesto)
        print(f"escrito {destino} (0600)")
        if pendientes:
            print("quedan con el valor de la plantilla, revísalos:")
            for clave in pendientes:
                print(f"  - {clave}")
        print(f"\ncomprueba que está bien: python3 {os.path.relpath(__file__, RAIZ)} verificar")
        return 0

    errores, avisos = verificar(args.entorno, args.manifiesto,
                                detallado=getattr(args, "detallado", False))
    for aviso in avisos:
        print(f"  aviso: {aviso}")
    for error in errores:
        print(f"  ERROR: {error}")
    if errores:
        print(f"\n{len(errores)} cosa(s) que arreglar en {args.entorno or RUTA}.")
        return 1
    print(f"  el entorno de {(args.entorno or RUTA)} está completo y es utilizable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
