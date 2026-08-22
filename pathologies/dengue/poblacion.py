"""Poblacion DANE por municipio y anio: denominador de incidencia y mortalidad
en indicators.py. Poblacion en riesgo = poblacion total (area geografica
"Total", cabecera + centros poblados y rural disperso) de los municipios del
Magdalena clasificados con algun nivel de transmision de dengue segun la
estratificacion de riesgo (ver estratificacion.py).

Los archivos de poblacion son intercambiables: viven en config/referencias/
nombrados poblacionDane-{anio_inicio}-{anio_fin}.xlsx (convencion de nombre de
las publicaciones del DANE). Cuando el DANE publique una proyeccion nueva, se
agrega el archivo con ese nombre y el sistema lo toma solo, sin tocar codigo.
La hoja y la fila de encabezado varian entre publicaciones del DANE, por eso
se detectan buscando la columna "DP" en vez de asumir una posicion fija.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

from pathologies.dengue.estratificacion import calcular_estratificacion

RUTA_REFERENCIAS = Path(__file__).parent / "config" / "referencias"

COD_DPTO_MAGDALENA = 47

# Niveles del lineamiento MSPS/INS que significan que el municipio NO aporta
# a la poblacion en riesgo de dengue (no hay transmision o no hay vector).
_NIVELES_SIN_TRANSMISION = {
    "Sin riesgo",
    "Sin transmisión sin vector",
    "Sin transmisión con vector",
}

# Claves de session_state donde queda la ultima estratificacion calculada
# esta sesion (obtener_mapeo_estratificacion_riesgo las escribe;
# _obtener_municipios_con_transmision y obtener_poblacion_por_municipio_anio
# las leen). No usa @st.cache_data en las funciones que dependen de estas
# claves: mezclar cache-por-argumentos con una lectura de session_state haria
# que el cache no se entere cuando session_state cambia (ej. el usuario pulsa
# "Actualizar"), y quedaria desactualizado en silencio.
_CLAVE_ESTRATIFICACION_SESION = "dengue_estratificacion_actual"
_CLAVE_POBLACION_ASIGNADA_SESION = "dengue_poblacion_asignada_actual"


def _leer_archivo_poblacion(ruta: Path) -> pd.DataFrame:
    """Lee un archivo poblacionDane-*.xlsx: busca la hoja y fila de encabezado
    por la columna "DP" (varian entre publicaciones del DANE) y normaliza
    columnas a cod_dpto, cod_mun_completo, ano, area_geografica, poblacion.

    engine="calamine": el lector por defecto de pandas (openpyxl) tarda ~4-6s en
    este archivo porque trae poblacion de TODO el pais (80k+ filas) antes de
    filtrar a Magdalena; calamine (el mismo lector rapido que ya usa
    core/ingestion/procesador.py para las cargas SIVIGILA) lo baja a ~1-2s.
    """
    libro = pd.ExcelFile(ruta, engine="calamine")
    for nombre_hoja in libro.sheet_names:
        vista_previa = pd.read_excel(libro, sheet_name=nombre_hoja, header=None, nrows=30)
        coincidencias = vista_previa[vista_previa.iloc[:, 0].astype(str).str.strip() == "DP"]
        if coincidencias.empty:
            continue
        datos = pd.read_excel(libro, sheet_name=nombre_hoja, header=coincidencias.index[0])
        datos.columns = [str(columna).strip() for columna in datos.columns]
        columna_poblacion = "TOTAL" if "TOTAL" in datos.columns else "Población"
        datos = datos.rename(columns={
            "DP": "cod_dpto",
            "MPIO": "cod_mun_completo",
            "AÑO": "ano",
            "ÁREA GEOGRÁFICA": "area_geografica",
            columna_poblacion: "poblacion",
        })
        return datos[["cod_dpto", "cod_mun_completo", "ano", "area_geografica", "poblacion"]]
    raise ValueError(f"No se encontro la fila de encabezado (columna DP) en {ruta.name}")


@st.cache_data
def _calcular_estratificacion_cacheada(datos: pd.DataFrame) -> pd.DataFrame:
    """El calculo en si (calcular_estratificacion) es caro y es el mismo para
    cualquier sesion que tenga cargado el mismo consolidado, asi que se
    cachea a nivel de PROCESO con st.cache_data (compartida entre todas las
    sesiones/usuarios). La escritura a session_state NO puede vivir aca
    adentro (ver obtener_mapeo_estratificacion_riesgo): si estuviera aca, una
    sesion nueva que le pegue a un cache-hit de OTRA sesion nunca ejecutaria
    este cuerpo, y se quedaria sin el dato en su propio session_state.
    """
    return calcular_estratificacion(datos)


def obtener_mapeo_estratificacion_riesgo(datos: pd.DataFrame) -> dict[int, str]:
    """Mapeo de cod_municipio (DIVIPOLA, coincide con cod_mun_completo) a
    nivel_riesgo, para el filtro global "Estratificacion de riesgo"
    (core/dashboard_base/filtros.py). A diferencia de poblacion en riesgo, aqui
    se devuelven TODOS los niveles (incluidos "sin riesgo"/"sin transmision"):
    es un filtro, la persona debe poder ver y elegir cualquier categoria.

    datos: el consolidado COMPLETO de dengue (layout.py lo llama con
    datos_completos, antes de aplicar los filtros globales).

    SIN @st.cache_data propio, a proposito: layout.py la llama una vez en
    CADA rerun, y siempre debe dejar su resultado en el session_state de ESA
    sesion (ver abajo). Si esta funcion tuviera @st.cache_data (que es una
    cache de PROCESO, compartida entre todas las sesiones/usuarios), una
    sesion nueva que pida el mismo "datos" que ya calculo otra sesion
    obtendria un cache-hit y esta funcion nunca se ejecutaria, dejando esa
    sesion nueva sin nada en su session_state: eso es exactamente el bug de
    "sin poblacion DANE disponible" que se veia con el segundo usuario o al
    refrescar. Lo caro (calcular_estratificacion) si sigue cacheado, en
    _calcular_estratificacion_cacheada.

    Ademas de devolver el mapeo, deja en session_state tanto el nivel_riesgo
    como la poblacion_asignada por municipio (Tabla 5 del lineamiento: Total,
    Cabecera Municipal, o Centros Poblados y Rural Disperso, ver
    estratificacion.py): es la unica forma en que _obtener_municipios_con_
    transmision y obtener_poblacion_por_municipio_anio los consultan, sin
    tener que recibir "datos" como argumento en cada una (ver
    _CLAVE_ESTRATIFICACION_SESION / _CLAVE_POBLACION_ASIGNADA_SESION).
    """
    estratificacion = _calcular_estratificacion_cacheada(datos)
    if estratificacion.empty:
        mapeo: dict[int, str] = {}
        mapeo_poblacion_asignada: dict[int, str] = {}
    else:
        mapeo = estratificacion.set_index("cod_municipio")["nivel_riesgo"].to_dict()
        mapeo_poblacion_asignada = estratificacion.set_index("cod_municipio")["poblacion_asignada"].to_dict()
    st.session_state[_CLAVE_ESTRATIFICACION_SESION] = mapeo
    st.session_state[_CLAVE_POBLACION_ASIGNADA_SESION] = mapeo_poblacion_asignada
    return mapeo


def _obtener_municipios_con_transmision() -> set[int]:
    """Municipios del Magdalena con algun nivel de transmision de dengue,
    segun la estratificacion calculada esta sesion (ver
    obtener_mapeo_estratificacion_riesgo, que layout.py llama una vez por
    rerun con el consolidado completo, antes de que cualquier pestana se
    dibuje). Poblacion en riesgo solo cuenta estos municipios: los marcados
    sin riesgo o sin transmision no aportan al denominador aunque tengan
    poblacion.

    Vacio si la estratificacion todavia no se pudo calcular (ver
    estratificacion.ANIOS_REQUERIDOS: hacen falta 6 anios de historico). Eso
    vacia tambien la poblacion en riesgo mas abajo, y calcular_indicadores()
    ya sabe mostrar "no disponible" cuando no hay poblacion, nunca cero.
    """
    mapeo = st.session_state.get(_CLAVE_ESTRATIFICACION_SESION, {})
    return {
        cod_municipio
        for cod_municipio, nivel_riesgo in mapeo.items()
        if nivel_riesgo not in _NIVELES_SIN_TRANSMISION
    }


@st.cache_data
def _leer_poblacion_magdalena_todas_areas() -> pd.DataFrame:
    """Consolida los archivos poblacionDane-*.xlsx, acotados al Magdalena, SIN
    colapsar por area geografica (deja Cabecera Municipal, Centros Poblados y
    Rural Disperso, y Total tal como los publica el DANE) y SIN filtrar por
    municipios con transmision: eso lo hacen obtener_poblacion_por_municipio_
    anio y obtener_poblacion_por_zona_municipio_anio, porque la transmision
    sale de session_state (ver _obtener_municipios_con_transmision) y esta
    funcion debe quedar cacheable solo por los archivos Excel, que son
    estaticos. Base comun de ambas.
    """
    archivos = sorted(RUTA_REFERENCIAS.glob("poblacionDane-*.xlsx"))
    if not archivos:
        raise FileNotFoundError(
            "No se encontro ningun archivo poblacionDane-*.xlsx en "
            f"{RUTA_REFERENCIAS}. La poblacion DANE es necesaria para "
            "incidencia y mortalidad."
        )

    piezas = [_leer_archivo_poblacion(archivo) for archivo in archivos]
    poblacion = pd.concat(piezas, ignore_index=True)

    poblacion = poblacion[poblacion["cod_dpto"].astype(str).str.strip() == str(COD_DPTO_MAGDALENA)]
    poblacion = poblacion.dropna(subset=["cod_mun_completo", "ano", "poblacion", "area_geografica"])
    poblacion["cod_mun_completo"] = poblacion["cod_mun_completo"].astype(int)
    poblacion["ano"] = poblacion["ano"].astype(int)
    poblacion["poblacion"] = poblacion["poblacion"].astype(int)
    poblacion["area_geografica"] = poblacion["area_geografica"].astype(str).str.strip()

    # Si dos archivos se solapan en el mismo anio+municipio+area, se prioriza el
    # ultimo leido: sorted() ya ordena los archivos por nombre, y el nombre
    # poblacionDane-inicio-fin hace que el rango mas reciente quede al final.
    poblacion = poblacion.drop_duplicates(subset=["cod_mun_completo", "ano", "area_geografica"], keep="last")

    return poblacion.reset_index(drop=True)


def obtener_poblacion_por_municipio_anio() -> pd.DataFrame:
    """Poblacion en riesgo del Magdalena por municipio y anio: solo de
    municipios con transmision de dengue, y con la poblacion DANE que le
    corresponde a cada uno segun donde tuvo casos (Tabla 5 del lineamiento,
    ver estratificacion._calcular_poblacion_asignada): Total si tuvo casos en
    cabecera y en zona rural, o solo la poblacion de la zona donde realmente
    tuvo casos. Antes se usaba "Total" para todos por igual; esto es mas
    preciso cuando un municipio solo tiene transmision confirmada en una de
    las dos zonas.

    Sin @st.cache_data propio a proposito: filtra por municipios_con_
    transmision y poblacion_asignada, que salen de session_state (ver
    _obtener_municipios_con_transmision) y pueden cambiar entre reruns sin que
    cambien los argumentos de esta funcion (no tiene ninguno). Lo caro (leer y
    parsear los Excel de poblacion) ya esta cacheado en
    _leer_poblacion_magdalena_todas_areas; filtrar sobre ese resultado es
    barato, asi que no hace falta cachear esto tambien.

    Devuelve columnas: cod_mun_completo, ano, poblacion.
    """
    municipios_con_transmision = _obtener_municipios_con_transmision()
    poblacion_asignada = st.session_state.get(_CLAVE_POBLACION_ASIGNADA_SESION, {})

    poblacion = _leer_poblacion_magdalena_todas_areas()
    poblacion = poblacion[poblacion["cod_mun_completo"].isin(municipios_con_transmision)].copy()
    poblacion["area_asignada"] = poblacion["cod_mun_completo"].map(poblacion_asignada).fillna("Total")
    poblacion = poblacion[poblacion["area_geografica"] == poblacion["area_asignada"]]
    return poblacion[["cod_mun_completo", "ano", "poblacion"]].reset_index(drop=True)


_AREA_DANE_CABECERA = "Cabecera Municipal"
_AREA_DANE_RESTO = "Centros Poblados y Rural Disperso"

# El dato SIVIGILA distingue 3 zonas de ocurrencia (cabecera municipal, centro
# poblado, rural disperso: ver _ZONA_AREA_MAP en tendencia.py) pero el DANE
# solo publica 2 categorias no-Total (cabecera vs el resto combinado); centro
# poblado y rural disperso comparten esa misma poblacion.
ZONA_A_AREA_DANE = {
    "Cabecera municipal": _AREA_DANE_CABECERA,
    "Centro poblado": _AREA_DANE_RESTO,
    "Rural disperso": _AREA_DANE_RESTO,
}


def obtener_poblacion_por_zona_municipio_anio() -> pd.DataFrame:
    """Poblacion DANE por municipio, anio y zona (Cabecera Municipal vs
    Centros Poblados y Rural Disperso), sin colapsar a Total. Denominador de
    calcular_tasa_por_zona_municipio (mapa, 3er nivel: zonas dentro de un
    municipio). Sin @st.cache_data propio: mismo motivo que
    obtener_poblacion_por_municipio_anio.

    Devuelve columnas: cod_mun_completo, ano, area_geografica, poblacion.
    """
    municipios_con_transmision = _obtener_municipios_con_transmision()
    poblacion = _leer_poblacion_magdalena_todas_areas()
    poblacion = poblacion[poblacion["cod_mun_completo"].isin(municipios_con_transmision)]
    poblacion = poblacion[poblacion["area_geografica"] != "Total"]
    return poblacion[["cod_mun_completo", "ano", "area_geografica", "poblacion"]].reset_index(drop=True)


def obtener_poblacion_en_riesgo_departamental(anios_en_alcance: list[int]) -> float | None:
    """Poblacion en riesgo del Magdalena completo (suma de los municipios con
    transmision) para los anios dados. Util para la linea de referencia
    departamental en graficas por subregion (ej. 5.7 en mortalidad.py). None si
    falta poblacion para alguno de esos anios, nunca un numero incompleto.

    OJO: pese al nombre "departamental", NO es la poblacion total de los 30
    municipios: sigue siendo poblacion en riesgo (excluye municipios sin
    transmision, usa la Tabla 5 de asignacion por zona). Para la poblacion total
    sin filtrar (denominador de la pestana Pronostico) usar
    obtener_poblacion_total_departamental.
    """
    if not anios_en_alcance:
        return None
    poblacion_municipio = obtener_poblacion_por_municipio_anio()
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]
    anios_con_poblacion = set(poblacion_periodo["ano"].unique())
    if not set(anios_en_alcance).issubset(anios_con_poblacion):
        return None
    return float(poblacion_periodo["poblacion"].sum())


def obtener_poblacion_total_departamental(anios_en_alcance: list[int]) -> float | None:
    """Poblacion TOTAL del Magdalena (los 30 municipios, area geografica "Total"
    del DANE), SIN excluir por estratificacion de riesgo. Denominador de la tasa
    (casos x100.000 hab.) de la pestana Pronostico: el pronostico es una serie
    departamental unica (no filtrable por municipio/subregion), asi que su tasa
    usa poblacion sin ajustar, no la poblacion en riesgo del resto del dashboard
    (ver CLAUDE.md, seccion de la pestana Pronostico). None si falta poblacion
    para alguno de los anios pedidos, nunca un numero incompleto.
    """
    if not anios_en_alcance:
        return None
    poblacion = _leer_poblacion_magdalena_todas_areas()
    poblacion = poblacion[poblacion["area_geografica"] == "Total"]
    poblacion_periodo = poblacion[poblacion["ano"].isin(anios_en_alcance)]
    anios_con_poblacion = set(poblacion_periodo["ano"].unique())
    if not set(anios_en_alcance).issubset(anios_con_poblacion):
        return None
    return float(poblacion_periodo["poblacion"].sum())


def obtener_poblacion_por_subregion_anio(mapeo_subregion: dict[int, str]) -> pd.DataFrame:
    """Poblacion en riesgo agregada a nivel subregion (suma de sus municipios) por
    anio. Reutiliza obtener_poblacion_por_municipio_anio(); es la base de las tasas
    por subregion en las vistas (tendencia, morbilidad, mortalidad).

    Devuelve columnas: subregion, ano, poblacion.
    """
    poblacion_municipio = obtener_poblacion_por_municipio_anio().copy()
    poblacion_municipio["subregion"] = poblacion_municipio["cod_mun_completo"].map(mapeo_subregion)
    poblacion_municipio = poblacion_municipio.dropna(subset=["subregion"])
    return poblacion_municipio.groupby(["subregion", "ano"], as_index=False)["poblacion"].sum()


def calcular_tasa_por_subregion(
    eventos: pd.DataFrame,
    anios_en_alcance: list[int],
    mapeo_subregion: dict[int, str],
) -> dict[str, float | None]:
    """Tasa por 100.000 hab. de cada subregion del Magdalena para el conjunto de
    eventos dado (casos o muertes, ya filtrados, con columna "subregion").

    anios_en_alcance son los anios cuya poblacion se suma como denominador
    (persona-anios si son varios, misma logica que indicators.py._poblacion_en_
    riesgo: no se usa un solo anio de referencia si el filtro cubre un rango).
    Si falta poblacion para alguno de los anios pedidos en una subregion, esa
    subregion queda en None (no disponible), nunca en cero: el sistema no
    publica numeros falsos.

    Devuelve un dict {subregion: tasa_o_None}, con TODAS las subregiones del
    mapeo (incluidas las que no tuvieron ningun evento: tasa 0.0, no None).
    """
    poblacion_subregion = obtener_poblacion_por_subregion_anio(mapeo_subregion)
    poblacion_periodo = poblacion_subregion[poblacion_subregion["ano"].isin(anios_en_alcance)]

    resultado: dict[str, float | None] = {}
    for subregion in sorted(set(mapeo_subregion.values())):
        if not anios_en_alcance:
            resultado[subregion] = None
            continue
        poblacion_sub = poblacion_periodo[poblacion_periodo["subregion"] == subregion]
        anios_con_poblacion = set(poblacion_sub["ano"].unique())
        if not set(anios_en_alcance).issubset(anios_con_poblacion):
            resultado[subregion] = None
            continue
        poblacion_total = poblacion_sub["poblacion"].sum()
        n_eventos = int((eventos["subregion"] == subregion).sum())
        resultado[subregion] = n_eventos / poblacion_total * 100_000

    return resultado


def calcular_tasa_por_municipio(
    eventos: pd.DataFrame,
    anios_en_alcance: list[int],
    municipios: list[int],
) -> dict[int, float | None]:
    """Tasa por 100.000 hab. de cada municipio dado, para el conjunto de eventos
    (casos o muertes, ya filtrados, con columna cod_mun_completo). Misma logica
    de persona-anios y "None si falta poblacion" que calcular_tasa_por_subregion,
    pero a escala municipio.

    Devuelve un dict {cod_mun_completo: tasa_o_None}.
    """
    poblacion_municipio = obtener_poblacion_por_municipio_anio()
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]

    resultado: dict[int, float | None] = {}
    for municipio in municipios:
        if not anios_en_alcance:
            resultado[municipio] = None
            continue
        poblacion_mun = poblacion_periodo[poblacion_periodo["cod_mun_completo"] == municipio]
        anios_con_poblacion = set(poblacion_mun["ano"].unique())
        if not set(anios_en_alcance).issubset(anios_con_poblacion):
            resultado[municipio] = None
            continue
        poblacion_total = poblacion_mun["poblacion"].sum()
        n_eventos = int((eventos["cod_mun_completo"] == municipio).sum())
        resultado[municipio] = n_eventos / poblacion_total * 100_000

    return resultado


def calcular_tasa_por_zona_municipio(
    casos_por_zona: dict[str, int],
    codigo_municipio: int,
    anios_en_alcance: list[int],
) -> dict[str, float | None]:
    """Tasa por 100.000 hab. de cada zona (cabecera municipal, centro poblado,
    rural disperso) DENTRO de un solo municipio (mapa, 3er nivel de detalle).

    Centro poblado y rural disperso comparten denominador porque el DANE no
    los separa (ver ZONA_A_AREA_DANE / obtener_poblacion_por_zona_municipio_
    anio); cabecera usa su propio denominador. None si falta poblacion DANE del
    municipio para alguno de los anios pedidos, nunca en cero.
    """
    if not anios_en_alcance:
        return {zona: None for zona in ZONA_A_AREA_DANE}

    poblacion = obtener_poblacion_por_zona_municipio_anio()
    poblacion_municipio = poblacion[poblacion["cod_mun_completo"] == codigo_municipio]
    poblacion_periodo = poblacion_municipio[poblacion_municipio["ano"].isin(anios_en_alcance)]

    resultado: dict[str, float | None] = {}
    for zona, area_dane in ZONA_A_AREA_DANE.items():
        poblacion_area = poblacion_periodo[poblacion_periodo["area_geografica"] == area_dane]
        anios_con_poblacion = set(poblacion_area["ano"].unique())
        if not set(anios_en_alcance).issubset(anios_con_poblacion):
            resultado[zona] = None
            continue
        poblacion_total = poblacion_area["poblacion"].sum()
        n_casos = casos_por_zona.get(zona, 0)
        resultado[zona] = n_casos / poblacion_total * 100_000

    return resultado
