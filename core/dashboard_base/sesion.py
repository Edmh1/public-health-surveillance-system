"""Login y manejo de la sesion del usuario contra el AuthProvider configurado.

La app solo conoce el contrato AuthProvider (core/auth/base.py); hoy la
implementacion concreta es Keycloak, pero esta pieza no lo sabe mas alla de
instanciarla una vez por sesion.
"""

import streamlit as st
from keycloak.exceptions import KeycloakConnectionError

from core.auth.base import AuthProvider, Usuario
from core.auth.keycloak_provider import KeycloakAuthProvider
from core.dashboard_base.estilos import AZUL_INSTITUCIONAL, aplicar_estilos, mostrar_franja_tricolor

CLAVE_USUARIO = "usuario"
CLAVE_PROVEEDOR_AUTH = "_proveedor_auth"


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
        proveedor.cerrar_sesion(usuario)
    st.session_state.clear()


def mostrar_formulario_login() -> None:
    aplicar_estilos()
    _mostrar_cabecera_login()

    _, columna_centro, _ = st.columns([1, 1.3, 1])
    with columna_centro:
        with st.form("formulario_login"):
            correo = st.text_input("Correo electronico", placeholder="nombre@unimagdalena.edu.co")
            contrasena = st.text_input("Contrasena", type="password")
            enviado = st.form_submit_button(
                "Entrar", type="primary", icon=":material/login:", use_container_width=True
            )
        st.caption(
            ":material/lock: Acceso seguro, vinculado a tu cuenta institucional de la Universidad del Magdalena."
        )

    if not enviado:
        return

    try:
        usuario = iniciar_sesion(correo, contrasena)
    except KeycloakConnectionError:
        st.error("No se pudo conectar al servidor de autenticacion. Intenta de nuevo en un momento.")
        return

    if usuario is None:
        st.error("Correo o contrasena invalidos, o el usuario no tiene un rol asignado en Keycloak")
        return

    st.rerun()


def _mostrar_cabecera_login() -> None:
    # TODO: una vez autorizado el uso del escudo oficial (ver DESIGN.md), poner la
    # imagen real en assets/ y reemplazar el circulo con iniciales de abajo por ella.
    st.markdown(
        f"""
        <div style="background-color:{AZUL_INSTITUCIONAL}; padding: 28px 32px; border-radius: 12px;
                    margin-bottom: 0; display:flex; align-items:center; gap:14px;">
            <div style="width:44px; height:44px; border-radius:50%; background-color:white;
                        color:{AZUL_INSTITUCIONAL}; display:flex; align-items:center; justify-content:center;
                        font-weight:500; font-size:15px; flex-shrink:0;">
                CITES
            </div>
            <div>
                <div style="color:white; font-size:22px; font-weight:500;">Vigilancia epidemiologica</div>
                <div style="color:#cfd8e6; font-size:14px;">CITES - Universidad del Magdalena</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    mostrar_franja_tricolor()
