"""Pestana 5 Mortalidad: muertes por dengue (cod_eve 580).

Historia: cuantas muertes, cuando, quien, donde, y si la letalidad supera la meta.
Diseno sobrio: sin alarmar visualmente pero sin suavizar la realidad.

El unico lugar del dashboard donde se usa color de estado (alerta/epidemia) en
un KPI es aqui: la letalidad se colorea cuando supera la meta nacional de 0.10 %,
segun la regla de DESIGN.md de "umbral epidemiologico definido".

Orden de arriba abajo (regla 1.4 de DESIGN.md):
  1. KPIs
  2. Par: Muertes por semana epidemiologica | Muertes por regimen de afiliacion,
     con filtro cruzado en ambos sentidos (regla 1.5): seleccionar semanas
     filtra el regimen y seleccionar un regimen filtra la serie semanal.
  3. Indicadores de mortalidad por subregion
  4. Muertes por sexo y edad
  5. Indicadores de mortalidad por territorio (tabla drill-down)
  6. Muertes por EPS de afiliacion
  7. Diagnostico que ocasiono la muerte relacionado con el evento

Muertes por semana suma, por numero de semana epidemiologica (1 a 53), todas las
muertes del periodo del filtro global: con 1 a 9 muertes por anio, un solo anio
deja casi siempre una o dos barras.

Tasa de mortalidad (muertes / poblacion en riesgo x 100.000) solo se ofrece por
subregion, nunca en la tabla drill-down, que se queda en letalidad (580/casos,
no depende de poblacion) para poder mostrar tambien el nivel municipio sin
romper la regla de tasas de CLAUDE.md.
"""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    MINIMO_CATEGORIAS_DISTRIBUCION,
    MINIMO_PUNTOS_SERIE,
    ANCHO_MEDIA_COLUMNA,
    NARANJA_INSTITUCIONAL,
    OPACIDAD_ATENUADA,
    agregar_linea_referencia,
    avisar_datos_insuficientes,
    describir_cantidad,
    eje_semanal,
    hay_datos_suficientes,
    mostrar_grafica,
    rango_con_margen,
)
from core.dashboard_base.filtros import CLAVE_FILTROS, resumen_filtros_activos
from core.dashboard_base.seleccion_cruzada import (
    clave_grafica,
    fijar_seleccion,
    leer_puntos,
    mostrar_aviso_seleccion,
    obtener_seleccion,
    sincronizar_con_filtros,
)
from pathologies.dengue.geografia import obtener_mapeo_subregion
from pathologies.dengue.indicators import calcular_indicadores
from pathologies.dengue.poblacion import calcular_tasa_por_subregion, obtener_poblacion_en_riesgo_departamental

COD_MUERTE = 580
CODIGOS_CASOS = {210, 220}
META_LETALIDAD = 0.10  # meta nacional INS/MSPS

_BINS_EDAD = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 200]
_LABS_EDAD = ["0-4", "5-9", "10-14", "15-19", "20-24", "25-29", "30-34",
              "35-39", "40-44", "45-49", "50-54", "55-59", "60-64", "65+"]

_TIP_SS_MAP = {
    "s": "Subsidiado", "c": "Contributivo", "n": "No asegurado",
    "p": "Excepción", "i": "Indígena", "e": "Especial",
}

_LAYOUT = dict(margin=dict(l=0, r=0, t=70, b=0))

_TOP_N = 10

# Par muertes por semana <-> muertes por regimen.
_PAR_SEMANA_REGIMEN = "mortalidad_semana_regimen"


def _pct(n: float, total: float, dec: int = 2) -> float:
    return round(n / total * 100, dec) if total else 0.0


# ---------------------------------------------------------------------------
# Orquestador
# ---------------------------------------------------------------------------

def mostrar_mortalidad(datos: pd.DataFrame) -> None:
    muertes = datos[datos["cod_eve"] == COD_MUERTE]
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]
    graves = datos[datos["cod_eve"] == 220]

    if muertes.empty:
        st.info(
            "No hay muertes por dengue registradas para los filtros actuales.",
            icon=":material/info:",
        )
        return

    # Tasa de mortalidad (poblacional) vive aca ademas de en Situacion: aca sigue
    # el filtro global (se puede ver por rangos). Sale de calcular_indicadores,
    # asi respeta la regla de "no disponible".
    filtros_actuales = st.session_state.get(CLAVE_FILTROS, {})
    resultado_indicadores = calcular_indicadores(datos, filtros_actuales)

    _mostrar_kpis(muertes, casos, graves, resultado_indicadores["mortalidad"])

    st.space("small")

    # --- Par: muertes por semana <-> muertes por regimen ---
    muertes_con_semana = _preparar_muertes(muertes)
    sincronizar_con_filtros(_PAR_SEMANA_REGIMEN)
    _procesar_clics_semana_regimen()
    seleccion = obtener_seleccion(_PAR_SEMANA_REGIMEN)
    descripcion = seleccion["descripcion"] if seleccion else None
    mostrar_aviso_seleccion(_PAR_SEMANA_REGIMEN, descripcion)

    origen = seleccion["origen"] if seleccion else None
    valores = seleccion["valores"] if seleccion else []

    muertes_para_semana = muertes_con_semana
    muertes_para_regimen = muertes_con_semana
    if origen == "regimen":
        muertes_para_semana = muertes_con_semana[muertes_con_semana["regimen"].isin(valores)]
    if origen == "semana":
        muertes_para_regimen = muertes_con_semana[muertes_con_semana["semana_int"].isin(valores)]

    col_temporal, col_regimen = st.columns([3, 2])
    with col_temporal:
        with st.container(border=True, height="stretch"):
            _mostrar_temporal(
                muertes_para_semana,
                filtro_cruzado=descripcion if origen == "regimen" else None,
                semanas_resaltadas=valores if origen == "semana" else None,
            )
    with col_regimen:
        with st.container(border=True, height="stretch"):
            _mostrar_regimen(
                muertes_para_regimen,
                filtro_cruzado=descripcion if origen == "semana" else None,
                regimenes_resaltados=valores if origen == "regimen" else None,
            )

    st.space("small")
    with st.container(border=True):
        _mostrar_tasas_subregion(muertes, casos, graves)

    st.space("small")
    with st.container(border=True):
        _mostrar_edad_sexo(muertes)

    st.space("small")
    with st.container(border=True):
        _mostrar_tabla_territorial(muertes, casos, graves)

    st.space("small")
    with st.container(border=True):
        _mostrar_eps(muertes)

    st.space("small")
    with st.container(border=True):
        _mostrar_cie10(muertes)


def _preparar_muertes(muertes: pd.DataFrame) -> pd.DataFrame:
    """Columnas auxiliares del par: semana epidemiologica entera y regimen legible."""
    df = muertes.dropna(subset=["semana"]).copy()
    df["semana_int"] = df["semana"].astype(int)
    if "tip_ss" in df.columns:
        df["regimen"] = df["tip_ss"].map(_TIP_SS_MAP)
    else:
        df["regimen"] = None
    return df


def _opacidades(categorias: list, resaltadas: list | None) -> list[float] | float:
    """Barra elegida a color pleno y las demas atenuadas, para que se vea cual
    es la seleccion activa del par. Sin seleccion, todas a color pleno."""
    if not resaltadas:
        return 1.0
    conjunto = set(resaltadas)
    return [1.0 if categoria in conjunto else OPACIDAD_ATENUADA for categoria in categorias]


def _procesar_clics_semana_regimen() -> None:
    """Lee el clic de la interaccion anterior en cualquiera de las dos graficas
    del par y lo guarda como seleccion (ver seleccion_cruzada.py)."""
    puntos_semana = leer_puntos(_PAR_SEMANA_REGIMEN, "semana")
    puntos_regimen = leer_puntos(_PAR_SEMANA_REGIMEN, "regimen")

    if puntos_semana:
        semanas = sorted({int(punto["x"]) for punto in puntos_semana if punto.get("x") is not None})
        if semanas:
            if len(semanas) == 1:
                descripcion = f"muertes de la semana epidemiológica {semanas[0]}"
            else:
                descripcion = "muertes de las semanas epidemiológicas " + ", ".join(str(s) for s in semanas)
            fijar_seleccion(_PAR_SEMANA_REGIMEN, "semana", semanas, descripcion)
        return

    if puntos_regimen:
        regimenes = [str(punto.get("y")) for punto in puntos_regimen if punto.get("y") is not None]
        if regimenes:
            descripcion = "régimen " + ", ".join(regimenes)
            fijar_seleccion(_PAR_SEMANA_REGIMEN, "regimen", regimenes, descripcion)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(
    muertes: pd.DataFrame, casos: pd.DataFrame, graves: pd.DataFrame, mortalidad: float | None
) -> None:
    n_total = len(muertes)
    n_casos = len(casos)
    n_graves = len(graves)

    letalidad = _pct(n_total, n_casos, 4)
    letalidad_grave = _pct(n_total, n_graves, 2)
    mortalidad_txt = f"{mortalidad:,.1f}" if mortalidad is not None else "No disponible"

    # Menores de 15 (grupo de atencion prioritaria en mortalidad por dengue)
    if "edad_anios" in muertes.columns:
        n_men15 = int((muertes["edad_anios"].dropna().astype(float) < 15).sum())
    else:
        n_men15 = 0

    supera_meta = letalidad > META_LETALIDAD

    # Los KPIs cubren todo el periodo filtrado. La letalidad se compara con la
    # meta ANUAL del INS: si el periodo abarca varios anios, es un valor combinado.
    anios = sorted(int(a) for a in casos["ano"].dropna().unique())
    periodo = (str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}") if anios else None
    if periodo is not None:
        st.caption(
            f":material/calendar_today: Indicadores del período filtrado ({periodo}). "
            "La letalidad se compara con la meta anual del INS."
        )

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.metric("Muertes por dengue", f"{n_total:,}", border=True)
    with c2:
        st.metric(
            "Mortalidad",
            mortalidad_txt,
            help=(
                "Muertes (580) / población en riesgo x 100.000. No disponible si falta "
                "población DANE, o el sistema todavía no tiene los 6 años de histórico "
                "que pide el lineamiento MSPS/INS para calcular la estratificación de "
                "riesgo."
            ),
            border=True,
        )
    with c3:
        st.metric(
            "Menores de 15 años",
            f"{n_men15:,}",
            delta=f"{_pct(n_men15, n_total, 1):.1f}%",
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            help="Grupo de atención prioritaria en mortalidad por dengue",
            border=True,
        )
    with c4:
        # delta_color="inverse" cuando supera la meta: senal epidemiologica real,
        # uso legitimo de color de alerta (DESIGN.md).
        ayuda_letalidad = (
            "Muertes (580) / casos de dengue y dengue grave (210+220) x 100. "
            f"La meta nacional INS establece una letalidad < {META_LETALIDAD}%: "
            "cada 1.000 casos de dengue debería haber menos de 1 muerte."
        )
        if periodo is not None:
            comparacion = "supera" if supera_meta else "cumple"
            ayuda_letalidad += (
                f" La letalidad acumulada de {periodo} ({letalidad:.4f}%) {comparacion} esa meta."
            )
        st.metric(
            "Letalidad",
            f"{letalidad:.4f}%",
            delta="Supera la meta INS" if supera_meta else None,
            delta_color="inverse" if supera_meta else "off",
            delta_arrow="off",
            help=ayuda_letalidad,
            border=True,
        )
    with c5:
        st.metric(
            "Letalidad grave",
            f"{letalidad_grave:.2f}%",
            help="Muertes (580) / casos de dengue grave (220) x 100",
            border=True,
        )


# ---------------------------------------------------------------------------
# Muertes por semana epidemiologica (suma del periodo filtrado por semana)
# ---------------------------------------------------------------------------

def _mostrar_temporal(
    muertes: pd.DataFrame, filtro_cruzado: str | None, semanas_resaltadas: list | None
) -> None:
    """Muertes de cada semana epidemiologica (1 a 53), sumadas sobre todos los
    anios del filtro global. Asi se ve en que semanas del anio se concentran las
    muertes, que es la lectura de los boletines; repartir 1 a 9 muertes por anio
    sobre una linea de tiempo de varios anios dejaba barras sueltas ilegibles."""
    st.subheader(":material/calendar_month: Muertes por semana epidemiológica")
    st.caption(":material/touch_app: Haz clic en una barra para ver el régimen de esas muertes.")

    contexto = resumen_filtros_activos()
    if filtro_cruzado:
        contexto = f"{contexto} · solo {filtro_cruzado}"

    semanal = muertes.groupby("semana_int").size().reset_index(name="n")

    # Umbral de serie temporal (4 semanas con muertes): con menos, la grafica no
    # muestra una distribucion temporal sino un par de barras sueltas.
    if not hay_datos_suficientes(semanal, MINIMO_PUNTOS_SERIE):
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(muertes), 'muerte', 'muertes')} en "
            f"{describir_cantidad(len(semanal), 'semana epidemiológica', 'semanas epidemiológicas')}. "
            "Amplía el período para ver la distribución temporal."
        )
        return

    anios = sorted(int(a) for a in muertes["ano"].dropna().unique())
    periodo = str(anios[0]) if len(anios) == 1 else f"{anios[0]}-{anios[-1]}"

    fig = px.bar(
        semanal, x="semana_int", y="n", text="n",
        labels={"semana_int": "Semana epidemiológica", "n": "Muertes"},
    )
    fig.update_traces(
        marker_color=AZUL_INSTITUCIONAL,
        marker_opacity=_opacidades(semanal["semana_int"].tolist(), semanas_resaltadas),
        textposition="outside",
        name="Muertes",
        showlegend=True,
        hovertemplate=f"Semana %{{x}} · %{{y}} muerte(s) en {periodo}<extra></extra>",
    )
    # Siempre el anio epidemiologico completo (semanas 1 a 53), aunque las
    # ultimas semanas no tengan muertes: asi se lee en que parte del anio caen.
    fig.update_xaxes(**eje_semanal(53, dtick=2), range=[0.5, 53.5])
    fig.update_layout(
        **_LAYOUT,
        height=460,
        bargap=0.15,
        yaxis={"range": rango_con_margen(semanal["n"].max()), "dtick": 1 if semanal["n"].max() <= 6 else None},
    )
    mostrar_grafica(
        fig,
        "Muertes por semana epidemiológica",
        contexto,
        ancho=ANCHO_MEDIA_COLUMNA,
        key=clave_grafica(_PAR_SEMANA_REGIMEN, "semana"),
        on_select="rerun",
        selection_mode="points",
    )


# ---------------------------------------------------------------------------
# Muertes por regimen de afiliacion (SGSSS)
# ---------------------------------------------------------------------------

def _mostrar_regimen(
    muertes: pd.DataFrame, filtro_cruzado: str | None, regimenes_resaltados: list | None
) -> None:
    st.subheader(":material/health_and_safety: Muertes por régimen de afiliación (SGSSS)")
    st.caption(":material/touch_app: Haz clic en un régimen para ver sus semanas.")

    contexto = resumen_filtros_activos()
    if filtro_cruzado:
        contexto = f"{contexto} · solo {filtro_cruzado}"

    conteo = muertes["regimen"].dropna().value_counts()
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(muertes), 'muerte', 'muertes')}, en "
            f"{describir_cantidad(len(conteo), 'régimen', 'regímenes', femenino=False)} de afiliación. "
            "Amplía el período o quita la selección para comparar entre regímenes."
        )
        return

    total = conteo.sum()
    df = conteo.reset_index()
    df.columns = ["regimen", "n"]
    df = df.sort_values("n")
    df["etiqueta"] = df.apply(lambda r: f"{r['n']}  ({r['n'] / total * 100:.1f}%)", axis=1)

    fig = px.bar(
        df, x="n", y="regimen", text="etiqueta", orientation="h",
        labels={"n": "Muertes", "regimen": ""},
    )
    fig.update_traces(
        textposition="outside",
        marker_color=AZUL_INSTITUCIONAL,
        marker_opacity=_opacidades(df["regimen"].tolist(), regimenes_resaltados),
        name="Muertes",
        showlegend=True,
    )
    fig.update_layout(
        **_LAYOUT,
        height=460,
        xaxis={"range": rango_con_margen(df["n"].max())},
    )
    mostrar_grafica(
        fig,
        "Muertes por régimen de afiliación (SGSSS)",
        contexto,
        ancho=ANCHO_MEDIA_COLUMNA,
        key=clave_grafica(_PAR_SEMANA_REGIMEN, "regimen"),
        on_select="rerun",
        selection_mode="points",
    )


# ---------------------------------------------------------------------------
# Muertes por sexo y edad
# ---------------------------------------------------------------------------

def _mostrar_edad_sexo(muertes: pd.DataFrame) -> None:
    st.subheader(":material/groups: Muertes por sexo y edad")

    if not {"edad_anios", "sexo"}.issubset(muertes.columns):
        st.caption("Sin datos de edad o sexo.")
        return

    df = muertes[["edad_anios", "sexo"]].dropna()
    df = df[df["sexo"].isin(["m", "f"])].copy()

    df["grupo"] = pd.cut(
        df["edad_anios"].astype(float),
        bins=_BINS_EDAD,
        labels=_LABS_EDAD,
        right=False,
    )
    conteo = df.groupby(["grupo", "sexo"], observed=True).size().reset_index(name="n")
    conteo = conteo[conteo["n"] > 0]
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(df), 'muerte', 'muertes')} con edad y "
            f"sexo registrados, en {describir_cantidad(len(conteo), 'grupo', 'grupos', femenino=False)} de "
            "sexo y edad. Amplía el período o el territorio para ver la distribución."
        )
        return

    conteo["sexo_label"] = conteo["sexo"].map({"m": "Masculino", "f": "Femenino"})
    total = conteo["n"].sum()
    conteo["pct"] = (conteo["n"] / total * 100).round(1)
    conteo["etiqueta"] = conteo.apply(
        lambda r: f"{r['n']}  ({r['pct']:.1f}%)" if r["n"] > 0 else "", axis=1
    )

    fig = px.bar(
        conteo,
        x="n",
        y="grupo",
        color="sexo_label",
        barmode="group",
        text="etiqueta",
        orientation="h",
        labels={"n": "Muertes", "grupo": "Grupo etario", "sexo_label": "Sexo"},
        color_discrete_map={"Masculino": AZUL_INSTITUCIONAL, "Femenino": NARANJA_INSTITUCIONAL},
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        **_LAYOUT,
        height=700,
        bargap=0.25,
        legend_title_text="",
        xaxis={"range": rango_con_margen(conteo["n"].max())},
        yaxis={"categoryorder": "array", "categoryarray": _LABS_EDAD},
    )
    mostrar_grafica(fig, "Muertes por sexo y edad", resumen_filtros_activos())


# ---------------------------------------------------------------------------
# Muertes por EPS de afiliacion
# ---------------------------------------------------------------------------

def _mostrar_eps(muertes: pd.DataFrame) -> None:
    st.subheader(":material/local_hospital: Muertes por EPS de afiliación")
    st.caption(f"Las {_TOP_N} EPS con más muertes de sus afiliados en el período filtrado.")

    if "nom_ase" not in muertes.columns:
        st.caption("Sin datos.")
        return

    conteo = muertes["nom_ase"].dropna().value_counts().head(_TOP_N)
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales las muertes con EPS registrada están en "
            f"{describir_cantidad(len(conteo), 'EPS', 'EPS')}. Amplía el período o el territorio "
            "para comparar entre EPS."
        )
        return

    df = conteo.reset_index()
    df.columns = ["eps", "n"]
    df["eps_short"] = df["eps"].apply(lambda s: s[:60] + "…" if len(s) > 60 else s)

    fig = px.bar(
        df, x="n", y="eps_short", text="n", orientation="h",
        labels={"n": "Muertes", "eps_short": ""},
        hover_data={"eps": True, "eps_short": False, "n": True},
    )
    fig.update_traces(textposition="outside", marker_color=AZUL_INSTITUCIONAL, name="Muertes", showlegend=True)
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["n"].max())},
        yaxis={"categoryorder": "total ascending"},
    )
    mostrar_grafica(fig, "Muertes por EPS de afiliación", resumen_filtros_activos())


# ---------------------------------------------------------------------------
# Indicadores de mortalidad por territorio (tabla drill-down)
# ---------------------------------------------------------------------------

def _mostrar_tabla_territorial(
    muertes: pd.DataFrame, casos: pd.DataFrame, graves: pd.DataFrame
) -> None:
    st.subheader(":material/table_chart: Indicadores de mortalidad por territorio")
    # La tabla no es una figura de Plotly: el contexto va en texto, debajo del titulo.
    st.caption(resumen_filtros_activos())
    st.caption(
        "Letalidad = muertes / casos de dengue y dengue grave (210+220). "
        "Letalidad grave = muertes / casos de dengue grave (220)."
    )

    # Selector de representacion: elige el nivel de agregacion de la tabla.
    nivel = st.segmented_control(
        "Nivel de agregación",
        ["Magdalena", "Subregión", "Municipio"],
        default="Subregión",
        required=True,
        key="mort_nivel_tabla",
    )

    def _calcular(key: str, m_df: pd.DataFrame, c_df: pd.DataFrame, g_df: pd.DataFrame) -> pd.DataFrame:
        if key == "Magdalena":
            return pd.DataFrame([{
                "Territorio": "Magdalena",
                "Muertes": len(m_df),
                "Casos (210+220)": len(c_df),
                "Casos graves (220)": len(g_df),
                "Letalidad (%)": round(_pct(len(m_df), len(c_df), 4), 4),
                "Letalidad grave (%)": round(_pct(len(m_df), len(g_df), 2), 2),
            }])

        col = "subregion" if key == "Subregión" else "nom_mun_o"
        if col not in m_df.columns:
            return pd.DataFrame()

        filas = []
        for territorio in sorted(m_df[col].dropna().unique()):
            n_m = int((m_df[col] == territorio).sum())
            n_c = int((c_df[col] == territorio).sum()) if col in c_df.columns else 0
            n_g = int((g_df[col] == territorio).sum()) if col in g_df.columns else 0
            nombre = str(territorio).title() if col == "nom_mun_o" else territorio
            filas.append({
                "Territorio": nombre,
                "Muertes": n_m,
                "Casos (210+220)": n_c,
                "Casos graves (220)": n_g,
                "Letalidad (%)": round(_pct(n_m, n_c, 4), 4),
                "Letalidad grave (%)": round(_pct(n_m, n_g, 2), 2),
            })

        if not filas:
            return pd.DataFrame()

        df = pd.DataFrame(filas).sort_values("Muertes", ascending=False)
        total_row = pd.DataFrame([{
            "Territorio": "TOTAL",
            "Muertes": len(m_df),
            "Casos (210+220)": len(c_df),
            "Casos graves (220)": len(g_df),
            "Letalidad (%)": round(_pct(len(m_df), len(c_df), 4), 4),
            "Letalidad grave (%)": round(_pct(len(m_df), len(g_df), 2), 2),
        }])
        return pd.concat([df, total_row], ignore_index=True)

    tabla = _calcular(nivel, muertes, casos, graves)
    if tabla.empty:
        st.caption(f"Sin datos de {nivel.lower()} disponibles.")
        return

    st.dataframe(tabla, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Indicadores de mortalidad por subregion (con selector de indicador)
# ---------------------------------------------------------------------------

def _subregiones_en_alcance(casos: pd.DataFrame, muertes: pd.DataFrame) -> list[str]:
    """Subregiones que el filtro global deja dentro del alcance. Sin filtro
    territorial, las 5; con filtro, solo las elegidas (si no, las demas
    aparecerian en cero aunque esten fuera del filtro, no porque no tengan
    muertes)."""
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    if filtros.get("subregion") or filtros.get("nom_mun_o"):
        presentes = set(muertes["subregion"].dropna()) | set(casos["subregion"].dropna())
        return sorted(presentes)
    return sorted(set(obtener_mapeo_subregion().values()))


def _mostrar_tasas_subregion(
    muertes: pd.DataFrame, casos: pd.DataFrame, graves: pd.DataFrame
) -> None:
    st.subheader(":material/bar_chart: Indicadores de mortalidad por subregión")

    col_sub = "subregion"
    if col_sub not in muertes.columns or col_sub not in casos.columns:
        st.caption("Sin datos de subregión (se deriva del mapeo DIVIPOLA en los filtros).")
        return

    subregiones = _subregiones_en_alcance(casos, muertes)
    if len(subregiones) < MINIMO_CATEGORIAS_DISTRIBUCION:
        avisar_datos_insuficientes(
            f"Con el filtro territorial actual hay {describir_cantidad(len(subregiones), 'subregión', 'subregiones')} "
            "en el alcance. Para comparar entre subregiones, quita o amplía el filtro de subregión o "
            "municipio en la barra lateral."
        )
        return

    # Selector de representacion: elige el indicador que se dibuja.
    indicador = st.segmented_control(
        "Indicador",
        ["Muertes (conteo)", "Letalidad (%)", "Letalidad grave (%)", "Tasa de mortalidad (x100.000)"],
        default="Letalidad (%)",
        required=True,
        key="mort_indicador_sub",
    )

    filas = []
    for sub in subregiones:
        n_m = int((muertes[col_sub] == sub).sum())
        n_c = int((casos[col_sub] == sub).sum())
        n_g = int((graves[col_sub] == sub).sum()) if col_sub in graves.columns else 0
        filas.append({"subregion": sub, "muertes": n_m, "casos": n_c, "graves": n_g})

    df = pd.DataFrame(filas)

    ref_m = len(muertes)
    ref_c = len(casos)
    ref_g = len(graves)

    if indicador == "Muertes (conteo)":
        df["valor"] = df["muertes"]
        # Sin linea de referencia: el total del Magdalena es la SUMA de las
        # subregiones, no un valor comparable con cada barra (la linea quedaba
        # lejos de todas las barras). En los indicadores que son razones o tasas
        # el valor del Magdalena si es una referencia comparable.
        ref_val = None
        etiqueta_eje = "Muertes"
        formato = ",.0f"
    elif indicador == "Letalidad (%)":
        df["valor"] = df.apply(lambda r: _pct(r["muertes"], r["casos"], 4), axis=1)
        ref_val = _pct(ref_m, ref_c, 4)
        etiqueta_eje = "Letalidad (%)"
        formato = ".4f"
    elif indicador == "Letalidad grave (%)":
        df["valor"] = df.apply(lambda r: _pct(r["muertes"], r["graves"], 2), axis=1)
        ref_val = _pct(ref_m, ref_g, 2)
        etiqueta_eje = "Letalidad grave (%)"
        formato = ".2f"
    else:
        # Tasa de mortalidad: unico indicador de esta grafica con denominador
        # poblacional. Subregion sin poblacion DANE queda fuera (None, nunca cero).
        anios_en_alcance = sorted(int(a) for a in casos["ano"].dropna().unique())
        mapeo_subregion = obtener_mapeo_subregion()
        tasas = calcular_tasa_por_subregion(muertes, anios_en_alcance, mapeo_subregion)
        df["valor"] = df["subregion"].map(tasas)
        poblacion_departamental = obtener_poblacion_en_riesgo_departamental(anios_en_alcance)
        ref_val = (ref_m / poblacion_departamental * 100_000) if poblacion_departamental else None
        etiqueta_eje = "Tasa de mortalidad (x100.000 hab.)"
        formato = ".2f"

    df = df.dropna(subset=["valor"]).sort_values("valor")
    if df.empty:
        st.caption("Sin población DANE disponible para el período filtrado.")
        return
    df["etiqueta"] = df["valor"].apply(lambda v: f"{v:{formato}}")

    fig = px.bar(
        df,
        x="valor",
        y="subregion",
        text="etiqueta",
        orientation="h",
        labels={"valor": etiqueta_eje, "subregion": ""},
    )
    fig.update_traces(textposition="outside", marker_color=AZUL_INSTITUCIONAL, name=etiqueta_eje, showlegend=True)
    if ref_val is not None:
        agregar_linea_referencia(fig, ref_val, f"Magdalena: {ref_val:{formato}}", eje="x")
    if indicador == "Muertes (conteo)":
        suma_subregiones = int(df["valor"].sum())
        sin_subregion = ref_m - suma_subregiones
        texto_total = f"Total del Magdalena: {ref_m:,} muertes."
        if sin_subregion > 0:
            texto_total += (
                f" {describir_cantidad(sin_subregion, 'muerte no tiene', 'muertes no tienen')} subregión "
                "identificable (municipio de ocurrencia no válido en DIVIPOLA), por eso las barras suman "
                f"{suma_subregiones:,}."
            )
        st.caption(texto_total)
    valor_max = max(df["valor"].max(), ref_val or 0)
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(valor_max)},
    )
    mostrar_grafica(fig, "Indicadores de mortalidad por subregión", resumen_filtros_activos())

    if indicador == "Letalidad (%)" and ref_val > META_LETALIDAD:
        anios_periodo = sorted(int(a) for a in casos["ano"].dropna().unique())
        periodo = (
            str(anios_periodo[0]) if len(anios_periodo) == 1
            else f"{anios_periodo[0]}-{anios_periodo[-1]}"
        ) if anios_periodo else "el período filtrado"
        st.caption(
            f":material/warning: La letalidad departamental acumulada de {periodo} "
            f"({ref_val:.4f}%) supera la meta nacional INS de {META_LETALIDAD}%."
        )


# ---------------------------------------------------------------------------
# Diagnostico que ocasiono la muerte relacionado con el evento
# ---------------------------------------------------------------------------

def _mostrar_cie10(muertes: pd.DataFrame) -> None:
    st.subheader(
        ":material/medical_information: Diagnóstico que ocasionó la muerte relacionado con el evento"
    )

    col_cod = "cbmte"
    col_nom = "nom_cbmte"

    if col_nom not in muertes.columns and col_cod not in muertes.columns:
        st.caption("Sin datos de causas CIE-10.")
        return

    if col_nom in muertes.columns:
        conteo = muertes[col_nom].dropna().value_counts().head(_TOP_N)
    else:
        conteo = muertes[col_cod].dropna().value_counts().head(_TOP_N)

    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales las muertes con diagnóstico CIE-10 registrado tienen "
            f"{describir_cantidad(len(conteo), 'diagnóstico', 'diagnósticos', femenino=False)}. "
            "Amplía el período o el territorio para comparar entre diagnósticos."
        )
        return

    total = conteo.sum()
    df = conteo.reset_index()
    df.columns = ["causa", "n"]
    df["causa"] = df["causa"].astype(str).str.capitalize()
    df["etiqueta"] = df["n"].apply(lambda v: f"{v:,}  ({v / total * 100:.1f}%)")

    # A ancho completo los nombres CIE-10 caben como etiquetas del eje: se leen
    # directo junto a su barra, sin ir a buscar el color en una leyenda.
    fig = px.bar(
        df,
        x="n",
        y="causa",
        text="etiqueta",
        orientation="h",
        labels={"n": "Muertes", "causa": ""},
    )
    fig.update_traces(textposition="outside", marker_color=AZUL_INSTITUCIONAL, name="Muertes", showlegend=True)
    fig.update_layout(
        margin=dict(l=0, r=0, t=70, b=0),
        height=max(360, 46 * len(df) + 120),
        xaxis={"range": rango_con_margen(df["n"].max())},
        yaxis={"categoryorder": "total ascending", "automargin": True},
    )
    mostrar_grafica(fig, "Diagnóstico que ocasionó la muerte relacionado con el evento", resumen_filtros_activos())
