"""Pestana 2 Situacion: KPIs, mapa de situacion (2.1) y canal endemico (2.2),
cuartiles y Bortman lado a lado, tal como el INS Colombia recomienda usarlos en
paralelo para confirmar senales de alerta. El pronostico de corto plazo (2.3)
sigue pendiente (modelo predictivo), ver PROGRESO.md.

Casos = cod_eve en {210, 220}. La mortalidad (580) no participa del canal endemico
ni del mapa de situacion, pero si de los KPIs (letalidad, mortalidad).
"""

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import streamlit as st

from core.dashboard_base.estilos import (
    COLOR_ALERTA_EPIDEMIOLOGICO,
    COLOR_EPIDEMIA,
    COLOR_EXITO_EPIDEMIOLOGICO,
    COLOR_SEGURIDAD_EPIDEMIOLOGICO,
)
from core.dashboard_base.filtros import CLAVE_FILTROS
from core.geografia import obtener_geojson_municipios_magdalena
from pathologies.dengue.canal_endemico import (
    ETIQUETAS_LINEAS,
    VENTANA_MAXIMA,
    VENTANA_MINIMA,
    ZONA_ALERTA,
    ZONA_EPIDEMIA,
    ZONA_EXITO,
    ZONA_SEGURIDAD,
    ZONAS_ORDEN,
    calcular_canal_endemico,
    calcular_situacion_actual_por_subregion,
)
from pathologies.dengue.indicators import calcular_indicadores

CODIGOS_CASOS = {210, 220}

META_LETALIDAD = 0.10  # meta nacional INS/MSPS

_ESCALA_OPCIONES = ["Subregión", "Municipio"]

_METODOS = [
    ("cuartiles", "Cuartiles / medianas (INS Colombia)"),
    ("bortman", "Bortman (media geométrica)"),
]

_ZONA_SIN_DATOS = "Sin datos suficientes"

# Colores institucionales de zona epidemiologica: unico lugar donde el calculo
# (canal_endemico.py, que no conoce colores) se conecta con la identidad visual.
_ZONA_COLOR = {
    ZONA_EXITO: COLOR_EXITO_EPIDEMIOLOGICO,
    ZONA_SEGURIDAD: COLOR_SEGURIDAD_EPIDEMIOLOGICO,
    ZONA_ALERTA: COLOR_ALERTA_EPIDEMIOLOGICO,
    ZONA_EPIDEMIA: COLOR_EPIDEMIA,
    _ZONA_SIN_DATOS: "#c9ccd1",
}


def mostrar_situacion(datos: pd.DataFrame) -> None:
    filtros_actuales = st.session_state.get(CLAVE_FILTROS, {})
    resultado_indicadores = calcular_indicadores(datos, filtros_actuales)

    with st.container(border=True):
        _mostrar_kpis(resultado_indicadores)

    st.space("small")

    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]
    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    with st.container(border=True):
        _mostrar_situacion_actual(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_canal_endemico(casos)

    st.caption(
        ":material/construction: El pronóstico de corto plazo (modelo predictivo a "
        "nivel departamental) se construye más adelante."
    )


# ---------------------------------------------------------------------------
# KPIs: incidencia, mortalidad, letalidad, letalidad grave, % confirmados
# graves, % hospitalizados graves.
# ---------------------------------------------------------------------------

def _formatear_tasa(valor: float | None) -> str:
    return f"{valor:,.1f}" if valor is not None else "No disponible"


def _formatear_pct(valor: float | None, decimales: int = 2) -> str:
    return f"{valor:.{decimales}f}%" if valor is not None else "No disponible"


def _mostrar_kpis(resultado: dict) -> None:
    st.subheader(":material/insights: Indicadores")

    incidencia = resultado["incidencia"]
    mortalidad = resultado["mortalidad"]
    letalidad = resultado["letalidad"]
    letalidad_grave = resultado["letalidad_grave"]
    pct_confirmados_grave = resultado["pct_confirmados_grave"]
    pct_hospitalizados_grave = resultado["pct_hospitalizados_grave"]

    ayuda_tasa_no_disponible = (
        "No disponible: puede faltar población DANE para alguno de los años "
        "filtrados, o el filtro está acotado a municipio(s) específicos (las tasas "
        "solo son confiables a escala subregión o departamento, nunca municipio, "
        "por el desplazamiento de pacientes entre municipios)."
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Incidencia",
            _formatear_tasa(incidencia),
            help=(
                "Casos (210+220) / población en riesgo x 100.000."
                if incidencia is not None else ayuda_tasa_no_disponible
            ),
        )
    with col2:
        st.metric(
            "Mortalidad",
            _formatear_tasa(mortalidad),
            help=(
                "Muertes (580) / población en riesgo x 100.000."
                if mortalidad is not None else ayuda_tasa_no_disponible
            ),
        )
    with col3:
        supera_meta = letalidad is not None and letalidad > META_LETALIDAD
        st.metric(
            "Letalidad",
            _formatear_pct(letalidad, decimales=4),
            delta=f"Meta INS < {META_LETALIDAD}%" if supera_meta else None,
            delta_color="inverse" if supera_meta else "off",
            help=(
                "Muertes (580) / casos (210+220) x 100. "
                f"Meta nacional INS: < {META_LETALIDAD}%."
            ),
        )

    col4, col5, col6 = st.columns(3)
    with col4:
        st.metric(
            "Letalidad grave",
            _formatear_pct(letalidad_grave),
            help="Muertes (580) / casos de dengue grave (220) x 100.",
        )
    with col5:
        st.metric(
            "% Confirmados graves",
            _formatear_pct(pct_confirmados_grave),
            help=(
                "Casos graves (220) confirmados / total de casos graves notificados x "
                "100. Mide cobertura de confirmación, no gravedad."
            ),
        )
    with col6:
        st.metric(
            "% Hospitalizados graves",
            _formatear_pct(pct_hospitalizados_grave),
            help="Casos graves (220) hospitalizados / total de casos graves (220) x 100. Meta: 100%.",
        )


# ---------------------------------------------------------------------------
# 2.1  Mapa de situacion (situacion actual por subregion)
# ---------------------------------------------------------------------------

def _mostrar_situacion_actual(casos: pd.DataFrame) -> None:
    st.subheader(":material/map: Situación actual por subregión")
    st.caption(
        "Compara los casos de la semana más reciente reportada en cada subregión contra "
        "el historial de esa misma semana calendario en años anteriores. No es un resumen "
        "del año completo ni una semana fija: se ajusta sola a medida que llegan más datos."
    )

    with st.expander(":material/help: ¿Qué semana se está comparando y por qué?"):
        st.markdown(
            "- Cada subregión se compara contra su propia última semana con casos "
            "reportados, no contra una semana fija del calendario: si hasta ahora se ha "
            "reportado hasta la semana 20 del año, se usa la semana 20. Las semanas "
            "siguientes, que todavía no han pasado, no se inventan.\n"
            "- Si una subregión reporta con más rezago que otra, su semana de referencia "
            "puede quedar más atrás que la de las demás — por eso cada tarjeta de la "
            "derecha muestra su propia semana y año, en vez de asumir que todas comparten "
            "la misma.\n"
            "- La comparación siempre es contra esa MISMA semana calendario en los años "
            "anteriores (ej. semana 20 de este año contra la semana 20 de cada año base), "
            "nunca contra el promedio o el total del año.\n"
            "- El año de vigilancia y la línea base de este mapa son ajustables abajo, "
            "igual que en Canal endémico, y se aplican a las 5 subregiones a la vez.\n"
            "- Las fórmulas completas y un ejemplo numérico paso a paso están en "
            "\"Metodología\", dentro de Canal endémico, más abajo en esta pestaña."
        )

    anios_disponibles = sorted((int(anio) for anio in casos["ano"].dropna().unique()), reverse=True)
    resultado_seleccion = _seleccionar_linea_base(anios_disponibles, key_prefix="situacion_mapa")
    if resultado_seleccion is None:
        return
    anio_vigilancia, anios_base_seleccionados = resultado_seleccion

    situacion = calcular_situacion_actual_por_subregion(
        casos, anio_vigilancia=anio_vigilancia, anios_base=anios_base_seleccionados
    )
    if situacion.empty:
        st.info(
            f"Ninguna subregión tiene casos reportados en {anio_vigilancia}.",
            icon=":material/info:",
        )
        return

    semanas_referencia = situacion[["ano", "semana"]].drop_duplicates()
    if len(semanas_referencia) == 1:
        fila_unica = semanas_referencia.iloc[0]
        st.caption(
            f":material/history: Semana de referencia (todas las subregiones): "
            f"semana {int(fila_unica['semana'])} de {int(fila_unica['ano'])}."
        )
    else:
        st.caption(
            ":material/history: Las subregiones no comparten la misma semana de "
            "referencia (alguna reporta con más rezago); el detalle está en cada tarjeta."
        )

    col_mapa, col_resumen = st.columns([1.6, 1])
    with col_mapa:
        st.plotly_chart(_graficar_mapa_situacion(casos, situacion), width="stretch")
    with col_resumen:
        for _, fila in situacion.sort_values("subregion").iterrows():
            zona = fila["situacion"]
            st.markdown(
                f'<div style="background-color:{_con_opacidad(_ZONA_COLOR[zona], 0.15)}; '
                f'border-left: 4px solid {_ZONA_COLOR[zona]}; border-radius: 6px; '
                f'padding: 0.5rem 0.8rem; margin-bottom: 0.6rem;">'
                f'<strong>{fila["subregion"]}</strong><br>'
                f'{zona} '
                f'<small style="color:#666;">— semana {int(fila["semana"])} de {int(fila["ano"])}</small>'
                f'</div>',
                unsafe_allow_html=True,
            )


def _graficar_mapa_situacion(casos: pd.DataFrame, situacion: pd.DataFrame) -> go.Figure:
    con_geo = casos[casos["mun_valido"]].dropna(subset=["cod_mun_completo", "subregion"])
    con_geo = con_geo.copy()
    con_geo["cod_mun_completo"] = con_geo["cod_mun_completo"].astype(int)

    municipios = con_geo[["cod_mun_completo", "subregion", "nom_mun_o"]].drop_duplicates(subset=["cod_mun_completo"])
    municipios = municipios.copy()
    municipios["cod_str"] = municipios["cod_mun_completo"].apply(lambda x: f"{x:05d}")

    municipios_con_situacion = municipios.merge(situacion[["subregion", "situacion"]], on="subregion", how="left")
    municipios_con_situacion["situacion"] = municipios_con_situacion["situacion"].fillna(_ZONA_SIN_DATOS)

    geojson = obtener_geojson_municipios_magdalena()

    fig = px.choropleth(
        municipios_con_situacion,
        geojson=geojson,
        locations="cod_str",
        featureidkey="properties.mpio_cdpmp",
        color="situacion",
        category_orders={"situacion": ZONAS_ORDEN + [_ZONA_SIN_DATOS]},
        color_discrete_map=_ZONA_COLOR,
        hover_data={"cod_str": False, "subregion": True, "nom_mun_o": True, "situacion": True},
        labels={"situacion": "Situación", "subregion": "Subregión", "nom_mun_o": "Municipio"},
    )
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(
        margin={"r": 0, "t": 0, "l": 0, "b": 0},
        height=360,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, title=None),
    )
    return fig


# ---------------------------------------------------------------------------
# 2.2  Canal endemico (cuartiles y Bortman lado a lado)
# ---------------------------------------------------------------------------

def _mostrar_canal_endemico(casos: pd.DataFrame) -> None:
    col_titulo, col_metodologia = st.columns([5, 1.3], vertical_alignment="center")
    with col_titulo:
        st.subheader(":material/monitoring: Canal endémico")
    with col_metodologia:
        if st.button(
            "Metodología",
            icon=":material/school:",
            key="situacion_canal_metodologia",
            width="stretch",
        ):
            _dialogo_metodologia()

    st.caption(
        "Compara los casos por semana epidemiológica del año de vigilancia contra el "
        "historial de años anteriores. El INS Colombia recomienda revisar cuartiles y "
        "Bortman en paralelo para confirmar señales de alerta."
    )

    col_escala, col_territorio = st.columns(2)

    with col_escala:
        escala = st.segmented_control(
            "Escala",
            _ESCALA_OPCIONES,
            default="Subregión",
            required=True,
            key="situacion_canal_escala",
        )
    columna_territorio = "subregion" if escala == "Subregión" else "nom_mun_o"

    territorios_disponibles = sorted(casos[columna_territorio].dropna().unique().tolist())
    if not territorios_disponibles:
        st.caption("Sin datos geográficos suficientes para esta escala.")
        return

    with col_territorio:
        territorio = st.selectbox(
            escala,
            territorios_disponibles,
            key=f"situacion_canal_territorio_{escala}",
        )
    datos_territorio = casos[casos[columna_territorio] == territorio]

    anios_disponibles = sorted(
        (int(anio) for anio in datos_territorio["ano"].dropna().unique()), reverse=True
    )
    if not anios_disponibles:
        st.caption("Sin datos para este territorio.")
        return

    resultado_seleccion = _seleccionar_linea_base(
        anios_disponibles, key_prefix=f"situacion_canal_{escala}_{territorio}"
    )
    if resultado_seleccion is None:
        return
    anio_vigilancia, anios_base_seleccionados = resultado_seleccion

    col_cuartiles, col_bortman = st.columns(2)
    for columna, (metodo, etiqueta) in zip((col_cuartiles, col_bortman), _METODOS):
        resultado = calcular_canal_endemico(
            datos_territorio,
            metodo=metodo,
            anio_vigilancia=anio_vigilancia,
            anios_base=anios_base_seleccionados,
        )
        with columna:
            st.plotly_chart(
                _graficar_canal(resultado, etiqueta, territorio, anio_vigilancia),
                width="stretch",
            )


def _seleccionar_linea_base(anios_disponibles: list[int], key_prefix: str) -> tuple[int, list[int]] | None:
    """Selector compartido de año de vigilancia + ventana (5-7 años) + exclusión
    manual: lo usan tanto el mapa de situación (2.1, se aplica a las 5 subregiones
    a la vez) como el canal endémico interactivo (2.2, un territorio a la vez), cada
    uno con su propio key_prefix para no compartir estado entre secciones.

    anios_disponibles debe venir ordenado de más reciente a más antiguo. Devuelve
    (año_vigilancia, años_base) listos para calcular_canal_endemico /
    calcular_situacion_actual_por_subregion, o None si no se puede calcular (ya
    avisa con st.warning por qué).
    """
    if not anios_disponibles:
        st.caption("Sin datos disponibles.")
        return None

    anio_vigilancia = st.selectbox(
        "Año de vigilancia", anios_disponibles, key=f"{key_prefix}_anio",
    )

    # Solo anios ANTERIORES al de vigilancia: se compara el presente contra el
    # pasado, nunca contra el futuro.
    anios_historicos_disponibles = [anio for anio in anios_disponibles if anio < anio_vigilancia]

    if len(anios_historicos_disponibles) < VENTANA_MINIMA:
        st.warning(
            f"No es posible calcular: el INS Colombia recomienda una línea base de al "
            f"menos {VENTANA_MINIMA} años históricos anteriores al año de vigilancia "
            f"(idealmente {VENTANA_MINIMA} a {VENTANA_MAXIMA}), y solo hay "
            f"{len(anios_historicos_disponibles)} año(s) anterior(es) a {anio_vigilancia}. "
            "Elige un año de vigilancia más reciente o amplía la ventana temporal en "
            "los filtros globales.",
            icon=":material/warning:",
        )
        return None

    limite_ventana = min(VENTANA_MAXIMA, len(anios_historicos_disponibles))
    clave_base = f"{key_prefix}_{anio_vigilancia}"

    if limite_ventana > VENTANA_MINIMA:
        tamano_ventana = st.slider(
            "Años hacia atrás en la línea base",
            min_value=VENTANA_MINIMA,
            max_value=limite_ventana,
            value=limite_ventana,
            key=f"{clave_base}_ventana",
            help=(
                f"El INS Colombia recomienda entre {VENTANA_MINIMA} y {VENTANA_MAXIMA} "
                f"años de historia. Se toman los años más recientes anteriores a "
                f"{anio_vigilancia}."
            ),
        )
    else:
        tamano_ventana = limite_ventana
        st.caption(
            f":material/info: Con {tamano_ventana} años disponibles antes de "
            f"{anio_vigilancia} se usan todos en la línea base (mínimo recomendado por "
            "el INS Colombia)."
        )

    anios_excluidos = st.multiselect(
        "Excluir años de la línea base",
        options=anios_historicos_disponibles,
        default=[],
        key=f"{clave_base}_excluidos",
        placeholder="Ningún año excluido",
        help=(
            "Exclusión manual: un año con un brote atípico infla el canal si se incluye. "
            f"Al excluir un año, el sistema extiende la ventana con el año disponible más "
            f"antiguo siguiente para mantener los {tamano_ventana} años objetivo, si hay "
            "historia suficiente."
        ),
    )

    anios_base = _construir_linea_base(anios_historicos_disponibles, tamano_ventana, anios_excluidos)

    if len(anios_base) < VENTANA_MINIMA:
        st.warning(
            f"No es posible calcular: el INS Colombia recomienda un mínimo de "
            f"{VENTANA_MINIMA} años históricos, y después de las exclusiones solo "
            f"quedan {len(anios_base)}. Excluye menos años o amplía la ventana temporal.",
            icon=":material/warning:",
        )
        return None

    st.caption(
        f":material/history: Línea base: {len(anios_base)} años "
        f"({', '.join(str(anio) for anio in anios_base)})"
    )
    return anio_vigilancia, anios_base


def _construir_linea_base(anios_disponibles_desc: list[int], tamano_objetivo: int, excluidos: list[int]) -> list[int]:
    """Rellena la ventana con los anios mas recientes de anios_disponibles_desc (ya
    ordenado de mas reciente a mas antiguo), saltando los excluidos y extendiendo
    hacia anios mas antiguos hasta completar tamano_objetivo o agotar el historial.
    Asi, excluir un anio de la ventana la extiende automaticamente un anio mas
    atras en vez de simplemente reducirla.
    """
    excluidos_set = set(excluidos)
    seleccionados = []
    for anio in anios_disponibles_desc:
        if anio in excluidos_set:
            continue
        seleccionados.append(anio)
        if len(seleccionados) == tamano_objetivo:
            break
    return sorted(seleccionados)


def _graficar_canal(resultado: dict, etiqueta_metodo: str, territorio: str, anio_vigilancia: int) -> go.Figure:
    bandas = resultado["bandas"]
    serie_actual = resultado["serie_actual"]
    etiquetas_linea = ETIQUETAS_LINEAS[resultado["metodo"]]
    semanas = bandas["semana"].tolist()
    ceros = [0.0] * len(semanas)

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=semanas + semanas[::-1],
        y=bandas["inferior"].tolist() + ceros[::-1],
        fill="toself",
        fillcolor=_con_opacidad(_ZONA_COLOR[ZONA_EXITO], 0.10),
        line=dict(color="rgba(0,0,0,0)"),
        name="Zona éxito",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=semanas + semanas[::-1],
        y=bandas["central"].tolist() + bandas["inferior"].tolist()[::-1],
        fill="toself",
        fillcolor=_con_opacidad(_ZONA_COLOR[ZONA_SEGURIDAD], 0.38),
        line=dict(color="rgba(0,0,0,0)"),
        name="Zona seguridad",
        hoverinfo="skip",
    ))
    # Linea de frontera exito/seguridad: sin esto, las dos zonas verdes son dificiles
    # de distinguir aunque el relleno tenga distinta opacidad.
    fig.add_trace(go.Scatter(
        x=semanas, y=bandas["inferior"],
        mode="lines",
        line=dict(color=_ZONA_COLOR[ZONA_EXITO], width=1.5, dash="dot"),
        name=etiquetas_linea["inferior"],
    ))
    fig.add_trace(go.Scatter(
        x=semanas + semanas[::-1],
        y=bandas["superior"].tolist() + bandas["central"].tolist()[::-1],
        fill="toself",
        fillcolor=_con_opacidad(_ZONA_COLOR[ZONA_ALERTA], 0.20),
        line=dict(color="rgba(0,0,0,0)"),
        name="Zona alerta",
        hoverinfo="skip",
    ))
    fig.add_trace(go.Scatter(
        x=semanas, y=bandas["superior"],
        mode="lines",
        line=dict(color=_ZONA_COLOR[ZONA_EPIDEMIA], width=1.5, dash="dash"),
        name=etiquetas_linea["superior"],
    ))
    fig.add_trace(go.Scatter(
        x=semanas, y=bandas["central"],
        mode="lines",
        line=dict(color=_ZONA_COLOR[ZONA_SEGURIDAD], width=2),
        name=etiquetas_linea["central"],
    ))

    if not serie_actual.empty:
        colores_puntos = [_ZONA_COLOR.get(zona, "#95a5a6") for zona in serie_actual["zona"]]
        fig.add_trace(go.Scatter(
            x=serie_actual["semana"], y=serie_actual["casos"],
            mode="markers",
            marker=dict(color=colores_puntos, size=7, line=dict(width=1, color="#ffffff")),
            name=f"Año {anio_vigilancia}",
        ))
    else:
        fig.add_annotation(
            text=f"Sin datos notificados para {anio_vigilancia}",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )

    fig.update_layout(
        title=dict(text=etiqueta_metodo, font=dict(size=13)),
        xaxis=dict(title="Semana epidemiológica", tickmode="linear", tick0=1, dtick=4),
        yaxis=dict(title="Casos"),
        margin=dict(l=0, r=0, t=40, b=0),
        legend=dict(orientation="h", yanchor="bottom", y=-0.35),
    )
    return fig


def _con_opacidad(color_hex: str, alpha: float) -> str:
    color_hex = color_hex.lstrip("#")
    rojo, verde, azul = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
    return f"rgba({rojo},{verde},{azul},{alpha})"


# ---------------------------------------------------------------------------
# Dialogo de metodologia: adaptado del proyecto de pasantia (pages/2_Teoria.py),
# con la terminologia y las 3 lineas ya alineadas a como se llaman en este dashboard.
# ---------------------------------------------------------------------------

_ZONAS_DESCRIPCION = [
    (ZONA_EXITO, "Casos por debajo del límite inferior. Transmisión menor a la habitual, situación favorable."),
    (ZONA_SEGURIDAD, "Casos entre el límite inferior y la línea central. Comportamiento dentro de lo esperado."),
    (ZONA_ALERTA, "Casos entre la línea central y el límite superior. Exceso moderado, vigilancia reforzada."),
    (ZONA_EPIDEMIA, "Casos por encima del límite superior. Exceso epidémico, respuesta inmediata."),
]


@st.dialog("Metodología del canal endémico", width="large")
def _dialogo_metodologia() -> None:
    st.markdown(
        "El canal endémico compara los casos de cada semana epidemiológica del año de "
        "vigilancia contra el comportamiento histórico de esa misma semana en años "
        "anteriores. Divide el año en 4 zonas de intensidad epidemiológica (Bortman, 1999)."
    )

    columnas_zonas = st.columns(4)
    for columna, (zona, descripcion) in zip(columnas_zonas, _ZONAS_DESCRIPCION):
        with columna:
            st.markdown(
                f'<div style="background-color:{_con_opacidad(_ZONA_COLOR[zona], 0.15)}; '
                f'border-left: 4px solid {_ZONA_COLOR[zona]}; border-radius: 6px; '
                f'padding: 0.5rem 0.7rem; height: 100%;">'
                f'<strong>{zona}</strong><br><small>{descripcion}</small></div>',
                unsafe_allow_html=True,
            )

    st.divider()

    tab_cuartiles, tab_bortman, tab_comparativa, tab_recursos = st.tabs(
        ["Cuartiles / medianas", "Bortman", "Comparativa", "Recursos"]
    )

    with tab_cuartiles:
        st.markdown(
            "Método no paramétrico recomendado por el INS Colombia para municipios de "
            "alta transmisión: no asume ninguna distribución estadística, trabaja "
            "directamente con los valores históricos de cada semana."
        )
        st.latex(r"""
        \begin{aligned}
        \text{Cuartil inferior} &= P_{25}(V_S) \quad \leftarrow \text{frontera Éxito/Seguridad} \\
        \text{Mediana} &= P_{50}(V_S) \quad \leftarrow \text{frontera Seguridad/Alerta} \\
        \text{Cuartil superior} &= P_{75}(V_S) \quad \leftarrow \text{frontera Alerta/Epidemia}
        \end{aligned}
        """)
        st.caption(
            "V_S son los casos de la semana S en los años de la línea base histórica, "
            "ordenados de menor a mayor."
        )

        st.markdown("##### Ejemplo numérico")
        st.markdown(
            "Semana 14, línea base de 5 años: "
            "`{2019: 45, 2020: 32, 2021: 58, 2022: 40, 2024: 37}`. "
            "Ordenados: $[32,\\ 37,\\ 40,\\ 45,\\ 58]$ con $n = 5$."
        )
        st.latex(r"""
        \begin{aligned}
        \text{Cuartil inferior} &= P_{25} = 35.5 \\
        \text{Mediana} &= P_{50} = 40.0 \\
        \text{Cuartil superior} &= P_{75} = 51.3
        \end{aligned}
        """)
        st.markdown(
            "**Clasificación de un caso** $c$ **contra estos límites:**\n\n"
            "| Casos año de vigilancia | Condición | Zona |\n"
            "|---|---|---|\n"
            "| 30 | $30 < 35.5$ | Éxito |\n"
            "| 38 | $35.5 \\leq 38 < 40$ | Seguridad |\n"
            "| 48 | $40 \\leq 48 < 51.3$ | Alerta |\n"
            "| 60 | $60 \\geq 51.3$ | Epidemia |"
        )

    with tab_bortman:
        st.markdown(
            "Método paramétrico (Bortman, 1999): transforma los casos al logaritmo, "
            "calcula media y desviación en esa escala, y regresa a la escala original. "
            "El límite inferior y superior son el intervalo de confianza al 95% de la "
            "media histórica, no ±1 desviación estándar de los años individuales."
        )
        st.latex(r"""
        \begin{aligned}
        L_i &= \ln(v_i + 1) &&\text{corrección de Kirkwood, permite semanas en cero} \\
        \mu &= \frac{1}{n}\sum_{i=1}^{n} L_i
            \qquad DE = \sqrt{\frac{\sum (L_i-\mu)^2}{n-1}} \\
        m &= t_{n-1} \cdot \frac{DE}{\sqrt{n}} &&\text{margen del IC95\%} \\[6pt]
        \text{Límite inferior IC 95\%} &= e^{\mu - m} - 1 &&\leftarrow \text{frontera Éxito/Seguridad} \\
        \text{Umbral estacional} &= e^{\mu} - 1 &&\leftarrow \text{frontera Seguridad/Alerta} \\
        \text{Límite superior IC 95\%} &= e^{\mu + m} - 1 &&\leftarrow \text{frontera Alerta/Epidemia}
        \end{aligned}
        """)
        st.caption(
            "t es el valor de la distribución t de Student para IC95% con n-1 grados de "
            "libertad, según los años que queden en la línea base histórica."
        )

        st.markdown("##### Ejemplo numérico")
        st.markdown(
            "Mismos datos de la semana 14: $v = [32, 37, 40, 45, 58]$, $n = 5$ años, "
            "$t_{4} = 2.78$ (tabla de Bortman, 1999)."
        )
        col_paso_1, col_paso_2 = st.columns(2)
        with col_paso_1:
            st.markdown("**Corrección de Kirkwood y logaritmo:**")
            st.latex(r"""
            \begin{array}{rll}
            v_i & v_i+1 & L_i=\ln(v_i+1) \\
            \hline
            32 & 33 & 3.497 \\
            37 & 38 & 3.638 \\
            40 & 41 & 3.714 \\
            45 & 46 & 3.829 \\
            58 & 59 & 4.078 \\
            \end{array}
            """)
            st.markdown("**Media y desviación en escala log:**")
            st.latex(r"\mu = \frac{3.497+3.638+3.714+3.829+4.078}{5} = 3.751")
            st.latex(r"DE = \sqrt{\frac{0.192}{4}} = 0.219")
            st.markdown("**Margen del IC95%:**")
            st.latex(r"m = 2.78 \times \frac{0.219}{\sqrt{5}} = 0.272")
        with col_paso_2:
            st.markdown("**Las tres líneas del canal:**")
            st.latex(r"""
            \begin{aligned}
            \text{Límite inferior IC 95\%} &= e^{3.751-0.272}-1 = \mathbf{31.4} \\[6pt]
            \text{Umbral estacional} &= e^{3.751}-1 = \mathbf{41.5} \\[6pt]
            \text{Límite superior IC 95\%} &= e^{3.751+0.272}-1 = \mathbf{54.9}
            \end{aligned}
            """)
            st.markdown("**Clasificación de un caso** $c$:")
            st.markdown(
                "| Casos año de vigilancia | Condición | Zona |\n"
                "|---|---|---|\n"
                "| 30 | $30 < 31.4$ | Éxito |\n"
                "| 38 | $31.4 \\leq 38 < 41.5$ | Seguridad |\n"
                "| 48 | $41.5 \\leq 48 < 54.9$ | Alerta |\n"
                "| 60 | $60 \\geq 54.9$ | Epidemia |"
            )

    with tab_comparativa:
        st.markdown(
            "El INS Colombia usa ambos métodos en paralelo para confirmar señales de "
            "alerta; por eso este dashboard los muestra lado a lado en vez de obligar "
            "a elegir uno."
        )
        st.markdown(
            "| | Cuartiles | Bortman |\n"
            "|---|---|---|\n"
            "| Tipo | No paramétrico | Paramétrico |\n"
            "| Sensible a valores extremos | Poco | Moderado |\n"
            "| Manejo de semanas en cero | Directo (son un valor más) | "
            "Corrección de Kirkwood (+1/−1) |\n"
            "| Límite inferior y superior basados en | Percentiles P25 y P75 | "
            "IC95% de la media en escala logarítmica |\n"
            "| Años mínimos recomendados en la línea base | 5 a 7 | 5 a 7 |"
        )

    with tab_recursos:
        st.markdown(":material/description: **Documentos oficiales**")
        st.markdown(
            "- [Protocolo de vigilancia de Dengue — INS Colombia]"
            "(https://www.ins.gov.co/buscador-eventos/Paginas/Info-Evento.aspx)\n"
            "- [Manual del usuario SIVIGILA — INS]"
            "(https://www.ins.gov.co/BibliotecaDigital/1-manual-sivigila-2018-2020.pdf)\n"
            "- [Portal de microdatos SIVIGILA — INS]"
            "(https://www.ins.gov.co/buscador-eventos/Paginas/Vigilancia-Rutinaria.aspx)\n"
            "- [Análisis e identificación de comportamientos inusuales de eventos de "
            "interés en salud pública — INS]"
            "(https://www.ins.gov.co/Noticias/documentosfetp/XXXI-Curso-Internacional-MEtodos/"
            "14-Presentaciones_DIA_6/2_comportamientos_inusuales.pdf)\n"
            "- [Bortman M. (1999) — Artículo original]"
            "(https://www.scielosp.org/pdf/rpsp/v5n1/5n1a1.pdf)"
        )
        st.caption(
            "Bortman M. Elaboración de corredores o canales endémicos mediante planillas "
            "de cálculo. Rev Panam Salud Pública. 1999;5(1)."
        )

    if st.button("Cerrar", width="stretch"):
        st.rerun()
