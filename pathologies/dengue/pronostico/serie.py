"""Serie semanal departamental de casos de dengue y su recorte por rango."""

import pandas as pd
from epiweeks import Week

from pathologies.dengue.pronostico.configuracion import CODIGOS_CASOS


def construir_serie_semanal_departamental(datos: pd.DataFrame) -> pd.DataFrame:
    """Serie semanal CONTINUA de casos NOTIFICADOS de dengue (210+220,
    probables y confirmados; sin filtrar por la columna confirmados, ver
    configuracion.DEFINICION_SERIE) a nivel Magdalena completo, por semana
    epidemiologica (convencion CDC, inicio domingo, igual que el resto del
    sistema). Reindexa sobre TODAS las semanas del rango (de la primera a la
    ultima con datos), rellenando con 0 las semanas sin casos notificados: los
    modelos necesitan una serie sin huecos, y una semana sin casos es un dato
    real (no informacion faltante), igual que en canal_endemico._tabla_anio_semana.

    Devuelve columnas: fecha_semana (datetime, inicio domingo CDC), ano, semana, casos.
    Vacio si no hay casos en datos.
    """
    casos = datos[datos["cod_eve"].isin(CODIGOS_CASOS)]
    if casos.empty:
        return pd.DataFrame(columns=["fecha_semana", "ano", "semana", "casos"])

    conteo = casos.groupby(["ano", "semana"]).size().reset_index(name="casos")
    conteo["ano"] = conteo["ano"].astype(int)
    conteo["semana"] = conteo["semana"].astype(int)
    conteo["fecha_semana"] = conteo.apply(
        lambda fila: pd.Timestamp(Week(fila["ano"], fila["semana"], system="CDC").startdate()),
        axis=1,
    )
    conteo = conteo.sort_values("fecha_semana").reset_index(drop=True)

    rango_completo = pd.date_range(conteo["fecha_semana"].min(), conteo["fecha_semana"].max(), freq="7D")
    serie = pd.DataFrame({"fecha_semana": rango_completo})
    serie = serie.merge(conteo[["fecha_semana", "casos"]], on="fecha_semana", how="left")
    serie["casos"] = serie["casos"].fillna(0).astype(int)
    serie = agregar_semana_epidemiologica(serie)
    return serie[["fecha_semana", "ano", "semana", "casos"]]


def agregar_semana_epidemiologica(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega ano y semana (CDC) a partir de fecha_semana."""
    df = df.copy()
    df["ano"] = df["fecha_semana"].apply(lambda fecha: Week.fromdate(fecha.date(), system="CDC").year)
    df["semana"] = df["fecha_semana"].apply(lambda fecha: Week.fromdate(fecha.date(), system="CDC").week)
    return df


def fecha_de_semana(anio: int, semana: int) -> pd.Timestamp:
    """Inicio (domingo) de la semana epidemiologica CDC."""
    return pd.Timestamp(Week(anio, semana, system="CDC").startdate())


def recortar_serie(
    serie: pd.DataFrame, desde: pd.Timestamp | None = None, hasta: pd.Timestamp | None = None
) -> pd.DataFrame:
    """Semanas entre desde y hasta (ambas inclusive). None = sin limite por ese lado."""
    recortada = serie
    if desde is not None:
        recortada = recortada[recortada["fecha_semana"] >= desde]
    if hasta is not None:
        recortada = recortada[recortada["fecha_semana"] <= hasta]
    return recortada.sort_values("fecha_semana").reset_index(drop=True)


def describir_rango(serie: pd.DataFrame) -> dict:
    """Rango de una serie, en el formato que guarda el manifest."""
    primera = serie.iloc[0]
    ultima = serie.iloc[-1]
    return {
        "anio_inicio": int(primera["ano"]),
        "semana_inicio": int(primera["semana"]),
        "anio_fin": int(ultima["ano"]),
        "semana_fin": int(ultima["semana"]),
        "fecha_primera_semana": pd.Timestamp(primera["fecha_semana"]).strftime("%Y-%m-%d"),
        "fecha_ultima_semana": pd.Timestamp(ultima["fecha_semana"]).strftime("%Y-%m-%d"),
    }
