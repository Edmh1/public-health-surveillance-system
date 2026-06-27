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
    RUTA_ESCUDO_UNIMAGDALENA,
    RUTA_LOGO_SIVIDEM,
    VERDE_INSTITUCIONAL,
    aplicar_estilos,
    imagen_a_data_uri,
)

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
        try:
            proveedor.cerrar_sesion(usuario)
        except Exception:
            pass
    st.session_state.clear()


def mostrar_formulario_login() -> None:
    aplicar_estilos()

    _, columna_centro, _ = st.columns([1, 1.2, 1])
    with columna_centro:
        with st.container(key="tarjeta_login"):
            _mostrar_franja_tricolor_superior()
            _mostrar_cabecera_login()

            with st.form("formulario_login"):
                correo = st.text_input("Correo electronico", placeholder="nombre@unimagdalena.edu.co")
                contrasena = st.text_input("Contrasena", type="password")
                enviado = st.form_submit_button(
                    "Entrar", type="primary", icon=":material/login:", use_container_width=True
                )
                st.caption(
                    ":material/lock: Acceso seguro, vinculado a tu cuenta institucional "
                    "de la Universidad del Magdalena."
                )

    if not enviado:
        return

    try:
        with st.spinner("Verificando credenciales..."):
            usuario = iniciar_sesion(correo, contrasena)
    except KeycloakConnectionError:
        st.error("No se pudo conectar al servidor de autenticacion. Intenta de nuevo en un momento.")
        return

    if usuario is None:
        st.error("Correo o contrasena invalidos, o el usuario no tiene un rol asignado en Keycloak")
        return

    st.rerun()


def _mostrar_franja_tricolor_superior() -> None:
    st.markdown(
        f"""
        <div style="display:flex; height:5px;">
            <div style="flex:1; background-color:{AZUL_INSTITUCIONAL};"></div>
            <div style="flex:1; background-color:{NARANJA_INSTITUCIONAL};"></div>
            <div style="flex:1; background-color:{VERDE_INSTITUCIONAL};"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _mostrar_cabecera_login() -> None:
    # Pendiente: confirmar con la tutora / Direccion de Comunicaciones la autorizacion
    # formal de uso del escudo de la Universidad del Magdalena (ver DESIGN.md). Por eso
    # se usa puntualmente solo aqui, en el login, y no en el resto de la aplicacion.
    escudo_data_uri = imagen_a_data_uri(RUTA_ESCUDO_UNIMAGDALENA)
    logo_data_uri = imagen_a_data_uri(RUTA_LOGO_SIVIDEM)
    st.markdown(
        f"""
        <div style="padding: 32px 36px 20px 36px; display:flex; align-items:center; gap:18px;">
            <div style="width:52px; height:52px; border-radius:50%; overflow:hidden; flex-shrink:0;
                        box-shadow: 0 0 0 1px #e2e5ea;">
                <img src="{escudo_data_uri}" style="width:100%; height:100%; object-fit:cover;" />
            </div>
            <div style="width:1px; height:40px; background-color:#e2e5ea;"></div>
            <div>
                <img src="{logo_data_uri}" style="height:42px;" />
                <div style="color:#666666; font-size:12px; margin-top:2px;">CITES - Universidad del Magdalena</div>
            </div>
        </div>
        <div style="height:1px; background-color:#eef0f3; margin: 0 36px 20px 36px;"></div>
        """,
        unsafe_allow_html=True,
    )
