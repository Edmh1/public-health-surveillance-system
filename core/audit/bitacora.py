"""Bitacora de auditoria: quien hizo que movimiento, sobre que pieza, y cuando.

Compartida entre todos los usuarios; solo la consultan Editor y Admin. La traza
de un movimiento sobrevive aunque la pieza misma desaparezca (ej. eliminar para siempre).
"""

from datetime import datetime, timezone

from core.audit.db import conectar

ACCIONES_VALIDAS = {"agregar", "editar", "eliminar", "restaurar", "eliminar_permanente"}


def registrar_movimiento(patologia: str, anio: int, codigo: int, accion: str, usuario: str, detalle: str | None = None) -> None:
    """Deja traza en la bitacora de un movimiento sobre una pieza (patologia+anio+codigo)."""
    if accion not in ACCIONES_VALIDAS:
        raise ValueError(f"Accion invalida: {accion}. Debe ser una de {sorted(ACCIONES_VALIDAS)}")

    fecha_movimiento = datetime.now(timezone.utc).isoformat()

    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            INSERT INTO bitacora (accion, patologia, anio, codigo, usuario, fecha, detalle)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (accion, patologia, anio, codigo, usuario, fecha_movimiento, detalle),
        )
    conexion.close()


def listar_movimientos(patologia: str | None = None) -> list[dict]:
    """Lista los movimientos de la bitacora, mas recientes primero."""
    conexion = conectar()

    if patologia is None:
        filas = conexion.execute("SELECT * FROM bitacora ORDER BY fecha DESC").fetchall()
    else:
        filas = conexion.execute(
            "SELECT * FROM bitacora WHERE patologia = ? ORDER BY fecha DESC", (patologia,)
        ).fetchall()

    conexion.close()

    movimientos = [dict(fila) for fila in filas]
    return movimientos
