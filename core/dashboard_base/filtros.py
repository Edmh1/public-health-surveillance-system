"""Filtros globales del dashboard.

Operan siempre sobre el dataframe ya cargado en session_state (core/dashboard_base/datos.py).
Cambiar un filtro nunca relee el consolidado del disco, solo indexa el dataframe en memoria.

Decisiones de UX:
- Anio y semana epidemiologica son range sliders (select_slider): mas natural seleccionar
  "2021 a 2024" que marcar anios sueltos en un multiselect de 6 items.
- Subregion y clasificacion del caso son pills: pocas opciones que conviene ver de golpe
  y activar con un solo toque, sin abrir un dropdown.
- Municipio sigue siendo multiselect porque puede tener hasta 30 opciones.
- Las 3 secciones principales se muestran siempre sin expander: un click extra para ver
  los filtros principales es una fricccion innecesaria en una herramienta de analisis.
- Solo "Proximamente" queda en expander colapsado, para que no confunda mostrando
  controles que todavia no funcionan.
"""

import pandas as pd
import streamlit as st

CLAVE_FILTROS = "filtros_globales"
_CLAVE_ANIOS_DISPONIBLES = "_filtro_anios_disponibles"
_CLAVE_SEMANAS_DISPONIBLES = "_filtro_semanas_disponibles"
_CLAVE_MAPEOS = "_filtro_mapeos_vigentes"

# Mapeo de codigos de clasificacion a nombres legibles.
# Aplica tanto a TIP_CAS (clasificacion inicial) como a AJUSTE / Estado_final_de_caso.
_ETIQUETAS_CLASIFICACION: dict[str, str] = {
    "1": "Sospechoso",
    "2": "Probable",
    "3": "Confirmado por laboratorio",
    "4": "Confirmado por clinica",
    "5": "Confirmado por nexo epidemiológico",
    "6": "Descartado",
    "0": "No aplica",
    "7": "Otro",
    "D": "Error de digitacion",
}


def _etiquetar_clasificacion(valor) -> str:
    """Devuelve el nombre legible del codigo de clasificacion.
    Si el valor ya es un texto no numerico (columna procesada con label), lo retorna tal cual.
    """
    return _ETIQUETAS_CLASIFICACION.get(str(valor).strip(), str(valor))


CLAVES_REINICIABLES = (
    "filtro_subregion",
    "filtro_municipio",
    "filtro_anio_rango",
    "filtro_semana_rango",
    "filtro_nivel_riesgo",
    "filtro_clasificacion",
)


def _opciones_de_columna(datos: pd.DataFrame, columna: str) -> list:
    if columna not in datos.columns:
        return []
    return sorted(datos[columna].dropna().unique().tolist())


def _agregar_columna_subregion(datos: pd.DataFrame, mapeo_subregion: dict[int, str]) -> pd.DataFrame:
    """Deriva subregion en memoria desde cod_mun_completo. No se persiste en ningun lado."""
    if "cod_mun_completo" not in datos.columns:
        return datos.assign(subregion=pd.NA)
    datos_con_subregion = datos.copy()
    datos_con_subregion["subregion"] = datos_con_subregion["cod_mun_completo"].map(mapeo_subregion)
    return datos_con_subregion


def _agregar_columna_nivel_riesgo(datos: pd.DataFrame, mapeo_estratificacion_riesgo: dict[int, str]) -> pd.DataFrame:
    """Deriva nivel_riesgo en memoria desde cod_mun_completo, igual que subregion.
    Si la patologia no tiene mapeo de estratificacion (mapeo vacio), la columna
    queda toda nula y el filtro simplemente no ofrece opciones.
    """
    if "cod_mun_completo" not in datos.columns:
        return datos.assign(nivel_riesgo=pd.NA)
    datos_con_nivel_riesgo = datos.copy()
    datos_con_nivel_riesgo["nivel_riesgo"] = datos_con_nivel_riesgo["cod_mun_completo"].map(mapeo_estratificacion_riesgo)
    return datos_con_nivel_riesgo


def _corregir_rango(clave: str, opciones: list) -> None:
    """Ajusta el rango guardado si las opciones cambiaron (ej. despues de Actualizar
    que trajo datos de nuevos anios). Evita que el slider falle con un valor fuera
    de las opciones disponibles.
    """
    rango = st.session_state.get(clave)
    if not (rango and isinstance(rango, tuple) and len(rango) == 2 and opciones):
        return
    inicio, fin = rango
    if inicio not in opciones or fin not in opciones:
        st.session_state[clave] = (opciones[0], opciones[-1])


def _contar_activos(anios_disponibles: list, semanas_disponibles: list) -> int:
    """Cuenta cuantos filtros estan activos (distintos del estado sin filtrar).
    Se lee desde session_state para poder mostrarlo ANTES de renderizar los widgets.
    """
    n = 0
    if st.session_state.get("filtro_subregion"):
        n += 1
    if st.session_state.get("filtro_municipio"):
        n += 1
    rango_anio = st.session_state.get("filtro_anio_rango")
    if anios_disponibles and len(anios_disponibles) >= 2 and rango_anio:
        if rango_anio != (anios_disponibles[0], anios_disponibles[-1]):
            n += 1
    rango_semana = st.session_state.get("filtro_semana_rango")
    if semanas_disponibles and len(semanas_disponibles) >= 2 and rango_semana:
        if rango_semana != (semanas_disponibles[0], semanas_disponibles[-1]):
            n += 1
    if st.session_state.get("filtro_nivel_riesgo"):
        n += 1
    if st.session_state.get("filtro_clasificacion"):
        n += 1
    return n


def mostrar_filtros_globales(
    datos: pd.DataFrame,
    columna_anio: str,
    mapeo_subregion: dict[int, str],
    mapeo_estratificacion_riesgo: dict[int, str],
) -> dict:
    """Dibuja los filtros globales en la barra lateral y devuelve los valores elegidos."""
    datos_con_subregion = _agregar_columna_subregion(datos, mapeo_subregion)
    anios_disponibles = _opciones_de_columna(datos, columna_anio)
    semanas_disponibles = _opciones_de_columna(datos, "semana")

    # Se guardan para que resumen_filtros_activos() pueda distinguir "el anio/
    # semana filtrado es el rango completo por defecto" (nada que mostrar) de
    # "el usuario de verdad achico el rango" (si hay que mostrarlo), sin tener
    # que recibir el dataframe completo en cada grafica que llama esa funcion.
    st.session_state[_CLAVE_ANIOS_DISPONIBLES] = anios_disponibles
    st.session_state[_CLAVE_SEMANAS_DISPONIBLES] = semanas_disponibles
    st.session_state[_CLAVE_MAPEOS] = (mapeo_subregion, mapeo_estratificacion_riesgo)

    # ----- Header: titulo + badge de activos + boton limpiar -----
    n_activos = _contar_activos(anios_disponibles, semanas_disponibles)

    if n_activos > 0:
        st.sidebar.markdown(
            f":material/filter_alt: **Filtros** &nbsp; :blue-badge[{n_activos} activos]"
        )
    else:
        st.sidebar.markdown(":material/filter_alt: **Filtros**")

    if st.sidebar.button(
        "Limpiar filtros",
        icon=":material/filter_alt_off:",
        key="limpiar_filtros",
        width="stretch",
    ):
        for clave in CLAVES_REINICIABLES:
            st.session_state.pop(clave, None)
        st.rerun()

    # ----- Territorio -----
    st.sidebar.caption(":material/map: TERRITORIO")

    subregiones_disponibles = sorted(set(mapeo_subregion.values()))
    subregiones_elegidas = st.sidebar.pills(
        "Subregion",
        subregiones_disponibles,
        selection_mode="multi",
        default=[],
        key="filtro_subregion",
        label_visibility="collapsed",
    )

    if subregiones_elegidas:
        datos_para_municipios = datos_con_subregion[
            datos_con_subregion["subregion"].isin(subregiones_elegidas)
        ]
    else:
        datos_para_municipios = datos_con_subregion
    municipios_disponibles = _opciones_de_columna(datos_para_municipios, "nom_mun_o")
    municipios_elegidos = st.sidebar.multiselect(
        "Municipio",
        municipios_disponibles,
        placeholder="Todos los municipios",
        key="filtro_municipio",
    )

    # ----- Periodo -----
    st.sidebar.caption(":material/calendar_today: PERIODO")

    if len(anios_disponibles) >= 2:
        _corregir_rango("filtro_anio_rango", anios_disponibles)
        rango_anio = st.sidebar.select_slider(
            "Años",
            options=anios_disponibles,
            value=(anios_disponibles[0], anios_disponibles[-1]),
            key="filtro_anio_rango",
        )
        anios_elegidos = [a for a in anios_disponibles if rango_anio[0] <= a <= rango_anio[1]]
    elif len(anios_disponibles) == 1:
        anios_elegidos = anios_disponibles
        st.sidebar.caption(f"Año disponible: {anios_disponibles[0]}")
    else:
        anios_elegidos = []

    if len(semanas_disponibles) >= 2:
        _corregir_rango("filtro_semana_rango", semanas_disponibles)
        rango_semana = st.sidebar.select_slider(
            "Semana epidemiológica",
            options=semanas_disponibles,
            value=(semanas_disponibles[0], semanas_disponibles[-1]),
            format_func=lambda s: f"Sem. {int(s)}",
            key="filtro_semana_rango",
        )
        semanas_elegidas = [s for s in semanas_disponibles if rango_semana[0] <= s <= rango_semana[1]]
    elif len(semanas_disponibles) == 1:
        semanas_elegidas = semanas_disponibles
    else:
        semanas_elegidas = []

    # ----- Estratificacion de riesgo -----
    # Si la patologia no tiene mapeo (dict vacio, ver PathologyPlugin.obtener_mapeo_
    # estratificacion_riesgo), esta seccion no se dibuja: no tiene sentido un filtro
    # sin opciones.
    if mapeo_estratificacion_riesgo:
        st.sidebar.caption(":material/warning: ESTRATIFICACIÓN DE RIESGO")

        datos_con_nivel_riesgo = _agregar_columna_nivel_riesgo(datos, mapeo_estratificacion_riesgo)
        niveles_disponibles = _opciones_de_columna(datos_con_nivel_riesgo, "nivel_riesgo")
        niveles_elegidos = st.sidebar.pills(
            "Estratificación de riesgo",
            niveles_disponibles,
            selection_mode="multi",
            default=[],
            key="filtro_nivel_riesgo",
            label_visibility="collapsed",
        )
    else:
        niveles_elegidos = []

    # ----- Clasificacion del caso -----
    st.sidebar.caption(":material/assignment: CLASIFICACIÓN DEL CASO")

    clasificaciones_disponibles = _opciones_de_columna(datos, "estado_final_de_caso")
    if clasificaciones_disponibles:
        clasificaciones_elegidas = st.sidebar.pills(
            "Clasificacion del caso",
            clasificaciones_disponibles,
            selection_mode="multi",
            default=[],
            key="filtro_clasificacion",
            label_visibility="collapsed",
            format_func=_etiquetar_clasificacion,
        )
    else:
        clasificaciones_elegidas = []

    filtros = {
        columna_anio: anios_elegidos,
        "semana": semanas_elegidas,
        "subregion": subregiones_elegidas,
        "nom_mun_o": municipios_elegidos,
        "nivel_riesgo": niveles_elegidos,
        "estado_final_de_caso": clasificaciones_elegidas,
    }
    st.session_state[CLAVE_FILTROS] = filtros
    return filtros


def aplicar_filtros(
    datos: pd.DataFrame,
    filtros: dict,
    mapeo_subregion: dict[int, str],
    mapeo_estratificacion_riesgo: dict[int, str],
) -> pd.DataFrame:
    """Filtra el dataframe en memoria segun los filtros elegidos. No toca el disco."""
    datos_filtrados = _agregar_columna_subregion(datos, mapeo_subregion)
    datos_filtrados = _agregar_columna_nivel_riesgo(datos_filtrados, mapeo_estratificacion_riesgo)
    for columna, valores_elegidos in filtros.items():
        if not valores_elegidos:
            continue
        if columna not in datos_filtrados.columns:
            continue
        datos_filtrados = datos_filtrados[datos_filtrados[columna].isin(valores_elegidos)]
    return datos_filtrados


# Claves fijas del dict de filtros (ver mostrar_filtros_globales); la unica que
# varia por patologia es la del anio (PathologyPlugin.columna_anio), asi que
# columna_anio_de_filtros() la identifica como "la que sobra" del dict.
_CLAVES_FILTRO_CONOCIDAS = {"semana", "subregion", "nom_mun_o", "nivel_riesgo", "estado_final_de_caso"}

# Clave del selector de patologia de la barra superior (layout.py).
_CLAVE_SELECTOR_PATOLOGIA = "selector_patologia"

LUGAR_POR_DEFECTO = "Magdalena"


def columna_anio_de_filtros(filtros: dict) -> str | None:
    """Nombre de la columna de anio dentro del dict de filtros globales."""
    return next((clave for clave in filtros if clave not in _CLAVES_FILTRO_CONOCIDAS), None)


def anios_del_filtro() -> list[int]:
    """Anios que deja pasar el filtro temporal global ahora mismo. Sin filtro
    acotado, son todos los anios del consolidado cargado."""
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    columna_anio = columna_anio_de_filtros(filtros)
    anios_elegidos = filtros.get(columna_anio) if columna_anio else None
    if anios_elegidos:
        return sorted(int(anio) for anio in anios_elegidos)
    anios_disponibles = st.session_state.get(_CLAVE_ANIOS_DISPONIBLES, [])
    return sorted(int(anio) for anio in anios_disponibles)


def ultimo_anio_del_filtro() -> int | None:
    """Anio de analisis de las graficas que necesitan UN anio concreto (las
    semanales y las comparativas): el ultimo anio del filtro temporal global.
    Reemplaza los antiguos selectores de anio propios de cada grafica."""
    anios = anios_del_filtro()
    if not anios:
        return None
    return anios[-1]


def _formatear_rango(valores: list[int]) -> str:
    valor_minimo = min(valores)
    valor_maximo = max(valores)
    if valor_minimo == valor_maximo:
        return str(valor_minimo)
    return f"{valor_minimo}-{valor_maximo}"


def _describir_lugar(filtros: dict) -> str:
    """Lugar del contexto: municipios si se eligieron (es lo mas especifico),
    si no las subregiones, y si no el departamento completo."""
    municipios = filtros.get("nom_mun_o")
    if municipios:
        nombres = ", ".join(str(municipio).title() for municipio in municipios)
        return nombres

    subregiones = filtros.get("subregion")
    if subregiones:
        if len(subregiones) == 1:
            return f"Subregión {subregiones[0]}"
        return f"Subregiones {', '.join(subregiones)}"

    return LUGAR_POR_DEFECTO


def resumen_filtros_activos(periodo: str | None = None, lugar: str | None = None) -> str:
    """Sufijo de contexto de toda grafica: patologia, lugar y periodo, mas los
    demas filtros que esten acotados. Ej. "Dengue · Magdalena · 2007-2024" o
    "Dengue · Subregión Río · 2022-2024 · Sem. 1-20".

    Nunca devuelve vacio. Es el criterio de la epidemiologia descriptiva (un
    titulo identifica tiempo, lugar y persona, ver regla 1.3 de DESIGN.md): sin
    filtros activos el contexto no desaparece, se vuelve explicito. El lugar por
    defecto es el Magdalena (techo fijo del sistema) y el periodo por defecto es
    el rango completo de anios del consolidado cargado, leido de session_state
    (mostrar_filtros_globales lo deja ahi en cada rerun), nunca escrito a mano:
    cambia cada vez que se carga un anio nuevo.

    periodo reemplaza el periodo del filtro global en las graficas que analizan
    un anio concreto (las semanales y las comparativas): ahi el sufijo declara el
    anio o los dos anios que de verdad se estan comparando, ej. "2024 frente a
    2023", en vez del rango del filtro.

    lugar reemplaza el lugar del filtro global cuando la grafica muestra un
    territorio mas acotado por la seleccion cruzada de su par (ej. la serie de
    Tendencia despues de hacer clic en una subregion del mapa).
    """
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    partes = []

    patologia = st.session_state.get(_CLAVE_SELECTOR_PATOLOGIA)
    if patologia:
        partes.append(str(patologia).capitalize())

    partes.append(lugar or _describir_lugar(filtros))

    if periodo:
        partes.append(periodo)
    else:
        anios = anios_del_filtro()
        if anios:
            partes.append(_formatear_rango(anios))

    semanas_elegidas = filtros.get("semana")
    semanas_disponibles = st.session_state.get(_CLAVE_SEMANAS_DISPONIBLES, [])
    if semanas_elegidas and len(semanas_disponibles) >= 2:
        rango_elegido = (min(semanas_elegidas), max(semanas_elegidas))
        rango_completo = (min(semanas_disponibles), max(semanas_disponibles))
        if rango_elegido != rango_completo:
            semanas_enteras = [int(semana) for semana in semanas_elegidas]
            partes.append(f"Sem. {_formatear_rango(semanas_enteras)}")

    niveles_riesgo = filtros.get("nivel_riesgo")
    if niveles_riesgo:
        partes.append(", ".join(niveles_riesgo))

    clasificaciones = filtros.get("estado_final_de_caso")
    if clasificaciones:
        partes.append(", ".join(_etiquetar_clasificacion(valor) for valor in clasificaciones))

    return " · ".join(partes)


def firma_filtros_globales() -> str:
    """Huella de los filtros globales vigentes. La usa la seleccion cruzada de
    los pares de graficas (seleccion_cruzada.py) para borrarse sola cuando la
    persona cambia cualquier filtro de la barra lateral."""
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    patologia = st.session_state.get(_CLAVE_SELECTOR_PATOLOGIA)
    partes = [str(patologia)]
    for clave in sorted(filtros):
        valores = filtros[clave]
        partes.append(f"{clave}={sorted(str(valor) for valor in valores)}")
    return "|".join(partes)


def aplicar_filtros_sin_periodo(datos: pd.DataFrame) -> pd.DataFrame:
    """Aplica los filtros globales vigentes MENOS el de anio. Lo usan las
    comparativas semanales: el anio de comparacion es el inmediatamente anterior
    en los datos, este o no dentro del filtro temporal, asi que no puede salir
    del dataframe ya filtrado por anio. Usa los mismos mapeos que la barra
    lateral (mostrar_filtros_globales los deja en session_state).
    """
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    columna_anio = columna_anio_de_filtros(filtros)
    filtros_sin_anio = {clave: valores for clave, valores in filtros.items() if clave != columna_anio}
    mapeo_subregion, mapeo_estratificacion_riesgo = st.session_state.get(_CLAVE_MAPEOS, ({}, {}))
    return aplicar_filtros(datos, filtros_sin_anio, mapeo_subregion, mapeo_estratificacion_riesgo)
