"""Estado de procesamientos del worker: cada pieza subida queda registrada como lista o fallida.

Visible para Editor y Admin en el apartado de Procesamientos. Los datos previos
nunca se tocan cuando un procesamiento falla; solo se documenta el motivo aqui.
"""

from datetime import datetime, timezone

from core.audit.db import conectar


def registrar_procesamiento_exitoso(patologia: str, anio: int, codigo: int, archivo_original: str, usuario: str) -> None:
    """Registra que una pieza se proceso y se promovio correctamente."""
    _insertar_procesamiento(patologia, anio, codigo, archivo_original, usuario, estado="listo", motivo_fallo=None)


def registrar_procesamiento_fallido(
    patologia: str, anio: int, codigo: int, archivo_original: str, usuario: str, motivo_fallo: str
) -> None:
    """Registra que una pieza fallo al procesarse, con el motivo del fallo."""
    _insertar_procesamiento(patologia, anio, codigo, archivo_original, usuario, estado="fallo", motivo_fallo=motivo_fallo)


def _insertar_procesamiento(
    patologia: str, anio: int, codigo: int, archivo_original: str, usuario: str, estado: str, motivo_fallo: str | None
) -> None:
    fecha_procesamiento = datetime.now(timezone.utc).isoformat()

    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            INSERT INTO procesamientos (patologia, anio, codigo, archivo_original, estado, motivo_fallo, usuario, fecha)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (patologia, anio, codigo, archivo_original, estado, motivo_fallo, usuario, fecha_procesamiento),
        )
    conexion.close()


def listar_procesamientos(patologia: str | None = None, usuario: str | None = None) -> list[dict]:
    """Lista los procesamientos, exitosos y fallidos, mas recientes primero."""
    condiciones = []
    parametros: list[str] = []

    if patologia is not None:
        condiciones.append("patologia = ?")
        parametros.append(patologia)
    if usuario is not None:
        condiciones.append("usuario = ?")
        parametros.append(usuario)

    consulta = "SELECT * FROM procesamientos"
    if condiciones:
        consulta += " WHERE " + " AND ".join(condiciones)
    consulta += " ORDER BY fecha DESC"

    conexion = conectar()
    filas = conexion.execute(consulta, parametros).fetchall()
    conexion.close()

    procesamientos = [dict(fila) for fila in filas]
    return procesamientos
