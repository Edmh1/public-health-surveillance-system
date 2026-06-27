"""Cola de trabajos: Redis + RQ. El dashboard encola y no espera; el worker atiende
un archivo a la vez, en fila, sin paralelismo.
"""

import os
from pathlib import Path

from redis import Redis
from rq import Queue
from rq.job import Job

NOMBRE_COLA = "procesamiento_piezas"


def conectar_redis() -> Redis:
    url_redis = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    return Redis.from_url(url_redis)


def obtener_cola() -> Queue:
    conexion_redis = conectar_redis()
    return Queue(NOMBRE_COLA, connection=conexion_redis)


def encolar_procesamiento(
    patologia: str,
    anio: int,
    codigo: int,
    ruta_archivo: Path,
    archivo_original: str,
    usuario: str,
) -> Job:
    """Encola el procesamiento de una pieza subida y ya confirmada por el usuario."""
    from core.ingestion.procesador import procesar_pieza

    cola = obtener_cola()
    trabajo = cola.enqueue(
        procesar_pieza,
        patologia=patologia,
        anio=anio,
        codigo=codigo,
        ruta_archivo=ruta_archivo,
        archivo_original=archivo_original,
        usuario=usuario,
    )
    return trabajo
