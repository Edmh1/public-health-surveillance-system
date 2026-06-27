"""Procesador de piezas: el trabajo que el worker ejecuta para cada archivo subido.

Pasos por pieza, en orden: leer el Excel con el lector rapido, limpiar con el
clean de la patologia, guardar el Parquet individual, consolidar, y marcar el
estado en SQLite con su traza en la bitacora. Si algo falla, no se guarda el
Excel ni se toca el consolidado o la pieza activa anterior; solo se documenta
el motivo del fallo.
"""

from pathlib import Path

import pandas as pd

from core.audit.bitacora import registrar_movimiento
from core.audit.procesamientos import registrar_procesamiento_exitoso, registrar_procesamiento_fallido
from core.audit.registro_piezas import marcar_pieza_inactiva, obtener_pieza_activa, registrar_pieza
from core.registry import obtener_patologia
from core.storage import rutas
from core.storage.consolidado import agregar_pieza
from core.storage.piezas import guardar_pieza


def _leer_excel(ruta_archivo: Path) -> pd.DataFrame:
    """Lee un Excel del SIVIGILA (.xls o .xlsx) con el lector rapido para archivos grandes."""
    datos_crudos = pd.read_excel(ruta_archivo, engine="calamine", dtype=str)
    return datos_crudos


def procesar_pieza(
    patologia: str,
    anio: int,
    codigo: int,
    ruta_archivo: Path,
    archivo_original: str,
    usuario: str,
    directorio_piezas: Path | None = None,
    ruta_consolidado: Path | None = None,
) -> None:
    """Procesa una pieza subida de punta a punta. Es el job que ejecuta el worker de RQ."""
    if directorio_piezas is None:
        directorio_piezas = rutas.directorio_piezas(patologia)
    if ruta_consolidado is None:
        ruta_consolidado = rutas.ruta_consolidado(patologia)

    try:
        plugin = obtener_patologia(patologia)
        datos_crudos = _leer_excel(ruta_archivo)
        datos_limpios = plugin.limpiar(datos_crudos)
    except Exception as error:
        registrar_procesamiento_fallido(patologia, anio, codigo, archivo_original, usuario, motivo_fallo=str(error))
        Path(ruta_archivo).unlink(missing_ok=True)
        return

    pieza_existente = obtener_pieza_activa(patologia, anio, codigo)
    accion = "editar" if pieza_existente is not None else "agregar"

    guardar_pieza(directorio_piezas, anio, codigo, datos_limpios)
    agregar_pieza(ruta_consolidado, plugin.columna_anio, plugin.columna_codigo, anio, codigo, datos_limpios)

    if pieza_existente is not None:
        marcar_pieza_inactiva(patologia, anio, codigo)
    ruta_pieza_guardada = directorio_piezas / f"{anio}_{codigo}.parquet"
    registrar_pieza(patologia, anio, codigo, archivo_original, str(ruta_pieza_guardada))

    registrar_procesamiento_exitoso(patologia, anio, codigo, archivo_original, usuario)
    registrar_movimiento(patologia, anio, codigo, accion, usuario)

    Path(ruta_archivo).unlink(missing_ok=True)
