"""Mapeo municipio -> subregion, leido desde el archivo de configuracion intercambiable
config/subregiones.csv. El mapeo es por codigo DIVIPOLA de municipio, no por nombre (los
nombres varian en tildes y espacios y rompen el join). No se guarda como columna del
dato procesado: se deriva en memoria donde se necesite, asi que cambiar este unico
archivo reagrupa todo sin reprocesar ninguna pieza.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

RUTA_SUBREGIONES = Path(__file__).parent / "config" / "subregiones.csv"


@st.cache_data
def obtener_mapeo_subregion() -> dict[int, str]:
    """Mapeo de cod_municipio (codigo DIVIPOLA, coincide con cod_mun_completo del dato
    limpio) a nombre de subregion.
    """
    subregiones = pd.read_csv(RUTA_SUBREGIONES)
    mapeo = subregiones.set_index("cod_municipio")["subregion"].to_dict()
    return mapeo
