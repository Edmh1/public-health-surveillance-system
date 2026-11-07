"""Lectura de docs/pronostico.md y ejemplos reales de los archivos de un paquete.

docs/pronostico.md es la fuente central de la documentacion del pronostico. La
Fundamentacion de la pestana y la guia "Ver estructura del paquete" de Gestion
muestran sus secciones tal cual, para que la aplicacion y la documentacion
tecnica no se contradigan. Los comentarios <!-- app:nombre --> marcan donde la
aplicacion inserta una grafica o una tabla con los datos del modelo activo.

Modulo de calculo puro: sin Streamlit.
"""

import json
import re
import zipfile
from pathlib import Path

RUTA_DOCUMENTACION = Path(__file__).resolve().parents[3] / "docs" / "pronostico.md"

_PATRON_SECCION = re.compile(r"^## (\d+)\. (.+)$", re.MULTILINE)
_PATRON_MARCADOR = re.compile(r"<!-- app:(\w+) -->")

TIPO_TEXTO = "texto"
TIPO_MARCADOR = "marcador"

_LINEAS_MAXIMAS_TEXTO = 20
_CARACTERES_MAXIMOS_JSON = 900


def leer_secciones(ruta: Path = RUTA_DOCUMENTACION) -> dict[int, dict[str, str]]:
    """{numero: {"titulo", "contenido"}} de cada seccion "## N. Titulo"."""
    texto = ruta.read_text(encoding="utf-8")
    coincidencias = list(_PATRON_SECCION.finditer(texto))
    secciones = {}
    for posicion, coincidencia in enumerate(coincidencias):
        inicio_contenido = coincidencia.end()
        if posicion + 1 < len(coincidencias):
            fin_contenido = coincidencias[posicion + 1].start()
        else:
            fin_contenido = len(texto)
        numero = int(coincidencia.group(1))
        secciones[numero] = {
            "titulo": coincidencia.group(2).strip(),
            "contenido": texto[inicio_contenido:fin_contenido].strip(),
        }
    return secciones


def partir_por_marcadores(contenido: str) -> list[tuple[str, str]]:
    """Trozos de una seccion en orden: (TIPO_TEXTO, markdown) o
    (TIPO_MARCADOR, nombre)."""
    trozos = []
    posicion = 0
    for coincidencia in _PATRON_MARCADOR.finditer(contenido):
        texto = contenido[posicion:coincidencia.start()].strip()
        if texto:
            trozos.append((TIPO_TEXTO, texto))
        trozos.append((TIPO_MARCADOR, coincidencia.group(1)))
        posicion = coincidencia.end()
    resto = contenido[posicion:].strip()
    if resto:
        trozos.append((TIPO_TEXTO, resto))
    return trozos


def quitar_marcadores(contenido: str) -> str:
    return _PATRON_MARCADOR.sub("", contenido).strip()


def _tamano_legible(cantidad_bytes: int) -> str:
    if cantidad_bytes < 1024:
        return f"{cantidad_bytes} B"
    if cantidad_bytes < 1024 * 1024:
        return f"{cantidad_bytes / 1024:.1f} KB"
    return f"{cantidad_bytes / (1024 * 1024):.1f} MB"


def arbol_del_paquete(carpeta: Path, manifest: dict) -> str:
    """Estructura del .zip que se obtiene de una version, con el tamano real
    de cada archivo y que es."""
    descripciones = {
        "manifest.json": "metadatos, hiperparámetros, librerías y métricas de la prueba",
        manifest.get("archivo_pronosticos_prueba", ""): "resultados individuales de la prueba",
    }
    for nombre in manifest.get("archivos_modelo", []):
        if nombre.endswith(".keras"):
            descripciones[nombre] = "modelo definitivo entrenado (arquitectura y pesos)"
        elif nombre == "escalador.json":
            descripciones[nombre] = "auxiliar: escalado de la ventana de entrada"
        else:
            descripciones[nombre] = "modelo definitivo entrenado (formato nativo)"

    archivos = sorted(ruta for ruta in carpeta.iterdir() if ruta.is_file())
    lineas = [f"{manifest.get('modelo', 'modelo')}.zip"]
    for posicion, ruta in enumerate(archivos):
        es_ultimo = posicion == len(archivos) - 1
        rama = "└──" if es_ultimo else "├──"
        descripcion = descripciones.get(ruta.name, "")
        tamano = _tamano_legible(ruta.stat().st_size)
        lineas.append(f"{rama} {ruta.name:<26} {tamano:>9}   {descripcion}")
    return "\n".join(lineas)


def _muestra_de_texto(ruta: Path) -> str:
    lineas = ruta.read_text(encoding="utf-8").splitlines()
    muestra = lineas[:_LINEAS_MAXIMAS_TEXTO]
    if len(lineas) > _LINEAS_MAXIMAS_TEXTO:
        muestra.append(f"... ({len(lineas) - _LINEAS_MAXIMAS_TEXTO} líneas más)")
    return "\n".join(muestra)


def _muestra_de_json(ruta: Path) -> str:
    texto = ruta.read_text(encoding="utf-8")
    if len(texto) <= _CARACTERES_MAXIMOS_JSON:
        return texto
    return texto[:_CARACTERES_MAXIMOS_JSON] + f"\n... ({len(texto) - _CARACTERES_MAXIMOS_JSON} caracteres más)"


def _muestra_de_keras(ruta: Path) -> str:
    """Un .keras es a su vez un .zip de Keras 3: se listan sus partes."""
    lineas = [
        f"{ruta.name} es un archivo binario de Keras 3 (un .zip interno) de "
        f"{_tamano_legible(ruta.stat().st_size)}. Contiene:"
    ]
    with zipfile.ZipFile(ruta) as interno:
        for entrada in interno.infolist():
            lineas.append(f"  {entrada.filename:<22} {_tamano_legible(entrada.file_size)}")
    lineas.append("config.json: la arquitectura; model.weights.h5: los pesos entrenados.")
    return "\n".join(lineas)


def ejemplos_de_archivos(carpeta: Path, manifest: dict) -> list[dict[str, str]]:
    """Muestra real de cada archivo de una version: [{"titulo", "lenguaje",
    "contenido"}]. Los archivos grandes se recortan."""
    ejemplos = []
    nombre_csv = manifest.get("archivo_pronosticos_prueba")
    orden = ["manifest.json"]
    if nombre_csv:
        orden.append(nombre_csv)
    orden.extend(manifest.get("archivos_modelo", []))

    for nombre in orden:
        ruta = carpeta / nombre
        if not ruta.exists():
            continue
        if nombre.endswith(".keras"):
            contenido = _muestra_de_keras(ruta)
            lenguaje = "text"
        elif nombre.endswith(".json"):
            if nombre == "manifest.json":
                contenido = json.dumps(manifest, ensure_ascii=False, indent=2)
            else:
                contenido = _muestra_de_json(ruta)
            lenguaje = "json"
        else:
            contenido = _muestra_de_texto(ruta)
            lenguaje = "text"
        ejemplos.append({"titulo": nombre, "lenguaje": lenguaje, "contenido": contenido})
    return ejemplos
