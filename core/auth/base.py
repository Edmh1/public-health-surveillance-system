"""Contrato AuthProvider: el resto de la aplicacion habla solo con este contrato, nunca con el proveedor concreto."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Usuario:
    """Datos minimos de la persona autenticada: identidad y rol."""

    id_usuario: str
    nombre_usuario: str
    rol: str


class AuthProvider(ABC):
    """Contrato de autenticacion. Hoy lo implementa Keycloak; el resto de la app no lo sabe."""

    @abstractmethod
    def autenticar(self, nombre_usuario: str, contrasena: str) -> Usuario | None:
        """Valida credenciales contra el proveedor de identidad.

        Devuelve el usuario autenticado con su rol, o None si las credenciales son invalidas.
        """

    @abstractmethod
    def cerrar_sesion(self, usuario: Usuario) -> None:
        """Cierra la sesion del usuario en el proveedor de identidad."""

    @abstractmethod
    def validar_sesion(self, token: str) -> Usuario | None:
        """Verifica si un token de sesion sigue siendo valido.

        Devuelve el usuario asociado al token, o None si el token no es valido.
        """
