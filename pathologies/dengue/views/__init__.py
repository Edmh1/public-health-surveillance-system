"""Las 5 pestanas del dashboard de dengue: Tendencia, Situacion, Sociodemografica,
Morbilidad y Mortalidad. Tendencia ya esta construida (ver tendencia.py); el resto
sigue como esqueleto (estado vacio) hasta que se construyan sus graficos; ver
CLAUDE.md para el detalle de cada pestana.
"""

import pandas as pd
import streamlit as st

from pathologies.dengue.views.morbilidad import mostrar_morbilidad
from pathologies.dengue.views.mortalidad import mostrar_mortalidad
from pathologies.dengue.views.sociodemografica import mostrar_sociodemografica
from pathologies.dengue.views.tendencia import mostrar_tendencia


def _mostrar_pendiente(mensaje: str) -> None:
    st.info(f":material/construction: {mensaje}")


def mostrar_situacion(datos: pd.DataFrame) -> None:
    _mostrar_pendiente(
        "Esta pestana mostrara los KPIs (incidencia, mortalidad, letalidad), el canal "
        "endemico y el pronostico de corto plazo. Se construye pronto."
    )






def obtener_vistas_dengue() -> list[tuple[str, callable]]:
    """Nombre de cada pestana y su funcion de render, en el orden en que se muestran."""
    return [
        ("Tendencia", mostrar_tendencia),
        ("Situacion", mostrar_situacion),
        ("Sociodemografica", mostrar_sociodemografica),
        ("Morbilidad", mostrar_morbilidad),
        ("Mortalidad", mostrar_mortalidad),
    ]
