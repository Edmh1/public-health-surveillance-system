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
RUTA_ESCUDO_UNIMAGDALENA = RUTA_ASSETS / "unimagdalena.png"
RUTA_ICONO_SIVIDEM = RUTA_ASSETS / "icono_sividem.svg"
RUTA_ICONO_SIVIDEM_PNG = RUTA_ASSETS / "icono_sividem.png"
RUTA_LOGO_SIVIDEM = RUTA_ASSETS / "logo_sividem.svg"

AZUL_INSTITUCIONAL = "#1b3a6b"
NARANJA_INSTITUCIONAL = "#e8852c"
VERDE_INSTITUCIONAL = "#3f9b46"

COLOR_EXITO_EPIDEMIOLOGICO = "#3f9b46"
COLOR_SEGURIDAD_EPIDEMIOLOGICO = "#6fb574"
COLOR_ALERTA_EPIDEMIOLOGICO = "#efb23c"
COLOR_EPIDEMIA = "#d0473f"

def aplicar_estilos() -> None:
    """Inyecta el CSS compartido. Se llama en cada rerun (login y dashboard) a proposito:
    Streamlit quita del DOM cualquier elemento que un rerun no vuelva a emitir, asi que un
    guard de "solo una vez por sesion" hacia que el bloque de estilos sobreviviera unicamente
    en el primer render (la pantalla de login) y desapareciera en todos los reruns
    posteriores del dashboard. Emitirlo siempre es barato (es solo texto) y evita ese bug.
    """
    st.html(
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
            padding: 0.6rem 1.6rem !important;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        .st-key-encabezado_fijo {
            background-color: #EEF1F5 !important;
            padding-bottom: 0.3rem !important;
            gap: 0.5rem !important;
        }
        .st-key-encabezado_fijo h1 {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        /* Streamlit envuelve cada elemento de nivel superior en un stLayoutWrapper que,
           por su layout flex interno, rompe position:sticky en sus hijos directos. El
           sticky si funciona aplicado al wrapper mismo, por eso se selecciona con :has().
           Todo el encabezado (titulo, contador de registros y marca/patologia/usuario) se
           fija como un solo bloque, para que nunca se pierda de vista al hacer scroll en el
           contenido de cualquier pestana. El fondo opaco y el ancho completo van en el
           wrapper (no solo en el div interno) para que nada del contenido que se desliza por
           detras se asome en los bordes; el z-index alto y el box-shadow inferior lo separan
           visualmente del contenido, para que se vea como una capa flotando y no como un
           corte abrupto. */
        div[data-testid="stLayoutWrapper"]:has(.st-key-encabezado_fijo) {
            position: sticky !important;
            top: 60px !important;
            z-index: 9999 !important;
            width: 100% !important;
            background-color: #EEF1F5 !important;
            box-shadow: 0 6px 10px -4px rgba(16, 24, 40, 0.12) !important;
        }
        [data-testid^="stBaseButton-"] {
            border-radius: 8px !important;
        }
        .st-key-tarjeta_login {
            background-color: #ffffff;
            border-radius: 16px;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07), 0 10px 28px rgba(16, 24, 40, 0.07);
            overflow: hidden;
            margin-top: 7vh;
        }
        .st-key-tarjeta_login div[data-testid="stForm"] {
            border: none;
            box-shadow: none;
            border-radius: 0;
            padding: 0.5rem 2.5rem 2rem 2.5rem;
            background-color: transparent;
        }
        .st-key-tarjeta_login label p {
            font-size: 1rem !important;
        }
        .st-key-tarjeta_login input {
            font-size: 1.05rem !important;
        }
        </style>
        """
    )


@st.cache_data(show_spinner=False)
def imagen_a_data_uri(ruta: Path) -> str:
    """Codifica una imagen de assets/ como data URI para incrustarla en HTML."""
    contenido = ruta.read_bytes()
    codificado = base64.b64encode(contenido).decode("ascii")
    return f"data:image/svg+xml;base64,{codificado}"
