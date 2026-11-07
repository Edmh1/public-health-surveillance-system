"""Exportar una version de un modelo y revisar un paquete .zip subido.

Las dos formas de crear una version pasan por el mismo mecanismo de exportacion:
- En la app, el worker llama a entrenar_evaluar_y_guardar con origen "sistema".
- Fuera de la app (por ejemplo, en un equipo con GPU) se llama a la misma
  funcion con el codigo del tablero y despues a exportar_zip; el .zip se sube
  desde Gestion y el worker lo revisa con revisar_paquete.

Contenido del paquete (archivos en la raiz del .zip o dentro de una sola
carpeta):
- manifest.json: metadatos, hiperparametros, librerias y metricas de la prueba.
- pronosticos_prueba.csv: resultados individuales de la prueba (fuente de verdad
  de las metricas).
- Los archivos del modelo definitivo en el formato nativo de su libreria y, en
  las redes, el escalador (ModeloPronostico.archivos_exportados).

Solo se aceptan formatos que no ejecutan codigo al cargarse (JSON, CSV, texto de
LightGBM y .keras de Keras 3 en modo seguro): nunca pickle ni joblib. Revisar un
paquete NO entrena: carga el modelo ya entrenado y hace un pronostico de prueba.
"""

import importlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from pathologies.dengue.pronostico import catalogo, evaluacion, inferencia
from pathologies.dengue.pronostico.configuracion import DEFINICION_SERIE, HORIZONTE_MAXIMO_SEMANAS
from pathologies.dengue.pronostico.manifest import (
    ARCHIVO_MANIFEST,
    ARCHIVO_PRONOSTICOS_PRUEBA,
    FORMATO_MANIFEST,
    ORIGEN_SUBIDO,
    campos_faltantes,
    construir_manifest,
)

_EXTENSIONES_PERMITIDAS = {".json", ".csv", ".txt", ".keras"}

# Diferencia relativa admitida entre las metricas del manifest y las que se
# reconstruyen desde el CSV (redondeo de punto flotante al escribir el CSV).
_TOLERANCIA_METRICAS = 1e-6

COMPATIBILIDAD_IGUAL = "igual"
COMPATIBILIDAD_MENOR_DISTINTA = "versión menor distinta"


def _escribir_manifest(carpeta: Path, manifest: dict) -> None:
    ruta = carpeta / ARCHIVO_MANIFEST
    ruta.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _escribir_pronosticos_prueba(carpeta: Path, registros: pd.DataFrame) -> None:
    """Valores sin redondear (Python escribe la representacion exacta de cada
    float); las fechas como AAAA-MM-DD."""
    registros.to_csv(carpeta / ARCHIVO_PRONOSTICOS_PRUEBA, index=False, date_format="%Y-%m-%d")


def entrenar_evaluar_y_guardar(
    clave_modelo: str,
    hiperparametros: dict[str, Any] | None,
    serie: pd.DataFrame,
    carpeta: Path,
    usuario: str,
    origen: str,
) -> dict[str, Any]:
    """Crea una version completa en carpeta, en este orden:

    1. Evalua: entrena el modelo de evaluacion con el primer 85 % de la serie y
       pronostica desde cada semana de origen del 15 % final (evaluacion.
       evaluar_en_prueba).
    2. Guarda los resultados individuales en pronosticos_prueba.csv y calcula
       desde ellos las metricas globales y por horizonte.
    3. Entrena el modelo definitivo con el 100 % de la serie y lo exporta en el
       formato nativo de su libreria. El modelo de evaluacion se descarta.
    4. Escribe el manifest.

    La evaluacion va primero a proposito: es la parte que puede fallar por
    historico insuficiente, y asi falla antes de entrenar el modelo definitivo.
    """
    clase = catalogo.obtener_modelo(clave_modelo)
    faltantes = clase.paquetes_faltantes()
    if faltantes:
        raise ValueError(f"Falta instalar: {', '.join(faltantes)}.")

    resultado_prueba = evaluacion.evaluar_en_prueba(clase, hiperparametros, serie)
    registros = resultado_prueba["registros"]
    metricas = evaluacion.metricas_desde_registros(registros)

    carpeta.mkdir(parents=True, exist_ok=True)
    _escribir_pronosticos_prueba(carpeta, registros)

    modelo_definitivo = clase(hiperparametros)
    modelo_definitivo.entrenar(serie)
    archivos_modelo = modelo_definitivo.guardar(carpeta)

    manifest = construir_manifest(
        modelo_definitivo,
        serie,
        resultado_prueba,
        metricas,
        archivos_modelo,
        usuario,
        origen,
    )
    _escribir_manifest(carpeta, manifest)
    return manifest


def exportar_zip(carpeta: Path, ruta_zip: Path) -> Path:
    """Empaqueta una carpeta escrita por entrenar_evaluar_y_guardar en un .zip
    con los archivos en la raiz, listo para subir desde Gestion."""
    ruta_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ruta_zip, "w", compression=zipfile.ZIP_DEFLATED) as archivo_zip:
        for ruta in sorted(carpeta.iterdir()):
            if ruta.is_file():
                archivo_zip.write(ruta, arcname=ruta.name)
    return ruta_zip


def leer_pronosticos_prueba(carpeta: Path, manifest: dict) -> pd.DataFrame | None:
    """Resultados individuales de la prueba de una version, o None si la version
    no los tiene (versiones del esquema anterior)."""
    nombre = manifest.get("archivo_pronosticos_prueba")
    if not nombre:
        return None
    ruta = carpeta / nombre
    if not ruta.exists():
        return None
    return pd.read_csv(ruta, parse_dates=["fecha_origen", "fecha_objetivo"])


# ---------------------------------------------------------------------------
# Revision de un paquete subido
# ---------------------------------------------------------------------------

def _version_mayor(version: str) -> int | None:
    coincidencia = re.match(r"\d+", str(version))
    if coincidencia is None:
        return None
    return int(coincidencia.group())


def comprobar_compatibilidad(clase, librerias_exportadas: dict[str, str]) -> dict[str, dict]:
    """Compara la version de cada libreria del modelo con la instalada. Con otra
    version MAYOR el paquete se rechaza (los formatos nativos no garantizan
    compatibilidad entre versiones mayores); con otra version menor se acepta y
    queda registrado. Devuelve {paquete: {"exportado", "instalado", "estado"}}."""
    resultado = {}
    for paquete_requerido in clase.paquetes_requeridos:
        exportado = librerias_exportadas.get(paquete_requerido)
        if exportado is None:
            raise ValueError(f"El manifest no declara la versión de {paquete_requerido} con que se exportó.")
        modulo = importlib.import_module(paquete_requerido)
        instalado = str(getattr(modulo, "__version__", "desconocida"))
        mayor_exportado = _version_mayor(exportado)
        mayor_instalado = _version_mayor(instalado)
        if mayor_exportado != mayor_instalado:
            raise ValueError(
                f"{paquete_requerido} {exportado} (con que se exportó) no es compatible con la "
                f"versión instalada en el servidor ({instalado}): cambia la versión mayor."
            )
        if exportado == instalado:
            estado = COMPATIBILIDAD_IGUAL
        else:
            estado = COMPATIBILIDAD_MENOR_DISTINTA
        resultado[paquete_requerido] = {"exportado": exportado, "instalado": instalado, "estado": estado}
    return resultado


def _comparar_metricas(declaradas: dict, recalculadas: dict, donde: str) -> None:
    for nombre_metrica, valor_recalculado in recalculadas.items():
        valor_declarado = declaradas.get(nombre_metrica)
        if valor_recalculado is None or valor_declarado is None:
            if valor_recalculado != valor_declarado:
                raise ValueError(f"La métrica {nombre_metrica} de {donde} no coincide con el CSV.")
            continue
        if not np.isclose(valor_declarado, valor_recalculado, rtol=_TOLERANCIA_METRICAS, atol=1e-9):
            raise ValueError(
                f"La métrica {nombre_metrica} de {donde} del manifest ({valor_declarado}) no "
                f"coincide con la reconstruida desde el CSV ({valor_recalculado})."
            )


def verificar_metricas_contra_csv(manifest: dict, registros: pd.DataFrame) -> None:
    """Reconstruye desde el CSV las metricas globales y por horizonte y exige que
    coincidan con las del manifest."""
    recalculadas = evaluacion.metricas_desde_registros(registros)
    declaradas = manifest["metricas_prueba"]
    for pronosticador, metricas in recalculadas["global"].items():
        _comparar_metricas(declaradas["global"][pronosticador], metricas, f"global ({pronosticador})")
    for horizonte, por_pronosticador in recalculadas["por_horizonte"].items():
        if horizonte not in declaradas["por_horizonte"]:
            raise ValueError(f"El manifest no trae las métricas del horizonte {horizonte}.")
        for pronosticador, metricas in por_pronosticador.items():
            _comparar_metricas(
                declaradas["por_horizonte"][horizonte][pronosticador],
                metricas,
                f"H{horizonte} ({pronosticador})",
            )


def revisar_paquete(carpeta: Path, serie: pd.DataFrame, usuario: str) -> dict[str, Any]:
    """Revisa un paquete ya descomprimido en carpeta (por el nucleo, de forma
    segura) antes de aceptarlo como version. Lanza ValueError con un mensaje
    legible si algo no cuadra. Si todo esta bien, completa el manifest con quien
    lo subio, cuando y la compatibilidad de librerias, y lo devuelve.

    Revisa, en orden: manifest y su formato, serie, modelo y familia en el
    catalogo, librerias instaladas y compatibles, tipos de archivo, archivos del
    modelo, CSV de la prueba y que las metricas del manifest se reconstruyan
    desde el, y por ultimo que el modelo cargue y pronostique valores validos.
    No entrena: solo carga el modelo ya entrenado.
    """
    ruta_manifest = carpeta / ARCHIVO_MANIFEST
    if not ruta_manifest.exists():
        raise ValueError("El .zip no trae manifest.json en la raíz.")
    try:
        manifest = json.loads(ruta_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(f"manifest.json no es un JSON válido: {error}") from error

    if manifest.get("formato") != FORMATO_MANIFEST:
        raise ValueError(
            f"El manifest es del formato {manifest.get('formato')} y el sistema espera el "
            f"{FORMATO_MANIFEST}. Exporta el modelo con la versión actual del código."
        )
    faltantes = campos_faltantes(manifest)
    if faltantes:
        raise ValueError(f"Al manifest le faltan campos: {', '.join(faltantes)}.")
    if manifest["patologia"] != "dengue":
        raise ValueError(f"El modelo es de {manifest['patologia']}, no de dengue.")
    if manifest["serie"] != DEFINICION_SERIE:
        raise ValueError(
            f"El modelo se entrenó con otra serie ({manifest['serie']}). El tablero pronostica: "
            f"{DEFINICION_SERIE}."
        )

    clave = manifest["modelo"]
    try:
        clase = catalogo.obtener_modelo(clave)
    except KeyError as error:
        raise ValueError(f"El modelo '{clave}' no existe en el catálogo de la app.") from error
    if manifest["familia"] != clase.familia:
        raise ValueError(
            f"El manifest dice que {clave} es de la familia {manifest['familia']}, "
            f"pero en la app es de {clase.familia}."
        )
    paquetes_faltantes = clase.paquetes_faltantes()
    if paquetes_faltantes:
        raise ValueError(
            f"El servidor no tiene instalada la librería de {clase.nombre}: "
            f"{', '.join(paquetes_faltantes)}."
        )
    compatibilidad = comprobar_compatibilidad(clase, manifest["librerias"])

    for ruta in carpeta.iterdir():
        if ruta.is_file() and ruta.suffix.lower() not in _EXTENSIONES_PERMITIDAS:
            raise ValueError(
                f"Tipo de archivo no permitido en el paquete: {ruta.name}. Solo se aceptan "
                f"{', '.join(sorted(_EXTENSIONES_PERMITIDAS))} (nunca pickle ni joblib)."
            )
    for nombre in manifest["archivos_modelo"]:
        if not (carpeta / nombre).exists():
            raise ValueError(f"El manifest declara el archivo {nombre}, pero no viene en el .zip.")

    registros = leer_pronosticos_prueba(carpeta, manifest)
    if registros is None:
        raise ValueError(f"El .zip no trae {manifest['archivo_pronosticos_prueba']}.")
    columnas_faltantes = [columna for columna in evaluacion.COLUMNAS_REGISTROS if columna not in registros.columns]
    if columnas_faltantes:
        raise ValueError(f"Al CSV de la prueba le faltan columnas: {', '.join(columnas_faltantes)}.")
    verificar_metricas_contra_csv(manifest, registros)

    modelo = clase(manifest["hiperparametros"])
    try:
        modelo.cargar(carpeta)
    except Exception as error:
        raise ValueError(f"El modelo no se pudo cargar: {error}") from error

    pronostico = inferencia.pronosticar(modelo, serie, HORIZONTE_MAXIMO_SEMANAS)
    valores = pronostico["casos_pronosticados"].to_numpy(dtype=float)
    if len(valores) != HORIZONTE_MAXIMO_SEMANAS or not np.all(np.isfinite(valores)):
        raise ValueError("El modelo cargó pero su pronóstico de prueba trae valores inválidos.")
    if np.any(valores < 0):
        raise ValueError("El modelo cargó pero pronostica casos negativos.")

    manifest["origen"] = ORIGEN_SUBIDO
    manifest["subido_por"] = usuario
    manifest["fecha_subida"] = datetime.now(timezone.utc).isoformat()
    manifest["compatibilidad"] = compatibilidad
    _escribir_manifest(carpeta, manifest)
    return manifest
