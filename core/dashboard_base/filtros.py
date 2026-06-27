"""Filtros globales del dashboard.

Operan siempre sobre el dataframe ya cargado en session_state (core/dashboard_base/datos.py).
Cambiar un filtro nunca relee el consolidado del disco, solo indexa el dataframe en memoria.

Anio, semana epidemiologica, departamento, municipio y clasificacion del caso
ya son funcionales contra el esquema procesado de dengue. Quedan deshabilitados
con TODO:
- Situacion: depende del canal endemico, que se construye al final.
- Estratificacion de riesgo: depende de un Excel externo (todavia por definir)
  en pathologies/dengue/config/, cruzado por codigo DIVIPOLA de municipio.
"""

import pandas as pd
import streamlit as st

CLAVE_FILTROS = "filtros_globales"


def _opciones_de_columna(datos: pd.DataFrame, columna: str) -> list:
    if columna not in datos.columns:
        return []
    valores_sin_nulos = datos[columna].dropna().unique().tolist()
    return sorted(valores_sin_nulos)


def mostrar_filtros_globales(datos: pd.DataFrame, columna_anio: str) -> dict:
    """Dibuja los filtros globales en la barra lateral y devuelve los valores elegidos."""
    st.sidebar.subheader(":material/filter_alt: Filtros")

    anios_disponibles = _opciones_de_columna(datos, columna_anio)
    anios_elegidos = st.sidebar.multiselect("Anio", anios_disponibles, default=anios_disponibles)

    semanas_disponibles = _opciones_de_columna(datos, "semana")
    semanas_elegidas = st.sidebar.multiselect("Semana epidemiologica", semanas_disponibles)

    departamentos_disponibles = _opciones_de_columna(datos, "nom_dpto_o")
    departamentos_elegidos = st.sidebar.multiselect("Departamento", departamentos_disponibles)

    municipios_disponibles = _opciones_de_columna(datos, "nom_mun_o")
    municipios_elegidos = st.sidebar.multiselect("Municipio", municipios_disponibles)

    clasificaciones_disponibles = _opciones_de_columna(datos, "estado_final_de_caso")
    clasificaciones_elegidas = st.sidebar.multiselect("Clasificacion del caso", clasificaciones_disponibles)

    st.sidebar.selectbox(
        "Estratificacion de riesgo (pendiente del Excel externo por DIVIPOLA)",
        options=[],
        disabled=True,
    )
    st.sidebar.selectbox(
        "Situacion (pendiente del canal endemico)",
        options=[],
        disabled=True,
    )

    filtros = {
        columna_anio: anios_elegidos,
        "semana": semanas_elegidas,
        "nom_dpto_o": departamentos_elegidos,
        "nom_mun_o": municipios_elegidos,
        "estado_final_de_caso": clasificaciones_elegidas,
    }
    st.session_state[CLAVE_FILTROS] = filtros
    return filtros


def aplicar_filtros(datos: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """Filtra el dataframe en memoria segun los filtros elegidos. No toca el disco."""
    datos_filtrados = datos
    for columna, valores_elegidos in filtros.items():
        if not valores_elegidos:
            continue
        if columna not in datos_filtrados.columns:
            continue
        datos_filtrados = datos_filtrados[datos_filtrados[columna].isin(valores_elegidos)]
    return datos_filtrados
