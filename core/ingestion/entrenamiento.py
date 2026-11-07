"""Trabajos del worker para los modelos de pronostico: entrenar una version en la
app o importar una version subida en un .zip (entrenada en otro equipo).

Los lanza el perfil de administracion desde Gestion. Entrenar una red o validar
walk-forward no puede bloquear la interfaz, y cargar un modelo subido importa
librerias pesadas, asi que ambos van a la MISMA cola que el procesamiento de
piezas del SIVIGILA (core/ingestion/cola.py): un trabajo a la vez, en fila, y
nunca en paralelo con una carga que este reescribiendo el consolidado.

Pasos comunes: lee el consolidado oficial, pide al plugin que entrene (o que
revise el paquete) en una carpeta temporal, promueve esa carpeta a version nueva
del modelo (sin pisar las anteriores), la activa en su familia si se pidio o si
la familia no tenia ninguna, y registra en la bitacora quien, cuando, que modelo
y con que datos. Si algo falla, se descarta la carpeta temporal, ninguna version
cambia y el fallo queda registrado con su motivo.
"""

import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from core.audit.entrenamientos import ACCION_ENTRENAR, ACCION_SUBIR, registrar_movimiento
from core.ingestion.cola import obtener_cola
from core.registry import obtener_patologia
from core.storage import modelos, rutas
from core.storage.consolidado import cargar_consolidado

# Tiempo maximo del trabajo en el worker. El default de RQ (3 minutos) no alcanza
# para entrenar y validar una red en CPU.
TIEMPO_MAXIMO_TRABAJO = "1h"


def describir_rango(rango: dict) -> str:
    """'2007 (sem. 1) a 2025 (sem. 52)' a partir del rango del manifest."""
    return (
        f"{rango['anio_inicio']} (sem. {rango['semana_inicio']}) a "
        f"{rango['anio_fin']} (sem. {rango['semana_fin']})"
    )


def _a_texto(fecha: pd.Timestamp | None) -> str | None:
    if fecha is None:
        return None
    return pd.Timestamp(fecha).strftime("%Y-%m-%d")


def _a_fecha(texto: str | None) -> pd.Timestamp | None:
    if texto is None:
        return None
    return pd.Timestamp(texto)


def encolar_entrenamiento(
    patologia: str,
    modelo: str,
    desde: pd.Timestamp | None,
    hasta: pd.Timestamp | None,
    hiperparametros: dict | None,
    activar: bool,
    usuario: str,
    fecha_solicitud: str,
):
    cola = obtener_cola()
    return cola.enqueue(
        ejecutar_entrenamiento,
        patologia=patologia,
        modelo=modelo,
        desde=_a_texto(desde),
        hasta=_a_texto(hasta),
        hiperparametros=hiperparametros,
        activar=activar,
        usuario=usuario,
        fecha_solicitud=fecha_solicitud,
        job_timeout=TIEMPO_MAXIMO_TRABAJO,
    )


def encolar_importacion(
    patologia: str,
    ruta_zip: Path,
    nombre_original: str,
    activar: bool,
    usuario: str,
    fecha_solicitud: str,
):
    cola = obtener_cola()
    return cola.enqueue(
        ejecutar_importacion,
        patologia=patologia,
        ruta_zip=str(ruta_zip),
        nombre_original=nombre_original,
        activar=activar,
        usuario=usuario,
        fecha_solicitud=fecha_solicitud,
        job_timeout=TIEMPO_MAXIMO_TRABAJO,
    )


def _cargar_datos_y_modulo(patologia: str):
    plugin = obtener_patologia(patologia)
    modulo_pronostico = plugin.obtener_pronostico()
    if modulo_pronostico is None:
        raise ValueError(f"La patología {patologia} no tiene pronóstico.")
    datos = cargar_consolidado(rutas.ruta_consolidado(patologia))
    if datos is None or datos.empty:
        raise ValueError("No hay consolidado cargado.")
    return modulo_pronostico, datos


def _guardar_y_activar(
    patologia: str, carpeta_temporal: Path, manifest: dict, version: str, activar: bool, usuario: str
) -> str:
    """Promueve la version y la activa si corresponde. Devuelve el nombre final
    de la version (puede llevar sufijo si el nombre ya estaba tomado)."""
    clave_modelo = manifest["modelo"]
    familia = manifest["familia"]
    version_final = modelos.promover_version(patologia, carpeta_temporal, clave_modelo, version)
    familia_sin_activo = familia not in modelos.leer_activos(patologia)
    if activar or familia_sin_activo:
        modelos.activar_version(patologia, clave_modelo, version_final, usuario)
    return version_final


def ejecutar_entrenamiento(
    patologia: str,
    modelo: str,
    desde: str | None,
    hasta: str | None,
    hiperparametros: dict | None,
    activar: bool,
    usuario: str,
    fecha_solicitud: str | None = None,
) -> str | None:
    """Job del worker. Devuelve la version creada, o None si fallo."""
    fecha_inicio = datetime.now(timezone.utc).isoformat()
    reloj_inicio = time.monotonic()
    version = modelos.nueva_version()
    carpeta_temporal = None
    familia = None
    detalle = {
        "solicitado": {
            "desde": desde,
            "hasta": hasta,
            "hiperparametros": hiperparametros,
            "activar": activar,
        }
    }

    try:
        modulo_pronostico, datos = _cargar_datos_y_modulo(patologia)
        clase = modulo_pronostico.catalogo().get(modelo)
        if clase is not None:
            familia = clase.familia
        carpeta_temporal = modelos.preparar_carpeta_temporal(patologia, version)
        manifest = modulo_pronostico.entrenar_y_exportar(
            datos, modelo, _a_fecha(desde), _a_fecha(hasta), hiperparametros, carpeta_temporal, usuario
        )
        version = _guardar_y_activar(patologia, carpeta_temporal, manifest, version, activar, usuario)
    except Exception as error:
        if carpeta_temporal is not None:
            modelos.descartar_carpeta_temporal(carpeta_temporal)
        registrar_movimiento(
            patologia=patologia,
            accion=ACCION_ENTRENAR,
            estado="fallo",
            detalle=detalle,
            usuario=usuario,
            fecha_inicio=fecha_inicio,
            fecha_fin=datetime.now(timezone.utc).isoformat(),
            modelo=modelo,
            familia=familia,
            fecha_solicitud=fecha_solicitud,
            duracion_segundos=round(time.monotonic() - reloj_inicio, 1),
            motivo_fallo=str(error),
        )
        return None

    registrar_movimiento(
        patologia=patologia,
        accion=ACCION_ENTRENAR,
        estado="listo",
        detalle=detalle,
        usuario=usuario,
        fecha_inicio=fecha_inicio,
        fecha_fin=datetime.now(timezone.utc).isoformat(),
        modelo=manifest["modelo"],
        familia=manifest["familia"],
        version=version,
        fecha_solicitud=fecha_solicitud,
        duracion_segundos=round(time.monotonic() - reloj_inicio, 1),
        rango_datos=describir_rango(manifest["rango"]),
    )
    return version


def ejecutar_importacion(
    patologia: str,
    ruta_zip: str,
    nombre_original: str,
    activar: bool,
    usuario: str,
    fecha_solicitud: str | None = None,
) -> str | None:
    """Job del worker. Descomprime el .zip de forma segura, pide al plugin que
    lo revise (carga y pronostico de prueba) y lo guarda como version nueva.
    El .zip se borra siempre al terminar: igual que un Excel malo, un paquete
    malo no se guarda; el motivo queda en la bitacora."""
    fecha_inicio = datetime.now(timezone.utc).isoformat()
    reloj_inicio = time.monotonic()
    version = modelos.nueva_version()
    carpeta_temporal = None
    manifest = None
    detalle = {"archivo": nombre_original, "activar": activar}

    try:
        modulo_pronostico, datos = _cargar_datos_y_modulo(patologia)
        carpeta_temporal = modelos.preparar_carpeta_temporal(patologia, version)
        modelos.extraer_zip_seguro(Path(ruta_zip), carpeta_temporal)
        manifest = modulo_pronostico.importar(carpeta_temporal, datos, usuario)
        version = _guardar_y_activar(patologia, carpeta_temporal, manifest, version, activar, usuario)
    except Exception as error:
        if carpeta_temporal is not None:
            modelos.descartar_carpeta_temporal(carpeta_temporal)
        registrar_movimiento(
            patologia=patologia,
            accion=ACCION_SUBIR,
            estado="fallo",
            detalle=detalle,
            usuario=usuario,
            fecha_inicio=fecha_inicio,
            fecha_fin=datetime.now(timezone.utc).isoformat(),
            modelo=manifest.get("modelo") if manifest else None,
            familia=manifest.get("familia") if manifest else None,
            fecha_solicitud=fecha_solicitud,
            duracion_segundos=round(time.monotonic() - reloj_inicio, 1),
            motivo_fallo=f"{nombre_original}: {error}",
        )
        return None
    finally:
        Path(ruta_zip).unlink(missing_ok=True)

    registrar_movimiento(
        patologia=patologia,
        accion=ACCION_SUBIR,
        estado="listo",
        detalle=detalle,
        usuario=usuario,
        fecha_inicio=fecha_inicio,
        fecha_fin=datetime.now(timezone.utc).isoformat(),
        modelo=manifest["modelo"],
        familia=manifest["familia"],
        version=version,
        fecha_solicitud=fecha_solicitud,
        duracion_segundos=round(time.monotonic() - reloj_inicio, 1),
        rango_datos=describir_rango(manifest["rango"]),
    )
    return version
