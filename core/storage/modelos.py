"""Versiones de los modelos de pronostico exportados, por patologia y por modelo.

data/<patologia>/modelos/<modelo>/<version>/   una carpeta por version de cada
                                               modelo (archivos + manifest.json)
data/<patologia>/modelos/activos.json          version activa de cada familia

Igual que las piezas de datos, cada modelo tiene sus propias versiones: se puede
entrenar, subir, activar o eliminar una sin tocar las demas. La pestana
Pronostico muestra la version activa de cada familia (la familia la declara el
manifest de la version; el nucleo no sabe cuales hay).

Regla de eliminacion: la version activa de una familia NO se puede eliminar
(primero hay que activar otra). Asi el puntero nunca apunta a algo que no
existe. La eliminacion es directa y definitiva (con confirmacion en la
interfaz); la traza queda en la bitacora de entrenamientos.

Escritura atomica, mismo principio que el consolidado: una version se escribe en
una carpeta temporal y solo cuando esta completa se promueve con un cambio de
nombre (os.replace). activos.json tambien se escribe aparte y se cambia de golpe.
Para eliminar, primero se renombra la carpeta (sale de la lista al instante) y
despues se borra: nunca queda a la vista una version a medio borrar.

Carpetas que empiezan con "_" (temporales, respaldos) no son modelos.
"""

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from core.storage.rutas import DIR_DATA

_NOMBRE_ACTIVOS = "activos.json"
_NOMBRE_MANIFEST = "manifest.json"
_PREFIJO_INTERNO = "_"
_PREFIJO_TEMPORAL = "_en_curso_"
_PREFIJO_ELIMINANDO = "_eliminando_"
_CARPETA_SUBIDAS = "_subidas"

# Limites del .zip de un modelo subido: muy por encima de lo que pesa un modelo
# real (unos pocos MB), pero cortan un archivo malicioso que se infla al
# descomprimir.
TAMANO_MAXIMO_ZIP_MB = 200
_TAMANO_MAXIMO_DESCOMPRIMIDO = 1024 * 1024 * 1024
_ARCHIVOS_MAXIMOS_ZIP = 50


def directorio_modelos(patologia: str) -> Path:
    return DIR_DATA / patologia / "modelos"


def ruta_version(patologia: str, modelo: str, version: str) -> Path:
    return directorio_modelos(patologia) / modelo / version


def nueva_version() -> str:
    """Nombre de una version nueva: marca de tiempo UTC, ordenable como texto."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ---------------------------------------------------------------------------
# Escritura de versiones
# ---------------------------------------------------------------------------

def preparar_carpeta_temporal(patologia: str, version: str) -> Path:
    carpeta = directorio_modelos(patologia) / f"{_PREFIJO_TEMPORAL}{version}"
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    return carpeta


def descartar_carpeta_temporal(carpeta: Path) -> None:
    if carpeta.exists():
        shutil.rmtree(carpeta, ignore_errors=True)


def _version_libre(patologia: str, modelo: str, version: str) -> str:
    """El nombre de version es la hora con segundos: dos trabajos rapidos (un
    XGBoost entrena en menos de un segundo) pueden coincidir. Si el nombre ya
    existe se le agrega _2, _3...; "_" ordena despues de "Z", asi que el orden
    cronologico como texto se mantiene."""
    candidato = version
    sufijo = 2
    while ruta_version(patologia, modelo, candidato).exists():
        candidato = f"{version}_{sufijo}"
        sufijo += 1
    return candidato


def promover_version(patologia: str, carpeta_temporal: Path, modelo: str, version: str) -> str:
    """Convierte la carpeta temporal en una version definitiva del modelo
    (cambio de nombre atomico). Nunca pisa una version existente: si el nombre
    ya esta tomado usa el siguiente libre. Devuelve el nombre final de la
    version. La carpeta temporal debe traer su manifest.json."""
    if not (carpeta_temporal / _NOMBRE_MANIFEST).exists():
        raise ValueError("La versión no tiene manifest.json.")
    version_final = _version_libre(patologia, modelo, version)
    destino = ruta_version(patologia, modelo, version_final)
    destino.parent.mkdir(parents=True, exist_ok=True)
    os.replace(carpeta_temporal, destino)
    return version_final


# ---------------------------------------------------------------------------
# Paquetes .zip subidos
# ---------------------------------------------------------------------------

def directorio_subidas(patologia: str) -> Path:
    """Donde la interfaz deja el .zip subido hasta que el worker lo procesa."""
    return directorio_modelos(patologia) / _CARPETA_SUBIDAS


def extraer_zip_seguro(ruta_zip: Path, carpeta_destino: Path) -> None:
    """Descomprime el paquete de un modelo en carpeta_destino, con los archivos
    en la raiz. Acepta los archivos en la raiz del .zip o dentro de una sola
    carpeta. Rechaza rutas absolutas o con "..", subcarpetas anidadas,
    demasiados archivos o un tamano descomprimido desmedido."""
    if not zipfile.is_zipfile(ruta_zip):
        raise ValueError("El archivo subido no es un .zip válido.")

    with zipfile.ZipFile(ruta_zip) as archivo_zip:
        entradas = [entrada for entrada in archivo_zip.infolist() if not entrada.is_dir()]
        if not entradas:
            raise ValueError("El .zip está vacío.")
        if len(entradas) > _ARCHIVOS_MAXIMOS_ZIP:
            raise ValueError(f"El .zip trae más de {_ARCHIVOS_MAXIMOS_ZIP} archivos.")
        tamano_total = sum(entrada.file_size for entrada in entradas)
        if tamano_total > _TAMANO_MAXIMO_DESCOMPRIMIDO:
            raise ValueError("El contenido del .zip es demasiado grande.")

        rutas_internas = []
        for entrada in entradas:
            ruta_interna = PurePosixPath(entrada.filename.replace("\\", "/"))
            if ruta_interna.is_absolute() or ".." in ruta_interna.parts:
                raise ValueError(f"Ruta no permitida dentro del .zip: {entrada.filename}")
            if len(ruta_interna.parts) > 2:
                raise ValueError(f"El .zip tiene carpetas anidadas: {entrada.filename}")
            rutas_internas.append(ruta_interna)

        carpetas_raiz = {ruta.parts[0] for ruta in rutas_internas if len(ruta.parts) == 2}
        hay_archivos_en_raiz = any(len(ruta.parts) == 1 for ruta in rutas_internas)
        if len(carpetas_raiz) > 1 or (carpetas_raiz and hay_archivos_en_raiz):
            raise ValueError("Los archivos del .zip deben ir en la raíz o dentro de una sola carpeta.")

        carpeta_destino.mkdir(parents=True, exist_ok=True)
        for entrada, ruta_interna in zip(entradas, rutas_internas):
            nombre = ruta_interna.name
            destino = carpeta_destino / nombre
            if destino.exists():
                raise ValueError(f"El .zip trae dos archivos con el nombre {nombre}.")
            with archivo_zip.open(entrada) as origen, open(destino, "wb") as salida:
                shutil.copyfileobj(origen, salida)


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def leer_manifest(patologia: str, modelo: str, version: str) -> dict | None:
    ruta = ruta_version(patologia, modelo, version) / _NOMBRE_MANIFEST
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def _es_carpeta_publica(carpeta: Path) -> bool:
    return carpeta.is_dir() and not carpeta.name.startswith(_PREFIJO_INTERNO)


def listar_versiones(patologia: str, modelo: str | None = None) -> list[dict]:
    """Versiones completas (con manifest), de la mas reciente a la mas antigua.
    Cada elemento: {"modelo", "version", "manifest"}. Con modelo, solo las de
    ese modelo."""
    directorio = directorio_modelos(patologia)
    if not directorio.exists():
        return []

    carpetas_modelo = []
    if modelo is not None:
        carpetas_modelo.append(directorio / modelo)
    else:
        for carpeta in directorio.iterdir():
            if _es_carpeta_publica(carpeta):
                carpetas_modelo.append(carpeta)

    versiones = []
    for carpeta_modelo in carpetas_modelo:
        if not carpeta_modelo.exists():
            continue
        for carpeta_version in carpeta_modelo.iterdir():
            if not _es_carpeta_publica(carpeta_version):
                continue
            ruta_manifest = carpeta_version / _NOMBRE_MANIFEST
            if not ruta_manifest.exists():
                continue
            manifest = json.loads(ruta_manifest.read_text(encoding="utf-8"))
            versiones.append({
                "modelo": carpeta_modelo.name,
                "version": carpeta_version.name,
                "manifest": manifest,
            })
    versiones.sort(key=lambda elemento: elemento["version"], reverse=True)
    return versiones


def _leer_archivo_activos(patologia: str) -> dict:
    ruta = directorio_modelos(patologia) / _NOMBRE_ACTIVOS
    if not ruta.exists():
        return {}
    return json.loads(ruta.read_text(encoding="utf-8"))


def _escribir_archivo_activos(patologia: str, activos: dict) -> None:
    directorio = directorio_modelos(patologia)
    directorio.mkdir(parents=True, exist_ok=True)
    ruta_temporal = directorio / f"{_NOMBRE_ACTIVOS}.tmp"
    ruta_temporal.write_text(json.dumps(activos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(ruta_temporal, directorio / _NOMBRE_ACTIVOS)


def leer_activos(patologia: str) -> dict[str, dict]:
    """Version activa de cada familia que tenga alguna:
    {familia: {"modelo", "version", "activada_por", "fecha_activacion"}}.

    Si una familia no tiene puntero valido (archivo perdido o editado a mano)
    pero si tiene versiones, se usa la mas reciente de esa familia: la pestana
    nunca se queda sin modelo habiendo uno disponible."""
    activos_guardados = _leer_archivo_activos(patologia)
    versiones = listar_versiones(patologia)
    existentes = {(elemento["modelo"], elemento["version"]) for elemento in versiones}

    activos = {}
    for familia, puntero in activos_guardados.items():
        clave = (puntero.get("modelo"), puntero.get("version"))
        if clave in existentes:
            activos[familia] = puntero

    for elemento in versiones:
        familia = elemento["manifest"].get("familia")
        if familia is None or familia in activos:
            continue
        activos[familia] = {
            "modelo": elemento["modelo"],
            "version": elemento["version"],
            "activada_por": None,
            "fecha_activacion": None,
        }
    return activos


def es_version_activa(patologia: str, modelo: str, version: str) -> bool:
    for puntero in leer_activos(patologia).values():
        if puntero["modelo"] == modelo and puntero["version"] == version:
            return True
    return False


# ---------------------------------------------------------------------------
# Activar y eliminar
# ---------------------------------------------------------------------------

def activar_version(patologia: str, modelo: str, version: str, usuario: str) -> str:
    """Deja la version como activa de su familia (la que dice su manifest).
    Devuelve la familia."""
    manifest = leer_manifest(patologia, modelo, version)
    if manifest is None:
        raise ValueError(f"No existe la versión {version} del modelo {modelo}.")
    familia = manifest.get("familia")
    if not familia:
        raise ValueError(f"El manifest de {modelo}/{version} no declara familia.")

    activos = _leer_archivo_activos(patologia)
    activos[familia] = {
        "modelo": modelo,
        "version": version,
        "activada_por": usuario,
        "fecha_activacion": datetime.now(timezone.utc).isoformat(),
    }
    _escribir_archivo_activos(patologia, activos)
    return familia


def eliminar_version(patologia: str, modelo: str, version: str) -> None:
    """Elimina para siempre una version. Rechaza la version activa de su
    familia: primero hay que activar otra."""
    carpeta = ruta_version(patologia, modelo, version)
    if not carpeta.exists():
        raise ValueError(f"No existe la versión {version} del modelo {modelo}.")
    if es_version_activa(patologia, modelo, version):
        raise ValueError(
            "No se puede eliminar la versión activa de una familia. Activa primero otra "
            "versión de esa familia."
        )

    carpeta_eliminando = carpeta.parent / f"{_PREFIJO_ELIMINANDO}{version}"
    os.replace(carpeta, carpeta_eliminando)
    shutil.rmtree(carpeta_eliminando, ignore_errors=True)

    carpeta_modelo = carpeta.parent
    if not any(carpeta_modelo.iterdir()):
        carpeta_modelo.rmdir()
