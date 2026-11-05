"""Versiones de los modelos de pronostico exportados, por patologia.

data/<patologia>/modelos/<version>/   una carpeta por entrenamiento (modelos + manifest.json)
data/<patologia>/modelos/activo.json  que version usa el tablero

Nada se sobrescribe: cada entrenamiento es una version nueva y las anteriores se
conservan, con la posibilidad de volver a cualquiera. Un reentrenamiento con
datos incompletos nunca deja al sistema sin un modelo bueno al que volver.

Mismo principio de escritura atomica que el consolidado: el entrenamiento
escribe en una carpeta temporal, y solo cuando termino bien se promueve con un
cambio de nombre (os.replace). El puntero activo.json tambien se escribe aparte
y se cambia de golpe. El tablero nunca ve una version a medio escribir.
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from core.storage.rutas import DIR_DATA

_NOMBRE_PUNTERO = "activo.json"
_PREFIJO_TEMPORAL = "_en_curso_"


def directorio_modelos(patologia: str) -> Path:
    return DIR_DATA / patologia / "modelos"


def ruta_version(patologia: str, version: str) -> Path:
    return directorio_modelos(patologia) / version


def nueva_version() -> str:
    """Nombre de una version nueva: marca de tiempo UTC, ordenable como texto."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def preparar_carpeta_temporal(patologia: str, version: str) -> Path:
    carpeta = directorio_modelos(patologia) / f"{_PREFIJO_TEMPORAL}{version}"
    if carpeta.exists():
        shutil.rmtree(carpeta)
    carpeta.mkdir(parents=True)
    return carpeta


def descartar_carpeta_temporal(carpeta: Path) -> None:
    if carpeta.exists():
        shutil.rmtree(carpeta, ignore_errors=True)


def promover_version(patologia: str, carpeta_temporal: Path, version: str) -> Path:
    """Convierte la carpeta temporal en una version definitiva (cambio de nombre
    atomico). Nunca pisa una version existente."""
    destino = ruta_version(patologia, version)
    if destino.exists():
        raise FileExistsError(f"Ya existe la version {version}")
    os.replace(carpeta_temporal, destino)
    return destino


def leer_manifest(patologia: str, version: str) -> dict | None:
    ruta = ruta_version(patologia, version) / "manifest.json"
    if not ruta.exists():
        return None
    return json.loads(ruta.read_text(encoding="utf-8"))


def listar_versiones(patologia: str) -> list[str]:
    """Versiones completas (con manifest), de la mas reciente a la mas antigua."""
    directorio = directorio_modelos(patologia)
    if not directorio.exists():
        return []
    versiones = []
    for carpeta in directorio.iterdir():
        if not carpeta.is_dir():
            continue
        if carpeta.name.startswith(_PREFIJO_TEMPORAL):
            continue
        if not (carpeta / "manifest.json").exists():
            continue
        versiones.append(carpeta.name)
    return sorted(versiones, reverse=True)


def version_activa(patologia: str) -> str | None:
    """Version que usa el tablero. Si el puntero no existe o apunta a una
    version que ya no esta, se usa la mas reciente disponible."""
    versiones = listar_versiones(patologia)
    if not versiones:
        return None
    ruta_puntero = directorio_modelos(patologia) / _NOMBRE_PUNTERO
    if ruta_puntero.exists():
        contenido = json.loads(ruta_puntero.read_text(encoding="utf-8"))
        version_apuntada = contenido.get("version")
        if version_apuntada in versiones:
            return version_apuntada
    return versiones[0]


def activar_version(patologia: str, version: str, usuario: str) -> None:
    """Cambia la version activa escribiendo el puntero aparte y reemplazandolo
    de golpe (os.replace)."""
    if version not in listar_versiones(patologia):
        raise ValueError(f"No existe la version {version}")
    directorio = directorio_modelos(patologia)
    contenido = {
        "version": version,
        "activada_por": usuario,
        "fecha_activacion": datetime.now(timezone.utc).isoformat(),
    }
    ruta_temporal = directorio / f"{_NOMBRE_PUNTERO}.tmp"
    ruta_temporal.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(ruta_temporal, directorio / _NOMBRE_PUNTERO)
