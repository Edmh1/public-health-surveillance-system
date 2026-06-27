"""Identidad visual del dashboard. Ver DESIGN.md (raiz del repo) para la guia completa.

Regla de oro: verde/amarillo/rojo son exclusivos del canal endemico y los estados
epidemiologicos. Nunca se usan aqui para decorar, botones o acentos. Por eso las
confirmaciones rutinarias de una operacion (subir, restaurar, etc.) usan azul
institucional (st.info) en vez de st.success: el verde queda intacto para cuando
se construya el canal endemico. st.error se mantiene para errores reales
(conexion, validacion) porque es una convencion de accesibilidad bien establecida,
no una decoracion.
"""

import base64
from pathlib import Path

import streamlit as st

RUTA_ASSETS = Path(__file__).resolve().parents[2] / "assets"
RUTA_ESCUDO_UNIMAGDALENA = RUTA_ASSETS / "unimagdalena.svg"
RUTA_ICONO_SIVIDEM = RUTA_ASSETS / "icono_sividem.svg"
RUTA_LOGO_SIVIDEM = RUTA_ASSETS / "logo_sividem.svg"

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
            background-color: #ffffff;
            border: 0.5px solid #e2e5ea;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        div[data-testid="stMainBlockContainer"] {
            padding-top: 2.5rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        .st-key-barra_superior {
            background-color: #ffffff !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 0.5rem 1.2rem !important;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        [data-testid^="stBaseButton-"] {
            border-radius: 8px !important;
        }
        .st-key-tarjeta_login {
            background-color: #ffffff;
            border-radius: 16px;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07), 0 10px 28px rgba(16, 24, 40, 0.07);
            overflow: hidden;
        }
        .st-key-tarjeta_login div[data-testid="stForm"] {
            border: none;
            box-shadow: none;
            border-radius: 0;
            padding: 0.5rem 2.5rem 2rem 2.5rem;
            background-color: transparent;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.session_state[CLAVE_ESTILOS_APLICADOS] = True


@st.cache_data(show_spinner=False)
def imagen_a_data_uri(ruta: Path) -> str:
    """Codifica una imagen de assets/ como data URI para incrustarla en HTML."""
    contenido = ruta.read_bytes()
    codificado = base64.b64encode(contenido).decode("ascii")
    return f"data:image/svg+xml;base64,{codificado}"
