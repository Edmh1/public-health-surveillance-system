"""Permisos por rol: la autorizacion vive aqui, no en Keycloak.

Keycloak solo entrega la etiqueta del rol (Editor, Visor o Admin); que puede
hacer cada rol es una decision de la app. Editor es global: cualquier Editor
gestiona cualquier patologia (no hay editor-asignado-por-patologia todavia).
"""

PERMISO_VER_DASHBOARD = "ver_dashboard"
PERMISO_SUBIR_PIEZA = "subir_pieza"
PERMISO_EDITAR_PIEZA = "editar_pieza"
PERMISO_ELIMINAR_PIEZA = "eliminar_pieza"
PERMISO_VER_PAPELERA = "ver_papelera"
PERMISO_RESTAURAR_PIEZA = "restaurar_pieza"
PERMISO_ELIMINAR_PARA_SIEMPRE = "eliminar_para_siempre"
PERMISO_VER_BITACORA = "ver_bitacora"
PERMISO_VER_PROCESAMIENTOS = "ver_procesamientos"
PERMISO_GESTIONAR_USUARIOS = "gestionar_usuarios"

PERMISOS_DE_VISOR = {
    PERMISO_VER_DASHBOARD,
}

PERMISOS_DE_EDITOR = PERMISOS_DE_VISOR | {
    PERMISO_SUBIR_PIEZA,
    PERMISO_EDITAR_PIEZA,
    PERMISO_ELIMINAR_PIEZA,
    PERMISO_VER_PAPELERA,
    PERMISO_RESTAURAR_PIEZA,
    PERMISO_VER_BITACORA,
    PERMISO_VER_PROCESAMIENTOS,
}

PERMISOS_DE_ADMIN = PERMISOS_DE_EDITOR | {
    PERMISO_ELIMINAR_PARA_SIEMPRE,
    PERMISO_GESTIONAR_USUARIOS,
}

_PERMISOS_POR_ROL = {
    "Visor": PERMISOS_DE_VISOR,
    "Editor": PERMISOS_DE_EDITOR,
    "Admin": PERMISOS_DE_ADMIN,
}


def permisos_de_rol(rol: str) -> set[str]:
    """Devuelve el conjunto de permisos que habilita un rol. Un rol desconocido no habilita ninguno."""
    return set(_PERMISOS_POR_ROL.get(rol, set()))


def tiene_permiso(rol: str, permiso: str) -> bool:
    """Indica si un rol habilita un permiso especifico."""
    return permiso in permisos_de_rol(rol)
