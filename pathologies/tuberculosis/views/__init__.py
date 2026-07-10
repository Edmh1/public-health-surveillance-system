"""Vistas del dashboard de tuberculosis: 5 pestanas en orden.
Tendencia, Situacion, Sociodemografica, Diagnostico, Resistencia.
"""

from pathologies.tuberculosis.views.diagnostico import mostrar_diagnostico
from pathologies.tuberculosis.views.resistencia import mostrar_resistencia
from pathologies.tuberculosis.views.situacion import mostrar_situacion
from pathologies.tuberculosis.views.sociodemografica import mostrar_sociodemografica
from pathologies.tuberculosis.views.tendencia import mostrar_tendencia


def obtener_vistas_tb() -> list[tuple[str, callable]]:
    """Nombre de cada pestana y su funcion de render, en el orden en que se muestran."""
    return [
        ("Tendencia", mostrar_tendencia),
        ("Situación", mostrar_situacion),
        ("Sociodemográfica", mostrar_sociodemografica),
        ("Diagnóstico", mostrar_diagnostico),
        ("Resistencia", mostrar_resistencia),
    ]
