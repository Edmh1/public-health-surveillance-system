"""Conversion de fechas UTC (como se guardan en SQLite) a hora local de Colombia.

Todo el sistema guarda fechas en UTC (datetime.now(timezone.utc).isoformat()) para que
comparar y ordenar timestamps sea inambiguo entre dashboard y worker. Pero quien lee el
dashboard esta en Colombia (UTC-5, sin horario de verano), asi que la hora debe convertirse
en la capa de presentacion; de lo contrario la fecha sale bien pero la hora aparece
adelantada 5 horas.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

ZONA_COLOMBIA = ZoneInfo("America/Bogota")


def formatear_fecha_local(fecha_utc_iso: str) -> str:
    """Convierte un timestamp UTC en formato ISO a hora de Colombia, formato legible."""
    momento_utc = datetime.fromisoformat(fecha_utc_iso)
    momento_local = momento_utc.astimezone(ZONA_COLOMBIA)
    return momento_local.strftime("%Y-%m-%d %H:%M:%S")
