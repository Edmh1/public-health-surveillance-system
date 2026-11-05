"""Pestana 4 Morbilidad: notificacion, clasificacion y hospitalizacion.

Orden de arriba abajo (regla 1.4 de DESIGN.md: una grafica por fila, salvo
pares complementarios):
  1. KPIs: casos totales, incidencia, hospitalizados, dengue grave, hospitalizados graves
  2. Par: Casos por tipo | Casos por clasificacion final (composicion inicial y
     final del mismo universo)
  3. Grafico de Sankey del flujo de clasificacion, a ancho completo, justo
     debajo: se ve la composicion al notificar, la composicion despues del
     ajuste y luego el flujo que conecta las dos.
  4. Casos por semana epidemiologica y tipo (barras apiladas)
  5. Clasificacion final de los casos por semana epidemiologica
  6. Casos hospitalizados por semana epidemiologica
  7. Tasa de hospitalizacion por territorio
  8. Incidencia de dengue por subregion
  9. Casos por fuente de notificacion

Las graficas semanales no tienen selector de anio propio: muestran el ULTIMO
anio del filtro temporal global, declarado en su sufijo (fase 2).

Casos = cod_eve 210 (dengue) y 220 (dengue grave). Los codigos numericos no van
en las etiquetas de las graficas (ver ETIQUETAS_TIPO_CASO), solo en las notas
metodologicas.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import (
    ANCHO_MEDIA_COLUMNA,
    AZUL_INSTITUCIONAL,
    MINIMO_CATEGORIAS_DISTRIBUCION,
    MINIMO_PUNTOS_SERIE,
    NARANJA_INSTITUCIONAL,
    avisar_datos_insuficientes,
    describir_cantidad,
    eje_semanal,
    hay_datos_suficientes,
    mostrar_grafica,
    rango_con_margen,
)
from core.dashboard_base.filtros import CLAVE_FILTROS, resumen_filtros_activos, ultimo_anio_del_filtro
from pathologies.dengue.geografia import obtener_mapeo_subregion
from pathologies.dengue.indicators import calcular_indicadores
from pathologies.dengue.poblacion import calcular_tasa_por_municipio, calcular_tasa_por_subregion

COD_DENGUE = 210
COD_DENGUE_GRAVE = 220
CODIGOS_CASOS = {COD_DENGUE, COD_DENGUE_GRAVE}

# Unica fuente de las etiquetas de tipo de caso en esta pestana: sin el codigo
# numerico entre parentesis (el codigo queda en las notas metodologicas).
ETIQUETAS_TIPO_CASO = {COD_DENGUE: "Dengue", COD_DENGUE_GRAVE: "Dengue grave"}
COLORES_TIPO_CASO = {
    ETIQUETAS_TIPO_CASO[COD_DENGUE]: AZUL_INSTITUCIONAL,
    ETIQUETAS_TIPO_CASO[COD_DENGUE_GRAVE]: NARANJA_INSTITUCIONAL,
}

_TIP_CAS_MAP = {
    "1": "Sospechoso",
    "2": "Probable",
    "3": "Confirmado por laboratorio",
    "4": "Confirmado por clínica",
    "5": "Confirmado por nexo epidemiológico",
}

_ESTADO_FINAL_MAP = {
    "2": "Probable",
    "3": "Confirmado por laboratorio",
    "4": "Confirmado por clínica",
    "5": "Confirmado por nexo epidemiológico",
    "6": "Descartado",
    "7": "Otro",
    "0": "Sin ajuste",
}

_FUENTE_MAP = {
    1: "Rutinaria",
    2: "Búsqueda activa institucional",
    3: "Vigilancia intensificada",
    4: "Búsqueda activa comunitaria",
    5: "Investigación",
}

# Un color fijo por clasificacion del caso, el mismo en el Sankey, en el anillo
# de clasificacion final y en la clasificacion final por semana. Tonos de familias
# bien distintas: ningun par se confunde (antes el violeta de Probable se
# confundia con el azul de Confirmado por laboratorio). Verde, amarillo y rojo
# quedan reservados para el canal endemico (DESIGN.md).
COLORES_CLASIFICACION = {
    "Confirmado por laboratorio": "#1b3a6b",
    "Confirmado por nexo epidemiológico": "#e8852c",
    "Confirmado por clínica": "#0891b2",
    "Probable": "#c026d3",
    "Sospechoso": "#8c564b",
    "Descartado": "#475569",
    "Sin ajuste": "#a8a29e",
    "Otro (inicial)": "#b0b7c3",
    "Otro (final)": "#b0b7c3",
    "Otro": "#b0b7c3",
}

_TIPO_CASO_OPTS = {
    "Ambos": [COD_DENGUE, COD_DENGUE_GRAVE],
    ETIQUETAS_TIPO_CASO[COD_DENGUE]: [COD_DENGUE],
    ETIQUETAS_TIPO_CASO[COD_DENGUE_GRAVE]: [COD_DENGUE_GRAVE],
}

_LAYOUT = dict(margin=dict(l=0, r=0, t=70, b=0))

_NOTA_CODIGOS = "Casos con cod_eve 210 (dengue) y 220 (dengue grave)."


def _subregiones_en_alcance(casos: pd.DataFrame) -> list[str]:
    """Subregiones que el filtro global deja dentro del alcance. Sin filtro
    territorial, las 5; con filtro, solo las elegidas: calcular_tasa_por_subregion
    devuelve las 5 y las que quedan fuera del filtro saldrian en cero aunque no
    sea cierto."""
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    if filtros.get("subregion") or filtros.get("nom_mun_o"):
        return sorted(casos["subregion"].dropna().unique())
    return sorted(set(obtener_mapeo_subregion().values()))


def _avisar_una_sola_subregion(subregiones: list[str]) -> None:
    avisar_datos_insuficientes(
        f"Con el filtro territorial actual hay {describir_cantidad(len(subregiones), 'subregión', 'subregiones')} "
        "en el alcance. Para comparar entre subregiones, quita o amplía el filtro de subregión o "
        "municipio en la barra lateral."
    )


def _pct(n: float, total: float) -> str:
    if total == 0:
        return "-"
    p = n / total * 100
    if p >= 1:
        return f"{p:.1f}%"
    elif p >= 0.1:
        return f"{p:.2f}%"
    elif p > 0:
        return f"{p:.3f}%"
    return "0%"


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def mostrar_morbilidad(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    # Incidencia (tasa poblacional) vive aca ademas de en Situacion: en Situacion
    # es de un solo anio; aca sigue el filtro global, asi que se puede ver por
    # rangos de anios. Respeta la regla de "no disponible" porque sale del mismo
    # calcular_indicadores.
    filtros_actuales = st.session_state.get(CLAVE_FILTROS, {})
    resultado_indicadores = calcular_indicadores(datos, filtros_actuales)

    anios = sorted(int(a) for a in casos["ano"].dropna().unique())
    if anios:
        periodo = str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}"
        st.caption(
            f":material/calendar_today: Indicadores del período filtrado ({periodo}). "
            "La incidencia es una tasa anual por 100.000 habitantes."
        )

    _mostrar_kpis(casos, resultado_indicadores["incidencia"])
    st.space("small")

    # Par: composicion inicial (tipo) y final (clasificacion final)
    col_tipo, col_clasificacion = st.columns(2)
    with col_tipo:
        with st.container(border=True, height="stretch"):
            _mostrar_tipo_caso(casos)
    with col_clasificacion:
        with st.container(border=True, height="stretch"):
            _mostrar_clasificacion_final_dona(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_sankey_clasificacion(casos)

    anio_analisis = ultimo_anio_del_filtro()

    st.space("small")
    with st.container(border=True):
        _mostrar_evolucion_semanal(casos, anio_analisis)

    st.space("small")
    with st.container(border=True):
        _mostrar_clasificacion_final_semanal(casos, anio_analisis)

    st.space("small")
    with st.container(border=True):
        _mostrar_hospitalizacion_semanal(casos, anio_analisis)

    st.space("small")
    with st.container(border=True):
        _mostrar_hospitalizacion_territorial(casos)

    st.space("small")
    with st.container(border=True):
        _mostrar_incidencia_subregion(casos)

    st.space("small")
    with st.container(border=True):
        _mostrar_fuente(casos)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame, incidencia: float | None) -> None:
    total = len(casos)
    graves = int((casos["cod_eve"] == COD_DENGUE_GRAVE).sum())

    hosp = 0
    hosp_graves = 0
    if "pac_hos" in casos.columns:
        hosp = int((casos["pac_hos"] == 1).sum())
        hosp_graves = int(
            ((casos["cod_eve"] == COD_DENGUE_GRAVE) & (casos["pac_hos"] == 1)).sum()
        )

    incidencia_txt = f"{incidencia:,.1f}" if incidencia is not None else "No disponible"

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Casos totales", f"{total:,}", help=_NOTA_CODIGOS, border=True)
    with c2:
        st.metric(
            "Incidencia",
            incidencia_txt,
            help=(
                "Casos de dengue y dengue grave / población en riesgo x 100.000. No disponible "
                "si falta población DANE, o el sistema todavía no tiene los 6 años de histórico "
                "que pide el lineamiento MSPS/INS para calcular la estratificación de riesgo."
            ),
            border=True,
        )
    with c3:
        st.metric(
            "Hospitalizados",
            f"{hosp:,}",
            delta=_pct(hosp, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )
    with c4:
        # Proporcion de graves: vive aqui como KPI (ya no como eje secundario de
        # la grafica semanal por tipo).
        st.metric(
            ETIQUETAS_TIPO_CASO[COD_DENGUE_GRAVE],
            f"{graves:,}",
            delta=_pct(graves, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            help="Casos de dengue grave (cod_eve 220) sobre el total de casos.",
            border=True,
        )
    with c5:
        st.metric(
            "Hospitalizados graves",
            f"{hosp_graves:,}",
            delta=_pct(hosp_graves, graves),
            delta_color="off",
            delta_arrow="off",
            delta_description="de los graves",
            help="Hospitalizados de dengue grave sobre el total de casos graves",
            border=True,
        )


# ---------------------------------------------------------------------------
# Casos por tipo (dona)
# ---------------------------------------------------------------------------

def _mostrar_tipo_caso(casos: pd.DataFrame) -> None:
    st.subheader(":material/pie_chart: Casos por tipo")

    conteo = casos["cod_eve"].value_counts()
    df = pd.DataFrame({
        "tipo": [ETIQUETAS_TIPO_CASO.get(codigo, str(codigo)) for codigo in conteo.index],
        "casos": conteo.values,
    })
    if not hay_datos_suficientes(df, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales los {len(casos):,} casos son de un solo tipo "
            f"({df['tipo'].iloc[0]}). Amplía el período o el territorio para ver la composición."
        )
        return

    fig = px.pie(
        df, names="tipo", values="casos", hole=0.55,
        color="tipo", color_discrete_map=COLORES_TIPO_CASO,
    )
    fig.update_traces(
        texttemplate="%{value:,} (%{percent})",
        textposition="outside",
    )
    fig.update_layout(
        showlegend=True,
        height=420,
        margin=dict(l=20, r=20, t=70, b=20),
    )
    mostrar_grafica(fig, "Casos por tipo", resumen_filtros_activos(), ancho=ANCHO_MEDIA_COLUMNA)


# ---------------------------------------------------------------------------
# Casos por clasificacion final (dona)
# ---------------------------------------------------------------------------

def _mostrar_clasificacion_final_dona(casos: pd.DataFrame) -> None:
    st.subheader(":material/fact_check: Casos por clasificación final")

    if "estado_final_de_caso" not in casos.columns:
        st.caption("Sin datos.")
        return

    conteo = (
        casos["estado_final_de_caso"]
        .dropna()
        .astype(str)
        .map(_ESTADO_FINAL_MAP)
        .value_counts()
    )
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales todos los casos con clasificación final caen en "
            f"{describir_cantidad(len(conteo), 'categoría', 'categorías')}. Amplía el período o "
            "el territorio para ver la composición."
        )
        return

    # Colores explicitos para evitar que la 3.a porcion reciba azul cielo.
    fig = px.pie(
        names=conteo.index,
        values=conteo.values,
        hole=0.55,
        color=conteo.index,
        color_discrete_map=COLORES_CLASIFICACION,
    )
    fig.update_traces(
        texttemplate="%{value:,} (%{percent})",
        textposition="outside",
    )
    fig.update_layout(
        showlegend=True,
        height=420,
        margin=dict(l=20, r=20, t=70, b=20),
    )
    mostrar_grafica(fig, "Casos por clasificación final", resumen_filtros_activos(), ancho=ANCHO_MEDIA_COLUMNA)


# ---------------------------------------------------------------------------
# Grafico de Sankey del flujo de clasificacion inicial -> final
# ---------------------------------------------------------------------------

def _hex_rgba(hex_color: str, alpha: float) -> str:
    """Convierte un color hex a rgba(r,g,b,alpha) para usarlo en Plotly."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def _mostrar_sankey_clasificacion(casos: pd.DataFrame) -> None:
    st.subheader(":material/account_tree: Gráfico de Sankey de flujo de clasificación de casos")

    cols_req = {"tip_cas", "estado_final_de_caso"}
    if not cols_req.issubset(casos.columns):
        st.caption("Sin datos de clasificación.")
        return

    df = casos[["tip_cas", "estado_final_de_caso"]].dropna().copy()
    df["inicial"] = df["tip_cas"].astype(str).map(_TIP_CAS_MAP).fillna("Otro (inicial)")
    df["final"] = df["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro (final)")

    if df.empty:
        st.caption("Sin datos de flujo de clasificación.")
        return

    conteo_inicial = df.groupby("inicial").size().reset_index(name="n")

    # Solo interesan los cambios de clasificacion: un caso que empieza y termina
    # en el mismo estado no aporta flujo que leer, y ademas dibujaria un lazo
    # circular sobre su propio nodo.
    transiciones = df.groupby(["inicial", "final"]).size().reset_index(name="n")
    transiciones = transiciones[transiciones["inicial"] != transiciones["final"]]

    if transiciones.empty:
        avisar_datos_insuficientes(
            f"Con los filtros actuales ninguno de los {len(df):,} casos cambió de clasificación "
            "entre la notificación y el ajuste final, así que no hay flujo que dibujar. Amplía el "
            "período o el territorio."
        )
        return

    # Colores por estado (no por posicion izq/der): mismo color para un estado
    # independientemente de si aparece como clasificacion inicial o final.
    # Verde/amarillo/rojo quedan reservados para el canal endemico (DESIGN.md).
    _PALETA_ESTADOS = COLORES_CLASIFICACION
    # Tres columnas de nodos: casos totales | clasificacion inicial | clasificacion
    # final. Inicial y final llevan nodos SEPARADOS aunque compartan etiqueta: si
    # "Probable" fuera un solo nodo, la transicion sin cambio se dibujaria como un
    # lazo circular sobre si misma.
    NODO_TOTAL = "Casos totales"
    nodos_iniciales = (
        conteo_inicial.sort_values("n", ascending=False)["inicial"].tolist()
    )

    # Orden vertical de la columna final: cada estado se coloca a la altura
    # promedio (ponderada por casos) de las clasificaciones iniciales que lo
    # alimentan, para minimizar el cruce de enlaces.
    posicion_inicial = {nombre: i for i, nombre in enumerate(nodos_iniciales)}
    altura_promedio_final = {}
    for nombre_final, grupo in transiciones.groupby("final"):
        peso = grupo["n"].sum()
        suma_ponderada = sum(
            posicion_inicial[fila["inicial"]] * fila["n"] for _, fila in grupo.iterrows()
        )
        altura_promedio_final[nombre_final] = suma_ponderada / peso
    nodos_finales = sorted(altura_promedio_final, key=altura_promedio_final.get)

    etiquetas = [NODO_TOTAL] + nodos_iniciales + nodos_finales
    idx_inicial = {nombre: 1 + i for i, nombre in enumerate(nodos_iniciales)}
    idx_final = {
        nombre: 1 + len(nodos_iniciales) + i for i, nombre in enumerate(nodos_finales)
    }

    # Posicion fija por columna: sin la x, un nodo inicial sin casos que cambien
    # de clasificacion (sin flujo de salida) se iria a la columna derecha por el
    # acomodo automatico de Plotly. La y fija el orden vertical calculado arriba.
    total_casos = int(conteo_inicial["n"].sum())

    def _centros_verticales(valores_columna: list[int]) -> list[float]:
        # La pila de cada columna se centra verticalmente: una columna con poco
        # flujo (la final solo lleva los casos que cambiaron) queda alineada al
        # medio del diagrama en vez de amontonada arriba.
        separacion = 0.04
        margen = 0.02
        cantidad = len(valores_columna)
        util = 1.0 - 2 * margen - separacion * max(cantidad - 1, 0)
        altos = [util * valor / total_casos for valor in valores_columna]
        alto_pila = sum(altos) + separacion * max(cantidad - 1, 0)
        cursor = max((1.0 - alto_pila) / 2, margen)
        centros = []
        for alto in altos:
            centros.append(min(max(cursor + alto / 2, 0.01), 0.99))
            cursor += alto + separacion
        return centros

    casos_por_inicial = conteo_inicial.set_index("inicial")["n"]
    casos_por_final = transiciones.groupby("final")["n"].sum()

    posiciones_x = (
        [0.01] + [0.5] * len(nodos_iniciales) + [0.99] * len(nodos_finales)
    )
    posiciones_y = (
        [0.5]
        + _centros_verticales([int(casos_por_inicial[n]) for n in nodos_iniciales])
        + _centros_verticales([int(casos_por_final[n]) for n in nodos_finales])
    )

    # El nodo del total va en gris oscuro: en azul se confundia con
    # "Confirmado por laboratorio", que tiene el azul institucional.
    colores_nodos = (
        ["#374151"]
        + [_PALETA_ESTADOS.get(n, "#6b7280") for n in nodos_iniciales]
        + [_PALETA_ESTADOS.get(n, "#6b7280") for n in nodos_finales]
    )

    # Flujos coloreados por la clasificacion inicial con transparencia: el ojo
    # puede seguir "que le paso a cada clasificacion inicial" por color.
    fuentes, destinos, valores, colores_links = [], [], [], []

    # Plotly apila los enlaces de cada nodo en el orden en que llegan, no por la
    # altura del nodo destino. Si se emiten en el orden del dataframe las bandas
    # se cruzan aunque los nodos esten bien colocados, asi que se ordenan por la
    # posicion vertical ya calculada (inicial, y luego final).
    posicion_final = {nombre: i for i, nombre in enumerate(nodos_finales)}

    conteo_inicial_ordenado = conteo_inicial.copy()
    conteo_inicial_ordenado["orden_inicial"] = conteo_inicial_ordenado["inicial"].map(posicion_inicial)
    conteo_inicial_ordenado = conteo_inicial_ordenado.sort_values("orden_inicial")

    transiciones_ordenadas = transiciones.copy()
    transiciones_ordenadas["orden_inicial"] = transiciones_ordenadas["inicial"].map(posicion_inicial)
    transiciones_ordenadas["orden_final"] = transiciones_ordenadas["final"].map(posicion_final)
    transiciones_ordenadas = transiciones_ordenadas.sort_values(["orden_inicial", "orden_final"])

    for _, fila in conteo_inicial_ordenado.iterrows():
        fuentes.append(0)
        destinos.append(idx_inicial[fila["inicial"]])
        valores.append(int(fila["n"]))
        colores_links.append(_hex_rgba(_PALETA_ESTADOS.get(fila["inicial"], "#6b7280"), 0.45))

    for _, fila in transiciones_ordenadas.iterrows():
        fuentes.append(idx_inicial[fila["inicial"]])
        destinos.append(idx_final[fila["final"]])
        valores.append(int(fila["n"]))
        colores_links.append(_hex_rgba(_PALETA_ESTADOS.get(fila["inicial"], "#6b7280"), 0.45))

    fig = go.Figure(go.Sankey(
        arrangement="snap",
        # Deja libre la franja de arriba para los encabezados de columna.
        domain=dict(y=[0, 0.92]),
        node=dict(
            label=etiquetas,
            x=posiciones_x,
            y=posiciones_y,
            color=colores_nodos,
            pad=24,
            thickness=22,
            line=dict(color="white", width=0.8),
            # Texto propio en espanol: el de Plotly por defecto dice "incoming
            # flow count / outgoing flow count" (cantidad de enlaces, no de casos).
            hovertemplate="%{label}<br>%{value:,} casos<extra></extra>",
        ),
        link=dict(
            source=fuentes,
            target=destinos,
            value=valores,
            color=colores_links,
            hovertemplate="%{source.label} → %{target.label}: %{value:,} casos<extra></extra>",
        ),
        textfont=dict(size=14, color="#1a1a1a", family="sans-serif"),
    ))

    # Encabezados de etapa sobre cada columna, para leer el diagrama sin adivinar.
    encabezados = [
        (0.01, "left", "Total"),
        (0.5, "center", "Clasificación inicial"),
        (0.99, "right", "Clasificación final"),
    ]
    # Van por DENTRO del borde superior del area de dibujo (y=1, yanchor top) y
    # el Sankey baja un poco su dominio para dejarles sitio: asi la leyenda y el
    # titulo del tema quedan encima sin pisarse, tambien en pantalla completa.
    for pos_x, ancla, texto in encabezados:
        fig.add_annotation(
            x=pos_x, y=1, xref="paper", yref="paper", yanchor="top",
            text=f"<b>{texto}</b>", showarrow=False,
            xanchor=ancla, font=dict(color="#374151"),
        )

    # Leyenda de colores por estado. El trazo Sankey no genera leyenda propia,
    # asi que se agregan puntos invisibles (sin datos) solo por su entrada de
    # leyenda; los ejes cartesianos que introducen se ocultan.
    estados_en_leyenda = set()
    for nombre in nodos_iniciales + nodos_finales:
        canonico = nombre.replace(" (inicial)", "").replace(" (final)", "")
        if canonico in estados_en_leyenda:
            continue
        estados_en_leyenda.add(canonico)
        fig.add_trace(go.Scatter(
            x=[None], y=[None],
            mode="markers",
            marker=dict(size=10, symbol="square", color=_PALETA_ESTADOS.get(nombre, "#6b7280")),
            name=canonico,
            hoverinfo="skip",
        ))

    fig.update_layout(
        height=660,
        margin=dict(l=10, r=10, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=True,
    )
    mostrar_grafica(fig, "Gráfico de Sankey de flujo de clasificación de casos", resumen_filtros_activos())


# ---------------------------------------------------------------------------
# Casos por semana epidemiologica y tipo (barras apiladas)
# ---------------------------------------------------------------------------

def _mostrar_evolucion_semanal(casos: pd.DataFrame, anio: int | None) -> None:
    st.subheader(":material/stacked_bar_chart: Casos por semana epidemiológica y tipo")

    if "semana" not in casos.columns or anio is None:
        st.caption("Sin datos de semana.")
        return

    subset = casos[casos["ano"] == anio].copy()
    subset["tipo"] = subset["cod_eve"].map(ETIQUETAS_TIPO_CASO)
    semanal = subset.groupby(["semana", "tipo"]).size().reset_index(name="casos")
    semanas_con_casos = semanal["semana"].nunique()
    if semanas_con_casos < MINIMO_PUNTOS_SERIE:
        avisar_datos_insuficientes(
            f"Con los filtros actuales {anio} tiene "
            f"{describir_cantidad(len(subset), 'caso', 'casos', femenino=False)} en "
            f"{describir_cantidad(semanas_con_casos, 'semana epidemiológica', 'semanas epidemiológicas')}. "
            "Amplía el rango de semanas o el territorio para ver la serie semanal."
        )
        return

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="tipo",
        barmode="stack",
        labels={"semana": "Semana epidemiológica", "casos": "Casos", "tipo": "Tipo"},
        color_discrete_map=COLORES_TIPO_CASO,
        category_orders={"tipo": [ETIQUETAS_TIPO_CASO[COD_DENGUE], ETIQUETAS_TIPO_CASO[COD_DENGUE_GRAVE]]},
    )
    fig.update_layout(legend_title_text="", **_LAYOUT)
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
    mostrar_grafica(fig, "Casos por semana epidemiológica y tipo", resumen_filtros_activos(periodo=str(anio)))
    st.caption(f"Año {anio}: el último del filtro de años de la barra lateral.")


# ---------------------------------------------------------------------------
# Clasificacion final de los casos por semana epidemiologica
# ---------------------------------------------------------------------------

def _mostrar_clasificacion_final_semanal(casos: pd.DataFrame, anio: int | None) -> None:
    st.subheader(":material/stacked_bar_chart: Clasificación final de los casos por semana epidemiológica")

    if "semana" not in casos.columns or "estado_final_de_caso" not in casos.columns or anio is None:
        st.caption("Sin datos.")
        return

    subset = casos[casos["ano"] == anio].copy()
    subset["clasificacion"] = (
        subset["estado_final_de_caso"].astype(str).map(_ESTADO_FINAL_MAP).fillna("Otro")
    )

    semanal = subset.groupby(["semana", "clasificacion"]).size().reset_index(name="casos")
    semanas_con_casos = semanal["semana"].nunique()
    if semanas_con_casos < MINIMO_PUNTOS_SERIE:
        avisar_datos_insuficientes(
            f"Con los filtros actuales {anio} tiene casos en "
            f"{describir_cantidad(semanas_con_casos, 'semana epidemiológica', 'semanas epidemiológicas')}. "
            "Amplía el rango de semanas o el territorio para ver la serie semanal."
        )
        return

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="clasificacion",
        barmode="stack",
        labels={"semana": "Semana epidemiológica", "casos": "Casos", "clasificacion": "Clasificación"},
        color_discrete_map=COLORES_CLASIFICACION,
    )
    fig.update_layout(height=440, legend_title_text="", **_LAYOUT)
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
    mostrar_grafica(fig, "Clasificación final de los casos por semana epidemiológica", resumen_filtros_activos(periodo=str(anio)))
    st.caption(f"Año {anio}: el último del filtro de años de la barra lateral.")


# ---------------------------------------------------------------------------
# Casos hospitalizados por semana epidemiologica
# ---------------------------------------------------------------------------

def _mostrar_hospitalizacion_semanal(casos: pd.DataFrame, anio: int | None) -> None:
    st.subheader(":material/local_hospital: Casos hospitalizados por semana epidemiológica")

    if "pac_hos" not in casos.columns or "semana" not in casos.columns or anio is None:
        st.caption("Sin datos.")
        return

    subset = casos[(casos["ano"] == anio) & (casos["pac_hos"] == 1)].copy()
    subset["tipo"] = subset["cod_eve"].map(ETIQUETAS_TIPO_CASO)

    semanal = subset.groupby(["semana", "tipo"]).size().reset_index(name="casos")
    semanas_con_casos = semanal["semana"].nunique()
    if semanas_con_casos < MINIMO_PUNTOS_SERIE:
        avisar_datos_insuficientes(
            f"Con los filtros actuales {anio} tiene "
            f"{describir_cantidad(len(subset), 'caso hospitalizado', 'casos hospitalizados', femenino=False)} en "
            f"{describir_cantidad(semanas_con_casos, 'semana epidemiológica', 'semanas epidemiológicas')}. "
            "Amplía el rango de semanas o el territorio para ver la serie semanal."
        )
        return

    fig = px.bar(
        semanal,
        x="semana",
        y="casos",
        color="tipo",
        barmode="stack",
        labels={"semana": "Semana epidemiológica", "casos": "Casos hospitalizados", "tipo": ""},
        color_discrete_map=COLORES_TIPO_CASO,
        category_orders={"tipo": [ETIQUETAS_TIPO_CASO[COD_DENGUE], ETIQUETAS_TIPO_CASO[COD_DENGUE_GRAVE]]},
    )
    fig.update_layout(legend_title_text="", **_LAYOUT)
    fig.update_xaxes(**eje_semanal(int(semanal["semana"].max())))
    mostrar_grafica(fig, "Casos hospitalizados por semana epidemiológica", resumen_filtros_activos(periodo=str(anio)))
    st.caption(f"Año {anio}: el último del filtro de años de la barra lateral. Casos con hospitalización registrada.")


# ---------------------------------------------------------------------------
# Tasa de hospitalizacion por territorio (subregion y municipio)
# ---------------------------------------------------------------------------

def _mostrar_hospitalizacion_territorial(casos: pd.DataFrame) -> None:
    st.subheader(":material/map: Tasa de hospitalización por territorio")

    if "pac_hos" not in casos.columns:
        st.caption("Sin datos de hospitalización.")
        return

    # Selector de representacion: elige que tipo de caso se dibuja.
    tipo_sel = st.segmented_control(
        "Tipo de caso",
        list(_TIPO_CASO_OPTS.keys()),
        default="Ambos",
        required=True,
        key="morbilidad_tipo_hosp",
    )
    codigos = _TIPO_CASO_OPTS.get(tipo_sel, list(CODIGOS_CASOS))
    subset = casos[(casos["cod_eve"].isin(codigos)) & (casos["pac_hos"] == 1)]

    if subset.empty:
        avisar_datos_insuficientes(
            "Con los filtros actuales no hay casos hospitalizados de ese tipo. Amplía el período "
            "o el territorio."
        )
        return

    anios_en_alcance = sorted(int(a) for a in casos["ano"].dropna().unique())
    contexto = resumen_filtros_activos()
    if tipo_sel != "Ambos":
        contexto = f"{contexto} · {tipo_sel}"

    if "subregion" in subset.columns:
        mapeo_subregion = obtener_mapeo_subregion()
        tasas = calcular_tasa_por_subregion(subset, anios_en_alcance, mapeo_subregion)

        sub = pd.DataFrame({"territorio": list(tasas.keys()), "tasa": list(tasas.values())})
        subregiones = _subregiones_en_alcance(casos)
        sub = sub[sub["territorio"].isin(subregiones)]
        sub = sub.dropna(subset=["tasa"]).sort_values("tasa")
        st.markdown("##### Por subregión")
        if len(subregiones) < MINIMO_CATEGORIAS_DISTRIBUCION:
            _avisar_una_sola_subregion(subregiones)
        elif sub.empty:
            st.caption("Sin población DANE disponible para el período filtrado.")
        else:
            fig_sub = px.bar(
                sub, x="tasa", y="territorio", text="tasa",
                orientation="h",
                labels={"tasa": "Hospitalizados x100.000 hab.", "territorio": ""},
            )
            fig_sub.update_traces(
                textposition="outside",
                texttemplate="%{text:.1f}",
                marker_color=AZUL_INSTITUCIONAL,
                name="Tasa x100.000 hab.",
                showlegend=True,
            )
            fig_sub.update_layout(
                margin=dict(l=0, r=0, t=70, b=0),
                xaxis={"range": rango_con_margen(sub["tasa"].max())},
            )
            mostrar_grafica(fig_sub, "Tasa de hospitalización por subregión", contexto)

    if "nom_mun_o" in subset.columns and "cod_mun_completo" in subset.columns:
        municipios_con_casos = sorted(subset["cod_mun_completo"].dropna().unique().astype(int))
        tasas_municipio = calcular_tasa_por_municipio(subset, anios_en_alcance, municipios_con_casos)

        nombres_municipio = (
            subset.dropna(subset=["nom_mun_o"])
            .drop_duplicates(subset=["cod_mun_completo"])
            .set_index("cod_mun_completo")["nom_mun_o"]
            .str.title()
        )

        mun = pd.DataFrame({
            "cod_mun_completo": list(tasas_municipio.keys()),
            "tasa": list(tasas_municipio.values()),
        })
        mun["municipio"] = mun["cod_mun_completo"].map(nombres_municipio)
        mun = mun.dropna(subset=["tasa", "municipio"]).sort_values("tasa", ascending=False).head(15)
        mun = mun.sort_values("tasa")

        st.markdown("##### Por municipio (los 15 con la tasa más alta)")
        if mun.empty:
            st.caption("Sin población DANE disponible para el período filtrado.")
        else:
            fig_mun = px.bar(
                mun, x="tasa", y="municipio", text="tasa",
                orientation="h",
                labels={"tasa": "Hospitalizados x100.000 hab.", "municipio": ""},
            )
            fig_mun.update_traces(
                textposition="outside",
                texttemplate="%{text:.1f}",
                marker_color=AZUL_INSTITUCIONAL,
                name="Tasa x100.000 hab.",
                showlegend=True,
            )
            fig_mun.update_layout(
                height=520,
                margin=dict(l=0, r=0, t=70, b=0),
                xaxis={"range": rango_con_margen(mun["tasa"].max())},
            )
            mostrar_grafica(fig_mun, "Tasa de hospitalización por municipio (los 15 más altos)", contexto)

    st.caption("Tasa = hospitalizados / población en riesgo x 100.000, en ambos niveles.")


# ---------------------------------------------------------------------------
# Incidencia de dengue por subregion
# ---------------------------------------------------------------------------

def _mostrar_incidencia_subregion(casos: pd.DataFrame) -> None:
    st.subheader(":material/bar_chart: Incidencia de dengue por subregión")

    if "subregion" not in casos.columns:
        st.caption("Sin datos de subregión.")
        return

    anios_en_alcance = sorted(int(a) for a in casos["ano"].dropna().unique())
    mapeo_subregion = obtener_mapeo_subregion()
    tasas = calcular_tasa_por_subregion(casos, anios_en_alcance, mapeo_subregion)

    df = pd.DataFrame({"subregion": list(tasas.keys()), "incidencia": list(tasas.values())})
    subregiones = _subregiones_en_alcance(casos)
    if len(subregiones) < MINIMO_CATEGORIAS_DISTRIBUCION:
        _avisar_una_sola_subregion(subregiones)
        return
    df = df[df["subregion"].isin(subregiones)]
    df = df.dropna(subset=["incidencia"]).sort_values("incidencia")
    if df.empty:
        st.caption("Sin población DANE disponible para el período filtrado.")
        return

    fig = px.bar(
        df, x="incidencia", y="subregion", text="incidencia",
        orientation="h",
        labels={"incidencia": "Incidencia x100.000 hab.", "subregion": ""},
    )
    fig.update_traces(
        textposition="outside",
        texttemplate="%{text:.1f}",
        marker_color=AZUL_INSTITUCIONAL,
        name="Incidencia x100.000 hab.",
        showlegend=True,
    )
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["incidencia"].max())},
    )
    mostrar_grafica(fig, "Incidencia de dengue por subregión", resumen_filtros_activos())
    st.caption("Incidencia = casos / población en riesgo x 100.000, por subregión.")


# ---------------------------------------------------------------------------
# Casos por fuente de notificacion
# ---------------------------------------------------------------------------

def _mostrar_fuente(casos: pd.DataFrame) -> None:
    """Barras horizontales para comparar todas las fuentes a la vez: la dona
    dificulta comparar magnitudes cuando hay grandes diferencias (ej. Rutinaria
    frente a la busqueda activa)."""
    st.subheader(":material/notification_important: Casos por fuente de notificación")

    if "fuente" not in casos.columns:
        st.caption("Sin datos de fuente.")
        return

    conteo = casos["fuente"].dropna().astype(int).map(_FUENTE_MAP).value_counts()
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales todos los casos llegaron por "
            f"{describir_cantidad(len(conteo), 'fuente de notificación', 'fuentes de notificación')}. "
            "Amplía el período o el territorio para comparar entre fuentes."
        )
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "fuente": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })

    fig = px.bar(
        df,
        x="casos",
        y="fuente",
        text="etiqueta",
        orientation="h",
        labels={"casos": "Casos", "fuente": ""},
    )
    fig.update_traces(textposition="outside", marker_color=AZUL_INSTITUCIONAL, name="Casos", showlegend=True)
    fig.update_layout(
        height=420,
        margin=dict(l=0, r=60, t=70, b=0),
        xaxis={"range": rango_con_margen(df["casos"].max())},
        yaxis={"categoryorder": "total ascending"},
    )
    mostrar_grafica(fig, "Casos por fuente de notificación", resumen_filtros_activos())
