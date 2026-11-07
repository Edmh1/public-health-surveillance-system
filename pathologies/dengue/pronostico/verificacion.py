"""Verificacion del sistema de pronostico de dengue (docs/pronostico.md, seccion 17).

Comprueba sobre las versiones activas:
1. Las metricas globales y por horizonte del manifest se reconstruyen desde el
   CSV de la prueba.
2. Cada horizonte tiene un registro por semana de prueba, todas las semanas
   objetivo pertenecen a la prueba y la ultima semana de origen se recupera del
   CSV con sus horizontes disponibles.
3. Los errores del CSV coinciden con los calculados desde los valores sin
   redondear (y el error porcentual queda vacio con 0 casos reales).
4. El modelo definitivo carga y pronostica las 6 semanas futuras sin ejecutar
   ningun entrenamiento (fit bloqueado en todas las librerias).

Con --todos-los-modelos ademas exporta los 7 modelos del catalogo, los importa
como un paquete subido y pronostica, tambien con el entrenamiento bloqueado.

Uso, desde la raiz del repositorio:
    python -m pathologies.dengue.pronostico.verificacion
    python -m pathologies.dengue.pronostico.verificacion --todos-los-modelos
"""

import argparse
import importlib
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from core.storage import modelos as almacen
from core.storage import rutas
from core.storage.consolidado import cargar_consolidado
from core.storage.modelos import extraer_zip_seguro
from pathologies.dengue.pronostico import catalogo, inferencia, paquete
from pathologies.dengue.pronostico.configuracion import FAMILIAS, HORIZONTE_MAXIMO_SEMANAS
from pathologies.dengue.pronostico.manifest import ORIGEN_SUBIDO, es_formato_vigente
from pathologies.dengue.pronostico.serie import construir_serie_semanal_departamental

PATOLOGIA = "dengue"

# Metodos de entrenamiento que se bloquean: (modulo, clase, metodo).
_METODOS_DE_ENTRENAMIENTO = [
    ("prophet.forecaster", "Prophet", "fit"),
    ("xgboost", "XGBRegressor", "fit"),
    ("lightgbm", "LGBMRegressor", "fit"),
    ("keras", "Model", "fit"),
    ("statsmodels.tsa.arima.model", "ARIMA", "fit"),
]


class EntrenamientoProhibido(RuntimeError):
    pass


def _prohibido(*argumentos, **opciones):
    raise EntrenamientoProhibido("Se intentó entrenar durante la importación o la inferencia.")


def bloquear_entrenamiento() -> list[str]:
    """Reemplaza los metodos fit de todas las librerias instaladas por uno que
    falla. Devuelve los metodos bloqueados."""
    bloqueados = []
    for nombre_modulo, nombre_clase, nombre_metodo in _METODOS_DE_ENTRENAMIENTO:
        try:
            modulo = importlib.import_module(nombre_modulo)
        except ImportError:
            continue
        clase = getattr(modulo, nombre_clase)
        setattr(clase, nombre_metodo, _prohibido)
        bloqueados.append(f"{nombre_clase}.{nombre_metodo}")
    return bloqueados


class Resultado:
    def __init__(self) -> None:
        self.fallos = []

    def comprobar(self, condicion: bool, descripcion: str) -> None:
        if condicion:
            estado = "OK   "
        else:
            estado = "FALLA"
            self.fallos.append(descripcion)
        print(f"  [{estado}] {descripcion}")


def _verificar_registros(manifest: dict, registros: pd.DataFrame, resultado: Resultado) -> None:
    prueba = manifest["prueba"]
    inicio = pd.Timestamp(prueba["inicio_prueba"])
    fin = pd.Timestamp(prueba["fin_prueba"])
    semanas_prueba = prueba["semanas_prueba"]

    try:
        paquete.verificar_metricas_contra_csv(manifest, registros)
        coinciden = True
    except ValueError as error:
        print(f"         {error}")
        coinciden = False
    resultado.comprobar(coinciden, "Métricas globales y H1-H6 del manifest = reconstruidas desde el CSV")

    global_modelo = manifest["metricas_prueba"]["global"]["modelo"]
    resultado.comprobar(
        global_modelo["n"] == len(registros),
        f"Métrica global calculada con todos los registros (n = {global_modelo['n']}, CSV = {len(registros)})",
    )

    conteos = registros.groupby("horizonte_semanas").size().to_dict()
    todos_completos = all(conteos.get(horizonte) == semanas_prueba for horizonte in range(1, HORIZONTE_MAXIMO_SEMANAS + 1))
    resultado.comprobar(todos_completos, f"Cada horizonte tiene {semanas_prueba} registros, uno por semana de prueba: {conteos}")

    dentro = registros["fecha_objetivo"].between(inicio, fin).all()
    resultado.comprobar(bool(dentro), f"Todas las semanas objetivo pertenecen a la prueba ({inicio.date()} a {fin.date()})")

    reales = registros["casos_reales"].to_numpy(dtype=float)
    pronosticos = registros["pronostico_modelo"].to_numpy(dtype=float)
    error_absoluto = np.abs(reales - pronosticos)
    resultado.comprobar(
        np.allclose(error_absoluto, registros["error_absoluto"].to_numpy(dtype=float)),
        "error_absoluto = |casos_reales - pronostico_modelo| con valores sin redondear",
    )
    con_casos = reales != 0
    esperado = error_absoluto[con_casos] / reales[con_casos] * 100
    porcentual = registros["error_porcentual"].to_numpy(dtype=float)
    porcentual_correcto = np.allclose(esperado, porcentual[con_casos]) and bool(np.isnan(porcentual[~con_casos]).all())
    resultado.comprobar(porcentual_correcto, "error_porcentual correcto y vacío cuando los casos reales son 0")

    ultimo_origen = registros["fecha_origen"].max()
    del_ultimo = registros[registros["fecha_origen"] == ultimo_origen].sort_values("horizonte_semanas")
    horizontes = del_ultimo["horizonte_semanas"].tolist()
    objetivo = del_ultimo["fecha_objetivo"].max()
    resultado.comprobar(
        objetivo == fin,
        f"Última semana de origen {ultimo_origen.date()} recuperada del CSV: horizontes {horizontes}, objetivo {objetivo.date()}",
    )


def _verificar_pronostico_futuro(clave: str, carpeta: Path, manifest: dict, serie: pd.DataFrame, resultado: Resultado) -> None:
    clase = catalogo.obtener_modelo(clave)
    modelo = clase(manifest["hiperparametros"])
    try:
        modelo.cargar(carpeta)
        pronostico = inferencia.pronosticar(modelo, serie, HORIZONTE_MAXIMO_SEMANAS)
    except EntrenamientoProhibido:
        resultado.comprobar(False, "El modelo definitivo pronostica sin entrenar")
        return
    valores = pronostico["casos_pronosticados"].to_numpy(dtype=float)
    validos = len(valores) == HORIZONTE_MAXIMO_SEMANAS and bool(np.all(np.isfinite(valores))) and bool(np.all(valores >= 0))
    texto = ", ".join(f"{valor:.1f}" for valor in valores)
    resultado.comprobar(validos, f"Modelo definitivo: 6 semanas futuras sin entrenar ({texto})")


def verificar_activos(serie: pd.DataFrame, resultado: Resultado) -> None:
    activos = almacen.leer_activos(PATOLOGIA)
    for familia in FAMILIAS:
        puntero = activos.get(familia)
        if puntero is None:
            print(f"\n{FAMILIAS[familia]}: sin versión activa")
            continue
        carpeta = almacen.ruta_version(PATOLOGIA, puntero["modelo"], puntero["version"])
        manifest = json.loads((carpeta / "manifest.json").read_text(encoding="utf-8"))
        print(f"\n{FAMILIAS[familia]}: {manifest.get('nombre')} {puntero['version']}")
        if not es_formato_vigente(manifest):
            resultado.comprobar(False, "La versión activa es del formato vigente")
            continue
        registros = paquete.leer_pronosticos_prueba(carpeta, manifest)
        _verificar_registros(manifest, registros, resultado)
        _verificar_pronostico_futuro(puntero["modelo"], carpeta, manifest, serie, resultado)


def verificar_todos_los_modelos(serie: pd.DataFrame, resultado: Resultado) -> None:
    """Exporta los 7 modelos (aqui si se entrena), bloquea el entrenamiento y los
    importa como paquetes subidos."""
    with tempfile.TemporaryDirectory() as directorio:
        directorio = Path(directorio)
        claves = list(catalogo.listar_modelos())
        for clave in claves:
            print(f"Exportando {clave}...")
            carpeta = directorio / "export" / clave
            paquete.entrenar_evaluar_y_guardar(clave, None, serie, carpeta, "verificacion", ORIGEN_SUBIDO)
            paquete.exportar_zip(carpeta, directorio / f"{clave}.zip")

        bloqueados = bloquear_entrenamiento()
        print(f"\nEntrenamiento bloqueado: {', '.join(bloqueados)}")
        for clave in claves:
            print(f"\nImportación de {clave}.zip")
            destino = directorio / "import" / clave
            extraer_zip_seguro(directorio / f"{clave}.zip", destino)
            try:
                manifest = paquete.revisar_paquete(destino, serie, "verificacion")
            except (ValueError, EntrenamientoProhibido) as error:
                resultado.comprobar(False, f"Se importa sin entrenar: {error}")
                continue
            resultado.comprobar(True, f"Se importa sin entrenar (compatibilidad: {manifest['compatibilidad']})")
            registros = paquete.leer_pronosticos_prueba(destino, manifest)
            _verificar_registros(manifest, registros, resultado)
            _verificar_pronostico_futuro(clave, destino, manifest, serie, resultado)


def main() -> int:
    argumentos = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    argumentos.add_argument("--todos-los-modelos", action="store_true")
    opciones = argumentos.parse_args()

    datos = cargar_consolidado(rutas.ruta_consolidado(PATOLOGIA))
    serie = construir_serie_semanal_departamental(datos)
    resultado = Resultado()

    if opciones.todos_los_modelos:
        verificar_todos_los_modelos(serie, resultado)
    else:
        bloqueados = bloquear_entrenamiento()
        print(f"Entrenamiento bloqueado: {', '.join(bloqueados)}")
        verificar_activos(serie, resultado)

    print()
    if resultado.fallos:
        print(f"{len(resultado.fallos)} comprobaciones fallaron.")
        return 1
    print("Todas las comprobaciones pasaron.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
