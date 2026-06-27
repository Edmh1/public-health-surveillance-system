"""Identidad visual del dashboard. Ver DESIGN.md (raiz del repo) para la guia completa.

Regla de oro: verde/amarillo/rojo son exclusivos del canal endemico y los estados
epidemiologicos. Nunca se usan aqui para decorar, botones o acentos. Por eso las
confirmaciones rutinarias de una operacion (subir, restaurar, etc.) usan azul
institucional (st.info) en vez de st.success: el verde queda intacto para cuando
se construya el canal endemico. st.error se mantiene para errores reales
(conexion, validacion) porque es una convencion de accesibilidad bien establecida,
no una decoracion.
"""

import streamlit as st

AZUL_INSTITUCIONAL = "#1b3a6b"
NARANJA_INSTITUCIONAL = "#e8852c"
VERDE_INSTITUCIONAL = "#3f9b46"

COLOR_EXITO_EPIDEMIOLOGICO = "#3f9b46"
COLOR_SEGURIDAD_EPIDEMIOLOGICO = "#6fb574"
COLOR_ALERTA_EPIDEMIOLOGICO = "#efb23c"
COLOR_EPIDEMIA = "#d0473f"

CLAVE_ESTILOS_APLICADOS = "_estilos_aplicados"


def aplicar_estilos() -> None:
    """Inyecta el CSS compartido. Se puede llamar varias veces por rerun sin costo extra."""
    if st.session_state.get(CLAVE_ESTILOS_APLICADOS):
        return

    st.markdown(
        """
        <style>
        div[data-testid="stForm"] {
            border: 0.5px solid #e0e0e0;
            border-radius: 12px;
            padding: 1.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state[CLAVE_ESTILOS_APLICADOS] = True


def mostrar_franja_tricolor() -> None:
    """Franja delgada azul/naranja/verde: guino institucional discreto bajo la cabecera."""
    st.markdown(
        f"""
        <div style="display:flex; height:4px; margin-bottom:1.5rem;">
            <div style="flex:1; background-color:{AZUL_INSTITUCIONAL};"></div>
            <div style="flex:1; background-color:{NARANJA_INSTITUCIONAL};"></div>
            <div style="flex:1; background-color:{VERDE_INSTITUCIONAL};"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
