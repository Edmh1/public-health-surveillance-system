"""Registro de piezas: que pieza Parquet genero cada archivo subido.

No reemplaza la papelera ni decide su logica de conflicto al restaurar; solo lleva
la cuenta de que pieza corresponde a que archivo y si esta activa.
"""

from datetime import datetime, timezone

from core.audit.db import conectar


def registrar_pieza(patologia: str, anio: int, codigo: int, archivo_original: str, ruta_pieza: str) -> None:
    """Registra la pieza generada al procesar un archivo subido."""
    fecha_creacion = datetime.now(timezone.utc).isoformat()

    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            INSERT INTO registro_piezas (patologia, anio, codigo, archivo_original, ruta_pieza, activa, fecha_creacion)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (patologia, anio, codigo, archivo_original, str(ruta_pieza), fecha_creacion),
        )
    conexion.close()


def obtener_pieza_activa(patologia: str, anio: int, codigo: int) -> dict | None:
    """Devuelve el registro de la pieza activa para patologia+anio+codigo, o None si no hay ninguna."""
    conexion = conectar()
    fila = conexion.execute(
        """
        SELECT * FROM registro_piezas
        WHERE patologia = ? AND anio = ? AND codigo = ? AND activa = 1
        ORDER BY fecha_creacion DESC
        LIMIT 1
        """,
        (patologia, anio, codigo),
    ).fetchone()
    conexion.close()

    if fila is None:
        return None
    return dict(fila)


def listar_piezas(patologia: str | None = None) -> list[dict]:
    """Lista el registro de piezas, mas recientes primero."""
    conexion = conectar()

    if patologia is None:
        filas = conexion.execute("SELECT * FROM registro_piezas ORDER BY fecha_creacion DESC").fetchall()
    else:
        filas = conexion.execute(
            "SELECT * FROM registro_piezas WHERE patologia = ? ORDER BY fecha_creacion DESC", (patologia,)
        ).fetchall()

    conexion.close()

    piezas = [dict(fila) for fila in filas]
    return piezas
