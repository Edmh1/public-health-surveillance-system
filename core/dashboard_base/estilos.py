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
import streamlit.components.v1 as componentes_v1

RUTA_ASSETS = Path(__file__).resolve().parents[2] / "assets"
RUTA_ESCUDO_UNIMAGDALENA = RUTA_ASSETS / "unimagdalena.png"
RUTA_ICONO_SIVIDEM = RUTA_ASSETS / "icono_sividem.svg"
RUTA_ICONO_SIVIDEM_PNG = RUTA_ASSETS / "icono_sividem.png"
RUTA_LOGO_SIVIDEM = RUTA_ASSETS / "logo_sividem.svg"

AZUL_INSTITUCIONAL = "#1b3a6b"
NARANJA_INSTITUCIONAL = "#e8852c"
VERDE_INSTITUCIONAL = "#3f9b46"

# Leyenda horizontal encima del area de dibujo: toda grafica debe declarar que
# esta mostrando (tipo/serie) con la leyenda en la parte superior.
LEYENDA_SUPERIOR = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)


def eje_semanal(ultima_semana: int) -> dict:
    """Configuracion del eje X para graficas por semana epidemiologica.

    Todas las semanas quedan etiquetadas (1 a la ultima con datos), con el numero
    horizontal para que se lea claro. minallowed/maxallowed impiden que al hacer
    pan o zoom aparezcan semanas negativas o mayores a las que existen.
    Aplicar con fig.update_xaxes(**eje_semanal(n)) o dentro del dict xaxis del layout.
    """
    return dict(
        tickmode="linear",
        tick0=1,
        dtick=1,
        tickangle=0,
        tickfont=dict(size=9),
        minallowed=0.5,
        maxallowed=ultima_semana + 0.5,
    )

def rango_con_margen(valor_maximo: float, factor: float = 1.2) -> list[float]:
    """Rango de eje con espacio extra para el texto "outside" de una barra.

    Sin esto, la etiqueta de la barra mas alta (barras verticales) o mas larga
    (barras horizontales) queda cortada contra el borde del area de dibujo,
    porque el autorange de Plotly llega justo hasta el valor de la barra, no
    hasta donde termina su texto. Aplicar con fig.update_yaxes(range=...) en
    barras verticales o fig.update_xaxes(range=...) en barras horizontales,
    usando el maximo del valor graficado (no el eje de categorias).
    """
    if valor_maximo is None or valor_maximo <= 0:
        return [0, 1]
    return [0, valor_maximo * factor]


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
        /* El selector :has() aplica al instante en navegadores modernos; la
           clase .sividem-header-fijo la agrega via JS el script de
           aplicar_estilos() y cubre navegadores sin :has() (ej. Firefox
           viejo), donde de lo contrario el header no se fijaria nunca. */
        div[data-testid="stLayoutWrapper"]:has(.st-key-encabezado_fijo),
        .sividem-header-fijo {
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
        /* Lista de pestanas sticky justo debajo del header SIVIDEM.
           El top exacto depende de la altura real del header (que varia con
           banners y titulos): un script en aplicar_estilos() lo mide en vivo y
           lo publica en la variable --sividem-tabs-top; 225px es solo el
           respaldo si el script aun no corrio. z-index 9999 (igual al header):
           el tab list aparece despues en el DOM asi que pinta encima si llegan
           a rozarse. */
        div[data-testid="stTabs"] div:has(> div[role="tablist"]),
        .sividem-tabs-fijas {
            position: sticky !important;
            top: var(--sividem-tabs-top, 225px) !important;
            z-index: 9999 !important;
            width: 100% !important;
            background-color: #EEF1F5 !important;
            padding-top: 0 !important;
            padding-left: 0.4rem;
            margin-top: 0 !important;
            box-shadow: 0 6px 10px -4px rgba(16, 24, 40, 0.12) !important;
        }
        /* Padding en el panel de cada pestana para que el primer elemento
           no quede tapado por la barra de navegacion sticky al hacer scroll. */
        [role="tabpanel"] > div:first-child {
            padding-top: 1rem !important;
        }
        /* Las pestanas dentro de un dialogo (ej. metodologia del canal endemico) no
           necesitan sticky: el top:225px se calculo para el header fijo de la pagina
           principal, no tiene sentido dentro de un modal. Selector mas especifico que
           el de arriba para ganar sobre el !important. */
        div[data-testid="stDialog"] div[data-testid="stTabs"] div:has(> div[role="tablist"]),
        div[data-testid="stDialog"] div[data-testid="stTabs"] div[role="tablist"] {
            position: static !important;
            top: auto !important;
            z-index: auto !important;
            box-shadow: none !important;
        }
        </style>
        """
    )
    _publicar_altura_header()


def _publicar_altura_header() -> None:
    """Script de apoyo del encabezado y el tab bar fijos. Hace dos cosas:

    1. Mide la altura real del header y publica el top del tab bar como
       variable CSS --sividem-tabs-top (60px del toolbar + altura del header +
       10px de margen). Asi el tab bar queda SIEMPRE justo debajo del header
       aunque este crezca (banners, titulo largo).
    2. Marca con clases propias (.sividem-header-fijo, .sividem-tabs-fijas)
       los elementos que deben fijarse: es el respaldo de los selectores
       :has() del CSS para navegadores que no los soportan.

    Corre en un iframe de componente porque st.html no ejecuta <script>. El
    intervalo re-consulta el DOM en cada tick porque Streamlit reemplaza nodos
    entre reruns (y React puede pisar las clases agregadas). El iframe mide
    0px y no agrega nada visible.
    """
    componentes_v1.html(
        """
        <script>
        const doc = window.parent.document;
        function actualizar() {
            const marcador = doc.querySelector('.st-key-encabezado_fijo');
            if (!marcador) { return; }
            const header = marcador.closest('[data-testid="stLayoutWrapper"]') || marcador;
            header.classList.add('sividem-header-fijo');
            const topTabs = 60 + header.offsetHeight + 10;
            doc.documentElement.style.setProperty('--sividem-tabs-top', topTabs + 'px');
            doc.querySelectorAll('div[role="tablist"]').forEach(function (lista) {
                if (lista.closest('[data-testid="stDialog"]')) { return; }
                const barra = lista.parentElement;
                if (barra) { barra.classList.add('sividem-tabs-fijas'); }
            });
        }
        actualizar();
        setInterval(actualizar, 1000);
        </script>
        """,
        height=0,
    )


@st.cache_data(show_spinner=False)
def imagen_a_data_uri(ruta: Path) -> str:
    """Codifica una imagen de assets/ como data URI para incrustarla en HTML."""
    contenido = ruta.read_bytes()
    codificado = base64.b64encode(contenido).decode("ascii")
    return f"data:image/svg+xml;base64,{codificado}"
