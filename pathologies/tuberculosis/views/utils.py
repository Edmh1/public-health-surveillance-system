"""Utilidades compartidas entre las vistas de tuberculosis."""

import pandas as pd
import streamlit as st

ETIQUETAS_TIPO_TB = {
    820: "Pulmonar",
    810: "Extrapulmonar",
    825: "Farmacorresistente",
}


def aplicar_filtro_tipo_tb(datos: pd.DataFrame) -> pd.DataFrame:
    """Filtro compartido de tipo de TB entre todas las pestanas.
    Usa session_state para que la seleccion persista al cambiar de tab.
    """
    opciones = sorted(ETIQUETAS_TIPO_TB.items(), key=lambda x: x[0])
    etiquetas_disponibles = [label for _, label in opciones]

    seleccionadas = st.pills(
        "Tipo de tuberculosis",
        options=etiquetas_disponibles,
        selection_mode="multi",
        default=[],
        key="filtro_tb_tipo",
    )

    if not seleccionadas:
        return datos

    codigos_seleccionados = [
        cod for cod, label in opciones if label in seleccionadas
    ]

    return datos[datos["cod_eve"].isin(codigos_seleccionados)]
