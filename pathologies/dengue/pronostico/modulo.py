"""Implementacion del contrato core.registry.ModuloPronostico para dengue: lo que
usa el nucleo (Gestion y worker) para entrenar o importar una version de un
modelo, sin saber que modelos hay ni como se arma la serie.
"""

from pathlib import Path
from typing import Any

import pandas as pd

from core.registry import ModeloPronostico, ModuloPronostico
from core.storage import modelos as almacen_modelos
from pathologies.dengue.pronostico import catalogo, documentacion, paquete
from pathologies.dengue.pronostico.configuracion import FAMILIAS
from pathologies.dengue.pronostico.manifest import ORIGEN_SISTEMA, es_formato_vigente
from pathologies.dengue.pronostico.serie import construir_serie_semanal_departamental, recortar_serie


PATOLOGIA = "dengue"


class PronosticoDengue(ModuloPronostico):

    def familias(self) -> dict[str, str]:
        return dict(FAMILIAS)

    def catalogo(self) -> dict[str, type[ModeloPronostico]]:
        return catalogo.listar_modelos()

    def semanas_disponibles(self, datos: pd.DataFrame) -> pd.DataFrame:
        serie = construir_serie_semanal_departamental(datos)
        return serie[["fecha_semana", "ano", "semana"]]

    def entrenar_y_exportar(
        self,
        datos: pd.DataFrame,
        modelo: str,
        desde: pd.Timestamp | None,
        hasta: pd.Timestamp | None,
        hiperparametros: dict[str, Any] | None,
        carpeta: Path,
        usuario: str,
    ) -> dict[str, Any]:
        serie_completa = construir_serie_semanal_departamental(datos)
        serie = recortar_serie(serie_completa, desde, hasta)
        if serie.empty:
            raise ValueError("No hay semanas con datos en el rango elegido.")
        return paquete.entrenar_evaluar_y_guardar(
            modelo, hiperparametros, serie, carpeta, usuario, ORIGEN_SISTEMA
        )

    def importar(self, carpeta: Path, datos: pd.DataFrame, usuario: str) -> dict[str, Any]:
        serie = construir_serie_semanal_departamental(datos)
        return paquete.revisar_paquete(carpeta, serie, usuario)

    def es_version_vigente(self, manifest: dict) -> bool:
        return es_formato_vigente(manifest)

    def describir_paquete(self) -> dict[str, Any]:
        """Secciones 5 (estructura del paquete) y 16 (generarlo fuera de la app)
        de docs/pronostico.md, y por cada modelo activo el arbol de su paquete y
        una muestra real de cada archivo."""
        secciones = documentacion.leer_secciones()
        textos = []
        for numero in [5, 16]:
            seccion = secciones[numero]
            textos.append({
                "titulo": f"{numero}. {seccion['titulo']}",
                "markdown": documentacion.quitar_marcadores(seccion["contenido"]),
            })

        ejemplos_por_modelo = {}
        for puntero in almacen_modelos.leer_activos(PATOLOGIA).values():
            manifest = almacen_modelos.leer_manifest(PATOLOGIA, puntero["modelo"], puntero["version"]) or {}
            if not es_formato_vigente(manifest):
                continue
            carpeta = almacen_modelos.ruta_version(PATOLOGIA, puntero["modelo"], puntero["version"])
            ejemplos_por_modelo[manifest.get("nombre", puntero["modelo"])] = {
                "arbol": documentacion.arbol_del_paquete(carpeta, manifest),
                "archivos": documentacion.ejemplos_de_archivos(carpeta, manifest),
            }
        return {"secciones": textos, "ejemplos_por_modelo": ejemplos_por_modelo}
