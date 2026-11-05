"""Pestana Pronostico: pronostico semanal de casos de dengue a nivel
departamental (Magdalena), de 1 a 6 semanas, con tres modelos sin clima, uno por
familia: Prophet (estadistico, el modelo por defecto), XGBoost (aprendizaje
automatico) y LSTM (aprendizaje profundo). Ver el dialogo de "Fundamentacion".

La pestana NO entrena en el pronostico en vivo: carga la version de modelos
exportada que el perfil de administracion genero desde Gestion (ver
core/ingestion/entrenamiento.py y core/storage/modelos.py) y muestra con que
datos fue entrenada. Si el consolidado tiene datos mas recientes que el modelo,
lo avisa. La unica excepcion es el modo de verificacion historica (ver
_entrenar_y_pronosticar_historico).

Serie DEPARTAMENTAL unica: esta pestana NO depende de los filtros globales de
subregion/municipio/anio/semana (los modelos se validaron a escala
departamental), por eso usa siempre el consolidado COMPLETO de la sesion en vez
del datos_filtrados que le llega por el contrato de pestana.

Tasa (casos x100.000 hab.): es una tasa SEMANAL, por eso el numero se ve chico
comparado con la Incidencia anual de Situacion; no son comparables entre si. Usa
poblacion TOTAL del Magdalena (los 30 municipios), NO la poblacion en riesgo que
usan Incidencia/Mortalidad: el pronostico es una serie departamental unica, y
depender de la estratificacion de riesgo (que exige 6 anios de historico)
acoplaria dos piezas independientes. Ver CLAUDE.md.
"""

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.auth.permisos import PERMISO_REENTRENAR_PRONOSTICO, tiene_permiso
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    COLOR_DATO_REAL,
    NARANJA_INSTITUCIONAL,
    mostrar_grafica,
)
from core.dashboard_base.filtros import CLAVE_FILTROS
from core.dashboard_base.gestion_entrenamiento import (
    dialogo_confirmar_reentrenamiento,
    formatear_fecha_larga,
)
from core.dashboard_base.sesion import usuario_actual
from core.storage import modelos as almacen_modelos
from pathologies.dengue.poblacion import obtener_poblacion_total_departamental
from pathologies.dengue.prediccion import (
    HORIZONTE_MAXIMO_SEMANAS,
    HORIZONTE_RECOMENDADO_SEMANAS,
    MODELO_LSTM,
    MODELO_POR_DEFECTO,
    MODELO_PROPHET,
    MODELO_XGBOOST,
    MODELOS_DISPONIBLES,
    NOMBRES_MODELOS,
    SEMANAS_MINIMAS_ENTRENAMIENTO,
    calcular_metricas,
    cargar_modelo,
    construir_serie_semanal_departamental,
    entrenar_modelo,
    pronosticar,
)

PATOLOGIA = "dengue"

# Un color por modelo, fijo en toda la pestana, para que al comparar los tres
# cada uno se reconozca sin leer la leyenda. El negro queda reservado para el
# dato real.
COLORES_MODELO = {
    MODELO_PROPHET: AZUL_INSTITUCIONAL,
    MODELO_XGBOOST: NARANJA_INSTITUCIONAL,
    # Verde azulado y no violeta: el violeta se confundia con el azul de Prophet.
    MODELO_LSTM: "#0891b2",
}

_OPCION_COMPARAR = "comparar"
_ETIQUETAS_SELECTOR_MODELO = {
    **NOMBRES_MODELOS,
    _OPCION_COMPARAR: "Comparar los tres",
}

_METRICAS = ["Casos", "Tasa semanal (x100.000 hab.)"]

_MODO_EN_VIVO = "Pronóstico en vivo (hoy)"
_MODO_PERSONALIZADO = "Elegir otra semana..."

# Ejemplos historicos para presentaciones/validacion: el modelo entrena SOLO con
# datos hasta esa fecha (nunca ve lo que paso despues) y el grafico superpone lo
# que realmente ocurrio, para comparar. Nunca inventa ni fuerza un resultado.
#
# Dos ejemplos A PROPOSITO, en direcciones distintas, para que no se vea como un
# caso aislado elegido a mano: una subida real (inicio del brote de octubre 2018,
# camino al pico de 177 casos/semana en diciembre) y un descenso real (tras ese
# mismo pico, enero 2019). _MODO_PERSONALIZADO deja probar CUALQUIER semana.
_EJEMPLOS_HISTORICOS = {
    "Ejemplo histórico: inicio del brote de octubre 2018": pd.Timestamp("2018-10-28"),
    "Ejemplo histórico: descenso tras el pico de enero 2019": pd.Timestamp("2019-01-06"),
}
_SEMANAS_CONTEXTO_REAL_HISTORICO = 8  # mas alla del horizonte, para ver hacia donde iba realmente

# Vista inicial del eje X: los ultimos dos anios. El rangeslider deja acercar y
# alejar sobre todo el historico sin otro control.
_SEMANAS_VISTA_INICIAL = 104


# ---------------------------------------------------------------------------
# Carga de modelos exportados y calculo (cacheados)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def _cargar_modelo_exportado(version: str, tipo: str):
    """Un modelo exportado se carga una vez por proceso y version. La LSTM
    importa TensorFlow aqui, solo cuando de verdad se pide."""
    carpeta = almacen_modelos.ruta_version(PATOLOGIA, version)
    return cargar_modelo(tipo, carpeta)


@st.cache_data(show_spinner=False)
def _pronosticar_con_exportado(version: str, tipo: str, serie: pd.DataFrame) -> pd.DataFrame:
    """Pronostico en vivo con el modelo exportado de la version activa, desde la
    ultima semana del consolidado cargado. Siempre a HORIZONTE_MAXIMO_SEMANAS:
    el selector de horizonte solo recorta, asi no se recalcula al moverlo."""
    modelo = _cargar_modelo_exportado(version, tipo)
    return pronosticar(modelo, serie, HORIZONTE_MAXIMO_SEMANAS)


# EXCEPCION DELIBERADA a "la pestana no entrena": el modo de verificacion
# historica entrena al vuelo con los datos hasta la fecha elegida, porque ahi el
# punto es justamente que el modelo NO vea lo que vino despues. Un modelo
# exportado ya vio todo el historico y no sirve para esta prueba. No quitar.
@st.cache_data(show_spinner=False)
def _entrenar_y_pronosticar_historico(serie_modelo: pd.DataFrame, tipo: str) -> pd.DataFrame | None:
    modelo = entrenar_modelo(serie_modelo, tipo)
    if modelo is None:
        return None
    return pronosticar(modelo, serie_modelo, HORIZONTE_MAXIMO_SEMANAS)


def _poblacion_por_anio(anios: list[int]) -> dict[int, float | None]:
    return {anio: obtener_poblacion_total_departamental([anio]) for anio in sorted(set(anios))}


def _agregar_tasa(df: pd.DataFrame, columna_casos: str) -> pd.DataFrame:
    """Agrega '<columna>_tasa' dividiendo por la poblacion TOTAL del Magdalena
    del anio de cada fila. None (no disponible) si falta poblacion para ese
    anio, nunca un numero inventado."""
    df = df.copy()
    poblacion = _poblacion_por_anio(df["ano"].tolist())
    tasas = []
    for _, fila in df.iterrows():
        poblacion_anio = poblacion[fila["ano"]]
        if poblacion_anio:
            tasas.append(fila[columna_casos] / poblacion_anio * 100_000)
        else:
            tasas.append(None)
    df[f"{columna_casos}_tasa"] = tasas
    return df


# ---------------------------------------------------------------------------
# Vista
# ---------------------------------------------------------------------------

def mostrar_pronostico(_datos_filtrados: pd.DataFrame) -> None:
    """_datos_filtrados llega por el contrato uniforme de pestana, pero se
    ignora a proposito: esta pestana siempre usa el consolidado completo."""
    datos_completos = modulo_datos.obtener_datos(PATOLOGIA)

    col_titulo, col_fundamentacion = st.columns([5, 1.6], vertical_alignment="center")
    with col_titulo:
        st.subheader(":material/query_stats: Pronóstico de casos de dengue")
    with col_fundamentacion:
        if st.button(
            "Fundamentación", icon=":material/school:", key="pronostico_fundamentacion", width="stretch"
        ):
            _dialogo_fundamentacion()

    st.caption(
        "Pronóstico a nivel departamental (todo el Magdalena). No depende de los filtros "
        "de la barra lateral: usa siempre el histórico completo."
    )
    _avisar_si_hay_filtros_geograficos_activos()

    serie = construir_serie_semanal_departamental(datos_completos)
    if len(serie) < SEMANAS_MINIMAS_ENTRENAMIENTO:
        st.warning(
            f"No es posible calcular el pronóstico: hacen falta al menos "
            f"{SEMANAS_MINIMAS_ENTRENAMIENTO} semanas de histórico semanal continuo "
            f"para estimar la estacionalidad anual, y hay {len(serie)} semanas "
            f"({len(serie) / 52:.1f} años) disponibles.",
            icon=":material/warning:",
        )
        return

    modo = st.selectbox(
        "Modo",
        [_MODO_EN_VIVO] + list(_EJEMPLOS_HISTORICOS.keys()) + [_MODO_PERSONALIZADO],
        key="pronostico_modo",
        help=(
            "Los modos históricos entrenan el mismo modelo como si solo conociera datos "
            "hasta esa fecha pasada (nunca ve lo que pasó después) y comparan contra los "
            "casos reales que ocurrieron: sirven para verificar el modelo con casos reales, no "
            "son el pronóstico de hoy. \"Elegir otra semana\" deja probar cualquier semana del "
            "histórico, no solo los ejemplos preseleccionados."
        ),
    )

    col_modelo, col_horizonte, col_metrica = st.columns([2.2, 2, 1.8], vertical_alignment="bottom")
    with col_modelo:
        opcion_modelo = st.selectbox(
            "Modelo",
            MODELOS_DISPONIBLES + [_OPCION_COMPARAR],
            index=MODELOS_DISPONIBLES.index(MODELO_POR_DEFECTO),
            format_func=lambda opcion: _ETIQUETAS_SELECTOR_MODELO[opcion],
            key="pronostico_modelo",
        )
    with col_horizonte:
        horizonte = st.select_slider(
            "Horizonte (semanas)",
            options=list(range(1, HORIZONTE_MAXIMO_SEMANAS + 1)),
            value=HORIZONTE_RECOMENDADO_SEMANAS,
            key="pronostico_horizonte",
        )
    with col_metrica:
        metrica = st.segmented_control(
            "Métrica", _METRICAS, default=_METRICAS[0], key="pronostico_metrica", required=True
        )

    if opcion_modelo == _OPCION_COMPARAR:
        tipos = list(MODELOS_DISPONIBLES)
    else:
        tipos = [opcion_modelo]

    if horizonte > HORIZONTE_RECOMENDADO_SEMANAS:
        st.warning(
            f"El documento técnico recomienda pronosticar hasta {HORIZONTE_RECOMENDADO_SEMANAS} "
            "semanas. Más allá el error crece de forma notoria: en la sexta semana, Prophet tuvo "
            "un MAPE del 35 % y un R² de 0.62, contra 0.87 en la primera.",
            icon=":material/warning:",
        )

    if modo == _MODO_EN_VIVO:
        _mostrar_en_vivo(serie, tipos, horizonte, metrica)
        return

    if modo == _MODO_PERSONALIZADO:
        origen = _seleccionar_semana_personalizada(serie)
        if origen is None:
            return
    else:
        origen = _EJEMPLOS_HISTORICOS[modo]
    _mostrar_historico(serie, origen, tipos, horizonte, metrica)


def _mostrar_en_vivo(serie: pd.DataFrame, tipos: list[str], horizonte: int, metrica: str) -> None:
    version = almacen_modelos.version_activa(PATOLOGIA)
    if version is None:
        _explicar_sin_modelo()
        return
    manifest = almacen_modelos.leer_manifest(PATOLOGIA, version) or {}
    _mostrar_procedencia(manifest, serie)

    pronosticos = {}
    for tipo in tipos:
        if tipo == MODELO_LSTM:
            mensaje = "Cargando la LSTM (la primera vez tarda porque carga TensorFlow)..."
        else:
            mensaje = f"Calculando el pronóstico con {NOMBRES_MODELOS[tipo]}..."
        with st.spinner(mensaje):
            pronostico_completo = _pronosticar_con_exportado(version, tipo, serie)
        pronosticos[tipo] = pronostico_completo[pronostico_completo["horizonte_semanas"] <= horizonte]

    _mostrar_error_esperado(manifest, tipos, horizonte)
    _dibujar(serie, pronosticos, metrica, contexto_real=None)
    _mostrar_semanas_pronosticadas(pronosticos, es_historico=False)


def _mostrar_historico(
    serie: pd.DataFrame, origen: pd.Timestamp, tipos: list[str], horizonte: int, metrica: str
) -> None:
    serie_modelo = serie[serie["fecha_semana"] <= origen].reset_index(drop=True)
    fin_contexto = origen + pd.Timedelta(weeks=_SEMANAS_CONTEXTO_REAL_HISTORICO)
    serie_contexto_real = serie[
        (serie["fecha_semana"] > origen) & (serie["fecha_semana"] <= fin_contexto)
    ].reset_index(drop=True)

    st.warning(
        f"Estás viendo un EJEMPLO HISTÓRICO, no el pronóstico de hoy: modelo entrenado aquí "
        f"mismo solo con datos hasta el {formatear_fecha_larga(origen.isoformat())}, comparado con "
        "los casos reales que ocurrieron después.",
        icon=":material/history_edu:",
    )

    if len(serie_modelo) < SEMANAS_MINIMAS_ENTRENAMIENTO:
        st.warning(
            "No hay suficiente histórico antes de esta fecha para entrenar el modelo.",
            icon=":material/warning:",
        )
        return

    pronosticos = {}
    for tipo in tipos:
        with st.spinner(f"Entrenando {NOMBRES_MODELOS[tipo]} con datos hasta esa fecha..."):
            pronostico_completo = _entrenar_y_pronosticar_historico(serie_modelo, tipo)
        if pronostico_completo is None:
            st.warning(f"No fue posible entrenar {NOMBRES_MODELOS[tipo]}.", icon=":material/warning:")
            continue
        pronosticos[tipo] = pronostico_completo[pronostico_completo["horizonte_semanas"] <= horizonte]

    if not pronosticos:
        return

    anios = int(serie_modelo["ano"].min()), int(serie_modelo["ano"].max())
    st.caption(
        f":material/history: Modelo entrenado con {len(serie_modelo)} semanas de histórico "
        f"({anios[0]}-{anios[1]})."
    )
    _mostrar_error_real(pronosticos, serie_contexto_real, horizonte)
    _dibujar(serie_modelo, pronosticos, metrica, contexto_real=serie_contexto_real)
    _mostrar_semanas_pronosticadas(pronosticos, es_historico=True, contexto_real=serie_contexto_real)


def _explicar_sin_modelo() -> None:
    st.info(
        "Todavía no hay un modelo de pronóstico entrenado, así que no se puede mostrar el "
        "pronóstico de hoy. Lo genera el perfil de administración desde Gestión, en el apartado "
        "Pronóstico. Mientras tanto, los modos históricos de arriba sí funcionan.",
        icon=":material/info:",
    )
    usuario = usuario_actual()
    if usuario is not None and tiene_permiso(usuario.rol, PERMISO_REENTRENAR_PRONOSTICO):
        if st.button("Entrenar ahora", icon=":material/model_training:", key="pronostico_entrenar_primero"):
            dialogo_confirmar_reentrenamiento(PATOLOGIA, usuario)


def _mostrar_procedencia(manifest: dict, serie: pd.DataFrame) -> None:
    """Con que datos fue entrenado el modelo en uso (visible, no en un tooltip)
    y aviso si el consolidado ya tiene datos mas recientes que el modelo."""
    rango = manifest.get("rango", {})
    fecha = formatear_fecha_larga(manifest["fecha_entrenamiento"])
    st.markdown(
        f":material/model_training: Modelo entrenado el {fecha} con {rango.get('anio_inicio')}-"
        f"{rango.get('anio_fin')} ({manifest.get('semanas')} semanas, hasta la semana "
        f"{rango.get('semana_fin')} de {rango.get('anio_fin')})."
    )

    fecha_ultima_modelo = pd.Timestamp(rango.get("fecha_ultima_semana"))
    fecha_ultima_datos = pd.Timestamp(serie["fecha_semana"].iloc[-1])
    if fecha_ultima_datos <= fecha_ultima_modelo:
        return

    ultima = serie.iloc[-1]
    semanas_nuevas = int((fecha_ultima_datos - fecha_ultima_modelo).days // 7)
    st.warning(
        f"El consolidado tiene datos más recientes que el modelo: llega hasta la semana "
        f"{int(ultima['semana'])} de {int(ultima['ano'])}, {semanas_nuevas} semana(s) después de lo "
        "que vio el modelo. El pronóstico se calcula desde la última semana cargada, pero el "
        "modelo no aprendió de esos datos nuevos. Hay que reentrenarlo desde Gestión, apartado "
        "Pronóstico (perfil de administración).",
        icon=":material/update:",
    )
    usuario = usuario_actual()
    if usuario is not None and tiene_permiso(usuario.rol, PERMISO_REENTRENAR_PRONOSTICO):
        if st.button("Reentrenar ahora", icon=":material/model_training:", key="pronostico_reentrenar_desactualizado"):
            dialogo_confirmar_reentrenamiento(PATOLOGIA, usuario)


def _formatear_numero(valor: float | None, sufijo: str = "", decimales: int = 1) -> str:
    if valor is None:
        return "No disponible"
    return f"{valor:,.{decimales}f}{sufijo}"


def _mostrar_tarjetas_metricas(metricas_por_modelo: dict) -> None:
    """Las cuatro metricas (RMSE, MAE, MAPE, R2). Con un modelo, una tarjeta por
    metrica; comparando los tres, una tabla con una fila por modelo. Dentro de un
    st.empty: el bloque cambia de forma (tarjetas o tabla) y asi nunca queda a la
    vista la forma anterior."""
    with st.empty().container():
        _dibujar_tarjetas_metricas(metricas_por_modelo)


def _dibujar_tarjetas_metricas(metricas_por_modelo: dict) -> None:
    if len(metricas_por_modelo) == 1:
        valores = next(iter(metricas_por_modelo.values()))
        columnas = st.columns(4)
        with columnas[0]:
            st.metric("RMSE (casos)", _formatear_numero(valores.get("RMSE")), border=True)
        with columnas[1]:
            st.metric("MAE (casos)", _formatear_numero(valores.get("MAE")), border=True)
        with columnas[2]:
            st.metric("MAPE", _formatear_numero(valores.get("MAPE"), " %"), border=True)
        with columnas[3]:
            st.metric("R²", _formatear_numero(valores.get("R2"), decimales=2), border=True)
        return

    filas = []
    for tipo, valores in metricas_por_modelo.items():
        filas.append({
            "Modelo": NOMBRES_MODELOS[tipo],
            "RMSE (casos)": valores.get("RMSE"),
            "MAE (casos)": valores.get("MAE"),
            "MAPE (%)": valores.get("MAPE"),
            "R²": valores.get("R2"),
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")


def _mostrar_error_esperado(manifest: dict, tipos: list[str], horizonte: int) -> None:
    """Error que el modelo obtuvo en la validacion walk-forward del sistema PARA
    EL HORIZONTE ELEGIDO. Nunca es el error de esta prediccion (el futuro todavia
    no paso): se rotula como error esperado."""
    metricas = manifest.get("metricas", {})
    st.caption(
        f":material/rule: Error esperado a {horizonte} semana(s), medido en validación histórica "
        "(walk-forward del sistema sobre los datos con que se entrenó esta versión). No es el "
        "error de esta predicción."
    )
    metricas_por_modelo = {tipo: metricas.get(tipo, {}).get(str(horizonte), {}) for tipo in tipos}
    _mostrar_tarjetas_metricas(metricas_por_modelo)


def _mostrar_error_real(pronosticos: dict, contexto_real: pd.DataFrame, horizonte: int) -> None:
    """En modo historico SI se puede medir el error real: lo que el modelo
    pronostico contra lo que paso en esas mismas semanas. Se muestran las cuatro
    metricas, R2 incluido, aunque con tan pocas semanas sea inestable."""
    reales = contexto_real.head(horizonte)
    if reales.empty:
        return
    cantidad = len(reales)
    st.caption(
        f":material/rule: Error real de este ejemplo: pronóstico contra lo que ocurrió en las "
        f"{cantidad} semana(s) siguientes."
    )
    metricas_por_modelo = {}
    for tipo, pronostico in pronosticos.items():
        comparables = pronostico.head(cantidad)["casos_pronosticados"].to_numpy()
        metricas_por_modelo[tipo] = calcular_metricas(reales["casos"].to_numpy()[:len(comparables)], comparables)
    _mostrar_tarjetas_metricas(metricas_por_modelo)


def _seleccionar_semana_personalizada(serie: pd.DataFrame) -> pd.Timestamp | None:
    """Deja elegir CUALQUIER semana del historico como origen, no solo los dos
    ejemplos preseleccionados. La fecha se ajusta a la semana epidemiologica mas
    cercana hacia atras (convencion CDC)."""
    fechas_disponibles = serie["fecha_semana"]
    if len(fechas_disponibles) <= SEMANAS_MINIMAS_ENTRENAMIENTO:
        st.info(
            "Todavía no hay suficiente histórico para elegir una semana personalizada.",
            icon=":material/info:",
        )
        return None

    primera_fecha_valida = fechas_disponibles.iloc[SEMANAS_MINIMAS_ENTRENAMIENTO - 1]
    ultima_fecha_valida = fechas_disponibles.iloc[-2]  # deja al menos 1 semana real de contexto despues

    fecha_elegida = st.date_input(
        "Semana de origen (se ajusta al inicio de esa semana epidemiológica)",
        value=primera_fecha_valida.date(),
        min_value=primera_fecha_valida.date(),
        max_value=ultima_fecha_valida.date(),
        key="pronostico_fecha_personalizada",
    )
    fecha_elegida = pd.Timestamp(fecha_elegida)

    semanas_hasta_fecha = fechas_disponibles[fechas_disponibles <= fecha_elegida]
    if semanas_hasta_fecha.empty:
        return primera_fecha_valida
    return semanas_hasta_fecha.iloc[-1]


def _avisar_si_hay_filtros_geograficos_activos() -> None:
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    if filtros.get("subregion") or filtros.get("nom_mun_o"):
        st.info(
            "Tienes un filtro de subregión o municipio activo: no afecta a esta pestaña, "
            "el pronóstico siempre es departamental.",
            icon=":material/info:",
        )


# ---------------------------------------------------------------------------
# Grafica
# ---------------------------------------------------------------------------

def _dibujar(serie: pd.DataFrame, pronosticos: dict, metrica: str, contexto_real: pd.DataFrame | None) -> None:
    usar_tasa = metrica == _METRICAS[1]
    serie_grafica = _agregar_tasa(serie, "casos") if usar_tasa else serie
    contexto_grafica = None
    if contexto_real is not None and not contexto_real.empty:
        contexto_grafica = _agregar_tasa(contexto_real, "casos") if usar_tasa else contexto_real
    pronosticos_grafica = {}
    for tipo, pronostico in pronosticos.items():
        if usar_tasa:
            pronosticos_grafica[tipo] = _agregar_tasa(pronostico, "casos_pronosticados")
        else:
            pronosticos_grafica[tipo] = pronostico

    figura = _graficar_pronostico(serie_grafica, pronosticos_grafica, usar_tasa, contexto_grafica)
    # Anio epidemiologico (no el calendario de la fecha): la semana 1 de 2007
    # empieza el 31 de diciembre de 2006.
    anio_inicio = int(serie["ano"].iloc[0])
    anio_fin = int(serie["ano"].iloc[-1])
    contexto_texto = f"Dengue · Magdalena · casos semanales {anio_inicio}-{anio_fin} y pronóstico"
    mostrar_grafica(figura, "Pronóstico de casos de dengue", contexto_texto, key="pronostico_grafica")


def _graficar_pronostico(
    serie: pd.DataFrame,
    pronosticos: dict,
    usar_tasa: bool,
    contexto_real: pd.DataFrame | None,
) -> go.Figure:
    """Negro continuo = dato real (incluido, en modo historico, lo que paso
    despues del corte). Punteado con marcadores = modelo, un color fijo por
    modelo. Sin banda de incertidumbre (ver prediccion.pronosticar)."""
    columna_real = "casos_tasa" if usar_tasa else "casos"
    columna_pronostico = "casos_pronosticados_tasa" if usar_tasa else "casos_pronosticados"
    etiqueta_eje = "Tasa semanal (x100.000 hab.)" if usar_tasa else "Casos"
    formato = ",.2f" if usar_tasa else ",.0f"

    fechas_reales = serie["fecha_semana"]
    valores_reales = serie[columna_real]
    if contexto_real is not None:
        fechas_reales = pd.concat([fechas_reales, contexto_real["fecha_semana"]])
        valores_reales = pd.concat([valores_reales, contexto_real[columna_real]])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=fechas_reales,
        y=valores_reales,
        mode="lines",
        line=dict(color=COLOR_DATO_REAL, width=1.4),
        name="Casos reales",
        hovertemplate=f"%{{x|%d %b %Y}} · %{{y:{formato}}}<extra>Real</extra>",
    ))

    # Puente entre la ultima semana que vio el modelo y la primera pronosticada:
    # sin este punto, la linea punteada queda desconectada del historico.
    fecha_corte = serie["fecha_semana"].iloc[-1]
    valor_corte = serie[columna_real].iloc[-1]
    for tipo, pronostico in pronosticos.items():
        fig.add_trace(go.Scatter(
            x=[fecha_corte] + pronostico["fecha_semana"].tolist(),
            y=[valor_corte] + pronostico[columna_pronostico].tolist(),
            mode="lines+markers",
            line=dict(color=COLORES_MODELO[tipo], width=2.2, dash="dot"),
            marker=dict(size=8, color=COLORES_MODELO[tipo]),
            name=NOMBRES_MODELOS[tipo],
            hovertemplate=f"%{{x|%d %b %Y}} · %{{y:{formato}}}<extra>{NOMBRES_MODELOS[tipo]}</extra>",
        ))

    fig.add_vline(x=fecha_corte, line_width=1.2, line_dash="dot", line_color="#6b7280")
    fig.add_annotation(
        x=fecha_corte, y=1, yref="paper", xanchor="right", yanchor="bottom",
        text="Último dato que vio el modelo", showarrow=False, font=dict(size=14, color="#4b5563"),
    )

    fecha_fin_visible = max(pronostico["fecha_semana"].iloc[-1] for pronostico in pronosticos.values())
    if contexto_real is not None and not contexto_real.empty:
        fecha_fin_visible = max(fecha_fin_visible, contexto_real["fecha_semana"].iloc[-1])
    semanas_visibles = min(len(serie), _SEMANAS_VISTA_INICIAL)
    inicio_visible = serie["fecha_semana"].iloc[-semanas_visibles]

    fig.update_layout(
        xaxis=dict(
            title="Semana epidemiológica (fecha de inicio)",
            range=[inicio_visible, fecha_fin_visible + pd.Timedelta(weeks=1)],
            rangeslider=dict(visible=True, thickness=0.08),
        ),
        yaxis=dict(title=etiqueta_eje, rangemode="tozero"),
        # Margen inferior para que el titulo del eje X no quede cortado debajo de
        # la barra deslizante (rangeslider), sobre todo en pantalla completa.
        margin=dict(l=0, r=10, b=70),
        height=560,
    )
    return fig


def _mostrar_semanas_pronosticadas(
    pronosticos: dict, es_historico: bool, contexto_real: pd.DataFrame | None = None
) -> None:
    st.space("small")
    etiqueta = "Semanas siguientes al ejemplo histórico" if es_historico else "Próximas semanas"
    st.caption(f":material/calendar_month: {etiqueta}")
    with st.empty().container():
        _dibujar_semanas_pronosticadas(pronosticos, contexto_real)


def _dibujar_semanas_pronosticadas(pronosticos: dict, contexto_real: pd.DataFrame | None) -> None:

    if len(pronosticos) == 1:
        tipo, pronostico = next(iter(pronosticos.items()))
        pronostico_con_tasa = _agregar_tasa(pronostico, "casos_pronosticados")
        # Siempre la misma cantidad de columnas (el horizonte maximo), aunque el
        # horizonte elegido sea menor: si la cantidad de columnas cambia entre
        # reruns del fragmento, Streamlit podia dejar a la vista la fila de
        # tarjetas anterior junto a la nueva (tarjetas duplicadas).
        columnas = st.columns(HORIZONTE_MAXIMO_SEMANAS)
        for columna, (_, fila) in zip(columnas, pronostico_con_tasa.iterrows()):
            tasa = fila["casos_pronosticados_tasa"]
            tasa_texto = f"{tasa:,.1f}" if tasa is not None else "No disponible"
            with columna:
                st.metric(
                    f"Sem. {int(fila['semana'])} · {int(fila['ano'])}",
                    f"{fila['casos_pronosticados']:,.0f} casos",
                    help=(
                        f"Tasa semanal: {tasa_texto} x100.000 hab. (población total del Magdalena, "
                        "no comparable con la Incidencia anual de Situación). Horizonte: "
                        f"{int(fila['horizonte_semanas'])} semana(s) desde la última semana con "
                        "datos reales."
                    ),
                    border=True,
                )
        return

    primer_pronostico = next(iter(pronosticos.values()))
    tabla = pd.DataFrame({
        "Semana": [
            f"Sem. {int(fila['semana'])} · {int(fila['ano'])}" for _, fila in primer_pronostico.iterrows()
        ],
    })
    for tipo, pronostico in pronosticos.items():
        tabla[NOMBRES_MODELOS[tipo]] = np.round(pronostico["casos_pronosticados"].to_numpy(), 0)
    if contexto_real is not None and not contexto_real.empty:
        reales = contexto_real.head(len(tabla))["casos"].tolist()
        reales = reales + [None] * (len(tabla) - len(reales))
        tabla["Casos reales"] = reales
    st.dataframe(tabla, hide_index=True, width="stretch")


# ---------------------------------------------------------------------------
# Dialogo de fundamentacion: resume el documento tecnico de modelado (repo de
# modelado, notebooks 03_dengue_modeling y 05_dengue_ablacion_clima_vs_lags).
# La tabla de aqui es la evaluacion del ESTUDIO DE MODELADO y justifica por que
# se eligieron estas tres familias; la tabla de error que acompana al pronostico
# en la pestana es la de la validacion del PROPIO SISTEMA. No mezclarlas.
# ---------------------------------------------------------------------------

_TABLA_NOTEBOOK_05 = (
    "| Modelo | H | RMSE | MAE | MAPE | R² |\n"
    "|---|---|---|---|---|---|\n"
    "| Prophet | 1 | 12.335 | 8.909 | 23.07 % | 0.8672 |\n"
    "| Prophet | 2 | 14.027 | 10.062 | 24.64 % | 0.8283 |\n"
    "| Prophet | 3 | 16.292 | 11.638 | 28.45 % | 0.7684 |\n"
    "| Prophet | 4 | 17.468 | 12.415 | 30.75 % | 0.7337 |\n"
    "| Prophet | 6 | 20.761 | 14.152 | 35.37 % | 0.6239 |\n"
    "| XGBoost | 1 | 12.912 | 9.528 | 24.65 % | 0.8545 |\n"
    "| XGBoost | 2 | 13.937 | 10.112 | 26.48 % | 0.8305 |\n"
    "| XGBoost | 3 | 15.884 | 11.807 | 30.42 % | 0.7798 |\n"
    "| XGBoost | 4 | 17.804 | 13.361 | 35.29 % | 0.7234 |\n"
    "| XGBoost | 6 | 23.585 | 16.665 | 40.74 % | 0.5146 |\n"
    "| LSTM | 1 | 12.968 | 9.025 | 22.40 % | 0.8533 |\n"
    "| LSTM | 2 | 14.661 | 10.229 | 24.37 % | 0.8124 |\n"
    "| LSTM | 3 | 17.387 | 11.787 | 27.40 % | 0.7362 |\n"
    "| LSTM | 4 | 19.815 | 13.479 | 31.10 % | 0.6574 |\n"
    "| LSTM | 6 | 24.317 | 16.267 | 35.89 % | 0.4840 |\n"
    "| Persistencia (línea base) | 1 | 13.211 | 9.950 | 26.11 % | 0.8477 |\n"
    "| Persistencia (línea base) | 2 | 14.007 | 10.440 | 25.90 % | 0.8288 |\n"
    "| Persistencia (línea base) | 3 | 17.543 | 12.702 | 30.76 % | 0.7315 |\n"
    "| Persistencia (línea base) | 4 | 19.942 | 14.929 | 36.52 % | 0.6530 |\n"
    "| Persistencia (línea base) | 6 | 24.926 | 17.702 | 44.25 % | 0.4579 |"
)


@st.dialog("Fundamentación del pronóstico", width="large")
def _dialogo_fundamentacion() -> None:
    st.markdown(
        "Resumen del documento técnico de modelado: por qué tres modelos, por qué sin variables "
        "climáticas y hasta dónde llega el horizonte útil."
    )

    tab_resumen, tab_familias, tab_clima, tab_horizonte, tab_datos = st.tabs(
        ["Resumen", "Tres familias", "¿Por qué sin clima?", "Horizonte", "Datos y validación"]
    )

    with tab_resumen:
        st.markdown(
            "Se evaluaron 6 modelos de tres familias (estadísticos: SARIMAX y Prophet; aprendizaje "
            "automático: XGBoost y LightGBM; aprendizaje profundo: LSTM y N-BEATS) con pronóstico "
            "multipaso walk-forward (origen móvil, sin ver los casos de las semanas que se "
            "pronostican). Es la evaluación honesta para alerta temprana: la comparación a un "
            "paso está inflada por la autocorrelación semanal de la serie."
        )
        st.markdown(
            "El tablero despliega el mejor de cada familia a multipaso y sin covariables "
            "climáticas, que es su escenario operativo real:\n\n"
            "- Estadístico: Prophet-AR (estacionalidad anual y rezagos de 1, 2, 4 y 8 semanas). "
            "SARIMAX fue peor en los cinco horizontes.\n"
            "- Aprendizaje automático: XGBoost sobre los mismos rezagos. LightGBM fue peor en los "
            "cinco horizontes.\n"
            "- Aprendizaje profundo: LSTM con una ventana de 12 semanas. N-BEATS fue peor en los "
            "cinco horizontes y se derrumba desde la tercera semana (R² de -1.13 en la sexta).\n\n"
            "Prophet queda por defecto: es el único que se sostiene en todo el rango de "
            "horizontes y el mejor a 4 semanas, el horizonte operativo."
        )

    with tab_familias:
        st.markdown(
            "Desempeño por horizonte (H, en semanas), sin clima. Evaluación del estudio de "
            "modelado: notebook 05 del repositorio dengue-surveillance-magdalena, validación "
            "walk-forward sobre la serie de investigación 2007-2024."
        )
        st.markdown(_TABLA_NOTEBOOK_05)
        st.markdown(
            "Dos lecturas de esta tabla:\n\n"
            "- XGBoost es el mejor en la segunda y la tercera semana; Prophet en la primera, la "
            "cuarta y la sexta.\n"
            "- La LSTM apenas supera a la persistencia a partir de la cuarta semana (RMSE de "
            "19.815 contra 19.942): en una serie de este tamaño, el aporte real del aprendizaje "
            "profundo es pequeño."
        )
        st.caption(
            "Esta tabla justifica la elección de las tres familias. El error que acompaña al "
            "pronóstico en la pestaña es otro: el de la validación que corre el propio sistema "
            "cada vez que se reentrena, sobre los datos del CITES."
        )

    with tab_clima:
        st.markdown(
            "Se comparó cada modelo entrenado con y sin variables climáticas (humedad, "
            "precipitación, temperatura), mismos hiperparámetros, única diferencia el clima."
        )
        st.markdown(
            "| Modelo | Δ R² h=1 | Δ R² h=3 | Δ R² h=4 | Δ R² h=6 |\n"
            "|---|---|---|---|---|\n"
            "| Prophet | -0.006 | -0.012 | -0.016 | -0.026 |\n"
            "| ARIMA / SARIMA | -0.003 | -0.035 | -0.053 | -0.120 |\n"
            "| XGBoost | -0.010 | -0.056 | -0.080 | -0.154 |\n"
            "| LightGBM | -0.017 | -0.050 | -0.081 | -0.093 |\n"
            "| LSTM | -0.022 | -0.064 | -0.081 | -0.119 |\n"
            "| N-BEATS | -0.026 | -0.218 | -0.481 | -1.555 |"
        )
        st.caption(
            "Δ R² = R² sin clima menos R² con clima (más negativo = el clima ayuda más). Prophet "
            "es el único cuya pérdida se mantiene marginal en todo el rango."
        )
        st.markdown(
            "Se optó por no usar covariables climáticas: el costo de adquirir, actualizar y "
            "validar series climáticas recae sobre la operación del sistema, y para el modelo por "
            "defecto (Prophet) esa mejora no es significativa en el horizonte útil."
        )

    with tab_horizonte:
        st.markdown(
            f"El selector deja pronosticar de 1 a {HORIZONTE_MAXIMO_SEMANAS} semanas. El documento "
            f"técnico recomienda hasta {HORIZONTE_RECOMENDADO_SEMANAS}: a partir de la quinta el "
            "error crece de forma notoria (en la sexta, MAPE del 35 % y R² de 0.62 en Prophet, "
            "contra 0.87 en la primera) y la pestaña lo avisa."
        )
        st.markdown(
            "El horizonte de 5 semanas no se evaluó en el notebook; el pronóstico recursivo lo "
            "produce igual y su error sale de la validación que hace el propio sistema al "
            "reentrenar."
        )
        st.markdown(
            "Pronóstico recursivo: para pronosticar más de una semana, los rezagos que caen dentro "
            "del horizonte se completan con la propia predicción del modelo, la misma lógica de la "
            "evaluación walk-forward."
        )

    with tab_datos:
        st.markdown(
            "La serie de investigación con que se validaron los modelos cubre 940 semanas "
            "epidemiológicas (2007-2024), dividida cronológicamente en 70 % entrenamiento, 15 % "
            "validación y 15 % prueba (2022-2024), sin barajar."
        )
        st.markdown(
            "Los modelos que usa este tablero no se entrenan solos: el perfil de administración "
            "los reentrena desde Gestión cuando se carga información nueva. Cada reentrenamiento "
            "es una versión nueva (las anteriores se conservan y se puede volver a ellas), queda "
            "registrado quién lo lanzó y con qué datos, y calcula su propio error por horizonte de "
            "1 a 6 semanas con una validación walk-forward sobre los datos del CITES (último 15 % "
            "de la serie como prueba). Ese es el error esperado que se muestra junto al pronóstico."
        )
        st.markdown(
            "El selector Modo incluye ejemplos históricos (una subida real y un descenso real) y la "
            "opción de elegir cualquier semana: ahí el modelo se entrena en el momento solo con "
            "datos hasta esa fecha y se compara contra lo que efectivamente ocurrió. Ninguno "
            "inventa ni ajusta el resultado. No reemplazan el pronóstico de hoy."
        )

    if st.button("Cerrar", width="stretch"):
        st.rerun()
