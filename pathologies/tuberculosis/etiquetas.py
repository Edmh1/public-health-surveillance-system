"""Etiquetas visibles de los eventos de tuberculosis.

Los codigos SIVIGILA (810, 820, 825) se usan solo en la capa de datos. En los
titulos y leyendas se muestran nombres legibles y se ajustan a los eventos que
realmente quedaron visibles despues de los filtros.
"""

import pandas as pd

ETIQUETAS_POR_CODIGO = {
    810: "Extrapulmonar",
    820: "Pulmonar",
    825: "Farmacorresistente",
}

# Pulmonar primero porque es el orden natural de lectura en los titulos.
_ORDEN_CODIGOS = [820, 810, 825]


def etiqueta_tipos_tb(datos: pd.DataFrame) -> str:
    """Devuelve 'tuberculosis pulmonar', 'tuberculosis pulmonar y extrapulmonar', etc."""
    if "cod_eve" not in datos.columns:
        return "tuberculosis"

    codigos = set(pd.to_numeric(datos["cod_eve"], errors="coerce").dropna().astype(int).unique())
    eventos = [ETIQUETAS_POR_CODIGO[codigo] for codigo in _ORDEN_CODIGOS if codigo in codigos]

    if not eventos:
        return "tuberculosis"
    if len(eventos) == 1:
        return f"tuberculosis {eventos[0].lower()}"
    return "tuberculosis " + ", ".join(evento.lower() for evento in eventos[:-1]) + " y " + eventos[-1].lower()
