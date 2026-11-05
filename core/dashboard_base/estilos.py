"""Identidad visual del dashboard. Ver DESIGN.md (raiz del repo) para la guia completa.

Regla de oro: verde/amarillo/rojo son exclusivos del canal endemico y los estados
epidemiologicos. Nunca se usan aqui para decorar, botones o acentos. Por eso las
confirmaciones rutinarias de una operacion (subir, restaurar, etc.) usan azul
institucional (st.info) en vez de st.success: el verde queda intacto para cuando
se construya el canal endemico. st.error se mantiene para errores reales
(conexion, validacion) porque es una convencion de accesibilidad bien establecida,
no una decoracion.
"""

import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as componentes_v1

RUTA_ASSETS = Path(__file__).resolve().parents[2] / "assets"
RUTA_ESCUDO_UNIMAGDALENA = RUTA_ASSETS / "unimagdalena.png"
RUTA_ICONO_SIVIDEM = RUTA_ASSETS / "icono_sividem.svg"
RUTA_ICONO_SIVIDEM_PNG = RUTA_ASSETS / "icono_sividem.png"

AZUL_INSTITUCIONAL = "#1b3a6b"
NARANJA_INSTITUCIONAL = "#e8852c"
VERDE_INSTITUCIONAL = "#3f9b46"

# Negro de dato real: en las series de tiempo (pronostico, por ejemplo) la linea
# negra continua es siempre lo que paso de verdad, nunca un modelo.
COLOR_DATO_REAL = "#1a1a1a"

# Regla 1.1 de DESIGN.md: tamano de letra de las graficas. Solo el TAMANO: la
# familia y el color los pone el tema de Streamlit (la misma letra del resto del
# tablero). Las etiquetas de eje, la leyenda y las anotaciones heredan de aqui;
# ninguna queda por debajo de 12.
FUENTE_GRAFICA = dict(size=15)

# Titulo dentro de la figura: primera linea el titulo fijo de la grafica (se ve
# en pantalla completa y en el PNG descargado), segunda linea el contexto
# (patologia, lugar y periodo).
TAMANO_FUENTE_TITULO = 17
TAMANO_FUENTE_CONTEXTO = 14
# Marcas de los ejes, textos sobre las barras y titulos de los ejes.
TAMANO_FUENTE_MARCAS = 14
TAMANO_FUENTE_EJE = 15
COLOR_TEXTO_CONTEXTO = "#4b5563"

# Fondo transparente: los mapas sin el rectangulo blanco se ven mas grandes y se
# integran con el fondo de la tarjeta.
FONDO_TRANSPARENTE = "rgba(0,0,0,0)"

# Regla 1.5: en un par con filtro cruzado, lo seleccionado queda a color pleno y
# lo demas atenuado, para que se vea de un vistazo que esta elegido.
OPACIDAD_ATENUADA = 0.28

# Regla 1.2 de DESIGN.md: la barra de herramientas de Plotly solo aparece al pasar
# el mouse y solo con los botones que sirven (descargar imagen, zoom, mover y
# volver a la vista inicial). Se quitan los demas en vez de listar los que quedan
# porque los mapas tienen sus propios botones de zoom (zoomInGeo, resetGeo) que
# si sirven y que una lista cerrada de botones cartesianos dejaria por fuera.
CONFIG_PLOTLY = {
    "displaylogo": False,
    "displayModeBar": "hover",
    "modeBarButtonsToRemove": [
        "zoomIn2d",
        "zoomOut2d",
        "autoScale2d",
        "select2d",
        "lasso2d",
        "hoverClosestCartesian",
        "hoverCompareCartesian",
        "toggleSpikelines",
        "hoverClosestGeo",
        "hoverClosestPie",
        "toggleHover",
    ],
    "toImageButtonOptions": {"format": "png", "scale": 2},
}

# Leyenda horizontal encima del area de dibujo, anclada a la IZQUIERDA: a la
# derecha queda justo debajo de la barra de herramientas de Plotly y la tapa.
LEYENDA_SUPERIOR = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0)


def eje_semanal(ultima_semana: int, dtick: int = 1) -> dict:
    """Configuracion del eje X para graficas por semana epidemiologica.

    Todas las semanas quedan etiquetadas (1 a la ultima con datos), con el numero
    horizontal para que se lea claro. minallowed/maxallowed impiden que al hacer
    pan o zoom aparezcan semanas negativas o mayores a las que existen.
    dtick=2 solo en una grafica concreta donde las 53 semanas se amontonen.
    Aplicar con fig.update_xaxes(**eje_semanal(n)) o dentro del dict xaxis del layout.
    """
    return dict(
        tickmode="linear",
        tick0=1,
        dtick=dtick,
        tickangle=0,
        tickfont=dict(size=13),
        minallowed=0.5,
        maxallowed=ultima_semana + 0.5,
    )


# Alturas aproximadas (px) de lo que va encima del area de dibujo, para que el
# margen superior alcance justo y no quede ni apinado ni con un hueco grande.
_ALTO_TITULO_DOS_LINEAS = 62
_ALTO_FILA_LEYENDA = 34
_RESPIRO_SUPERIOR = 10
_CENTRO_TITULO_DESDE_ARRIBA = 38
# Altura con que st.plotly_chart dibuja una figura que no declara la suya. El
# tema la fija explicitamente: la posicion del titulo se calcula en pixeles y
# tiene que coincidir con la altura real en cualquier pantalla.
_ALTURA_POR_DEFECTO = 450

# Ancho que se supone para una grafica a ancho completo y para una de media
# columna (pares complementarios), al estimar cuantas filas ocupa la leyenda.
ANCHO_COMPLETO = 1200
ANCHO_MEDIA_COLUMNA = 600
# Ancho aproximado (px) de cada caracter y de la muestra de color de una entrada
# de la leyenda, con letra de 15.
_ANCHO_CARACTER_LEYENDA = 8.2
_ANCHO_MUESTRA_LEYENDA = 46


def _filas_de_leyenda(fig, ancho: int) -> int:
    """Cuantas filas ocupa la leyenda horizontal en ese ancho. Una leyenda
    larga en media columna parte en dos filas y, si el margen solo contaba una,
    se montaba sobre el titulo."""
    nombres = []
    for traza in fig.data:
        if traza.type == "pie":
            etiquetas = traza.labels if traza.labels is not None else []
            nombres.extend(str(etiqueta) for etiqueta in etiquetas)
            continue
        if traza.type == "sankey":
            continue
        if traza.showlegend is False or not traza.name:
            continue
        nombres.append(str(traza.name))
    if not nombres:
        return 1
    filas = 1
    ocupado = 0.0
    disponible = ancho * 0.92
    for nombre in nombres:
        ancho_entrada = _ANCHO_MUESTRA_LEYENDA + _ANCHO_CARACTER_LEYENDA * len(nombre)
        if ocupado + ancho_entrada > disponible and ocupado > 0:
            filas += 1
            ocupado = 0.0
        ocupado += ancho_entrada
    return filas


def _tiene_leyenda(fig) -> bool:
    if fig.layout.showlegend is False:
        return False
    if fig.layout.showlegend is True:
        return True
    trazas_en_leyenda = [
        traza for traza in fig.data
        if traza.showlegend is not False and traza.type != "sankey"
    ]
    if any(traza.type == "pie" for traza in fig.data):
        return True
    if any(traza.showlegend is True for traza in trazas_en_leyenda):
        return True
    return len(trazas_en_leyenda) >= 2


def _valores_no_negativos(valores) -> bool:
    if valores is None:
        return False
    numericos = []
    for valor in valores:
        if valor is None:
            continue
        try:
            numericos.append(float(valor))
        except (TypeError, ValueError):
            return False
    return bool(numericos) and min(numericos) >= 0


def _impedir_valores_negativos(fig) -> None:
    """Un conteo o una tasa nunca es negativo: si todas las barras o lineas de
    un eje de valores son >= 0, el eje no deja hacer pan ni zoom por debajo de
    cero (minallowed). La piramide (hombres en negativo) queda por fuera sola,
    porque sus valores son negativos."""
    ejes_x_positivos = []
    ejes_y_positivos = []
    for traza in fig.data:
        if traza.type == "bar":
            if traza.orientation == "h":
                ejes_x_positivos.append(_valores_no_negativos(traza.x))
            else:
                ejes_y_positivos.append(_valores_no_negativos(traza.y))
        elif traza.type == "scatter":
            ejes_y_positivos.append(_valores_no_negativos(traza.y))
    if ejes_x_positivos and all(ejes_x_positivos):
        fig.update_xaxes(minallowed=0)
    if ejes_y_positivos and all(ejes_y_positivos):
        fig.update_yaxes(minallowed=0)


def aplicar_tema(fig, titulo: str | None = None, contexto: str | None = None, ancho: int = ANCHO_COMPLETO):
    """Aplica las reglas 1.1 a 1.3 de DESIGN.md a una figura de Plotly.

    - Letra: solo el tamano (la familia es la del tema de Streamlit).
    - Titulo dentro de la figura: el titulo fijo en negrita y debajo el contexto
      (patologia, lugar y periodo, ver filtros.resumen_filtros_activos). Va
      DENTRO de la figura porque en pantalla completa y en el PNG descargado con
      la camara de Plotly el st.subheader de la pagina no aparece.
    - Margen superior calculado segun haya titulo y leyenda, para que la barra
      de herramientas caiga sobre el margen y nada quede apinado ni con un hueco.
    - Leyenda arriba a la izquierda, sin titulo de leyenda.
    - Mapas sin fondo blanco; ejes con margen automatico para que el titulo del
      eje X no se corte; ejes de conteos que no bajan de cero.

    - Ningun texto de la grafica se encoge por debajo de 13 (uniformtext): sin
      esto, Plotly achica la etiqueta de una barra delgada hasta volverla
      ilegible.

    ancho: ancho aproximado en pantalla (ANCHO_MEDIA_COLUMNA en los pares), para
    reservar las filas que de verdad ocupa la leyenda.

    Respeta un margen superior mayor o una posicion de leyenda mas alta que ya
    traiga la figura (ej. el Sankey, con encabezados de columna encima).
    """
    if fig.layout.height is None:
        fig.update_layout(height=_ALTURA_POR_DEFECTO)

    lleva_titulo = bool(titulo or contexto)
    lleva_leyenda = _tiene_leyenda(fig)

    margen_necesario = _RESPIRO_SUPERIOR
    if lleva_titulo:
        margen_necesario += _ALTO_TITULO_DOS_LINEAS
    if lleva_leyenda:
        margen_necesario += _ALTO_FILA_LEYENDA * _filas_de_leyenda(fig, ancho)
    margen_actual = fig.layout.margin.t or 0
    margen_superior = max(margen_actual, margen_necesario)

    # Anillos: la etiqueta de afuera de una porcion chica se salia por arriba y
    # chocaba con la leyenda. Se deja aire entre el anillo y la leyenda.
    fig.update_traces(domain=dict(y=[0, 0.88]), selector=dict(type="pie"))

    posicion_leyenda = fig.layout.legend.y
    if posicion_leyenda is None or posicion_leyenda < 1:
        posicion_leyenda = 1.02

    fig.update_layout(
        font=FUENTE_GRAFICA,
        margin=dict(t=margen_superior),
        legend=dict(
            orientation="h", yanchor="bottom", y=posicion_leyenda, xanchor="left", x=0,
            title_text="", font=dict(size=FUENTE_GRAFICA["size"]),
        ),
        hoverlabel=dict(font=dict(size=14)),
        paper_bgcolor=FONDO_TRANSPARENTE,
        uniformtext=dict(minsize=13, mode="show"),
    )

    tiene_mapa = any(traza.type == "choropleth" for traza in fig.data)
    if tiene_mapa:
        fig.update_geos(bgcolor=FONDO_TRANSPARENTE, showframe=False)
        # Barra de color angosta y pegada al mapa: con el ancho por defecto
        # quedaba un hueco grande entre el mapa y la barra.
        if fig.layout.coloraxis.colorscale is not None:
            fig.update_layout(coloraxis_colorbar=dict(thickness=12, len=0.75, xpad=4))
    else:
        # automargin + standoff: el titulo de cada eje queda separado de sus
        # etiquetas y nunca se corta (tampoco en pantalla completa).
        fig.update_xaxes(automargin=True, title_standoff=10, title_font_size=TAMANO_FUENTE_EJE)
        fig.update_yaxes(automargin=True, title_standoff=12, title_font_size=TAMANO_FUENTE_EJE)
        # Las marcas de un eje que ya declaro su tamano (ej. el eje semanal, con
        # 53 semanas) se respetan; las demas suben al tamano comun.
        if fig.layout.xaxis.tickfont.size is None:
            fig.update_xaxes(tickfont_size=TAMANO_FUENTE_MARCAS)
        if fig.layout.yaxis.tickfont.size is None:
            fig.update_yaxes(tickfont_size=TAMANO_FUENTE_MARCAS)
        fig.update_traces(textfont_size=TAMANO_FUENTE_MARCAS, selector=dict(type="bar"))
        _impedir_valores_negativos(fig)

    if lleva_titulo:
        partes = []
        if titulo:
            partes.append(f"<b>{titulo}</b>")
        if contexto:
            partes.append(
                f"<span style='font-size:{TAMANO_FUENTE_CONTEXTO}px;color:{COLOR_TEXTO_CONTEXTO}'>{contexto}</span>"
            )
        # Se ancla el CENTRO del bloque de dos lineas a una distancia fija del
        # borde superior: con yanchor="top" Plotly ubica mal un titulo de varias
        # lineas y la primera quedaba recortada arriba.
        altura = fig.layout.height or _ALTURA_POR_DEFECTO
        fig.update_layout(
            title=dict(
                text="<br>".join(partes),
                x=0,
                xanchor="left",
                xref="container",
                y=1 - _CENTRO_TITULO_DESDE_ARRIBA / altura,
                yanchor="middle",
                yref="container",
                pad=dict(t=0, l=6),
                font=dict(size=TAMANO_FUENTE_TITULO),
            )
        )
    return fig


def mostrar_grafica(fig, titulo: str | None = None, contexto: str | None = None, **opciones_plotly_chart):
    """Unica puerta de entrada de una figura a la pagina: aplica el tema y la
    dibuja con CONFIG_PLOTLY. Asi ninguna grafica queda sin la configuracion de
    la barra de herramientas (regla 1.2). Devuelve lo mismo que st.plotly_chart
    (incluida la seleccion, cuando se pasa on_select).
    """
    ancho = opciones_plotly_chart.pop("ancho", ANCHO_COMPLETO)
    aplicar_tema(fig, titulo, contexto, ancho=ancho)
    opciones = {"width": "stretch", **opciones_plotly_chart}
    return st.plotly_chart(fig, config=CONFIG_PLOTLY, **opciones)


# ---------------------------------------------------------------------------
# Guarda de datos insuficientes (fase 4, observacion 13)
# ---------------------------------------------------------------------------

# Umbrales por tipo de grafica. Una grafica con una sola barra no comunica nada.
MINIMO_CATEGORIAS_DISTRIBUCION = 2
MINIMO_PUNTOS_SERIE = 4
MINIMO_ANIOS_COMPARATIVA = 2


def hay_datos_suficientes(df, minimo_categorias: int = MINIMO_CATEGORIAS_DISTRIBUCION) -> bool:
    """True si la tabla ya agregada (una fila por categoria, semana o anio) tiene
    al menos minimo_categorias filas. Se aplica antes de dibujar cualquier
    grafica de distribucion o de serie.
    """
    if df is None:
        return False
    cantidad_filas = len(df)
    return cantidad_filas >= minimo_categorias


def describir_cantidad(cantidad: int, singular: str, plural: str, femenino: bool = True) -> str:
    """'una sola semana epidemiologica', 'un solo grupo', '3 semanas...'. Para
    armar el mensaje de datos insuficientes en castellano correcto."""
    if cantidad == 0:
        articulo_cero = "ninguna" if femenino else "ningun"
        return f"{articulo_cero} {singular}"
    if cantidad == 1:
        articulo_uno = "una sola" if femenino else "un solo"
        return f"{articulo_uno} {singular}"
    return f"{cantidad:,} {plural}"


def avisar_datos_insuficientes(mensaje: str) -> None:
    """Reemplaza la grafica cuando no hay datos suficientes. El mensaje debe decir
    cuantos registros hay y que ampliar: un 'Sin datos' seco no deja saber si es
    un error del sistema o del filtro. Se llama dentro del mismo contenedor con
    borde de la grafica, para que la pagina no cambie de estructura.
    """
    st.info(mensaje, icon=":material/filter_alt:")

def rango_con_margen(valor_maximo: float, factor: float = 1.2) -> list[float]:
    """Rango de eje con espacio extra para el texto "outside" de una barra.

    Sin esto, la etiqueta de la barra mas alta (barras verticales) o mas larga
    (barras horizontales) queda cortada contra el borde del area de dibujo,
    porque el autorange de Plotly llega justo hasta el valor de la barra, no
    hasta donde termina su texto. Aplicar con fig.update_yaxes(range=...) en
    barras verticales o fig.update_xaxes(range=...) en barras horizontales,
    usando el maximo del valor graficado (no el eje de categorias).
    """
    if valor_maximo is None or valor_maximo <= 0:
        return [0, 1]
    return [0, valor_maximo * factor]


COLOR_EXITO_EPIDEMIOLOGICO = "#3f9b46"
COLOR_SEGURIDAD_EPIDEMIOLOGICO = "#6fb574"
COLOR_ALERTA_EPIDEMIOLOGICO = "#efb23c"
COLOR_EPIDEMIA = "#d0473f"

def aplicar_estilos() -> None:
    """Inyecta el CSS compartido. Se llama en cada rerun (login y dashboard) a proposito:
    Streamlit quita del DOM cualquier elemento que un rerun no vuelva a emitir, asi que un
    guard de "solo una vez por sesion" hacia que el bloque de estilos sobreviviera unicamente
    en el primer render (la pantalla de login) y desapareciera en todos los reruns
    posteriores del dashboard. Emitirlo siempre es barato (es solo texto) y evita ese bug.
    """
    st.html(
        """
        <style>
        /* Regla 1.1 de DESIGN.md: letra mas grande para que el tablero se lea
           proyectado. Sube el cuerpo y las etiquetas de los controles; los
           titulos de seccion no suben en la misma proporcion para no aplanar
           la jerarquia visual. */
        /* Solo el texto de st.markdown: las tarjetas de KPI (st.metric) tambien
           usan stMarkdownContainer por dentro y se dejan como estaban. */
        div[data-testid="stMarkdown"] div[data-testid="stMarkdownContainer"] p,
        div[data-testid="stMarkdown"] div[data-testid="stMarkdownContainer"] li {
            font-size: 1.08rem;
        }
        div[data-testid="stCaptionContainer"],
        div[data-testid="stCaptionContainer"] p {
            font-size: 0.98rem !important;
        }
        div[data-testid="stWidgetLabel"] p,
        div[data-testid="stWidgetLabel"] label {
            font-size: 1.12rem !important;
        }
        /* Etiqueta de las tarjetas de KPI (ej. "Incidencia"): mas grande, sin
           tocar el valor ni el resto de la tarjeta. */
        div[data-testid="stMetricLabel"] div[data-testid="stMarkdownContainer"] p {
            font-size: 1.1rem !important;
        }
        div[data-testid="stAlert"] div[data-testid="stMarkdownContainer"] p {
            font-size: 1.05rem !important;
        }
        div[data-testid="stExpander"] summary div[data-testid="stMarkdownContainer"] p {
            font-size: 1.05rem !important;
        }
        [data-testid^="stBaseButton-segmented_control"] div[data-testid="stMarkdownContainer"] p,
        [data-testid^="stBaseButton-pills"] div[data-testid="stMarkdownContainer"] p {
            font-size: 1.02rem !important;
        }
        div[data-baseweb="select"] div {
            font-size: 1.02rem;
        }
        /* Nombres de las pestanas (Situacion, Pronostico, ...). */
        button[data-baseweb="tab"] div[data-testid="stMarkdownContainer"] p {
            font-size: 1.12rem !important;
        }
        div[data-testid="stForm"] {
            background-color: #ffffff;
            border: 0.5px solid #e2e5ea;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        div[data-testid="stMainBlockContainer"] {
            padding-top: 2.5rem;
            padding-bottom: 2rem;
        }
        div[data-testid="stDataFrame"] {
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        .st-key-barra_superior {
            background-color: #ffffff !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 0.6rem 1.6rem !important;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07);
        }
        .st-key-encabezado_fijo {
            background-color: #EEF1F5 !important;
            padding-bottom: 0.3rem !important;
            gap: 0.5rem !important;
        }
        .st-key-encabezado_fijo h1 {
            margin-bottom: 0 !important;
            padding-bottom: 0 !important;
        }
        /* Streamlit envuelve cada elemento de nivel superior en un stLayoutWrapper que,
           por su layout flex interno, rompe position:sticky en sus hijos directos. El
           sticky si funciona aplicado al wrapper mismo, por eso se selecciona con :has().
           Todo el encabezado (titulo, contador de registros y marca/patologia/usuario) se
           fija como un solo bloque, para que nunca se pierda de vista al hacer scroll en el
           contenido de cualquier pestana. El fondo opaco y el ancho completo van en el
           wrapper (no solo en el div interno) para que nada del contenido que se desliza por
           detras se asome en los bordes; el z-index alto y el box-shadow inferior lo separan
           visualmente del contenido, para que se vea como una capa flotando y no como un
           corte abrupto. */
        /* El selector :has() aplica al instante en navegadores modernos; la
           clase .sividem-header-fijo la agrega via JS el script de
           aplicar_estilos() y cubre navegadores sin :has() (ej. Firefox
           viejo), donde de lo contrario el header no se fijaria nunca. */
        div[data-testid="stLayoutWrapper"]:has(.st-key-encabezado_fijo),
        .sividem-header-fijo {
            position: sticky !important;
            top: 60px !important;
            z-index: 9999 !important;
            width: 100% !important;
            background-color: #EEF1F5 !important;
            box-shadow: 0 6px 10px -4px rgba(16, 24, 40, 0.12) !important;
        }
        [data-testid^="stBaseButton-"] {
            border-radius: 8px !important;
        }
        .st-key-tarjeta_login {
            background-color: #ffffff;
            border-radius: 16px;
            box-shadow: 0 1px 3px rgba(16, 24, 40, 0.07), 0 10px 28px rgba(16, 24, 40, 0.07);
            overflow: hidden;
            margin-top: 7vh;
        }
        .st-key-tarjeta_login div[data-testid="stForm"] {
            border: none;
            box-shadow: none;
            border-radius: 0;
            padding: 0.5rem 2.5rem 2rem 2.5rem;
            background-color: transparent;
        }
        .st-key-tarjeta_login label p {
            font-size: 1rem !important;
        }
        .st-key-tarjeta_login input {
            font-size: 1.05rem !important;
        }
        /* Lista de pestanas sticky justo debajo del header SIVIDEM.
           El top exacto depende de la altura real del header (que varia con
           banners y titulos): un script en aplicar_estilos() lo mide en vivo y
           lo publica en la variable --sividem-tabs-top; 225px es solo el
           respaldo si el script aun no corrio. z-index 9999 (igual al header):
           el tab list aparece despues en el DOM asi que pinta encima si llegan
           a rozarse. */
        div[data-testid="stTabs"] div:has(> div[role="tablist"]),
        .sividem-tabs-fijas {
            position: sticky !important;
            top: var(--sividem-tabs-top, 225px) !important;
            z-index: 9999 !important;
            width: 100% !important;
            background-color: #EEF1F5 !important;
            padding-top: 0 !important;
            padding-left: 0.4rem;
            margin-top: 0 !important;
            box-shadow: 0 6px 10px -4px rgba(16, 24, 40, 0.12) !important;
        }
        /* Padding en el panel de cada pestana para que el primer elemento
           no quede tapado por la barra de navegacion sticky al hacer scroll. */
        [role="tabpanel"] > div:first-child {
            padding-top: 1rem !important;
        }
        /* Las pestanas dentro de un dialogo (ej. metodologia del canal endemico) no
           necesitan sticky: el top:225px se calculo para el header fijo de la pagina
           principal, no tiene sentido dentro de un modal. Selector mas especifico que
           el de arriba para ganar sobre el !important. */
        div[data-testid="stDialog"] div[data-testid="stTabs"] div:has(> div[role="tablist"]),
        div[data-testid="stDialog"] div[data-testid="stTabs"] div[role="tablist"] {
            position: static !important;
            top: auto !important;
            z-index: auto !important;
            box-shadow: none !important;
        }
        </style>
        """
    )
    _publicar_altura_header()


def _publicar_altura_header() -> None:
    """Script de apoyo del encabezado y el tab bar fijos. Hace dos cosas:

    1. Mide la altura real del header y publica el top del tab bar como
       variable CSS --sividem-tabs-top (60px del toolbar + altura del header +
       10px de margen). Asi el tab bar queda SIEMPRE justo debajo del header
       aunque este crezca (banners, titulo largo).
    2. Marca con clases propias (.sividem-header-fijo, .sividem-tabs-fijas)
       los elementos que deben fijarse: es el respaldo de los selectores
       :has() del CSS para navegadores que no los soportan.

    Corre en un iframe de componente porque st.html no ejecuta <script>. El
    intervalo re-consulta el DOM en cada tick porque Streamlit reemplaza nodos
    entre reruns (y React puede pisar las clases agregadas). El iframe mide
    0px y no agrega nada visible.
    """
    componentes_v1.html(
        """
        <script>
        const doc = window.parent.document;
        function actualizar() {
            const marcador = doc.querySelector('.st-key-encabezado_fijo');
            if (!marcador) { return; }
            const header = marcador.closest('[data-testid="stLayoutWrapper"]') || marcador;
            header.classList.add('sividem-header-fijo');
            const topTabs = 60 + header.offsetHeight + 10;
            doc.documentElement.style.setProperty('--sividem-tabs-top', topTabs + 'px');
            doc.querySelectorAll('div[role="tablist"]').forEach(function (lista) {
                if (lista.closest('[data-testid="stDialog"]')) { return; }
                const barra = lista.parentElement;
                if (barra) { barra.classList.add('sividem-tabs-fijas'); }
            });
        }
        actualizar();
        setInterval(actualizar, 1000);
        </script>
        """,
        height=0,
    )


@st.cache_data(show_spinner=False)
def imagen_a_data_uri(ruta: Path) -> str:
    """Codifica una imagen de assets/ como data URI para incrustarla en HTML."""
    contenido = ruta.read_bytes()
    codificado = base64.b64encode(contenido).decode("ascii")
    if ruta.suffix.lower() == ".svg":
        tipo_mime = "image/svg+xml"
    else:
        tipo_mime = "image/png"
    return f"data:{tipo_mime};base64,{codificado}"
