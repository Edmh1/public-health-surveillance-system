"""Pestana 3 Sociodemografica: perfil de la poblacion afectada por dengue.

Historia que cuenta:
  1. KPIs de vulnerabilidad (total, gestantes, menores de 5, mayores de 65)
  2. Par complementario: Piramide de casos por sexo y edad + Distribucion
     demografica de casos (selector de representacion: Area / Estrato / Etnia /
     Regimen). Filtro cruzado en ambos sentidos (regla 1.5 de DESIGN.md): una
     barra de la piramide (grupo de edad y sexo) filtra la distribucion, y una
     categoria de la distribucion filtra la piramide. Lo elegido queda a color
     pleno y lo demas atenuado.
  3. Pueblos indigenas (condicional)
  4. Casos por EPS de afiliacion y Casos notificados por UPGD, una debajo de la
     otra (no son un par complementario).

Agrupacion de edad de la piramide: grupos quinquenales, los de los boletines del
INS. PENDIENTE: verificar el estandar al que se refirio la codirectora ("32-80",
probablemente la Resolucion 3280 de 2018 del Ministerio de Salud, momentos del
curso de vida). Si se adopta hay que fijar un corte y declararlo, porque esos
momentos se solapan (adolescencia 12 a 18 y juventud 14 a 26).
"""

import math

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    MINIMO_CATEGORIAS_DISTRIBUCION,
    ANCHO_MEDIA_COLUMNA,
    NARANJA_INSTITUCIONAL,
    OPACIDAD_ATENUADA,
    avisar_datos_insuficientes,
    describir_cantidad,
    hay_datos_suficientes,
    mostrar_grafica,
    rango_con_margen,
)
from core.dashboard_base.filtros import resumen_filtros_activos
from core.dashboard_base.seleccion_cruzada import (
    clave_grafica,
    fijar_seleccion,
    leer_puntos,
    mostrar_aviso_seleccion,
    obtener_seleccion,
    sincronizar_con_filtros,
)

CODIGOS_CASOS = {210, 220}
_TOP_N = 10

_BINS_EDAD   = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 200]
_LABELS_EDAD = ["0-4","5-9","10-14","15-19","20-24","25-29","30-34",
                "35-39","40-44","45-49","50-54","55-59","60-64","65+"]

_AREA_MAP_FULL = {1: "Cabecera municipal", 2: "Centro poblado", 3: "Rural disperso"}

_TIP_SS_MAP = {
    "s": "Subsidiado",
    "c": "Contributivo",
    "n": "No asegurado",
    "p": "Excepción",
    "i": "Indígena",
    "e": "Especial",
}

_ETN_MAP = {
    1: "Indígena",
    2: "ROM",
    3: "Raizal",
    4: "Palenquero",
    5: "Afrocolombiano",
    6: "Ninguno / sin dato",
}

_SIN_INFO = {"sin informacion", "sin información", "sin info", "", "nan", "none"}

_LAYOUT = dict(margin=dict(l=0, r=0, t=70, b=0))

# Par piramide -> distribucion demografica.
_PAR_PIRAMIDE = "sociodem_piramide_distribucion"
# Orden de las trazas de la piramide: la seleccion de Plotly trae el numero de
# traza (curve_number), que dice de que sexo es la barra.
# Trazas 0 y 1: el espacio vacio de cada fila, a la izquierda y a la derecha de
# las barras (clic ahi = el grupo de edad completo, ambos sexos). Trazas 2 y 3:
# las barras de cada sexo. Las zonas de "ambos" no se superponen con las barras,
# asi un clic nunca queda en duda entre un sexo y el grupo completo.
_AMBOS_SEXOS = "ambos"
_SEXO_POR_TRAZA = {0: _AMBOS_SEXOS, 1: _AMBOS_SEXOS, 2: "m", 3: "f"}
_NOMBRE_SEXO = {"m": "Masculino", "f": "Femenino", _AMBOS_SEXOS: "Ambos sexos"}


# ---------------------------------------------------------------------------
# Helper: porcentaje con decimales inteligentes
# ---------------------------------------------------------------------------

def _pct(n: float, total: float) -> str:
    """Devuelve porcentaje con la precision justa para que nunca salga '0%'
    cuando hay casos reales."""
    if total == 0:
        return "—"
    p = n / total * 100
    if p >= 10:
        return f"{p:.1f}%"
    elif p >= 1:
        return f"{p:.1f}%"
    elif p >= 0.1:
        return f"{p:.2f}%"
    elif p > 0:
        return f"{p:.3f}%"
    return "0%"


# ---------------------------------------------------------------------------
# Orquestador principal
# ---------------------------------------------------------------------------

def mostrar_sociodemografica(datos: pd.DataFrame) -> None:
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]

    if casos.empty:
        st.info("No hay casos de dengue para los filtros actuales.", icon=":material/info:")
        return

    # 1. KPIs de vulnerabilidad
    _mostrar_kpis(casos)

    st.space("small")

    # 2. Par: piramide + distribucion demografica, con filtro cruzado en ambos
    # sentidos: una barra de la piramide filtra la distribucion, y una categoria
    # de la distribucion filtra la piramide.
    sincronizar_con_filtros(_PAR_PIRAMIDE)
    _procesar_clics_del_par()
    seleccion = obtener_seleccion(_PAR_PIRAMIDE)
    descripcion = seleccion["descripcion"] if seleccion else None
    origen = seleccion["origen"] if seleccion else None
    mostrar_aviso_seleccion(_PAR_PIRAMIDE, descripcion)

    casos_piramide = casos
    casos_distribucion = casos
    if origen == "piramide":
        casos_distribucion = _filtrar_por_grupos_de_piramide(casos, seleccion["valores"])
    if origen == "distribucion":
        variable, categorias = seleccion["valores"]
        etiquetas = _etiquetar_variable(casos, variable)
        casos_piramide = casos[etiquetas.isin(categorias)]

    col_pir, col_exp = st.columns([1.15, 1])
    with col_pir:
        with st.container(border=True, height="stretch"):
            _mostrar_piramide(
                casos_piramide,
                filtro_cruzado=descripcion if origen == "distribucion" else None,
                resaltados=seleccion["valores"] if origen == "piramide" else None,
            )
    with col_exp:
        with st.container(border=True, height="stretch"):
            _explorador_demografico(
                casos_distribucion,
                filtro_cruzado=descripcion if origen == "piramide" else None,
                seleccion_propia=seleccion["valores"] if origen == "distribucion" else None,
            )


    # 3. Pueblos indigenas (condicional)
    tiene_indigenas = (
        "per_etn" in casos.columns and (casos["per_etn"] == 1).any()
    )
    if tiene_indigenas:
        st.space("small")
        with st.container(border=True):
            _mostrar_pueblos_indigenas(casos)

    st.space("small")

    # 4. Actores del sistema: EPS y UPGD, una debajo de la otra
    with st.container(border=True):
        _mostrar_eps(casos)

    st.space("small")

    with st.container(border=True):
        _mostrar_upgd(casos)


def _agregar_grupo_edad(casos: pd.DataFrame) -> pd.DataFrame:
    df = casos.copy()
    df["grupo_edad"] = pd.cut(
        df["edad_anios"].astype(float),
        bins=_BINS_EDAD,
        labels=_LABELS_EDAD,
        right=False,
    ).astype(str)
    return df


def _procesar_clics_del_par() -> None:
    """Lee el clic de la interaccion anterior en la piramide o en la distribucion
    y lo guarda como seleccion del par (ver seleccion_cruzada.py)."""
    puntos_piramide = leer_puntos(_PAR_PIRAMIDE, "piramide")
    puntos_distribucion = leer_puntos(_PAR_PIRAMIDE, "distribucion")

    if puntos_piramide:
        pares = []
        for punto in puntos_piramide:
            sexo = _SEXO_POR_TRAZA.get(punto.get("curve_number"))
            grupo = punto.get("y")
            if sexo is None or grupo is None:
                continue
            pares.append([str(grupo), sexo])
        if pares:
            partes = [f"{_NOMBRE_SEXO[sexo]} de {grupo} años" for grupo, sexo in pares]
            fijar_seleccion(_PAR_PIRAMIDE, "piramide", pares, ", ".join(partes))
        return

    if puntos_distribucion:
        # La variable es la que estaba dibujada cuando se hizo el clic.
        variable = st.session_state.get("sociodem_explorador", "Area")
        categorias = [str(punto.get("y")) for punto in puntos_distribucion if punto.get("y") is not None]
        if categorias:
            descripcion = f"{_NOMBRE_VARIABLE[variable]}: " + ", ".join(categorias)
            fijar_seleccion(_PAR_PIRAMIDE, "distribucion", [variable, categorias], descripcion)


def _filtrar_por_grupos_de_piramide(casos: pd.DataFrame, pares: list) -> pd.DataFrame:
    if not {"edad_anios", "sexo"}.issubset(casos.columns):
        return casos
    con_grupo = _agregar_grupo_edad(casos.dropna(subset=["edad_anios"]))
    claves_elegidas = {(grupo, sexo) for grupo, sexo in pares}
    coincide = [
        (grupo, sexo) in claves_elegidas or (grupo, _AMBOS_SEXOS) in claves_elegidas
        for grupo, sexo in zip(con_grupo["grupo_edad"], con_grupo["sexo"])
    ]
    return con_grupo[coincide]


def _etiquetar_variable(casos: pd.DataFrame, variable: str) -> pd.Series:
    """Categoria legible de cada caso para una variable de la distribucion
    (misma etiqueta que se dibuja en el eje). Nulo si el caso no tiene el dato."""
    columna = _COLUMNA_VARIABLE[variable]
    if columna not in casos.columns:
        return pd.Series([None] * len(casos), index=casos.index, dtype=object)
    valores = casos[columna]
    if variable == "Area":
        return valores.map(lambda v: _AREA_MAP_FULL.get(int(v)) if pd.notna(v) else None)
    if variable == "Estrato":
        return valores.map(lambda v: f"Estrato {int(v)}" if pd.notna(v) else None)
    if variable == "Etnia":
        return valores.map(lambda v: _ETN_MAP.get(int(v)) if pd.notna(v) else None)
    return valores.map(lambda v: _TIP_SS_MAP.get(v) if pd.notna(v) else None)


def _opacidades(categorias: list, resaltadas: list | None) -> list[float] | float:
    """Lo seleccionado a color pleno y lo demas atenuado (regla 1.5)."""
    if not resaltadas:
        return 1.0
    conjunto = set(resaltadas)
    return [1.0 if categoria in conjunto else OPACIDAD_ATENUADA for categoria in categorias]


def _paso_redondo(valor_maximo: float) -> int:
    """Paso de marcas del eje 'redondo' (1, 2 o 5 por potencia de 10), para que
    la piramide no muestre marcas como 980 o 2940."""
    paso_crudo = max(valor_maximo / 3, 1)
    potencia = 10 ** int(math.floor(math.log10(paso_crudo)))
    for multiplo in (1, 2, 5, 10):
        paso = multiplo * potencia
        if paso >= paso_crudo:
            return int(paso)
    return int(10 * potencia)


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------

def _mostrar_kpis(casos: pd.DataFrame) -> None:
    total = len(casos)

    if "gp_gestan" in casos.columns:
        n_gest = int((casos["gp_gestan"] == 1).sum())
    else:
        n_gest = 0

    if "edad_anios" in casos.columns:
        edad = casos["edad_anios"].dropna().astype(float)
        n_men5  = int((edad < 5).sum())
        n_may65 = int((edad >= 65).sum())
    else:
        n_men5 = n_may65 = 0

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Casos totales", f"{total:,}", border=True)
    with c2:
        st.metric(
            "Gestantes",
            f"{n_gest:,}",
            delta=_pct(n_gest, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )
    with c3:
        st.metric(
            "Menores de 5 años",
            f"{n_men5:,}",
            delta=_pct(n_men5, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )
    with c4:
        st.metric(
            "Mayores de 65 años",
            f"{n_may65:,}",
            delta=_pct(n_may65, total),
            delta_color="off",
            delta_arrow="off",
            delta_description="del total",
            border=True,
        )


# ---------------------------------------------------------------------------
# Piramide de casos por sexo y edad
# ---------------------------------------------------------------------------

def _mostrar_piramide(casos: pd.DataFrame, filtro_cruzado: str | None, resaltados: list | None) -> None:
    st.subheader(":material/groups: Pirámide de casos por sexo y edad")
    st.caption(
        ":material/touch_app: Haz clic en una barra para ver ese sexo y grupo de edad, o en el "
        "espacio vacío de la fila para ver el grupo de edad completo (ambos sexos)."
    )

    if not {"edad_anios", "sexo"}.issubset(casos.columns):
        st.caption("Sin datos de edad o sexo.")
        return

    df = casos[["edad_anios", "sexo"]].dropna()
    df = df[df["sexo"].isin(["m", "f"])].copy()
    df = _agregar_grupo_edad(df).rename(columns={"grupo_edad": "grupo"})
    grupos_con_casos = df["grupo"].nunique()
    if not hay_datos_suficientes(df.drop_duplicates(subset=["grupo"]), MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(df), 'caso', 'casos', femenino=False)} con "
            f"edad y sexo registrados, en {describir_cantidad(grupos_con_casos, 'grupo de edad', 'grupos de edad', femenino=False)}. "
            "Amplía el período, el territorio o quita la selección para ver la pirámide."
        )
        return

    conteo = df.groupby(["grupo", "sexo"]).size().reset_index(name="n")
    hombres = conteo[conteo["sexo"] == "m"].set_index("grupo")["n"].reindex(_LABELS_EDAD, fill_value=0)
    mujeres = conteo[conteo["sexo"] == "f"].set_index("grupo")["n"].reindex(_LABELS_EDAD, fill_value=0)

    resaltados_hombres = [grupo for grupo, sexo in (resaltados or []) if sexo in ("m", _AMBOS_SEXOS)]
    resaltados_mujeres = [grupo for grupo, sexo in (resaltados or []) if sexo in ("f", _AMBOS_SEXOS)]
    if resaltados and not resaltados_hombres:
        opacidad_hombres = OPACIDAD_ATENUADA
    else:
        opacidad_hombres = _opacidades(_LABELS_EDAD, resaltados_hombres)
    if resaltados and not resaltados_mujeres:
        opacidad_mujeres = OPACIDAD_ATENUADA
    else:
        opacidad_mujeres = _opacidades(_LABELS_EDAD, resaltados_mujeres)

    valor_maximo = max(int(hombres.max()), int(mujeres.max()), 1)
    paso = _paso_redondo(valor_maximo)
    limite = valor_maximo * 1.15
    marcas = [paso * multiplo for multiplo in range(-6, 7) if abs(paso * multiplo) <= limite]

    fig = go.Figure()
    # Zonas invisibles del grupo completo: de la punta de cada barra al borde del
    # grafico, a cada lado. Se agregan primero para que queden detras.
    totales = (hombres + mujeres).values
    plantilla_ambos = "%{y} · ambos sexos: %{customdata:,} casos<extra>Clic: grupo completo</extra>"
    fig.add_trace(go.Bar(
        y=_LABELS_EDAD,
        x=[limite - v for v in hombres.values],
        base=[-limite] * len(_LABELS_EDAD),
        orientation="h",
        marker_color="rgba(0,0,0,0)",
        customdata=totales,
        hovertemplate=plantilla_ambos,
        showlegend=False,
        name="Ambos sexos",
    ))
    fig.add_trace(go.Bar(
        y=_LABELS_EDAD,
        x=[limite - v for v in mujeres.values],
        base=list(mujeres.values),
        orientation="h",
        marker_color="rgba(0,0,0,0)",
        customdata=totales,
        hovertemplate=plantilla_ambos,
        showlegend=False,
        name="Ambos sexos",
    ))
    fig.add_trace(go.Bar(
        y=_LABELS_EDAD,
        x=[-v for v in hombres.values],
        name="Masculino",
        orientation="h",
        marker_color=AZUL_INSTITUCIONAL,
        marker_opacity=opacidad_hombres,
        hovertemplate="%{y}: %{customdata:,} casos<extra>Masculino</extra>",
        customdata=hombres.values,
    ))
    fig.add_trace(go.Bar(
        y=_LABELS_EDAD,
        x=list(mujeres.values),
        name="Femenino",
        orientation="h",
        marker_color=NARANJA_INSTITUCIONAL,
        marker_opacity=opacidad_mujeres,
        hovertemplate="%{y}: %{x:,} casos<extra>Femenino</extra>",
    ))

    fig.update_layout(
        barmode="overlay",
        bargap=0.12,
        xaxis=dict(
            range=[-limite, limite],
            minallowed=-limite,
            maxallowed=limite,
            tickvals=marcas,
            ticktext=[f"{abs(marca):,}" for marca in marcas],
            title="Casos",
        ),
        yaxis_title="Grupo etario",
        height=500,
        **_LAYOUT,
    )
    contexto = resumen_filtros_activos()
    if filtro_cruzado:
        contexto = f"{contexto} · solo {filtro_cruzado}"
    mostrar_grafica(
        fig,
        "Pirámide de casos por sexo y edad",
        contexto,
        ancho=ANCHO_MEDIA_COLUMNA,
        key=clave_grafica(_PAR_PIRAMIDE, "piramide"),
        on_select="rerun",
        selection_mode="points",
    )


# ---------------------------------------------------------------------------
# Distribucion demografica de casos (panel derecho)
# ---------------------------------------------------------------------------

_OPCIONES_EXPLORADOR = ["Area", "Estrato", "Etnia", "Regimen"]
_ICONOS_EXPLORADOR = {
    "Area":    ":material/home:",
    "Estrato": ":material/apartment:",
    "Etnia":   ":material/diversity_2:",
    "Regimen": ":material/health_and_safety:",
}
_ETIQUETAS_EXPLORADOR = {"Area": "Área", "Estrato": "Estrato", "Etnia": "Etnia", "Regimen": "Régimen"}
_NOMBRE_VARIABLE = {"Area": "área", "Estrato": "estrato", "Etnia": "etnia", "Regimen": "régimen"}
_COLUMNA_VARIABLE = {"Area": "area", "Estrato": "estrato", "Etnia": "per_etn", "Regimen": "tip_ss"}
_COLORES_AREA = {
    "Cabecera municipal": AZUL_INSTITUCIONAL,
    "Centro poblado": NARANJA_INSTITUCIONAL,
    "Rural disperso": "#0891b2",
}


def _explorador_demografico(
    casos: pd.DataFrame, filtro_cruzado: str | None, seleccion_propia: list | None
) -> None:
    st.subheader(":material/tune: Distribución demográfica de casos")

    # Selector de representacion: no filtra datos, elige que variable se dibuja.
    variable = st.segmented_control(
        "Ver distribución por",
        _OPCIONES_EXPLORADOR,
        default="Area",
        required=True,
        format_func=lambda o: f"{_ICONOS_EXPLORADOR[o]} {_ETIQUETAS_EXPLORADOR[o]}",
        key="sociodem_explorador",
    )
    st.caption(":material/touch_app: Haz clic en una barra para ver solo esos casos en la pirámide.")

    contexto = resumen_filtros_activos()
    if filtro_cruzado:
        contexto = f"{contexto} · solo {filtro_cruzado}"

    resaltadas = None
    if seleccion_propia and seleccion_propia[0] == variable:
        resaltadas = seleccion_propia[1]

    _grafica_distribucion(casos, variable, contexto, resaltadas)


def _avisar_distribucion_insuficiente(casos: pd.DataFrame, categorias: int, variable: str) -> None:
    avisar_datos_insuficientes(
        f"Con los filtros actuales hay {describir_cantidad(len(casos), 'caso', 'casos', femenino=False)}, "
        f"en {describir_cantidad(categorias, 'categoría', 'categorías')} de {variable}. "
        "Amplía el período, el territorio o quita la selección de la pirámide para ver una distribución."
    )


def _grafica_distribucion(casos: pd.DataFrame, variable: str, contexto: str, resaltadas: list | None) -> None:
    """Barras horizontales de la variable elegida (area, estrato, etnia o
    regimen). Son barras y no anillo para que se pueda hacer clic en una
    categoria y filtrar la piramide: el anillo no admite seleccion."""
    nombre_variable = _NOMBRE_VARIABLE[variable]
    etiquetas = _etiquetar_variable(casos, variable)
    conteo = etiquetas.dropna().value_counts()
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        _avisar_distribucion_insuficiente(casos, len(conteo), nombre_variable)
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "categoria": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    if variable == "Estrato":
        df = df.sort_values("categoria", ascending=False)
    else:
        df = df.sort_values("casos")

    if variable == "Area":
        colores = [_COLORES_AREA.get(categoria, AZUL_INSTITUCIONAL) for categoria in df["categoria"]]
    else:
        colores = AZUL_INSTITUCIONAL

    fig = px.bar(
        df, x="casos", y="categoria", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "categoria": ""},
    )
    fig.update_traces(
        marker_color=colores,
        marker_opacity=_opacidades(df["categoria"].tolist(), resaltadas),
        textposition="outside",
        name="Casos",
        # En area cada barra tiene su color: una leyenda "Casos" tomaria el color
        # de una sola barra y confundiria. Las categorias ya estan en el eje.
        showlegend=variable != "Area",
    )
    fig.update_layout(
        height=470,
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["casos"].max(), factor=1.35)},
        yaxis={"categoryorder": "array", "categoryarray": df["categoria"].tolist()},
    )
    mostrar_grafica(
        fig,
        f"Distribución demográfica de casos por {nombre_variable}",
        contexto,
        ancho=ANCHO_MEDIA_COLUMNA,
        key=clave_grafica(_PAR_PIRAMIDE, "distribucion"),
        on_select="rerun",
        selection_mode="points",
    )


# ---------------------------------------------------------------------------
# Pueblos indígenas — condicional (3.3)
# ---------------------------------------------------------------------------

def _mostrar_pueblos_indigenas(casos: pd.DataFrame) -> None:
    st.subheader(":material/forest: Pueblos indígenas afectados")

    if "nom_grupo" not in casos.columns:
        st.caption("Sin datos de pueblo indigena.")
        return

    indigenas = casos[(casos["per_etn"] == 1) & casos["nom_grupo"].notna()].copy()
    # Filtrar valores sin informacion
    indigenas = indigenas[
        ~indigenas["nom_grupo"].str.lower().str.strip().isin(_SIN_INFO)
    ]
    conteo = indigenas["nom_grupo"].str.title().value_counts().head(_TOP_N)

    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales hay {describir_cantidad(len(indigenas), 'caso', 'casos', femenino=False)} "
            f"con pueblo indígena identificado, en {describir_cantidad(len(conteo), 'pueblo', 'pueblos', femenino=False)}. "
            "Amplía el período o el territorio para comparar entre pueblos."
        )
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "pueblo": conteo.index,
        "casos": conteo.values,
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="pueblo", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "pueblo": ""},
    )
    fig.update_traces(
        marker_color=AZUL_INSTITUCIONAL,
        textposition="outside",
        name="Casos",
        showlegend=True,
    )
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["casos"].max())},
        yaxis={"categoryorder": "total ascending"},
    )
    mostrar_grafica(fig, "Pueblos indígenas afectados", resumen_filtros_activos())


# ---------------------------------------------------------------------------
# EPS (3.5) y UPGD (3.6)
# ---------------------------------------------------------------------------

def _mostrar_eps(casos: pd.DataFrame) -> None:
    st.subheader(":material/local_hospital: Casos por EPS de afiliación")
    st.caption(f"Las {_TOP_N} EPS con más casos de sus afiliados en el período filtrado.")

    if "nom_ase" not in casos.columns:
        st.caption("Sin datos.")
        return
    conteo = casos["nom_ase"].dropna().value_counts().head(_TOP_N)
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales todos los casos con EPS registrada están en "
            f"{describir_cantidad(len(conteo), 'EPS', 'EPS')}. Amplía el período o el territorio "
            "para comparar entre EPS."
        )
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "eps": conteo.index,
        "casos": conteo.values,
        "eps_short": [s[:60] + "…" if len(s) > 60 else s for s in conteo.index],
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="eps_short", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "eps_short": ""},
        hover_data={"eps": True, "eps_short": False, "casos": True, "etiqueta": False},
    )
    fig.update_traces(
        marker_color=AZUL_INSTITUCIONAL,
        textposition="outside",
        name="Casos",
        showlegend=True,
    )
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["casos"].max())},
        yaxis={"categoryorder": "total ascending"},
    )
    mostrar_grafica(fig, "Casos por EPS de afiliación", resumen_filtros_activos())


def _mostrar_upgd(casos: pd.DataFrame) -> None:
    st.subheader(":material/medical_services: Casos notificados por UPGD")
    st.caption(f"Las {_TOP_N} unidades con más casos notificados en el período filtrado.")

    if "nom_upgd" not in casos.columns:
        st.caption("Sin datos.")
        return
    conteo = casos["nom_upgd"].dropna().str.title().value_counts().head(_TOP_N)
    if not hay_datos_suficientes(conteo, MINIMO_CATEGORIAS_DISTRIBUCION):
        avisar_datos_insuficientes(
            f"Con los filtros actuales todos los casos los notificó "
            f"{describir_cantidad(len(conteo), 'unidad', 'unidades')}. Amplía el período o el "
            "territorio para comparar entre UPGD."
        )
        return

    total = conteo.sum()
    df = pd.DataFrame({
        "upgd": conteo.index,
        "casos": conteo.values,
        "upgd_short": [s[:60] + "…" if len(s) > 60 else s for s in conteo.index],
        "etiqueta": [f"{v:,}  ({_pct(v, total)})" for v in conteo.values],
    })
    fig = px.bar(
        df, x="casos", y="upgd_short", text="etiqueta", orientation="h",
        labels={"casos": "Casos", "upgd_short": ""},
        hover_data={"upgd": True, "upgd_short": False, "casos": True, "etiqueta": False},
    )
    fig.update_traces(
        marker_color=AZUL_INSTITUCIONAL,
        textposition="outside",
        name="Casos",
        showlegend=True,
    )
    fig.update_layout(
        **_LAYOUT,
        xaxis={"range": rango_con_margen(df["casos"].max())},
        yaxis={"categoryorder": "total ascending"},
    )
    mostrar_grafica(fig, "Casos notificados por UPGD", resumen_filtros_activos())
