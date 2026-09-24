"""Vistas del dashboard de tuberculosis: 5 pestanas en orden.
Situacion primero (resumen ejecutivo de como estamos ahora).
"""

from pathologies.tuberculosis.views.morbilidad import mostrar_morbilidad
from pathologies.tuberculosis.views.mortalidad import mostrar_mortalidad
from pathologies.tuberculosis.views.situacion import mostrar_situacion
from pathologies.tuberculosis.views.sociodemografica import mostrar_sociodemografica
from pathologies.tuberculosis.views.tendencia import mostrar_tendencia


def obtener_vistas_tb() -> list[tuple[str, callable]]:
    """Nombre de cada pestana y su funcion de render, en el orden en que se muestran."""
    return [
        ("Situación", mostrar_situacion),
        ("Tendencia", mostrar_tendencia),
        ("Sociodemográfica", mostrar_sociodemografica),
        ("Morbilidad", mostrar_morbilidad),
        ("Mortalidad", mostrar_mortalidad),
    ]
