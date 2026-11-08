"""Bitacora de los modelos de pronostico: entrenar, subir, activar y eliminar
versiones.

Tabla aparte de la bitacora de piezas (bitacora.py) porque una version de un
modelo no es una pieza anio+codigo: lo que importa es quien hizo que, sobre que
modelo y version, cuando, con que rango de datos y cuanto tardo. Compartida
entre todos los usuarios, como el resto de la base SQLite. La traza sobrevive
aunque la version se elimine: al eliminar, detalle guarda una copia de su
manifest (hiperparametros, metricas, rango). Al entrenar, detalle guarda lo que
se pidio (rango, hiperparametros, si se activaba); al subir, el nombre del .zip.
"""

import json

from core.audit.db import conectar

ACCION_ENTRENAR = "entrenar"
ACCION_SUBIR = "subir"
ACCION_ACTIVAR = "activar"
ACCION_ELIMINAR = "eliminar"

# Acciones que corren en el worker y avisan con un toast al terminar.
ACCIONES_DEL_WORKER = [ACCION_ENTRENAR, ACCION_SUBIR]


def registrar_movimiento(
    patologia: str,
    accion: str,
    estado: str,
    usuario: str,
    fecha_inicio: str,
    fecha_fin: str,
    modelo: str | None = None,
    familia: str | None = None,
    version: str | None = None,
    fecha_solicitud: str | None = None,
    duracion_segundos: float | None = None,
    rango_datos: str | None = None,
    motivo_fallo: str | None = None,
    detalle: dict | None = None,
) -> None:
    detalle_texto = None
    if detalle is not None:
        detalle_texto = json.dumps(detalle, ensure_ascii=False, default=str)
    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            INSERT INTO entrenamientos (
                patologia, accion, estado, modelo, familia, version, usuario,
                fecha_solicitud, fecha_inicio, fecha_fin, duracion_segundos,
                rango_datos, motivo_fallo, detalle
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patologia, accion, estado, modelo, familia, version, usuario,
                fecha_solicitud, fecha_inicio, fecha_fin, duracion_segundos,
                rango_datos, motivo_fallo, detalle_texto,
            ),
        )
    conexion.close()


def registrar_accion_inmediata(
    patologia: str,
    accion: str,
    usuario: str,
    fecha: str,
    modelo: str,
    familia: str | None,
    version: str,
    rango_datos: str | None,
    detalle: dict | None = None,
) -> None:
    """Activar o eliminar: acciones instantaneas desde la interfaz."""
    registrar_movimiento(
        patologia=patologia,
        accion=accion,
        estado="listo",
        usuario=usuario,
        fecha_inicio=fecha,
        fecha_fin=fecha,
        modelo=modelo,
        familia=familia,
        version=version,
        duracion_segundos=0.0,
        rango_datos=rango_datos,
        detalle=detalle,
    )


def listar_entrenamientos(patologia: str | None = None, usuario: str | None = None) -> list[dict]:
    """Movimientos de la bitacora, mas recientes primero."""
    condiciones = []
    parametros: list[str] = []
    if patologia is not None:
        condiciones.append("patologia = ?")
        parametros.append(patologia)
    if usuario is not None:
        condiciones.append("usuario = ?")
        parametros.append(usuario)

    consulta = "SELECT * FROM entrenamientos"
    if condiciones:
        consulta += " WHERE " + " AND ".join(condiciones)
    consulta += " ORDER BY fecha_fin DESC"

    conexion = conectar()
    filas = conexion.execute(consulta, parametros).fetchall()
    conexion.close()
    movimientos = []
    for fila in filas:
        movimiento = dict(fila)
        texto = movimiento.get("detalle")
        if texto:
            movimiento["detalle"] = json.loads(texto)
        movimientos.append(movimiento)
    return movimientos
