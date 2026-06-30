"""Filtros globales del dashboard.

Operan siempre sobre el dataframe ya cargado en session_state (core/dashboard_base/datos.py).
Cambiar un filtro nunca relee el consolidado del disco, solo indexa el dataframe en memoria.

No existe filtro de departamento: el sistema es departamental del Magdalena, el departamento
es un techo fijo, no una variable (ver CLAUDE.md, "Alcance geografico y regla de tasas").
Subregion es el filtro territorial principal; municipio queda subordinado a la subregion
elegida. Subregion no es una columna del dato procesado: se deriva en memoria a partir de
cod_mun_completo y el mapeo intercambiable de la patologia (config/subregiones.csv), asi
que cambiar ese archivo reagrupa todo sin reprocesar ninguna pieza.

Anio, semana epidemiologica, subregion, municipio y clasificacion del caso ya son
funcionales contra el esquema procesado de dengue. Quedan deshabilitados con TODO:
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


def _agregar_columna_subregion(datos: pd.DataFrame, mapeo_subregion: dict[int, str]) -> pd.DataFrame:
    """Deriva subregion en memoria desde cod_mun_completo. No se persiste en ningun lado."""
    if "cod_mun_completo" not in datos.columns:
        return datos.assign(subregion=pd.NA)
    datos_con_subregion = datos.copy()
    datos_con_subregion["subregion"] = datos_con_subregion["cod_mun_completo"].map(mapeo_subregion)
    return datos_con_subregion


def mostrar_filtros_globales(datos: pd.DataFrame, columna_anio: str, mapeo_subregion: dict[int, str]) -> dict:
    """Dibuja los filtros globales en la barra lateral y devuelve los valores elegidos."""
    st.sidebar.subheader(":material/filter_alt: Filtros")

    datos_con_subregion = _agregar_columna_subregion(datos, mapeo_subregion)

    anios_disponibles = _opciones_de_columna(datos, columna_anio)
    anios_elegidos = st.sidebar.multiselect("Anio", anios_disponibles, default=anios_disponibles)

    semanas_disponibles = _opciones_de_columna(datos, "semana")
    semanas_elegidas = st.sidebar.multiselect("Semana epidemiologica", semanas_disponibles)

    subregiones_disponibles = sorted(set(mapeo_subregion.values()))
    subregiones_elegidas = st.sidebar.multiselect("Subregion", subregiones_disponibles)

    if subregiones_elegidas:
        datos_para_municipios = datos_con_subregion[datos_con_subregion["subregion"].isin(subregiones_elegidas)]
    else:
        datos_para_municipios = datos_con_subregion
    municipios_disponibles = _opciones_de_columna(datos_para_municipios, "nom_mun_o")
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
        "subregion": subregiones_elegidas,
        "nom_mun_o": municipios_elegidos,
        "estado_final_de_caso": clasificaciones_elegidas,
    }
    st.session_state[CLAVE_FILTROS] = filtros
    return filtros


def aplicar_filtros(datos: pd.DataFrame, filtros: dict, mapeo_subregion: dict[int, str]) -> pd.DataFrame:
    """Filtra el dataframe en memoria segun los filtros elegidos. No toca el disco."""
    datos_filtrados = _agregar_columna_subregion(datos, mapeo_subregion)
    for columna, valores_elegidos in filtros.items():
        if not valores_elegidos:
            continue
        if columna not in datos_filtrados.columns:
            continue
        datos_filtrados = datos_filtrados[datos_filtrados[columna].isin(valores_elegidos)]
    return datos_filtrados
