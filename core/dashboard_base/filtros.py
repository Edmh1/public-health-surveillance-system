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
funcionales contra el esquema procesado de dengue. Quedan pendientes (agrupados en el
expander "Proximamente" en vez de un widget deshabilitado, para no aparentar un control
roto):
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


CLAVES_REINICIABLES = ("filtro_semana", "filtro_subregion", "filtro_municipio", "filtro_clasificacion")


def mostrar_filtros_globales(datos: pd.DataFrame, columna_anio: str, mapeo_subregion: dict[int, str]) -> dict:
    """Dibuja los filtros globales en la barra lateral, agrupados por tema, y devuelve
    los valores elegidos. Anio queda fuera de "Limpiar filtros": su default ya es
    "todos los anios", o sea que ya esta en su estado sin filtrar.
    """
    st.sidebar.subheader(":material/filter_alt: Filtros")

    if st.sidebar.button("Limpiar filtros", icon=":material/filter_alt_off:", width="stretch", key="limpiar_filtros"):
        for clave in CLAVES_REINICIABLES:
            st.session_state.pop(clave, None)
        st.rerun()

    datos_con_subregion = _agregar_columna_subregion(datos, mapeo_subregion)

    with st.sidebar.expander("Geografia", icon=":material/map:", expanded=True):
        subregiones_disponibles = sorted(set(mapeo_subregion.values()))
        subregiones_elegidas = st.pills(
            "Subregion (filtro territorial principal)",
            subregiones_disponibles,
            selection_mode="multi",
            default=[],
            key="filtro_subregion",
        )

        if subregiones_elegidas:
            datos_para_municipios = datos_con_subregion[datos_con_subregion["subregion"].isin(subregiones_elegidas)]
        else:
            datos_para_municipios = datos_con_subregion
        municipios_disponibles = _opciones_de_columna(datos_para_municipios, "nom_mun_o")
        municipios_elegidos = st.multiselect(
            "Municipio", municipios_disponibles, key="filtro_municipio"
        )

    with st.sidebar.expander("Periodo", icon=":material/calendar_today:", expanded=True):
        anios_disponibles = _opciones_de_columna(datos, columna_anio)
        anios_elegidos = st.multiselect(
            "Anio", anios_disponibles, default=anios_disponibles, key="filtro_anio"
        )

        semanas_disponibles = _opciones_de_columna(datos, "semana")
        semanas_elegidas = st.multiselect(
            "Semana epidemiologica", semanas_disponibles, key="filtro_semana"
        )

    with st.sidebar.expander("Caso", icon=":material/assignment:", expanded=True):
        clasificaciones_disponibles = _opciones_de_columna(datos, "estado_final_de_caso")
        clasificaciones_elegidas = st.multiselect(
            "Clasificacion del caso", clasificaciones_disponibles, key="filtro_clasificacion"
        )

    with st.sidebar.expander("Proximamente", icon=":material/schedule:", expanded=False):
        st.caption(
            ":material/construction: Estratificacion de riesgo: pendiente del Excel "
            "externo cruzado por codigo DIVIPOLA."
        )
        st.caption(":material/construction: Situacion: pendiente del canal endemico.")

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
