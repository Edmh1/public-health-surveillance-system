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


def obtener_pieza_en_papelera(patologia: str, anio: int, codigo: int) -> dict | None:
    """Devuelve el registro de la pieza en papelera (inactiva) para patologia+anio+codigo."""
    conexion = conectar()
    fila = conexion.execute(
        """
        SELECT * FROM registro_piezas
        WHERE patologia = ? AND anio = ? AND codigo = ? AND activa = 0
        ORDER BY fecha_creacion DESC
        LIMIT 1
        """,
        (patologia, anio, codigo),
    ).fetchone()
    conexion.close()

    if fila is None:
        return None
    return dict(fila)


def marcar_pieza_inactiva(patologia: str, anio: int, codigo: int) -> None:
    """Marca como inactiva la pieza activa de patologia+anio+codigo: se va a papelera."""
    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            UPDATE registro_piezas
            SET activa = 0
            WHERE id = (
                SELECT id FROM registro_piezas
                WHERE patologia = ? AND anio = ? AND codigo = ? AND activa = 1
                ORDER BY fecha_creacion DESC
                LIMIT 1
            )
            """,
            (patologia, anio, codigo),
        )
    conexion.close()


def marcar_pieza_activa(patologia: str, anio: int, codigo: int) -> None:
    """Marca como activa la pieza mas reciente en papelera de patologia+anio+codigo: se restaura."""
    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            UPDATE registro_piezas
            SET activa = 1
            WHERE id = (
                SELECT id FROM registro_piezas
                WHERE patologia = ? AND anio = ? AND codigo = ? AND activa = 0
                ORDER BY fecha_creacion DESC
                LIMIT 1
            )
            """,
            (patologia, anio, codigo),
        )
    conexion.close()


def marcar_activa_por_id(id_pieza: int) -> None:
    """Marca activa una fila puntual por su id. Usar cuando ya se sabe exactamente
    cual fila (no "la mas reciente"), como al restaurar reemplazando un conflicto.
    """
    conexion = conectar()
    with conexion:
        conexion.execute("UPDATE registro_piezas SET activa = 1 WHERE id = ?", (id_pieza,))
    conexion.close()


def marcar_inactiva_por_id(id_pieza: int) -> None:
    """Marca inactiva una fila puntual por su id. Ver marcar_activa_por_id."""
    conexion = conectar()
    with conexion:
        conexion.execute("UPDATE registro_piezas SET activa = 0 WHERE id = ?", (id_pieza,))
    conexion.close()


def eliminar_registro_pieza_por_id(id_pieza: int) -> None:
    """Elimina una fila puntual por su id: se usa cuando esa fila ya no representa
    ningun archivo real (ej. la pieza activa que se descarto al restaurar reemplazando).
    """
    conexion = conectar()
    with conexion:
        conexion.execute("DELETE FROM registro_piezas WHERE id = ?", (id_pieza,))
    conexion.close()


def eliminar_registro_pieza(patologia: str, anio: int, codigo: int) -> None:
    """Elimina el registro de la pieza mas reciente en papelera: se elimino para siempre."""
    conexion = conectar()
    with conexion:
        conexion.execute(
            """
            DELETE FROM registro_piezas
            WHERE id = (
                SELECT id FROM registro_piezas
                WHERE patologia = ? AND anio = ? AND codigo = ? AND activa = 0
                ORDER BY fecha_creacion DESC
                LIMIT 1
            )
            """,
            (patologia, anio, codigo),
        )
    conexion.close()


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


def listar_piezas_activas(patologia: str) -> list[dict]:
    """Piezas activas de la patologia: las que estan en piezas/ y en el consolidado."""
    return [pieza for pieza in listar_piezas(patologia) if pieza["activa"] == 1]


def listar_piezas_en_papelera(patologia: str) -> list[dict]:
    """Piezas inactivas de la patologia: las que estan en papelera/, fuera del consolidado."""
    return [pieza for pieza in listar_piezas(patologia) if pieza["activa"] == 0]
