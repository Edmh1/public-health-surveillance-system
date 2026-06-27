"""Punto de entrada del worker: registra las patologias disponibles y atiende la
cola de Redis+RQ, un archivo a la vez.
"""

from rq import Worker

from core.ingestion.cola import NOMBRE_COLA, conectar_redis
from core.registry import registrar_patologia
from pathologies.dengue.plugin import DenguePathologyPlugin


def registrar_patologias_disponibles() -> None:
    registrar_patologia(DenguePathologyPlugin())


def main() -> None:
    registrar_patologias_disponibles()
    conexion_redis = conectar_redis()
    worker = Worker([NOMBRE_COLA], connection=conexion_redis)
    worker.work()


if __name__ == "__main__":
    main()
