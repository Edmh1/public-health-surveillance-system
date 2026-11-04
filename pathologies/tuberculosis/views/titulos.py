"""Titulos de las graficas de tuberculosis con un tamano unico."""

import streamlit as st

TAMANO_TITULO = 16


def titulo_tb(texto: str, *, clave: str, help: str | None = None) -> None:
    """Renderiza un st.subheader con el tamano estandar del modulo TB."""
    with st.container(key=clave):
        st.subheader(texto, help=help)

    st.html(
        f"""
        <style>
        .st-key-{clave} h3,
        .st-key-{clave} [data-testid="stHeading"] {{
            font-size: {TAMANO_TITULO}px !important;
        }}
        </style>
        """
    )
