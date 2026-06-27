"""Las 5 pestanas del dashboard de dengue: Tendencia, Situacion, Sociodemografica,
Morbilidad y Mortalidad. Cada una es por ahora un esqueleto (estado vacio) hasta que
se construyan sus graficos; ver CLAUDE.md para el detalle de cada pestana.
"""

import pandas as pd
import streamlit as st


def _mostrar_pendiente(mensaje: str) -> None:
    st.info(f":material/construction: {mensaje}")


def mostrar_tendencia(datos: pd.DataFrame) -> None:
    _mostrar_pendiente(
        "Esta pestana mostrara la serie historica anual, casos semanales, comparacion "
        "contra el anio anterior y el mapa coropletico por subregion. Se construye pronto."
    )


def mostrar_situacion(datos: pd.DataFrame) -> None:
    _mostrar_pendiente(
        "Esta pestana mostrara los KPIs (incidencia, mortalidad, letalidad), el canal "
        "endemico y el pronostico de corto plazo. Se construye pronto."
    )


def mostrar_sociodemografica(datos: pd.DataFrame) -> None:
    _mostrar_pendiente(
        "Esta pestana mostrara las distribuciones por sexo, edad, etnia, regimen, EPS, "
        "UPGD, estrato, area y ocupacion. Se construye pronto."
    )


def mostrar_morbilidad(datos: pd.DataFrame) -> None:
    _mostrar_pendiente(
        "Esta pestana mostrara la fuente de notificacion, clasificacion del caso y las "
        "tasas de hospitalizacion e incidencia por subregion. Se construye pronto."
    )


def mostrar_mortalidad(datos: pd.DataFrame) -> None:
    _mostrar_pendiente(
        "Esta pestana mostrara las muertes por semana, sexo, edad, EPS y las tasas de "
        "mortalidad y letalidad por subregion, con causas CIE-10. Se construye pronto."
    )


def obtener_vistas_dengue() -> list[tuple[str, callable]]:
    """Nombre de cada pestana y su funcion de render, en el orden en que se muestran."""
    return [
        ("Tendencia", mostrar_tendencia),
        ("Situacion", mostrar_situacion),
        ("Sociodemografica", mostrar_sociodemografica),
        ("Morbilidad", mostrar_morbilidad),
        ("Mortalidad", mostrar_mortalidad),
    ]
