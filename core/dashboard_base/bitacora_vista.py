"""Vista de bitacora: quien hizo que movimiento, sobre que pieza, y cuando.

Agregado filtro de tipo de accion por pills para que la bitacora sea util
cuando tiene muchos registros: el usuario puede ver solo las eliminaciones,
solo las restauraciones, etc.
"""

import pandas as pd
import streamlit as st

from core.audit.bitacora import listar_movimientos
from core.audit.zona_horaria import formatear_fecha_local

ETIQUETAS_ACCION = {
    "agregar":            "Agregar",
    "editar":             "Editar",
    "eliminar":           "Eliminar",
    "restaurar":          "Restaurar",
    "eliminar_permanente": "Eliminar para siempre",
}

ICONOS_ACCION = {
    "agregar":            ":material/add_circle:",
    "editar":             ":material/edit:",
    "eliminar":           ":material/delete:",
    "restaurar":          ":material/restore:",
    "eliminar_permanente": ":material/delete_forever:",
}

COLUMNAS_TABLA = {
    "fecha":   "Fecha",
    "accion":  "Acción",
    "anio":    "Año",
    "codigo":  "Código",
    "usuario": "Usuario",
}


def mostrar_bitacora(patologia: str) -> None:
    st.subheader(":material/history: Bitácora de movimientos")

    movimientos = listar_movimientos(patologia=patologia)
    if not movimientos:
        st.caption("Aqui apareceran los movimientos en cuanto haya el primero.")
        return

    # Filtros: tipo de accion (pills) + usuario (selectbox)
    col_accion, col_usuario = st.columns([2, 1])

    with col_accion:
        acciones_presentes = sorted({m["accion"] for m in movimientos})
        accion_elegida = st.pills(
            "Accion",
            options=acciones_presentes,
            format_func=lambda a: ETIQUETAS_ACCION.get(a, a),
            selection_mode="single",
            default=None,
            key="bitacora_filtro_accion",
        )

    with col_usuario:
        usuarios_presentes = sorted({m["usuario"] for m in movimientos})
        opciones_usuario = ["Todos"] + usuarios_presentes
        usuario_elegido = st.selectbox(
            "Usuario",
            options=opciones_usuario,
            key="bitacora_filtro_usuario",
        )

    movimientos_filtrados = movimientos
    if accion_elegida:
        movimientos_filtrados = [m for m in movimientos_filtrados if m["accion"] == accion_elegida]
    if usuario_elegido and usuario_elegido != "Todos":
        movimientos_filtrados = [m for m in movimientos_filtrados if m["usuario"] == usuario_elegido]

    etiquetas_activas = []
    if accion_elegida:
        etiquetas_activas.append(ETIQUETAS_ACCION.get(accion_elegida, accion_elegida))
    if usuario_elegido and usuario_elegido != "Todos":
        etiquetas_activas.append(usuario_elegido)

    st.caption(
        f"{len(movimientos_filtrados)} de {len(movimientos)} movimientos"
        + (f" · {' · '.join(etiquetas_activas)}" if etiquetas_activas else "")
    )

    if not movimientos_filtrados:
        st.caption("Sin movimientos con ese filtro.")
        return

    tabla = pd.DataFrame(movimientos_filtrados)
    tabla["accion"] = tabla["accion"].map(lambda a: ETIQUETAS_ACCION.get(a, a))
    tabla["fecha"] = tabla["fecha"].map(formatear_fecha_local)
    tabla = tabla[list(COLUMNAS_TABLA.keys())].rename(columns=COLUMNAS_TABLA)

    st.dataframe(tabla, hide_index=True, width="stretch", height=320)
