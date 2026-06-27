"""Implementacion concreta de AuthProvider contra Keycloak.

El resto de la aplicacion solo conoce el contrato AuthProvider (core/auth/base.py).
Keycloak entrega unicamente la identidad y la etiqueta del rol (un realm role:
Editor, Visor o Admin). Que puede hacer cada rol es decision de la app, en
core/auth/permisos.py; esta pieza nunca decide permisos, solo identidad.
"""

import os

from keycloak import KeycloakOpenID
from keycloak.exceptions import KeycloakAuthenticationError

from core.auth.base import AuthProvider, Usuario

ROLES_VALIDOS = {"Editor", "Visor", "Admin"}


def _extraer_rol(roles_realm: list[str]) -> str | None:
    """De los realm roles del token, devuelve el que coincide con un rol valido de la app."""
    roles_normalizados = {rol.strip().lower(): rol for rol in ROLES_VALIDOS}
    for rol_realm in roles_realm:
        rol_valido = roles_normalizados.get(rol_realm.strip().lower())
        if rol_valido is not None:
            return rol_valido
    return None


def _usuario_desde_token(informacion_token: dict, token_acceso: str, token_refresco: str | None) -> Usuario | None:
    roles_realm = informacion_token.get("realm_access", {}).get("roles", [])
    rol = _extraer_rol(roles_realm)
    if rol is None:
        return None

    usuario = Usuario(
        id_usuario=informacion_token["sub"],
        nombre_usuario=informacion_token.get("preferred_username", ""),
        rol=rol,
        token_acceso=token_acceso,
        token_refresco=token_refresco,
    )
    return usuario


class KeycloakAuthProvider(AuthProvider):
    """AuthProvider respaldado por un servidor Keycloak, via grant de usuario y contrasena."""

    def __init__(
        self,
        server_url: str | None = None,
        realm_name: str | None = None,
        client_id: str | None = None,
        client_secret_key: str | None = None,
    ):
        self.cliente_keycloak = KeycloakOpenID(
            server_url=server_url or os.environ["KEYCLOAK_SERVER_URL"],
            realm_name=realm_name or os.environ["KEYCLOAK_REALM"],
            client_id=client_id or os.environ["KEYCLOAK_CLIENT_ID"],
            client_secret_key=client_secret_key or os.environ.get("KEYCLOAK_CLIENT_SECRET"),
        )

    def autenticar(self, nombre_usuario: str, contrasena: str) -> Usuario | None:
        try:
            token = self.cliente_keycloak.token(nombre_usuario, contrasena)
        except KeycloakAuthenticationError:
            return None

        informacion_token = self.cliente_keycloak.decode_token(token["access_token"])
        usuario = _usuario_desde_token(informacion_token, token["access_token"], token["refresh_token"])
        return usuario

    def cerrar_sesion(self, usuario: Usuario) -> None:
        if usuario.token_refresco is not None:
            self.cliente_keycloak.logout(usuario.token_refresco)

    def validar_sesion(self, token: str) -> Usuario | None:
        try:
            informacion_token = self.cliente_keycloak.decode_token(token)
        except Exception:
            return None

        usuario = _usuario_desde_token(informacion_token, token, token_refresco=None)
        return usuario
