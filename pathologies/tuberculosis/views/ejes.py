"""Configuracion comun de los ejes X de las graficas de tuberculosis.

La idea es que el eje X muestre todos los valores posibles cuando el rango es
manejable (anios, semanas, conteos pequenos). Si el rango es muy grande, se
limita el numero de marcas para que las etiquetas no se encimen.
"""

import numpy as np
import streamlit as st


def _valores_x(fig) -> list:
    valores = []
    for traza in fig.data:
        x = getattr(traza, "x", None)
        if x is not None:
            valores.extend(list(x))
    return valores


def configurar_eje_x(fig):
    """Muestra todas las marcas X cuando el rango es razonable."""
    valores = _valores_x(fig)
    if not valores:
        return fig

    numericos = []
    for valor in valores:
        if valor is None:
            continue
        try:
            numero = float(valor)
        except (TypeError, ValueError):
            numericos = []
            break
        if not np.isnan(numero):
            numericos.append(numero)

    if numericos:
        numericos = sorted(set(numericos))

        # Piramides: el lado masculino se dibuja con valores negativos, pero
        # las marcas del eje deben leerse como cantidades positivas.
        if numericos[0] < 0 < numericos[-1]:
            max_abs = max(abs(numericos[0]), abs(numericos[-1]))
            paso = max(1, int(max_abs // 4))
            limite = paso * 4
            tickvals = [-limite, -3 * paso, -2 * paso, -paso, 0, paso, 2 * paso, 3 * paso, limite]
            fig.update_xaxes(
                range=[-max(max_abs * 1.1, limite), max(max_abs * 1.1, limite)],
                tickvals=tickvals,
                ticktext=[str(abs(valor)) for valor in tickvals],
                tickangle=0,
                tickfont=dict(size=9),
                automargin=True,
            )
            return fig

        rango = numericos[-1] - numericos[0]
        todos_enteros = all(numero.is_integer() for numero in numericos)
        horizontal = any(getattr(traza, "orientation", None) == "h" for traza in fig.data)
        angulo = 0 if horizontal else -45
        limite_marcas = 30 if horizontal else 60

        if todos_enteros and rango <= limite_marcas:
            fig.update_xaxes(
                tickmode="linear",
                tick0=numericos[0],
                dtick=1,
                tickangle=angulo,
                tickfont=dict(size=9),
                automargin=True,
            )
        else:
            fig.update_xaxes(
                nticks=20,
                tickangle=angulo,
                tickfont=dict(size=9),
                automargin=True,
            )
    else:
        categorias = list(dict.fromkeys(str(valor) for valor in valores if valor is not None))
        fig.update_xaxes(
            type="category",
            categoryorder="array",
            categoryarray=categorias,
            tickangle=-45,
            tickfont=dict(size=9),
            automargin=True,
        )

    return fig


def mostrar_grafica_tb(fig, **kwargs):
    """Aplica el eje X comun y renderiza la grafica."""
    configurar_eje_x(fig)
    return st.plotly_chart(fig, **kwargs)
