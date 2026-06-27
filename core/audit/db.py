"""Conexion y esquema de la base SQLite compartida.

Una sola base de datos para todo el sistema: procesamientos (estado y fallos del
worker), bitacora (auditoria de agregar/editar/eliminar/restaurar) y registro_piezas
(que pieza Parquet genero cada archivo subido). Es compartida entre todos los usuarios
y entre el dashboard y el worker.
"""

import sqlite3
from pathlib import Path

RUTA_BASE_DATOS = Path(__file__).resolve().parents[2] / "data" / "sistema.db"

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
"""


def conectar(ruta_base_datos: Path | None = None) -> sqlite3.Connection:
    """Abre una conexion a la base SQLite, creando el esquema si todavia no existe."""
    if ruta_base_datos is None:
        ruta_base_datos = RUTA_BASE_DATOS
    ruta_base_datos.parent.mkdir(parents=True, exist_ok=True)
    conexion = sqlite3.connect(ruta_base_datos)
    conexion.row_factory = sqlite3.Row
    conexion.executescript(ESQUEMA_SQL)
    return conexion
