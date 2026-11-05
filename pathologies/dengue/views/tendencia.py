"""Pestana 1 Tendencia.

Casos = cod_eve en {210, 220}. La mortalidad (580) va en Mortalidad.

Orden de arriba abajo:
  1. KPIs (casos totales, semana pico, municipio mas afectado).
  2. Par complementario: Casos por anio + Incidencia por subregion en el
     Magdalena (mapa). El mapa filtra la serie (regla 1.5 de DESIGN.md): al
     entrar a una subregion, a un municipio o a una zona del municipio, Casos
     por anio muestra solo ese territorio. En la reunion se habia pedido
     separarlas; se decidio despues mantenerlas juntas justamente porque el
     mapa actua como filtro de la serie.
  3. Casos por semana epidemiologica: casos de la semana del anio de analisis +
     comparacion con el anio anterior (par complementario), con la variacion
     del anio anotada sobre la comparativa.
  4. Variacion porcentual semanal, sola, a ancho completo.
  5. Evolucion de la incidencia por territorio.

Sin selector de anio propio: el anio de analisis de la seccion semanal es el
ULTIMO anio del filtro temporal global, y el de comparacion el inmediatamente
anterior en los datos, este o no dentro del filtro (fase 2).
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    MINIMO_ANIOS_COMPARATIVA,
    MINIMO_PUNTOS_SERIE,
    ANCHO_MEDIA_COLUMNA,
    NARANJA_INSTITUCIONAL,
    OPACIDAD_ATENUADA,
    avisar_datos_insuficientes,
    describir_cantidad,
    eje_semanal,
    hay_datos_suficientes,
    mostrar_grafica,
    rango_con_margen,
)
from core.dashboard_base.filtros import (
    aplicar_filtros_sin_periodo,
    resumen_filtros_activos,
    ultimo_anio_del_filtro,
)
from core.dashboard_base.seleccion_cruzada import (
    clave_grafica,
    fijar_seleccion,
    leer_puntos,
    limpiar_seleccion,
    mostrar_aviso_seleccion,
    obtener_seleccion,
    recargar_seccion,
    sincronizar_con_filtros,
)
from core.geografia import (
    ATRIBUCION_CAPA_URBANO_RURAL,
    ZONA_GEOMETRIA_CABECERA,
    ZONA_GEOMETRIA_RESTO_RURAL,
    obtener_geojson_dos_zonas_municipio,
    obtener_geojson_municipios_magdalena,
    obtener_geojson_subregiones,
)
from pathologies.dengue.geografia import obtener_mapeo_subregion
from pathologies.dengue.poblacion import (
    calcular_tasa_por_municipio,
    calcular_tasa_por_subregion,
    ZONA_CABECERA,
    ZONA_RESTO_RURAL,
    calcular_tasa_por_zona_municipio,
    obtener_poblacion_por_municipio_anio,
    obtener_poblacion_por_subregion_anio,
)

PATOLOGIA = "dengue"
CODIGOS_CASOS = {210, 220}

# Escala azul para los mapas de coropletas. NO arranca en blanco: la escala
# "Blues" de Plotly llega casi a blanco en su extremo bajo, y la subregion de
# menor valor se perdia contra el fondo blanco de la pagina. El piso es un azul
# claro pero visible; el techo, el azul institucional oscuro.
ESCALA_INCIDENCIA = ["#9ecae1", "#5ba3d0", "#2a6db0", "#1b3a6b"]
COLOR_SIN_POBLACION = "#c9ccd1"

_NIVEL_OPCIONES = ["Subregión", "Municipio"]
_NIVEL_ETIQUETAS = {
    "Subregión": ":material/map: Subregión",
    "Municipio": ":material/location_city: Municipio",
}

_LAYOUT_BASE = dict(margin=dict(l=0, r=0, t=70, b=0))

# Par mapa -> serie anual. Las claves del drill-down del mapa forman parte de la
# seleccion del par: se limpian juntas cuando cambia un filtro global o cuando
# se pulsa "Quitar seleccion".
_PAR_MAPA_SERIE = "tendencia_mapa_serie"
_CLAVE_SUBREGION_MAPA = "mapa_subregion_seleccionada"
_CLAVE_MUNICIPIO_MAPA = "mapa_municipio_seleccionado"
_CLAVES_MAPA = (_CLAVE_SUBREGION_MAPA, _CLAVE_MUNICIPIO_MAPA)

# Zonas con tasa valida dentro de un municipio: cabecera y resto rural (ver
# ZONA_A_AREA_DANE en poblacion.py). Codigos de area SIVIGILA de cada una.
_AREAS_POR_ZONA = {ZONA_CABECERA: [1], ZONA_RESTO_RURAL: [2, 3]}
# Feature de la geometria de dos zonas (core/geografia.py) -> zona con tasa.
_ZONA_POR_GEOMETRIA = {
    ZONA_GEOMETRIA_CABECERA: ZONA_CABECERA,
    ZONA_GEOMETRIA_RESTO_RURAL: ZONA_RESTO_RURAL,
}
_ZONA_COLORES = {
    ZONA_CABECERA: AZUL_INSTITUCIONAL,
    ZONA_RESTO_RURAL: "#0891b2",
}


def mostrar_tendencia(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    _mostrar_kpis(casos)

    st.space("small")

    # --- Par: serie anual + mapa (el mapa filtra la serie) ---
    sincronizar_con_filtros(_PAR_MAPA_SERIE, claves_extra=_CLAVES_MAPA)
    _procesar_clic_en_zona(casos)
    casos_seleccion, descripcion_seleccion = _resolver_seleccion_territorial(casos)
    mostrar_aviso_seleccion(_PAR_MAPA_SERIE, descripcion_seleccion, claves_extra=_CLAVES_MAPA)

    col_serie, col_mapa = st.columns([2, 3])
    with col_serie:
        with st.container(border=True, height="stretch"):
            _mostrar_casos_por_anio(casos_seleccion, descripcion_seleccion)
    with col_mapa:
        with st.container(border=True, height="stretch"):
            _mostrar_mapa(casos)

    st.space("small")

    anio_analisis = ultimo_anio_del_filtro()
    casos_anio_anterior, anio_anterior = _casos_del_anio_anterior(anio_analisis)

    with st.container(border=True):
        _mostrar_seccion_semanal(casos, anio_analisis, casos_anio_anterior, anio_anterior)

    st.space("small")

    with st.container(border=True):
        _mostrar_variacion_porcentual(casos, anio_analisis, casos_anio_anterior, anio_anterior)

    st.space("small")

    with st.container(border=True):
        _mostrar_evolucion_temporal(casos)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame) -> None:
    """Casos totales, semana pico y municipio mas afectado. El alza contra el
    anio anterior ya no va aqui: va anotada sobre la grafica comparativa, que es
    donde se esta viendo esa comparacion."""
    total = len(casos)

    anios_ordenados = sorted(int(a) for a in casos["ano"].dropna().unique())
    anio_actual = anios_ordenados[-1] if anios_ordenados else None

    # Semana pico y municipio mas afectado se calculan SOBRE EL ANIO MAS RECIENTE
    # (no sobre todos los anios combinados, que daria una semana/municipio "pico"
    # sumando anios distintos, poco interpretable).
    casos_anio = casos[casos["ano"] == anio_actual] if anio_actual is not None else casos

    if "semana" in casos_anio.columns and not casos_anio["semana"].dropna().empty:
        por_semana = casos_anio.groupby("semana").size()
        semana_pico = int(por_semana.idxmax())
        casos_pico = int(por_semana.max())
        semana_label = f"Sem. {semana_pico}"
        semana_help = f"{casos_pico:,} casos en la semana {semana_pico} de {anio_actual}"
    else:
        semana_label, semana_help = "-", None

    top_mun, top_help = "-", None
    if "nom_mun_o" in casos_anio.columns:
        por_municipio = casos_anio["nom_mun_o"].dropna().value_counts()
        if not por_municipio.empty:
            top_mun = str(por_municipio.index[0]).title()
            top_help = f"{int(por_municipio.iloc[0]):,} casos en {anio_actual}"

    if anio_actual is not None:
        st.caption(
            f":material/calendar_today: Casos totales cubren todo el período filtrado; "
            f"semana pico y municipio más afectado corresponden a {anio_actual} "
            "(el año más reciente)."
        )

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric(
            "Casos totales",
            f"{total:,}",
            help="Casos (dengue y dengue grave) en todos los años filtrados. No incluye mortalidad, que vive en la pestaña Mortalidad.",
            border=True,
        )
    with c2:
        etiqueta_semana = f"Semana pico {anio_actual}" if anio_actual is not None else "Semana pico"
        st.metric(etiqueta_semana, semana_label, help=semana_help, border=True)
    with c3:
        st.metric("Municipio más afectado", top_mun, help=top_help, border=True)


# ---------------------------------------------------------------------------
# Seleccion cruzada del par serie anual + mapa
# ---------------------------------------------------------------------------

def _nombre_municipio(casos: pd.DataFrame, codigo: int) -> str:
    if "nom_mun_o" not in casos.columns:
        return str(codigo)
    nombres = casos.loc[casos["cod_mun_completo"] == codigo, "nom_mun_o"].dropna()
    if nombres.empty:
        return str(codigo)
    return str(nombres.iloc[0]).title()


def _procesar_clic_en_zona(casos: pd.DataFrame) -> None:
    """Clic en una zona del mapa de tercer nivel (cabecera o resto rural): la
    serie anual se filtra a esa zona. Se lee antes de dibujar (ver
    seleccion_cruzada.py)."""
    codigo_municipio = st.session_state.get(_CLAVE_MUNICIPIO_MAPA)
    if not codigo_municipio:
        return
    puntos = leer_puntos(_PAR_MAPA_SERIE, "mapa_zonas")
    if not puntos:
        return
    zona = _ZONA_POR_GEOMETRIA.get(puntos[0].get("location"))
    if zona is None:
        return
    nombre = _nombre_municipio(casos, int(codigo_municipio))
    descripcion = f"{nombre} · {zona}"
    fijar_seleccion(_PAR_MAPA_SERIE, "zona", _AREAS_POR_ZONA[zona], descripcion)


def _resolver_seleccion_territorial(casos: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    """Territorio que marca el mapa (subregion, municipio o zona) y los casos de
    ese territorio para la serie anual. Sin seleccion, todos los casos."""
    subregion = st.session_state.get(_CLAVE_SUBREGION_MAPA)
    codigo_municipio = st.session_state.get(_CLAVE_MUNICIPIO_MAPA)
    seleccion_zona = obtener_seleccion(_PAR_MAPA_SERIE)

    if not subregion:
        return casos, None

    if not codigo_municipio:
        casos_subregion = casos[casos["subregion"] == subregion]
        return casos_subregion, f"Subregión {subregion}"

    codigo = int(codigo_municipio)
    casos_municipio = casos[casos["cod_mun_completo"] == codigo]
    nombre = _nombre_municipio(casos, codigo)

    if seleccion_zona and seleccion_zona["origen"] == "zona" and "area" in casos.columns:
        casos_zona = casos_municipio[casos_municipio["area"].isin(seleccion_zona["valores"])]
        return casos_zona, seleccion_zona["descripcion"]

    return casos_municipio, f"{nombre} (subregión {subregion})"


# ---------------------------------------------------------------------------
# Casos por anio
# ---------------------------------------------------------------------------

def _mostrar_casos_por_anio(casos: pd.DataFrame, lugar_seleccion: str | None) -> None:
    st.subheader(":material/bar_chart: Casos por año")

    if casos.empty:
        avisar_datos_insuficientes(
            "El territorio seleccionado en el mapa no tiene casos con los filtros actuales. "
            "Quita la selección o amplía el período."
        )
        return

    por_anio = casos.groupby("ano").size().reset_index(name="casos")

    fig = px.bar(por_anio, x="ano", y="casos", text="casos",
                 labels={"ano": "Año", "casos": "Casos"})
    fig.update_xaxes(type="category")
    fig.update_traces(
        texttemplate="%{text:,}",
        textposition="outside",
        marker_color=AZUL_INSTITUCIONAL,
        name="Casos",
        showlegend=True,
    )

    # Linea de promedio anual: referencia de "anio alto vs anio bajo". Con un
    # solo anio el promedio es ese mismo anio y la linea no aporta nada.
    if len(por_anio) >= 2:
        promedio = float(por_anio["casos"].mean())
        # La referencia va en la leyenda y no como texto sobre la linea: el
        # texto se montaba sobre las etiquetas del eje y sobre las barras.
        fig.add_trace(go.Scatter(
            x=por_anio["ano"],
            y=[promedio] * len(por_anio),
            mode="lines",
            line=dict(color=NARANJA_INSTITUCIONAL, dash="dot", width=2),
            name=f"Promedio anual ({promedio:,.0f})",
            hoverinfo="skip",
        ))
    fig.update_layout(
        **_LAYOUT_BASE,
        yaxis={"range": rango_con_margen(por_anio["casos"].max())},
    )
    if len(por_anio) > 10:
        # En media columna los anios no caben horizontales: se inclinan en vez
        # de quedar parados en vertical.
        fig.update_xaxes(tickangle=-45)
    mostrar_grafica(fig, "Casos por año", resumen_filtros_activos(lugar=lugar_seleccion), ancho=ANCHO_MEDIA_COLUMNA)


# ---------------------------------------------------------------------------
# Incidencia por subregion en el Magdalena (mapa, 3 niveles)
# ---------------------------------------------------------------------------

def _mostrar_mapa(casos: pd.DataFrame) -> None:
    """Vista general por subregion (incidencia). Tres niveles de detalle, todos
    en incidencia (x100.000 hab.): clic en subregion -> municipios de esa
    subregion; clic en un municipio -> el municipio partido en sus tres zonas
    (cabecera municipal, centro poblado, rural disperso). Cada nivel filtra la
    serie de Casos por año, al lado.
    """
    st.subheader(":material/map: Incidencia por subregión en el Magdalena")

    subregion_activa = st.session_state.get(_CLAVE_SUBREGION_MAPA)
    municipio_activo = st.session_state.get(_CLAVE_MUNICIPIO_MAPA)

    con_geo = casos[casos["mun_valido"]].dropna(subset=["cod_mun_completo", "subregion"])
    if con_geo.empty:
        st.info("Sin casos con geografía válida.", icon=":material/info:")
        return

    con_geo = con_geo.copy()
    con_geo["cod_mun_completo"] = con_geo["cod_mun_completo"].astype(int)

    if subregion_activa and municipio_activo:
        _mostrar_mapa_zonas(con_geo, subregion_activa, municipio_activo)
    elif subregion_activa:
        _mostrar_mapa_drilldown(con_geo, subregion_activa)
    else:
        _mostrar_mapa_overview(con_geo)


def _mostrar_mapa_overview(con_geo: pd.DataFrame) -> None:
    st.caption(":material/touch_app: Haz clic en una subregión para ver sus municipios y filtrar la serie anual.")

    anios_en_alcance = sorted(int(a) for a in con_geo["ano"].dropna().unique())
    mapeo_subregion = obtener_mapeo_subregion()
    incidencia_por_subregion = calcular_tasa_por_subregion(con_geo, anios_en_alcance, mapeo_subregion)
    casos_por_subregion = con_geo["subregion"].value_counts().to_dict()

    todas_subregiones = sorted(set(mapeo_subregion.values()))
    datos_mapa = pd.DataFrame({"subregion": todas_subregiones})
    datos_mapa["incidencia"] = datos_mapa["subregion"].map(incidencia_por_subregion)
    datos_mapa["casos"] = datos_mapa["subregion"].map(casos_por_subregion).fillna(0).astype(int)

    geojson = obtener_geojson_subregiones(mapeo_subregion)

    fig = px.choropleth(
        datos_mapa,
        geojson=geojson,
        locations="subregion",
        featureidkey="properties.subregion",
        color="incidencia",
        color_continuous_scale=ESCALA_INCIDENCIA,
        labels={"casos": "Casos", "incidencia": "Incidencia (x100.000 hab.)", "subregion": "Subregión"},
        hover_data={"subregion": True, "casos": True, "incidencia": ":.1f"},
    )
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=1)
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 70, "l": 0, "b": 0}, height=430)

    resultado = mostrar_grafica(
        fig, "Incidencia por subregión en el Magdalena", resumen_filtros_activos(),
        on_select="rerun", selection_mode="points", key="mapa_overview",
    )

    try:
        puntos = resultado.selection.points
    except AttributeError:
        puntos = []
    if puntos:
        # locations="subregion" -> el clic devuelve el nombre de la subregion directo.
        subregion_clickeada = puntos[0].get("location")
        if subregion_clickeada:
            st.session_state[_CLAVE_SUBREGION_MAPA] = str(subregion_clickeada)
            recargar_seccion()

    st.caption(
        "Incidencia = casos de dengue y dengue grave / población en riesgo x 100.000. "
        "Subregiones en gris no tienen población DANE para el período filtrado."
    )


def _mostrar_mapa_drilldown(con_geo: pd.DataFrame, subregion_activa: str) -> None:
    col_volver, col_titulo = st.columns([1, 4], vertical_alignment="center")
    with col_volver:
        if st.button("Volver", icon=":material/arrow_back:", key="mapa_volver", width="stretch"):
            limpiar_seleccion(_PAR_MAPA_SERIE, claves_extra=_CLAVES_MAPA)
            recargar_seccion()
    with col_titulo:
        st.caption(
            f":material/location_on: Subregión {subregion_activa}: municipios por incidencia. "
            "Haz clic en un municipio para ver sus zonas."
        )

    mapeo_subregion = obtener_mapeo_subregion()
    municipios_subregion = sorted(
        cod for cod, sub in mapeo_subregion.items() if sub == subregion_activa
    )

    anios_en_alcance = sorted(int(a) for a in con_geo["ano"].dropna().unique())
    tasas_municipio = calcular_tasa_por_municipio(con_geo, anios_en_alcance, municipios_subregion)
    casos_por_municipio = con_geo["cod_mun_completo"].value_counts().to_dict()

    tiene_nom_mun = "nom_mun_o" in con_geo.columns
    nombres_municipio = {}
    if tiene_nom_mun:
        nombres_municipio = (
            con_geo.dropna(subset=["nom_mun_o"])
            .drop_duplicates(subset=["cod_mun_completo"])
            .set_index("cod_mun_completo")["nom_mun_o"]
            .str.title()
            .to_dict()
        )

    datos_mapa = pd.DataFrame({"cod_mun_completo": municipios_subregion})
    datos_mapa["incidencia"] = datos_mapa["cod_mun_completo"].map(tasas_municipio)
    datos_mapa["casos"] = datos_mapa["cod_mun_completo"].map(casos_por_municipio).fillna(0).astype(int)
    datos_mapa["cod_str"] = datos_mapa["cod_mun_completo"].apply(lambda x: f"{x:05d}")
    if tiene_nom_mun:
        datos_mapa["nom_mun_o"] = datos_mapa["cod_mun_completo"].map(nombres_municipio).fillna("")

    hover = {"cod_str": False, "casos": True, "incidencia": ":.1f"}
    if tiene_nom_mun:
        hover["nom_mun_o"] = True

    geojson = obtener_geojson_municipios_magdalena()

    fig = px.choropleth(
        datos_mapa,
        geojson=geojson,
        locations="cod_str",
        featureidkey="properties.mpio_cdpmp",
        color="incidencia",
        color_continuous_scale=ESCALA_INCIDENCIA,
        labels={"casos": "Casos", "incidencia": "Incidencia (x100.000 hab.)", "nom_mun_o": "Municipio"},
        hover_data=hover,
    )
    fig.update_traces(marker_line_color="#ffffff", marker_line_width=1)
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 70, "l": 0, "b": 0}, height=430)
    resultado = mostrar_grafica(
        fig, "Incidencia por municipio", resumen_filtros_activos(lugar=f"Subregión {subregion_activa}"),
        key="mapa_drill", on_select="rerun", selection_mode="points",
    )

    try:
        puntos = resultado.selection.points
    except AttributeError:
        puntos = []
    if puntos:
        # locations="cod_str" -> el clic devuelve el codigo DIVIPOLA del municipio.
        codigo_clickeado = puntos[0].get("location")
        if codigo_clickeado:
            st.session_state[_CLAVE_MUNICIPIO_MAPA] = str(codigo_clickeado)
            recargar_seccion()

    st.caption(
        "Incidencia = casos de dengue y dengue grave / población en riesgo del municipio x 100.000. "
        "Municipios en gris no tienen población DANE para el período filtrado."
    )


def _mostrar_mapa_zonas(con_geo: pd.DataFrame, subregion_activa: str, codigo_municipio: str) -> None:
    """Tercer nivel del mapa: el municipio en sus dos zonas con dato, cabecera y
    resto rural (centros poblados y rural disperso juntos). Los centros poblados
    no se dibujan por separado: no hay casos ni poblacion a ese nivel de
    desagregacion (indicacion del codirector)."""
    codigo_int = int(codigo_municipio)
    datos_municipio = con_geo[con_geo["cod_mun_completo"] == codigo_int]
    nombre_municipio = _nombre_municipio(con_geo, codigo_int)

    col_volver, col_titulo = st.columns([1, 4], vertical_alignment="center")
    with col_volver:
        if st.button("Volver", icon=":material/arrow_back:", key="mapa_volver_zona", width="stretch"):
            st.session_state[_CLAVE_MUNICIPIO_MAPA] = None
            limpiar_seleccion(_PAR_MAPA_SERIE)
            recargar_seccion()
    with col_titulo:
        st.caption(
            f":material/location_on: {nombre_municipio} (subregión {subregion_activa}): incidencia "
            "en la cabecera y en el resto rural. Clic en una zona para filtrar la serie anual."
        )

    if datos_municipio.empty:
        st.info("Sin casos para este municipio con los filtros actuales.", icon=":material/info:")
        return

    anios_en_alcance = sorted(int(a) for a in datos_municipio["ano"].dropna().unique())

    conteo_areas = {1: 0, 2: 0, 3: 0}
    if "area" in datos_municipio.columns:
        conteo_areas.update(datos_municipio["area"].dropna().astype(int).value_counts().to_dict())
    conteo_zonas = {
        ZONA_CABECERA: int(conteo_areas.get(1, 0)),
        ZONA_RESTO_RURAL: int(conteo_areas.get(2, 0)) + int(conteo_areas.get(3, 0)),
    }
    tasas_zona = calcular_tasa_por_zona_municipio(conteo_zonas, codigo_int, anios_en_alcance)

    col_mapa, col_zonas = st.columns([1.2, 1])

    # st.empty: la key del mapa cambia con cada clic; asi Streamlit nunca deja a
    # la vista el mapa anterior debajo del nuevo (mapa duplicado).
    with col_mapa, st.empty().container():
        seleccion_zona = obtener_seleccion(_PAR_MAPA_SERIE)
        areas_resaltadas = None
        if seleccion_zona and seleccion_zona["origen"] == "zona":
            areas_resaltadas = seleccion_zona["valores"]
        figura_zonas = _graficar_mapa_zonas(codigo_int, conteo_zonas, tasas_zona, areas_resaltadas)
        mostrar_grafica(
            figura_zonas,
            "Incidencia por zona del municipio",
            resumen_filtros_activos(lugar=nombre_municipio),
            ancho=360,
            key=clave_grafica(_PAR_MAPA_SERIE, "mapa_zonas"),
            on_select="rerun",
            selection_mode="points",
        )

    with col_zonas:
        df_zonas = pd.DataFrame({
            "zona": [ZONA_CABECERA, "Resto rural"],
            "zona_completa": [ZONA_CABECERA, ZONA_RESTO_RURAL],
            "incidencia": [tasas_zona.get(ZONA_CABECERA), tasas_zona.get(ZONA_RESTO_RURAL)],
        })
        df_zonas = df_zonas.dropna(subset=["incidencia"])
        if df_zonas.empty:
            st.caption("Sin población DANE disponible para el período filtrado.")
        else:
            df_zonas["etiqueta"] = df_zonas["incidencia"].apply(lambda v: f"{v:,.1f}")
            fig_zonas = px.bar(
                df_zonas, x="incidencia", y="zona", text="etiqueta",
                orientation="h",
                labels={"incidencia": "Incidencia x100.000 hab.", "zona": ""},
            )
            fig_zonas.update_traces(
                textposition="outside",
                marker_color=[_ZONA_COLORES[zona] for zona in df_zonas["zona_completa"]],
            )
            fig_zonas.update_layout(
                height=340,
                showlegend=False,
                margin=dict(l=0, r=40, b=0),
                xaxis={"range": rango_con_margen(df_zonas["incidencia"].max(), factor=1.3)},
                yaxis={"categoryorder": "array", "categoryarray": ["Resto rural", ZONA_CABECERA]},
            )
            mostrar_grafica(fig_zonas, "Incidencia por zona del municipio", resumen_filtros_activos(lugar=nombre_municipio), key="mapa_zona_bar")
        st.markdown(
            f"Casos por área de ocurrencia: **{conteo_areas.get(1, 0):,}** en la cabecera, "
            f"**{conteo_areas.get(2, 0):,}** en centros poblados y **{conteo_areas.get(3, 0):,}** en "
            "rural disperso."
        )
        st.caption(
            "Centro poblado y rural disperso se muestran solo como conteo: el DANE publica una sola "
            "población para los dos juntos, así que la tasa válida es la del resto rural."
        )

    st.caption(
        "Incidencia x100.000 hab. según el área de ocurrencia del caso. Hay dos tasas: la de la "
        "cabecera y la del resto rural (centros poblados y rural disperso juntos, como agrupa la "
        "población en riesgo el lineamiento MSPS/INS y como la publica el DANE). Los centros "
        "poblados no se dibujan por separado porque no hay datos a ese nivel: SIVIGILA no "
        "registra en cuál de ellos ocurrió el caso y no hay población por centro poblado. En "
        "gris, las zonas sin población de referencia."
    )
    st.caption(ATRIBUCION_CAPA_URBANO_RURAL)
    with st.expander("Límites de la capa de zonas", icon=":material/info:"):
        st.markdown(
            "- En la capa original el polígono «cabecera» era todo el sector urbano del municipio, "
            "con el casco de los centros poblados incluido. Se corrigió: la cabecera es la parte "
            "que no toca ningún centro poblado, y ese casco pasó al resto rural.\n"
            "- El resto rural une los centros poblados (manzanas censales de 2018 y casco urbano "
            "del MGN 2020) y el rural disperso (secciones rurales de 2018). Los bordes vienen de "
            "dos años distintos, así que pueden no coincidir exactamente."
        )


def _opacidad_zona(zona: str, areas_resaltadas: list | None) -> float:
    """Zona elegida a color pleno y la otra atenuada (regla 1.5)."""
    if not areas_resaltadas:
        return 1.0
    if set(_AREAS_POR_ZONA[zona]) == set(areas_resaltadas):
        return 1.0
    return OPACIDAD_ATENUADA


def _graficar_mapa_zonas(
    codigo_municipio: int,
    conteo_zonas: dict,
    tasas_zona: dict,
    areas_resaltadas: list | None = None,
) -> go.Figure:
    """Coropleto del municipio en sus dos zonas con dato (cabecera y resto
    rural), en la misma escala de color que los otros dos niveles. Una zona sin
    poblacion de referencia se pinta en gris (si quedara en blanco se leeria
    como cero casos)."""
    geojson = obtener_geojson_dos_zonas_municipio(codigo_municipio)
    filas = []
    for feature in geojson["features"]:
        codigo_zona = feature["properties"]["zona"]
        zona = _ZONA_POR_GEOMETRIA[codigo_zona]
        filas.append({
            "codigo": codigo_zona,
            "zona": zona,
            "casos": int(conteo_zonas.get(zona, 0)),
            "incidencia": tasas_zona.get(zona),
            "opacidad": _opacidad_zona(zona, areas_resaltadas),
        })
    zonas = pd.DataFrame(filas)
    con_tasa = zonas[zonas["incidencia"].notna()]
    sin_tasa = zonas[zonas["incidencia"].isna()]

    plantilla_hover = (
        "%{customdata[0]}<br>Casos: %{customdata[1]:,}<br>Incidencia: %{customdata[2]}<extra></extra>"
    )

    fig = go.Figure()
    if not con_tasa.empty:
        etiquetas_incidencia = con_tasa["incidencia"].apply(lambda valor: f"{valor:,.1f} x100.000 hab.")
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            featureidkey="properties.zona",
            locations=con_tasa["codigo"],
            z=con_tasa["incidencia"],
            colorscale=ESCALA_INCIDENCIA,
            marker_line_color="#ffffff",
            marker_line_width=1,
            marker_opacity=con_tasa["opacidad"].tolist(),
            # Barra de color horizontal, debajo del mapa: en la columna angosta,
            # vertical se comia el ancho y el municipio quedaba pequeno.
            colorbar=dict(
                title=dict(text="Incidencia x100.000 hab.", side="top"),
                orientation="h",
                thickness=12,
                len=0.9,
                x=0.5,
                xanchor="center",
                y=-0.02,
                yanchor="top",
            ),
            customdata=list(zip(con_tasa["zona"], con_tasa["casos"], etiquetas_incidencia)),
            hovertemplate=plantilla_hover,
            name="Incidencia",
            showlegend=False,
        ))
    if not sin_tasa.empty:
        fig.add_trace(go.Choropleth(
            geojson=geojson,
            featureidkey="properties.zona",
            locations=sin_tasa["codigo"],
            z=[0] * len(sin_tasa),
            marker_opacity=sin_tasa["opacidad"].tolist(),
            colorscale=[[0, COLOR_SIN_POBLACION], [1, COLOR_SIN_POBLACION]],
            showscale=False,
            marker_line_color="#ffffff",
            marker_line_width=1,
            customdata=list(zip(sin_tasa["zona"], sin_tasa["casos"], ["sin población de referencia"] * len(sin_tasa))),
            hovertemplate=plantilla_hover,
            name="Sin población de referencia",
            showlegend=True,
        ))
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(margin={"r": 0, "t": 70, "l": 0, "b": 70}, height=470)
    return fig


# ---------------------------------------------------------------------------
# Casos por semana epidemiologica (anio de analisis + comparacion)
# ---------------------------------------------------------------------------

def _casos_del_anio_anterior(anio_analisis: int | None) -> tuple[pd.DataFrame, int | None]:
    """Casos del anio inmediatamente anterior en los datos, con los filtros
    globales vigentes MENOS el de anio: el anio de comparacion se toma este o no
    dentro del filtro temporal (fase 2)."""
    if anio_analisis is None:
        return pd.DataFrame(), None
    datos_completos = modulo_datos.obtener_datos(PATOLOGIA)
    datos_sin_periodo = aplicar_filtros_sin_periodo(datos_completos)
    casos_sin_periodo = datos_sin_periodo[datos_sin_periodo["cod_eve"].isin(CODIGOS_CASOS)]
    anios_previos = sorted(int(a) for a in casos_sin_periodo["ano"].dropna().unique() if int(a) < anio_analisis)
    if not anios_previos:
        return pd.DataFrame(), None
    anio_anterior = anios_previos[-1]
    return casos_sin_periodo[casos_sin_periodo["ano"] == anio_anterior], anio_anterior


def _periodo_comparado(anio_analisis: int, anio_anterior: int | None) -> str:
    if anio_anterior is None:
        return str(anio_analisis)
    return f"{anio_analisis} frente a {anio_anterior}"


def _mostrar_seccion_semanal(
    casos: pd.DataFrame, anio_analisis: int | None, casos_anterior: pd.DataFrame, anio_anterior: int | None
) -> None:
    st.subheader(":material/show_chart: Casos por semana epidemiológica")
    if anio_analisis is None:
        st.caption("Sin datos.")
        return

    if anio_anterior is None:
        st.caption(
            f"Semana a semana, {anio_analisis}. No hay un año anterior en los datos cargados, "
            "así que la comparación muestra solo el año de análisis."
        )
    else:
        st.caption(
            f"Semana a semana, {anio_analisis} frente a {anio_anterior}. El año de análisis es el "
            "último del filtro de años de la barra lateral; el de comparación, el anterior en los datos."
        )

    casos_anio = casos[casos["ano"] == anio_analisis]

    col_semanal, col_comparacion = st.columns(2)
    with col_semanal:
        _grafica_semanal_anio(casos_anio, anio_analisis)
    with col_comparacion:
        _grafica_comparacion_vs_anterior(casos_anio, anio_analisis, casos_anterior, anio_anterior)


def _grafica_semanal_anio(casos_anio: pd.DataFrame, anio: int) -> None:
    """Casos de cada semana del anio de analisis, con linea de promedio semanal
    (un promedio entre semanas dentro del anio: esa linea si se conserva)."""
    semanal = casos_anio.groupby("semana").size().reset_index(name="casos")
    if not hay_datos_suficientes(semanal, MINIMO_PUNTOS_SERIE):
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(casos_anio), 'caso', 'casos', femenino=False)} "
            f"en {describir_cantidad(len(semanal), 'semana epidemiológica', 'semanas epidemiológicas')} de {anio}. "
            "Amplía el rango de semanas o el territorio para ver la serie semanal."
        )
        return

    promedio = float(semanal["casos"].mean())
    fig = px.bar(
        semanal, x="semana", y="casos",
        labels={"semana": "Semana epidemiológica", "casos": "Casos"},
    )
    fig.update_traces(name=f"Casos {anio}", showlegend=True, marker_color=AZUL_INSTITUCIONAL)
    fig.add_trace(go.Scatter(
        x=semanal["semana"],
        y=[promedio] * len(semanal),
        mode="lines",
        line=dict(color=NARANJA_INSTITUCIONAL, dash="dot", width=2),
        name=f"Promedio semanal ({promedio:,.0f})",
        hoverinfo="skip",
    ))
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max()), dtick=2))
    mostrar_grafica(fig, "Casos por semana epidemiológica", resumen_filtros_activos(periodo=str(anio)), ancho=ANCHO_MEDIA_COLUMNA)


def _grafica_comparacion_vs_anterior(
    casos_anio: pd.DataFrame, anio: int, casos_anterior: pd.DataFrame, anio_anterior: int | None
) -> None:
    """Barras (anio anterior) + linea (anio de analisis), con la variacion del
    anio anotada encima: es donde se esta viendo esa comparacion."""
    def _semanal(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return pd.DataFrame(columns=["semana", "casos"])
        return df.groupby("semana").size().reset_index(name="casos")

    df_act = _semanal(casos_anio)
    df_prev = _semanal(casos_anterior)

    if not hay_datos_suficientes(df_act, MINIMO_PUNTOS_SERIE):
        avisar_datos_insuficientes(
            f"Con los filtros actuales {anio} tiene casos en "
            f"{describir_cantidad(len(df_act), 'semana epidemiológica', 'semanas epidemiológicas')}. "
            "Amplía el rango de semanas o el territorio para comparar con el año anterior."
        )
        return

    fig = go.Figure()

    if not df_prev.empty:
        fig.add_trace(go.Bar(
            x=df_prev["semana"], y=df_prev["casos"],
            name=str(anio_anterior),
            marker_color=NARANJA_INSTITUCIONAL,
            opacity=0.65,
            hovertemplate=f"Semana %{{x}} · %{{y:,}} casos ({anio_anterior})<extra></extra>",
        ))

    fig.add_trace(go.Scatter(
        x=df_act["semana"], y=df_act["casos"],
        mode="lines+markers",
        name=str(anio),
        line=dict(color=AZUL_INSTITUCIONAL, width=2),
        marker=dict(size=5),
        hovertemplate=f"Semana %{{x}} · %{{y:,}} casos ({anio})<extra></extra>",
    ))

    anotacion = _texto_variacion_anual(df_act, df_prev, anio, anio_anterior)
    if anotacion:
        fig.add_annotation(
            text=anotacion,
            xref="paper", yref="paper", x=0.01, y=0.98,
            xanchor="left", yanchor="top", showarrow=False, align="left",
            bgcolor="rgba(255,255,255,0.85)", bordercolor="#d1d5db", borderwidth=1, borderpad=6,
        )

    fig.update_layout(
        xaxis_title="Semana epidemiológica",
        yaxis_title="Casos",
        **_LAYOUT_BASE,
    )
    semanas_todas = pd.concat([df_prev["semana"], df_act["semana"]])
    fig.update_xaxes(**eje_semanal(int(semanas_todas.max()), dtick=2))
    mostrar_grafica(fig, "Casos por semana frente al año anterior", resumen_filtros_activos(periodo=_periodo_comparado(anio, anio_anterior)), ancho=ANCHO_MEDIA_COLUMNA)


def _texto_variacion_anual(df_act: pd.DataFrame, df_prev: pd.DataFrame, anio: int, anio_anterior: int | None) -> str | None:
    """Alza o baja del anio de analisis frente al anterior, sobre las MISMAS
    semanas: si el anio de analisis va por la semana 20, se compara contra las
    semanas 1 a 20 del anterior, no contra su total, que seria enganoso."""
    if anio_anterior is None or df_prev.empty:
        return None
    ultima_semana = int(df_act["semana"].max())
    total_actual = int(df_act["casos"].sum())
    total_anterior = int(df_prev.loc[df_prev["semana"] <= ultima_semana, "casos"].sum())
    if total_anterior == 0:
        return None
    variacion = (total_actual - total_anterior) / total_anterior * 100
    return (
        f"{anio}: {total_actual:,} casos hasta la semana {ultima_semana}<br>"
        f"{variacion:+.1f} % frente a las mismas semanas de {anio_anterior} ({total_anterior:,})"
    )


def _mostrar_variacion_porcentual(
    casos: pd.DataFrame, anio: int | None, casos_anterior: pd.DataFrame, anio_anterior: int | None
) -> None:
    """Variacion porcentual semanal frente al anio anterior, a ancho completo."""
    st.subheader(":material/percent: Variación porcentual semanal frente al año anterior")
    if anio is None:
        st.caption("Sin datos.")
        return
    if anio_anterior is None:
        avisar_datos_insuficientes(
            f"No hay un año anterior a {anio} en los datos cargados, así que no hay contra qué "
            "calcular la variación."
        )
        return

    serie_actual = casos[casos["ano"] == anio].groupby("semana").size()
    serie_anterior = casos_anterior.groupby("semana").size()

    semanas_comunes = serie_actual.index.intersection(serie_anterior.index)
    semanas_con_base = [semana for semana in semanas_comunes if serie_anterior[semana] > 0]
    if len(semanas_con_base) < MINIMO_PUNTOS_SERIE:
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(semanas_con_base), 'semana', 'semanas')} "
            f"con casos en {anio} y en {anio_anterior} a la vez. Amplía el rango de semanas o el "
            "territorio para ver la variación semana a semana."
        )
        return

    actuales = serie_actual[semanas_con_base]
    anteriores = serie_anterior[semanas_con_base]
    variacion = pd.DataFrame({
        "semana": semanas_con_base,
        "variacion": ((actuales - anteriores) / anteriores * 100).values,
    })
    variacion["signo"] = ["Aumento" if v >= 0 else "Disminución" for v in variacion["variacion"]]

    fig = px.bar(
        variacion, x="semana", y="variacion",
        color="signo",
        color_discrete_map={
            "Aumento": AZUL_INSTITUCIONAL,
            "Disminución": NARANJA_INSTITUCIONAL,
        },
        labels={"semana": "Semana epidemiológica", "variacion": "Variación (%)", "signo": ""},
    )
    fig.add_hline(y=0, line_color="#9ca3af", line_width=1)
    fig.update_layout(**_LAYOUT_BASE)
    fig.update_xaxes(**eje_semanal(int(variacion["semana"].max())))
    mostrar_grafica(fig, "Variación porcentual semanal frente al año anterior", resumen_filtros_activos(periodo=_periodo_comparado(anio, anio_anterior)))


# ---------------------------------------------------------------------------
# Evolucion de la incidencia por territorio
# ---------------------------------------------------------------------------

def _mostrar_evolucion_temporal(casos: pd.DataFrame) -> None:
    st.subheader(":material/timeline: Evolución de la incidencia por territorio")

    # Selector de representacion (no filtra datos: elige el nivel que se dibuja).
    nivel = st.segmented_control(
        "Agrupar por",
        _NIVEL_OPCIONES,
        default="Subregión",
        required=True,
        format_func=lambda o: _NIVEL_ETIQUETAS[o],
        key="tendencia_evolucion_nivel",
    )
    col_nivel = "subregion" if nivel == "Subregión" else "nom_mun_o"

    subset = casos.dropna(subset=[col_nivel, "cod_mun_completo"])
    if subset.empty:
        st.info("Sin casos con geografía válida.", icon=":material/info:")
        return

    anios = sorted(int(a) for a in subset["ano"].dropna().unique())
    if len(anios) < MINIMO_ANIOS_COMPARATIVA:
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(anios), 'año', 'años', femenino=False)} "
            f"({', '.join(str(a) for a in anios)}). La evolución necesita al menos "
            f"{MINIMO_ANIOS_COMPARATIVA} años: amplía el período en la barra lateral."
        )
        return

    evolucion_casos = subset.groupby(["ano", col_nivel]).size().reset_index(name="casos")

    if nivel == "Subregión":
        poblacion = obtener_poblacion_por_subregion_anio(obtener_mapeo_subregion())
        evolucion = evolucion_casos.merge(poblacion, on=["ano", "subregion"], how="left")
    else:
        # Un municipio solo tiene un cod_mun_completo, asi que el merge por
        # cod_mun_completo + ano no duplica filas.
        cod_por_municipio = subset.drop_duplicates(subset=["nom_mun_o"]).set_index("nom_mun_o")["cod_mun_completo"]
        evolucion_casos["cod_mun_completo"] = evolucion_casos["nom_mun_o"].map(cod_por_municipio)
        poblacion = obtener_poblacion_por_municipio_anio()
        evolucion = evolucion_casos.merge(poblacion, on=["ano", "cod_mun_completo"], how="left")
        evolucion["nom_mun_o"] = evolucion["nom_mun_o"].str.title()

    evolucion["incidencia"] = evolucion["casos"] / evolucion["poblacion"] * 100_000
    evolucion = evolucion.dropna(subset=["incidencia"])
    if evolucion.empty:
        st.caption("Sin población DANE disponible para el período filtrado.")
        return

    evolucion["ano"] = evolucion["ano"].astype(str)

    # Paleta de alto contraste, curada a mano: prioriza que cada linea se
    # distinga de las demas. Sin rosados ni fucsias, que se confunden con el
    # rojo. Light24 solo como reserva para los 30 municipios.
    paleta_contraste = [
        "#2E91E5",  # azul
        "#FB0D0D",  # rojo
        "#1CA71C",  # verde
        "#B68100",  # ambar
        "#750D86",  # morado
        "#00A08B",  # verde azulado
        "#511CFB",  # indigo
        "#EB663B",  # naranja
        "#222A2A",  # grafito
        "#0D2A63",  # azul marino
        "#6C7C32",  # oliva
        "#A777F1",  # lila
        "#620042",  # vinotinto
        "#1616A7",  # azul profundo
        "#6C4516",  # cafe
    ] + px.colors.qualitative.Light24

    fig = px.line(
        evolucion, x="ano", y="incidencia", color=col_nivel, markers=True,
        color_discrete_sequence=paleta_contraste,
        labels={"ano": "Año", "incidencia": "Incidencia x100.000 hab.", col_nivel: nivel},
    )
    fig.update_layout(**_LAYOUT_BASE)
    mostrar_grafica(fig, "Evolución de la incidencia por territorio", resumen_filtros_activos())
    st.caption("Incidencia = casos de dengue y dengue grave / población en riesgo x 100.000.")
