"""Login y manejo de la sesion del usuario contra el AuthProvider configurado.

La app solo conoce el contrato AuthProvider (core/auth/base.py); hoy la
implementacion concreta es Keycloak, pero esta pieza no lo sabe mas alla de
instanciarla una vez por sesion.
"""

import streamlit as st
from keycloak.exceptions import KeycloakConnectionError

from core.auth.base import AuthProvider, Usuario
from core.auth.keycloak_provider import KeycloakAuthProvider
from core.dashboard_base.estilos import (
    AZUL_INSTITUCIONAL,
    NARANJA_INSTITUCIONAL,
    VERDE_INSTITUCIONAL,
    RUTA_ESCUDO_UNIMAGDALENA,
    RUTA_ICONO_SIVIDEM,
    aplicar_estilos,
    imagen_a_data_uri,
)

CLAVE_USUARIO = "usuario"
CLAVE_PROVEEDOR_AUTH = "_proveedor_auth"
CLAVE_INTENTO_LOGIN = "_intento_login"


def obtener_proveedor_auth() -> AuthProvider:
    if CLAVE_PROVEEDOR_AUTH not in st.session_state:
        st.session_state[CLAVE_PROVEEDOR_AUTH] = KeycloakAuthProvider()
    return st.session_state[CLAVE_PROVEEDOR_AUTH]


def usuario_actual() -> Usuario | None:
    return st.session_state.get(CLAVE_USUARIO)


def iniciar_sesion(nombre_usuario: str, contrasena: str) -> Usuario | None:
    proveedor = obtener_proveedor_auth()
    usuario = proveedor.autenticar(nombre_usuario, contrasena)
    if usuario is not None:
        st.session_state[CLAVE_USUARIO] = usuario
    return usuario


def cerrar_sesion() -> None:
    usuario = usuario_actual()
    if usuario is not None:
        proveedor = obtener_proveedor_auth()
        try:
            proveedor.cerrar_sesion(usuario)
        except Exception:
            pass
    st.session_state.clear()


def mostrar_formulario_login() -> None:
    """Login en dos fases para evitar parpadeo mientras Keycloak responde:
    1. Usuario confirma el formulario -> credenciales a session_state -> rerun instantaneo.
    2. Siguiente rerun: se verifica contra Keycloak bajo un spinner en el mismo panel.
    """
    aplicar_estilos()
    _aplicar_estilos_login()

    intento = st.session_state.get(CLAVE_INTENTO_LOGIN)
    enviado = False

    col_contexto, col_formulario = st.columns([1.15, 0.85])

    with col_contexto:
        _panel_contexto()

    with col_formulario:
        with st.container(key="panel_form_login"):
            if intento is not None:
                _mostrar_verificando(intento)
                return
            enviado = _panel_formulario()

    if enviado:
        st.rerun()


# ---------------------------------------------------------------------------
# Paneles
# ---------------------------------------------------------------------------

def _panel_contexto() -> None:
    icono_uri = imagen_a_data_uri(RUTA_ICONO_SIVIDEM)
    escudo_uri = imagen_a_data_uri(RUTA_ESCUDO_UNIMAGDALENA)

    st.html(f"""
    <div style="
        background: linear-gradient(155deg, {AZUL_INSTITUCIONAL} 0%, #0d2040 100%);
        border-radius: 16px;
        padding: 52px 30px 48px 30px;
        display: flex;
        min-height: 720px; 
        flex-direction: column;
        justify-content: flex-start;
        font-family: sans-serif;
        box-shadow: 0 4px 32px rgba(27, 58, 107, 0.35);
    ">
        <!-- Cabecera: icono en badge blanco + nombre + acento tricolor + descripcion -->
        <div style="
            max-width: 430px;
            margin-left: 20px;
        ">
            <!-- Icono en contenedor blanco para que sea visible sobre el fondo oscuro -->
            <div style="
                width: 60px; height: 60px;
                background: rgba(255,255,255,0.92);
                border-radius: 14px;
                display: flex;
                align-items: center;
                justify-content: center;
                margin-bottom: 24px;
                box-shadow: 0 2px 12px rgba(0,0,0,0.2);
            ">
                <img src="{escudo_uri}" style="height: 48px;">
            </div>

            <h1 style="
                color: white;
                margin: 0 0 4px;
                font-size: 38px;
                font-weight: 700;
                letter-spacing: -0.8px;
                line-height: 1;
            ">SIVIDEM</h1>

            <p style="
                color: rgba(255,255,255,0.6);
                font-size: 11.5px;
                margin: 0 0 22px;
                letter-spacing: 1.2px;
                text-transform: uppercase;
            ">Sistema de Vigilancia Departamental del Magdalena</p>

            <!-- Acento tricolor institucional -->
            <div style="display:flex; gap:4px; margin-bottom: 30px; align-items: center;">
                <div style="height:3px; width:36px; background:{AZUL_INSTITUCIONAL};
                            border: 1px solid rgba(255,255,255,0.35); border-radius: 2px;"></div>
                <div style="height:3px; width:36px; background:{NARANJA_INSTITUCIONAL}; border-radius: 2px;"></div>
                <div style="height:3px; width:36px; background:{VERDE_INSTITUCIONAL};
                            border-radius: 2px; opacity: 0.75;"></div>
            </div>

            <p style="
                color: rgba(255,255,255,0.72);
                font-size: 14.5px;
                line-height: 1.8;
                max-width: 460px;
                margin: 0 0 36px;
            ">
                Herramienta de análisis epidemiológico departamental para la toma
                de decisiones en salud pública. Monitoreo de tendencias, situación
                territorial e indicadores de alerta temprana.
            </p>

            <!-- Capacidades del sistema como lista con punto naranja -->
            <div style="display: flex; flex-direction: column; gap: 11px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width:7px; height:7px; border-radius:50%; background:{NARANJA_INSTITUCIONAL}; flex-shrink:0;"></div>
                    <span style="color:rgba(255,255,255,0.73); font-size:13.5px;">Análisis de tendencias y ciclos epidemicos</span>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width:7px; height:7px; border-radius:50%; background:{NARANJA_INSTITUCIONAL}; flex-shrink:0;"></div>
                    <span style="color:rgba(255,255,255,0.73); font-size:13.5px;">Situación epidemiológica actual por subregión</span>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width:7px; height:7px; border-radius:50%; background:{NARANJA_INSTITUCIONAL}; flex-shrink:0;"></div>
                    <span style="color:rgba(255,255,255,0.73); font-size:13.5px;">Perfil sociodemográfico de la población afectada</span>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width:7px; height:7px; border-radius:50%; background:{NARANJA_INSTITUCIONAL}; flex-shrink:0;"></div>
                    <span style="color:rgba(255,255,255,0.73); font-size:13.5px;">Indicadores de morbilidad, mortalidad y letalidad</span>
                </div>
                <div style="display: flex; align-items: center; gap: 12px;">
                    <div style="width:7px; height:7px; border-radius:50%; background:{NARANJA_INSTITUCIONAL}; flex-shrink:0;"></div>
                    <span style="color:rgba(255,255,255,0.73); font-size:13.5px;">Canal endémico y pronóstico de corto plazo</span>
                </div>
            </div>
        </div>

        <!-- Pie: escudo + CITES -->
        <div style="
            display: flex;
            align-items: center;
            gap: 14px;
            padding-top: 32px;
            margin-top: 36px;
            border-top: 1px solid rgba(255,255,255,0.1);
            max-width:520px;
            margin-left:20px;
        ">
            <img src="{icono_uri}" style="height: 56px; opacity: 0.85;">
            <div>
                <div style="color: rgba(255,255,255,0.88); font-size: 13px; font-weight: 600;">
                    CITES &mdash; Centro de Innovación y Transferencia en Salud
                </div>
                <div style="color: rgba(255,255,255,0.5); font-size: 11px; margin-top: 1px;">
                    Universidad del Magdalena &middot; Santa Marta, Colombia
                </div>
            </div>
        </div>
    </div>
    """)


def _panel_formulario() -> bool:
    """Renderiza la cabecera y el formulario de acceso. Retorna True si el formulario
    fue enviado (lo que indica que el caller debe hacer st.rerun()).
    """
    st.space(70)

    st.markdown(
        f"""
        <div style="padding: 0 2rem;">
            <p style="
                color: {NARANJA_INSTITUCIONAL};
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 1.5px;
                text-transform: uppercase;
                margin: 0 0 8px;
            ">Acceso restringido</p>
            <h2 style="
                color: {AZUL_INSTITUCIONAL};
                font-size: 28px;
                font-weight: 700;
                margin: 0 0 8px;
                letter-spacing: -0.4px;
            ">Bienvenido</h2>
            <p style="color: #6b7280; font-size: 14px; margin: 0 0 32px; line-height: 1.5;">
                Ingresa con tus credenciales institucionales de la
                Universidad del Magdalena.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    correo = ""
    contrasena = ""

    with st.form("formulario_login", border=False):
        correo = st.text_input(
            ":material/alternate_email: Correo electrónico",
            placeholder="nombre@unimagdalena.edu.co",
        )
        contrasena = st.text_input(
            ":material/lock: Contraseña",
            type="password",
            placeholder="Tu contraseña institucional",
        )
        st.space("small")
        enviado = st.form_submit_button(
            "Ingresar al sistema",
            type="primary",
            icon=":material/login:",
            width="stretch",
        )

    error_previo = st.session_state.pop("_error_login", None)
    if error_previo is not None:
        st.error(error_previo, icon=":material/error:")

    st.space(100)

    st.markdown(
        """
        <div style="display: flex; align-items: center; gap: 8px; padding: 12px 0px; color: #6b7280; font-size: 13px; border-top: 1px solid #eceff3; line-height: 1;">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6b7280" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink: 0; display: inline-block; vertical-align: middle; margin-left: 20px; margin-top: 8px">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
                <path d="m9 12 2 2 4-4"/>
            </svg>
            <span style="display: inline-block; vertical-align: middle; margin-top: 8px">Acceso seguro vinculado a tu cuenta institucional.</span>
        </div>
        """, 
        unsafe_allow_html=True
    )

    if enviado:
        st.session_state[CLAVE_INTENTO_LOGIN] = (correo, contrasena)
    
    return enviado


def _mostrar_verificando(intento: tuple[str, str]) -> None:
    """Fase 2 del login: verificacion contra Keycloak. Se muestra en el mismo
    panel derecho para evitar parpadeo de la pagina completa.
    """
    correo, contrasena = intento

    st.space(120)
    with st.container(horizontal_alignment="center"):
        with st.spinner("Verificando credenciales..."):
            try:
                usuario = iniciar_sesion(correo, contrasena)
            except KeycloakConnectionError:
                st.session_state.pop(CLAVE_INTENTO_LOGIN, None)
                st.session_state["_error_login"] = (
                    "No se pudo conectar al servidor de autenticación. "
                    "Intenta de nuevo en un momento."
                )
                st.rerun()
                return

    st.session_state.pop(CLAVE_INTENTO_LOGIN, None)
    if usuario is None:
        st.session_state["_error_login"] = (
            "Correo o contraseña inválidos, "
            "o el usuario no tiene un rol asignado en Keycloak."
        )
        st.rerun()
        return

    st.rerun()


# ---------------------------------------------------------------------------
# CSS especifico del login (se aplica solo cuando el usuario no esta autenticado)
# ---------------------------------------------------------------------------

def _aplicar_estilos_login() -> None:
    st.html("""
    <style>
    /* Reduce top padding en la pagina de login */
    div[data-testid="stMainBlockContainer"] {
        max-width: 1500px;
        margin: 0 auto;
        padding-top: 3.5rem !important;
    }
            
    div[data-testid="stHorizontalBlock"]{
        align-items: stretch;
    }

    /* Panel derecho: tarjeta blanca con sombra */
    .st-key-panel_form_login {
        background: white;
        border-radius: 16px;
        box-shadow:
            0 1px 3px rgba(16, 24, 40, 0.06),
            0 8px 32px rgba(16, 24, 40, 0.09);
        
        min-height:720px;
    }

    /* Quita borde y sombra del stForm dentro del panel de login */
    .st-key-panel_form_login div[data-testid="stForm"] {
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        border-radius: 0 !important;
        padding: 0.25rem 2rem 1rem 2rem !important;
    }

    /* Labels mas fuertes en el formulario */
    .st-key-panel_form_login label p {
        font-size: 0.88rem !important;
        font-weight: 500 !important;
        color: #374151 !important;
    }

    /* Inputs mas confortables */
    .st-key-panel_form_login input {
        font-size: 1rem !important;
        padding: 0.6rem 0.75rem !important;
    }
    </style>
    """)
