"""Papelera: restaurar piezas o eliminarlas permanentemente.

Rediseñado con tarjetas en lugar de tabla+seleccion de fila.
Las acciones (Restaurar / Eliminar para siempre) son visibles directamente
en cada tarjeta. Las confirmaciones de acciones destructivas se muestran
expandidas debajo de la tarjeta correspondiente.
"""

import streamlit as st

from core.auth.permisos import PERMISO_ELIMINAR_PARA_SIEMPRE, tiene_permiso
from core.audit.registro_piezas import listar_piezas_en_papelera
from core.audit.zona_horaria import formatear_fecha_local
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.paginacion import buscar_y_paginar, mostrar_controles_paginacion
from core.ingestion.papelera import ConflictoDeRestauracion, eliminar_para_siempre, restaurar_pieza
from core.registry import obtener_patologia
from core.storage import rutas

CLAVE_CONFIRMAR_RESTAURAR = "papelera_confirmar_restaurar"
CLAVE_CONFIRMAR_ELIMINAR  = "papelera_confirmar_eliminar"
CLAVE_CONFLICTO_RESTAURAR = "papelera_conflicto_restaurar"


def mostrar_papelera(patologia: str, usuario) -> None:
    piezas = listar_piezas_en_papelera(patologia)

    if not piezas:
        with st.container(border=True):
            st.info(
                ":material/delete: La papelera esta vacia. "
                "Aqui apareceran las piezas que elimines desde Piezas activas.",
                icon=":material/info:",
            )
        return

    pagina_items, pagina, total = buscar_y_paginar(
        piezas,
        clave="papelera",
        campos_busqueda=["archivo_original", "anio", "codigo"],
        placeholder="Buscar por archivo, año o codigo...",
    )
    if total > 0:
        st.caption("Todas las piezas aqui son recuperables desde Restaurar.")

    for pieza in pagina_items:
        clave = f"{patologia}_{pieza['anio']}_{pieza['codigo']}"
        _mostrar_tarjeta_papelera(patologia, pieza, usuario, clave)

    mostrar_controles_paginacion("papelera", pagina, total)


def _mostrar_tarjeta_papelera(patologia: str, pieza: dict, usuario, clave: str) -> None:
    with st.container(border=True):
        col_info, col_acciones = st.columns([3, 1], vertical_alignment="center")

        with col_info:
            st.markdown(f":material/description: **{pieza['archivo_original']}**")
            fecha = formatear_fecha_local(pieza["fecha_creacion"])
            st.caption(f"Año {pieza['anio']} · Codigo {pieza['codigo']} · Eliminada el {fecha}")

        with col_acciones:
            if st.button(
                "Restaurar",
                icon=":material/restore:",
                key=f"restaurar_{clave}",
                width="stretch",
                type="primary",
            ):
                st.session_state.setdefault(CLAVE_CONFIRMAR_RESTAURAR, {})[clave] = True
                st.session_state.setdefault(CLAVE_CONFIRMAR_ELIMINAR, {})[clave] = False

            if tiene_permiso(usuario.rol, PERMISO_ELIMINAR_PARA_SIEMPRE):
                if st.button(
                    "Eliminar",
                    icon=":material/delete_forever:",
                    key=f"eliminar_siempre_{clave}",
                    width="stretch",
                    help="Destruye el archivo permanentemente. Solo Admin.",
                ):
                    st.session_state.setdefault(CLAVE_CONFIRMAR_ELIMINAR, {})[clave] = True
                    st.session_state.setdefault(CLAVE_CONFIRMAR_RESTAURAR, {})[clave] = False

    # Confirmacion de restaurar
    if st.session_state.get(CLAVE_CONFIRMAR_RESTAURAR, {}).get(clave):
        _confirmar_restaurar(patologia, pieza, usuario, clave)

    # Confirmacion de eliminar para siempre
    if st.session_state.get(CLAVE_CONFIRMAR_ELIMINAR, {}).get(clave):
        _confirmar_eliminar_para_siempre(patologia, pieza, usuario, clave)

    # Conflicto al restaurar
    if st.session_state.get(CLAVE_CONFLICTO_RESTAURAR, {}).get(clave):
        _resolver_conflicto(patologia, pieza, usuario, clave)


def _confirmar_restaurar(patologia: str, pieza: dict, usuario, clave: str) -> None:
    with st.container(border=True):
        st.info(
            f":material/restore: Restaurar **{pieza['archivo_original']}** "
            f"(Año {pieza['anio']} · Codigo {pieza['codigo']}) al consolidado activo.",
            icon=None,
        )
        col_cancelar, col_confirmar = st.columns(2)
        with col_cancelar:
            if st.button("Cancelar", key=f"cancelar_restaurar_{clave}", width="stretch"):
                st.session_state[CLAVE_CONFIRMAR_RESTAURAR][clave] = False
                st.rerun()
        with col_confirmar:
            if st.button(
                "Si, restaurar",
                type="primary",
                icon=":material/restore:",
                key=f"ok_restaurar_{clave}",
                width="stretch",
            ):
                st.session_state[CLAVE_CONFIRMAR_RESTAURAR][clave] = False
                _restaurar(patologia, pieza["anio"], pieza["codigo"], usuario, clave, forzar=False)


def _confirmar_eliminar_para_siempre(patologia: str, pieza: dict, usuario, clave: str) -> None:
    with st.container(border=True):
        st.warning(
            f":material/warning: Esto destruye **{pieza['archivo_original']}** de forma irreversible. "
            "No se puede deshacer.",
        )
        col_cancelar, col_confirmar = st.columns(2)
        with col_cancelar:
            if st.button("Cancelar", key=f"cancelar_eliminar_{clave}", width="stretch"):
                st.session_state[CLAVE_CONFIRMAR_ELIMINAR][clave] = False
                st.rerun()
        with col_confirmar:
            if st.button(
                "Si, eliminar para siempre",
                type="primary",
                icon=":material/delete_forever:",
                key=f"ok_eliminar_{clave}",
                width="stretch",
            ):
                eliminar_para_siempre(
                    patologia,
                    rutas.directorio_papelera(patologia),
                    pieza["anio"],
                    pieza["codigo"],
                    usuario.nombre_usuario,
                    rol=usuario.rol,
                    confirmado=True,
                )
                st.session_state[CLAVE_CONFIRMAR_ELIMINAR][clave] = False
                st.rerun()


def _resolver_conflicto(patologia: str, pieza: dict, usuario, clave: str) -> None:
    with st.container(border=True):
        st.warning(
            ":material/warning: Ya existe una pieza activa con el mismo año y codigo. "
            "Restaurar la reemplazara."
        )
        col_cancelar, col_reemplazar = st.columns(2)
        with col_cancelar:
            if st.button("Cancelar", key=f"cancelar_conflicto_{clave}", width="stretch"):
                st.session_state[CLAVE_CONFLICTO_RESTAURAR][clave] = False
                st.rerun()
        with col_reemplazar:
            if st.button(
                "Si, reemplazar",
                type="primary",
                icon=":material/published_with_changes:",
                key=f"ok_conflicto_{clave}",
                width="stretch",
            ):
                st.session_state[CLAVE_CONFLICTO_RESTAURAR][clave] = False
                _restaurar(patologia, pieza["anio"], pieza["codigo"], usuario, clave, forzar=True)


def _restaurar(patologia: str, anio: int, codigo: int, usuario, clave: str, forzar: bool) -> None:
    plugin = obtener_patologia(patologia)
    try:
        restaurar_pieza(
            patologia,
            rutas.directorio_piezas(patologia),
            rutas.directorio_papelera(patologia),
            rutas.ruta_consolidado(patologia),
            plugin.columna_anio,
            plugin.columna_codigo,
            anio,
            codigo,
            usuario.nombre_usuario,
            reemplazar_si_existe=forzar,
        )
    except ConflictoDeRestauracion:
        st.session_state.setdefault(CLAVE_CONFLICTO_RESTAURAR, {})[clave] = True
        st.rerun()
        return

    st.session_state.setdefault(CLAVE_CONFLICTO_RESTAURAR, {})[clave] = False
    modulo_datos.actualizar(patologia)
    st.rerun()
