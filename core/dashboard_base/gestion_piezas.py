"""Piezas activas de la patologia: editarlas o moverlas a la papelera.

Rediseñado con tarjetas en lugar de tabla+seleccion de fila: las acciones
estan siempre visibles junto a cada pieza sin requerir que el usuario
seleccione primero una fila y despues encuentre los botones debajo.
"""

import streamlit as st

from core.audit.registro_piezas import listar_piezas_activas
from core.audit.zona_horaria import formatear_fecha_local
from core.dashboard_base import datos as modulo_datos
from core.dashboard_base.gestion_subida import encolar_subida
from core.dashboard_base.paginacion import buscar_y_paginar, mostrar_controles_paginacion
from core.ingestion.papelera import mover_a_papelera
from core.registry import obtener_patologia
from core.storage import rutas

CLAVE_EDITANDO = "piezas_editando"
CLAVE_CONTADOR_UPLOADER_EDITAR = "piezas_contador_widget_uploader_editar"


def mostrar_piezas_activas(patologia: str, usuario) -> None:
    piezas = listar_piezas_activas(patologia)

    if not piezas:
        with st.container(border=True):
            st.info(
                f":material/folder_open: Aun no hay piezas activas para {patologia}. "
                "Usa la pestana Subir para agregar la primera.",
                icon=":material/info:",
            )
        return

    # Primero el año mas reciente; dentro de cada año, orden por codigo
    piezas_ordenadas = sorted(piezas, key=lambda p: (-p["anio"], p["codigo"]))

    pagina_items, pagina, total = buscar_y_paginar(
        piezas_ordenadas,
        clave="piezas_activas",
        campos_busqueda=["archivo_original", "anio", "codigo"],
        placeholder="Buscar por archivo, año o código...",
    )

    for pieza in pagina_items:
        clave_pieza = f"{patologia}_{pieza['anio']}_{pieza['codigo']}"
        _mostrar_tarjeta_pieza(patologia, pieza, usuario, clave_pieza)
        if st.session_state.get(CLAVE_EDITANDO, {}).get(clave_pieza):
            _mostrar_formulario_editar(patologia, pieza, usuario, clave_pieza)

    mostrar_controles_paginacion("piezas_activas", pagina, total)


def _mostrar_tarjeta_pieza(patologia: str, pieza: dict, usuario, clave_pieza: str) -> None:
    with st.container(border=True):
        col_info, col_acciones = st.columns([3, 1], vertical_alignment="center")

        with col_info:
            st.markdown(f":material/description: **{pieza['archivo_original']}**")
            fecha = formatear_fecha_local(pieza["fecha_creacion"])
            st.caption(f"Año {pieza['anio']} · Código {pieza['codigo']} · {fecha}")

        with col_acciones:
            if st.button(
                "Editar",
                icon=":material/edit:",
                key=f"editar_{clave_pieza}",
                width="stretch",
                help="Reemplaza el archivo de esta pieza con una versión corregida.",
            ):
                editando = st.session_state.setdefault(CLAVE_EDITANDO, {})
                editando[clave_pieza] = not editando.get(clave_pieza, False)

            if st.button(
                "Eliminar",
                icon=":material/delete:",
                key=f"eliminar_{clave_pieza}",
                width="stretch",
                help="Mueve esta pieza a la papelera. Es recuperable desde la pestaña Papelera.",
            ):
                _eliminar(patologia, pieza["anio"], pieza["codigo"], usuario)


def _mostrar_formulario_editar(patologia: str, pieza: dict, usuario, clave_pieza: str) -> None:
    anio = pieza["anio"]
    codigo = pieza["codigo"]

    contadores = st.session_state.setdefault(CLAVE_CONTADOR_UPLOADER_EDITAR, {})
    contador = contadores.get(clave_pieza, 0)

    with st.container(border=True):
        st.caption(
            f"Sube la versión corregida de **{pieza['archivo_original']}** "
            f"(Año {anio} · Código {codigo}). El histórico de otras piezas no se toca."
        )
        with st.form(f"editar_pieza_{clave_pieza}", border=False):
            archivo = st.file_uploader(
                "Archivo SIVIGILA (.xls o .xlsx)",
                type=["xls", "xlsx"],
                key=f"archivo_editar_{clave_pieza}_{contador}",
            )
            col_cancelar, col_confirmar = st.columns(2)
            with col_cancelar:
                cancelar = st.form_submit_button("Cancelar", width="stretch")
            with col_confirmar:
                confirmar = st.form_submit_button(
                    "Confirmar y procesar",
                    type="primary",
                    icon=":material/check_circle:",
                    width="stretch",
                )

    if cancelar:
        st.session_state.setdefault(CLAVE_EDITANDO, {})[clave_pieza] = False
        st.rerun()

    if not confirmar:
        return

    if archivo is None:
        st.warning("Selecciona un archivo antes de confirmar.")
        return

    encolar_subida(patologia, anio, codigo, archivo.name, archivo.getvalue(), usuario)
    st.session_state.setdefault(CLAVE_EDITANDO, {})[clave_pieza] = False
    contadores[clave_pieza] = contador + 1


def _eliminar(patologia: str, anio: int, codigo: int, usuario) -> None:
    plugin = obtener_patologia(patologia)
    mover_a_papelera(
        patologia,
        rutas.directorio_piezas(patologia),
        rutas.directorio_papelera(patologia),
        rutas.ruta_consolidado(patologia),
        plugin.columna_anio,
        plugin.columna_codigo,
        anio,
        codigo,
        usuario.nombre_usuario,
    )
    modulo_datos.actualizar(patologia)
    st.rerun()
