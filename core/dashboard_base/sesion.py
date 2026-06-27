"""Login y manejo de la sesion del usuario contra el AuthProvider configurado.

La app solo conoce el contrato AuthProvider (core/auth/base.py); hoy la
implementacion concreta es Keycloak, pero esta pieza no lo sabe mas alla de
instanciarla una vez por sesion.
"""

import streamlit as st
from keycloak.exceptions import KeycloakConnectionError

from core.auth.base import AuthProvider, Usuario
from core.auth.keycloak_provider import KeycloakAuthProvider

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
    st.title("Vigilancia Epidemiologica - Magdalena")

    with st.form("formulario_login"):
        correo = st.text_input("Correo electronico")
        contrasena = st.text_input("Contrasena", type="password")
        enviado = st.form_submit_button("Ingresar")

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
