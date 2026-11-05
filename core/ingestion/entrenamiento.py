"""Reentrenamiento del pronostico como trabajo del worker.

Lo lanza el perfil de administracion desde Gestion. Entrenar varios modelos (uno
de ellos una red LSTM) mas la validacion walk-forward completa no puede
bloquear la interfaz, asi que va a la MISMA cola que el procesamiento de piezas
del SIVIGILA (core/ingestion/cola.py): un trabajo a la vez, en fila, y un
entrenamiento nunca corre en paralelo con una carga que este reescribiendo el
consolidado.

Pasos: lee el consolidado oficial, pide al plugin que entrene, valide y exporte
en una carpeta temporal, promueve esa carpeta a version nueva (sin pisar las
anteriores), la deja activa y registra en la bitacora de entrenamientos quien lo
lanzo, cuando, con que rango de datos y cuanto tardo. Si algo falla, se descarta
la carpeta temporal, la version activa anterior sigue intacta y el fallo queda
registrado con su motivo.
"""

import time
from datetime import datetime, timezone

from core.audit.entrenamientos import registrar_entrenamiento
from core.ingestion.cola import obtener_cola
from core.registry import obtener_patologia
from core.storage import modelos, rutas
from core.storage.consolidado import cargar_consolidado

# Tiempo maximo del trabajo en el worker. El default de RQ (3 minutos) no alcanza
# para entrenar y validar una LSTM en CPU.
TIEMPO_MAXIMO_ENTRENAMIENTO = "1h"


def describir_rango(rango: dict) -> str:
    """'2007 (sem. 1) a 2025 (sem. 52)' a partir del rango del manifest."""
    return (
        f"{rango['anio_inicio']} (sem. {rango['semana_inicio']}) a "
        f"{rango['anio_fin']} (sem. {rango['semana_fin']})"
    )


def encolar_entrenamiento(patologia: str, usuario: str, fecha_solicitud: str):
    cola = obtener_cola()
    trabajo = cola.enqueue(
        ejecutar_entrenamiento,
        patologia=patologia,
        usuario=usuario,
        fecha_solicitud=fecha_solicitud,
        job_timeout=TIEMPO_MAXIMO_ENTRENAMIENTO,
    )
    return trabajo


def ejecutar_entrenamiento(patologia: str, usuario: str, fecha_solicitud: str | None = None) -> str | None:
    """Job del worker. Devuelve la version creada, o None si fallo."""
    fecha_inicio = datetime.now(timezone.utc).isoformat()
    reloj_inicio = time.monotonic()
    version = modelos.nueva_version()
    carpeta_temporal = None

    try:
        plugin = obtener_patologia(patologia)
        modulo_pronostico = plugin.obtener_pronostico()
        if modulo_pronostico is None:
            raise ValueError(f"La patología {patologia} no tiene pronóstico.")

        datos = cargar_consolidado(rutas.ruta_consolidado(patologia))
        if datos is None or datos.empty:
            raise ValueError("No hay consolidado cargado para entrenar.")

        carpeta_temporal = modelos.preparar_carpeta_temporal(patologia, version)
        manifest = modulo_pronostico.entrenar_y_exportar(datos, carpeta_temporal, usuario)
        modelos.promover_version(patologia, carpeta_temporal, version)
        modelos.activar_version(patologia, version, usuario)
    except Exception as error:
        if carpeta_temporal is not None:
            modelos.descartar_carpeta_temporal(carpeta_temporal)
        duracion = time.monotonic() - reloj_inicio
        registrar_entrenamiento(
            patologia=patologia,
            estado="fallo",
            usuario=usuario,
            fecha_solicitud=fecha_solicitud,
            fecha_inicio=fecha_inicio,
            fecha_fin=datetime.now(timezone.utc).isoformat(),
            duracion_segundos=round(duracion, 1),
            motivo_fallo=str(error),
        )
        return None

    duracion = time.monotonic() - reloj_inicio
    registrar_entrenamiento(
        patologia=patologia,
        estado="listo",
        usuario=usuario,
        fecha_solicitud=fecha_solicitud,
        fecha_inicio=fecha_inicio,
        fecha_fin=datetime.now(timezone.utc).isoformat(),
        duracion_segundos=round(duracion, 1),
        version=version,
        rango_datos=describir_rango(manifest["rango"]),
    )
    return version
