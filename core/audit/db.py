"""Conexion y esquema de la base SQLite compartida.

Una sola base de datos para todo el sistema: procesamientos (estado y fallos del
worker), bitacora (auditoria de agregar/editar/eliminar/restaurar), registro_piezas
(que pieza Parquet genero cada archivo subido) y entrenamientos (bitacora de los
modelos de pronostico: entrenar, subir, activar y eliminar versiones; quien,
cuando, que modelo, con que rango de datos y cuanto tardo). Es compartida entre
todos los usuarios y entre el dashboard y el worker.
"""

import sqlite3
from pathlib import Path

RUTA_BASE_DATOS = Path(__file__).resolve().parents[2] / "data" / "sistema.db"

# Columnas de la tabla entrenamientos. modelo y familia llegaron con las
# versiones por modelo (antes una version traia los tres modelos juntos); las
# filas anteriores quedan con modelo y familia vacios. Las acciones subir y
# eliminar tambien son de esa epoca: ver _migrar_entrenamientos. detalle es un
# JSON con lo que hace falta para reconstruir el movimiento (ver
# core/audit/entrenamientos.py).
COLUMNAS_ENTRENAMIENTOS = """    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patologia TEXT NOT NULL,
    accion TEXT NOT NULL CHECK (accion IN ('entrenar', 'subir', 'activar', 'eliminar')),
    estado TEXT NOT NULL CHECK (estado IN ('listo', 'fallo')),
    modelo TEXT,
    familia TEXT,
    version TEXT,
    usuario TEXT NOT NULL,
    fecha_solicitud TEXT,
    fecha_inicio TEXT NOT NULL,
    fecha_fin TEXT NOT NULL,
    duracion_segundos REAL,
    rango_datos TEXT,
    motivo_fallo TEXT,
    detalle TEXT"""

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS procesamientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patologia TEXT NOT NULL,
    anio INTEGER NOT NULL,
    codigo INTEGER NOT NULL,
    archivo_original TEXT NOT NULL,
    estado TEXT NOT NULL CHECK (estado IN ('listo', 'fallo')),
    motivo_fallo TEXT,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS bitacora (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    accion TEXT NOT NULL CHECK (accion IN ('agregar', 'editar', 'eliminar', 'restaurar', 'eliminar_permanente')),
    patologia TEXT NOT NULL,
    anio INTEGER NOT NULL,
    codigo INTEGER NOT NULL,
    usuario TEXT NOT NULL,
    fecha TEXT NOT NULL,
    detalle TEXT
);

CREATE TABLE IF NOT EXISTS entrenamientos (
{COLUMNAS_ENTRENAMIENTOS}
);

CREATE TABLE IF NOT EXISTS registro_piezas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patologia TEXT NOT NULL,
    anio INTEGER NOT NULL,
    codigo INTEGER NOT NULL,
    archivo_original TEXT NOT NULL,
    ruta_pieza TEXT NOT NULL,
    activa INTEGER NOT NULL DEFAULT 1,
    fecha_creacion TEXT NOT NULL
);
""".replace("{COLUMNAS_ENTRENAMIENTOS}", COLUMNAS_ENTRENAMIENTOS)


def _migrar_entrenamientos(conexion: sqlite3.Connection) -> None:
    """Lleva la tabla entrenamientos del formato anterior (sin modelo ni
    familia, acciones solo entrenar/activar) al actual. SQLite no deja cambiar
    un CHECK, asi que se reconstruye la tabla conservando todas las filas.
    BEGIN IMMEDIATE + volver a mirar adentro: si el dashboard y el worker
    arrancan a la vez, solo uno migra."""
    columnas = [fila["name"] for fila in conexion.execute("PRAGMA table_info(entrenamientos)")]
    if "modelo" in columnas:
        _agregar_columna_detalle(conexion, columnas)
        return
    conexion.execute("BEGIN IMMEDIATE")
    try:
        columnas = [fila["name"] for fila in conexion.execute("PRAGMA table_info(entrenamientos)")]
        if "modelo" in columnas:
            conexion.execute("COMMIT")
            return
        conexion.execute("ALTER TABLE entrenamientos RENAME TO entrenamientos_anterior")
        conexion.execute(f"CREATE TABLE entrenamientos ({COLUMNAS_ENTRENAMIENTOS})")
        conexion.execute(
            """
            INSERT INTO entrenamientos (
                id, patologia, accion, estado, version, usuario, fecha_solicitud,
                fecha_inicio, fecha_fin, duracion_segundos, rango_datos, motivo_fallo
            )
            SELECT
                id, patologia, accion, estado, version, usuario, fecha_solicitud,
                fecha_inicio, fecha_fin, duracion_segundos, rango_datos, motivo_fallo
            FROM entrenamientos_anterior
            """
        )
        conexion.execute("DROP TABLE entrenamientos_anterior")
        conexion.execute("COMMIT")
    except Exception:
        conexion.execute("ROLLBACK")
        raise


def _agregar_columna_detalle(conexion: sqlite3.Connection, columnas: list[str]) -> None:
    """La columna detalle llego despues de modelo y familia: en una base que ya
    tenia esas columnas se agrega sola (ALTER TABLE ADD COLUMN, sin reconstruir).
    Si otro proceso la agrego primero, SQLite avisa con duplicate column y se ignora."""
    if "detalle" in columnas:
        return
    try:
        conexion.execute("ALTER TABLE entrenamientos ADD COLUMN detalle TEXT")
        conexion.commit()
    except sqlite3.OperationalError as error:
        if "duplicate column" not in str(error):
            raise


def conectar(ruta_base_datos: Path | None = None) -> sqlite3.Connection:
    """Abre una conexion a la base SQLite, creando el esquema si todavia no existe."""
    if ruta_base_datos is None:
        ruta_base_datos = RUTA_BASE_DATOS
    ruta_base_datos.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta_base_datos)
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA_SQL)
    _migrar_entrenamientos(conexion)
    return conexion
