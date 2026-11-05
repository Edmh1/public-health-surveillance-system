"""Bitacora de los reentrenamientos del pronostico y de los cambios de version.

Tabla aparte de la bitacora de piezas (bitacora.py) porque un entrenamiento no
es un movimiento sobre una pieza anio+codigo: lo que importa es quien lo lanzo,
cuando, con que rango de datos y cuanto tardo. Compartida entre todos los
usuarios, como el resto de la base SQLite.
"""

from core.audit.db import conectar


def registrar_entrenamiento(
    patologia: str,
    estado: str,
    usuario: str,
    fecha_solicitud: str | None,
    fecha_inicio: str,
    fecha_fin: str,
    duracion_segundos: float,
    version: str | None = None,
    rango_datos: str | None = None,
    motivo_fallo: str | None = None,
) -> None:
    _insertar(
        patologia, "entrenar", estado, version, usuario, fecha_solicitud,
        fecha_inicio, fecha_fin, duracion_segundos, rango_datos, motivo_fallo,
    )


def registrar_activacion(patologia: str, version: str, usuario: str, fecha: str, rango_datos: str | None) -> None:
    """Deja traza de un cambio manual de version activa (volver a una anterior)."""
    _insertar(patologia, "activar", "listo", version, usuario, None, fecha, fecha, 0.0, rango_datos, None)


def _insertar(
    patologia, accion, estado, version, usuario, fecha_solicitud,
    fecha_inicio, fecha_fin, duracion_segundos, rango_datos, motivo_fallo,
) -> None:
    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            INSERT INTO entrenamientos (
                patologia, accion, estado, version, usuario, fecha_solicitud,
                fecha_inicio, fecha_fin, duracion_segundos, rango_datos, motivo_fallo
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                patologia, accion, estado, version, usuario, fecha_solicitud,
                fecha_inicio, fecha_fin, duracion_segundos, rango_datos, motivo_fallo,
            ),
        )
    conexion.close()


def listar_entrenamientos(patologia: str | None = None, usuario: str | None = None) -> list[dict]:
    """Movimientos de la bitacora de entrenamientos, mas recientes primero."""
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
    return [dict(fila) for fila in filas]
