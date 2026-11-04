"""Datos y colores para los mapas municipales de tuberculosis.

La semaforizacion usa la incidencia (casos por 100.000 habitantes) del periodo
filtrado. Los cortes son terciles de la incidencia municipal; si los cuantiles
colapsan por exceso de municipios sin casos, se usa la mediana de los valores
positivos para separar el amarillo del rojo. Los municipios sin poblacion DANE
quedan como "Sin dato" (gris).
"""

import unicodedata

import pandas as pd
import streamlit as st

from core.dashboard_base.filtros import CLAVE_FILTROS, limpiar_municipio
from core.geografia import obtener_geojson_municipios_magdalena
from pathologies.tuberculosis.geografia import obtener_mapeo_subregion
from pathologies.tuberculosis.poblacion import obtener_poblacion_por_municipio_anio

COLOR_SELECCIONADO = "#1b3a6b"
COLORES_SEMAFORO = {
    "Baja": "#2e7d32",
    "Media": "#f9a825",
    "Alta": "#c62828",
    "Sin dato": "#d9d9d9",
    "Seleccionado": COLOR_SELECCIONADO,
}
ORDEN_SEMAFORO = ["Baja", "Media", "Alta", "Sin dato", "Seleccionado"]

# Keys de los tres mapas de TB. Al volver a todos los municipios se renuevan
# todas para que ninguna seleccion vieja vuelva a aplicar el filtro.
CLAVES_MAPAS_TB = ("tb_mapa_situacion", "tb_mapa_tendencia", "tb_mapa_mortalidad")


def _normalizar(texto) -> str:
    """Minusculas y sin tildes, para comparar nombres del GeoJSON con los del dato."""
    sin_tildes = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode("ascii")
    return sin_tildes.strip().lower()


def _titulo_municipio(nombre) -> str:
    """Titulo con conectores en minuscula: 'Cerro de San Antonio'."""
    conectores = {"de", "del", "la", "las", "los", "y"}
    palabras = str(nombre).lower().split()
    return " ".join(
        palabra if indice > 0 and palabra in conectores else palabra.capitalize()
        for indice, palabra in enumerate(palabras)
    )


def _municipios_base() -> pd.DataFrame:
    """Codigo y nombre de los 30 municipios, tomados del GeoJSON."""
    geojson = obtener_geojson_municipios_magdalena()
    filas = [
        {
            "cod_mun_completo": int(feature["properties"]["mpio_cdpmp"]),
            "municipio": _titulo_municipio(feature["properties"]["mpio_cnmbr"]),
        }
        for feature in geojson["features"]
    ]
    base = pd.DataFrame(filas)
    base["municipio_normalizado"] = base["municipio"].map(_normalizar)
    base["subregion"] = base["cod_mun_completo"].map(obtener_mapeo_subregion())
    return base


def _municipios_en_alcance(casos: pd.DataFrame) -> pd.DataFrame:
    """Municipios que respetan los filtros globales de subregion o municipio."""
    base = _municipios_base()
    filtros = st.session_state.get(CLAVE_FILTROS, {})
    municipios = filtros.get("nom_mun_o") or []
    subregiones = filtros.get("subregion") or []

    if municipios:
        seleccionados = {_normalizar(municipio) for municipio in municipios}
        if "nom_mun_o" in casos.columns:
            nombres_dato = (
                casos.dropna(subset=["cod_mun_completo", "nom_mun_o"])
                .drop_duplicates("cod_mun_completo")
                .set_index("cod_mun_completo")["nom_mun_o"]
                .to_dict()
            )
            codigos = {
                codigo for codigo, nombre in nombres_dato.items()
                if _normalizar(nombre) in seleccionados
            }
            if codigos:
                return base[base["cod_mun_completo"].isin(codigos)]
        return base[base["municipio_normalizado"].isin(seleccionados)]
    if subregiones:
        return base[base["subregion"].isin(subregiones)]
    return base


def _preferir_nombres_dato(base: pd.DataFrame, casos: pd.DataFrame) -> pd.DataFrame:
    """Usa el nombre oficial del dato cuando existe (ej. Chibolo, no Chivolo)."""
    if "nom_mun_o" not in casos.columns:
        return base

    nombres = (
        casos.dropna(subset=["cod_mun_completo", "nom_mun_o"])
        .drop_duplicates("cod_mun_completo")
        .set_index("cod_mun_completo")["nom_mun_o"]
    )
    base["municipio"] = base["cod_mun_completo"].map(nombres).fillna(base["municipio"])
    return base


def _poblacion_por_municipio(anios: list[int]) -> pd.DataFrame:
    if not anios:
        return pd.DataFrame(columns=["cod_mun_completo", "poblacion"])

    poblacion = obtener_poblacion_por_municipio_anio()
    poblacion = poblacion[poblacion["ano"].isin(anios)]
    return poblacion.groupby("cod_mun_completo", as_index=False)["poblacion"].sum()


def _anios_de(casos: pd.DataFrame) -> list[int]:
    if "ano" not in casos.columns:
        return []
    return sorted(int(anio) for anio in casos["ano"].dropna().unique())


def _clasificar_semaforo(valores: pd.Series) -> pd.Series:
    validos = valores.dropna()
    if validos.empty:
        return pd.Series("Sin dato", index=valores.index, dtype="object")

    if validos.max() == 0:
        return pd.Series("Baja", index=valores.index, dtype="object")

    p33 = validos.quantile(1 / 3)
    p66 = validos.quantile(2 / 3)

    # Con muchos municipios en cero, los dos cuantiles pueden coincidir. En ese
    # caso el amarillo/rojo se separa con la mediana de los valores positivos.
    if p33 == p66:
        p33 = 0
        p66 = validos[validos > 0].median()

    def clasificar(valor) -> str:
        if pd.isna(valor):
            return "Sin dato"
        if valor <= p33:
            return "Baja"
        if valor <= p66:
            return "Media"
        return "Alta"

    return valores.apply(clasificar)


def _agregar_poblacion_y_semaforo(datos: pd.DataFrame, columna_tasa: str, anios: list[int]) -> pd.DataFrame:
    datos = datos.merge(_poblacion_por_municipio(anios), on="cod_mun_completo", how="left")
    datos[columna_tasa] = datos["eventos"] / datos["poblacion"] * 100_000
    datos["semaforo"] = _clasificar_semaforo(datos[columna_tasa])

    # Con un solo municipio no hay comparacion posible: se pinta con el color
    # institucional y se oculta la leyenda del semaforo en la vista.
    if len(st.session_state.get("filtro_municipio", [])) == 1:
        datos["semaforo"] = "Seleccionado"

    datos["cod_mun_str"] = datos["cod_mun_completo"].astype(str)
    return datos


def datos_mapa_casos(casos: pd.DataFrame) -> pd.DataFrame:
    """Incidencia municipal de casos para el mapa, incluyendo municipios sin casos."""
    base = _municipios_en_alcance(casos)
    base = _preferir_nombres_dato(base, casos)
    casos_por_municipio = casos.groupby("cod_mun_completo").size().reset_index(name="eventos")
    base = base.merge(casos_por_municipio, on="cod_mun_completo", how="left")
    base["eventos"] = base["eventos"].fillna(0).astype(int)
    base["casos"] = base["eventos"]
    return _agregar_poblacion_y_semaforo(base, "incidencia", _anios_de(casos))


def datos_mapa_muertes(casos: pd.DataFrame, muertes: pd.DataFrame) -> pd.DataFrame:
    """Mortalidad municipal para el mapa, incluyendo municipios sin muertes."""
    base = _municipios_en_alcance(casos)
    base = _preferir_nombres_dato(base, casos)

    casos_por_municipio = casos.groupby("cod_mun_completo").size().reset_index(name="casos")
    muertes_por_municipio = muertes.groupby("cod_mun_completo").size().reset_index(name="eventos")

    base = base.merge(casos_por_municipio, on="cod_mun_completo", how="left")
    base = base.merge(muertes_por_municipio, on="cod_mun_completo", how="left")
    base["casos"] = base["casos"].fillna(0).astype(int)
    base["eventos"] = base["eventos"].fillna(0).astype(int)
    base["muertes"] = base["eventos"]
    return _agregar_poblacion_y_semaforo(base, "tasa_mortalidad", _anios_de(casos))


def clave_mapa(clave_base: str) -> str:
    """Key renovable para st.plotly_chart.

    Al volver a todos los municipios se incrementa el contador para que el mapa
    se renderice con una key nueva y no conserve la seleccion anterior.
    """
    contador = st.session_state.get(f"{clave_base}_contador", 0)
    return f"{clave_base}_{contador}"


def boton_volver_municipio(clave_base: str) -> None:
    """Boton para quitar el filtro de municipio cuando hay exactamente uno."""
    if len(st.session_state.get("filtro_municipio", [])) != 1:
        return

    if st.button(
        "Volver",
        icon=":material/arrow_back:",
        help="Quitar el filtro de municipio y volver a todos los municipios",
        key=f"volver_{clave_base}",
    ):
        limpiar_municipio()
        for clave in CLAVES_MAPAS_TB:
            contador_key = f"{clave}_contador"
            st.session_state[contador_key] = st.session_state.get(contador_key, 0) + 1
        st.rerun()


def municipio_desde_seleccion(resultado, mapa: pd.DataFrame) -> str | None:
    """Nombre del municipio clickeado en un st.plotly_chart, o None si no hay clic."""
    try:
        puntos = resultado.selection.points
    except AttributeError:
        return None
    if not puntos:
        return None

    codigo = str(puntos[0].get("location", ""))
    fila = mapa.loc[mapa["cod_mun_str"] == codigo]
    if fila.empty:
        return None
    return str(fila.iloc[0]["municipio"])


def resumen_semaforo(datos: pd.DataFrame, columna: str, unidad: str) -> str:
    """Texto con los cortes usados, para mostrarlo debajo del mapa."""
    validos = datos[columna].dropna()
    if validos.empty:
        return "Sin población DANE disponible para el período filtrado."

    if validos.max() == 0:
        return f"Semáforo: todos los municipios tienen {unidad} igual a 0."

    p33 = validos.quantile(1 / 3)
    p66 = validos.quantile(2 / 3)
    if p33 == p66:
        p33 = 0
        p66 = validos[validos > 0].median()

    return f"Semáforo: Baja ≤ {p33:.1f}; Media ≤ {p66:.1f}; Alta > {p66:.1f} {unidad}."
