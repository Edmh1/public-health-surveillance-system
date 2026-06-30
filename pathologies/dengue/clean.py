"""Limpieza especifica de dengue: Pipeline de scikit-learn con ColumnTransformer.

Reproduce las 7 transformaciones de la seccion "Especificacion de clean.py" del
CLAUDE.md, en orden: descarte de columnas, minusculas, conversion de tipos,
edad_anios, validacion geografica, enriquecimiento por joins y consolidacion
de grupo etnico.
"""

from pathlib import Path

import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer

DIR_REFERENCIAS = Path(__file__).parent / "config" / "referencias"

# Paso 1, bloque 1: columnas sin valor analitico (identificadores de exportacion,
# variables administrativas, codigos sin uso analitico).
COLUMNAS_SIN_VALOR_ANALITICO = [
    "CONSECUTIVE",
    "CONSECUTIVE2",
    "consecutive_origen",
    "CONSECUTIVE_12",
    "Partición",
    "Particion",
    "Separación",
    "COD_SUB",
    "COD_PRE",
    "FEC_ARC_XL",
    "FEC_AJU",
    "FM_FUERZA",
    "FM_UNIDAD",
    "FM_GRADO",
    "va_sispro",
    "CER_DEF",
]

# Paso 1, bloque 2: columnas de texto redundantes con su codigo (no transitividad).
# GRU_POB, EDAD y UNI_MED no van aqui: se usan en los pasos 4 y 7 y se descartan ahi.
COLUMNAS_NO_TRANSITIVAS = [
    "nombre_nacionalidad",
    "nom_est_f_caso",
    "Nombre_evento",
    "COD_EVE.1",
    "Pais_ocurrencia",
    "Departamento_ocurrencia",
    "Municipio_ocurrencia",
    "Pais_residencia",
    "Departamento_residencia",
    "Municipio_residencia",
    "Departamento_Notificacion",
    "Municipio_notificacion",
    "FECHA_NTO",
]

# Paso 2: columnas de texto que se estandarizan a minusculas (nombres ya en minuscula).
COLUMNAS_TEXTO_A_MINUSCULAS = ["sexo", "tip_ss", "nom_upgd", "cbmte", "nom_grupo", "cod_ase"]

# Paso 3: columnas de fecha a convertir a datetime.
COLUMNAS_FECHA = ["fec_not", "fec_con", "ini_sin", "fec_hos", "fec_def"]

# Paso 3: resto de columnas numericas a convertir a Int64.
COLUMNAS_ENTERAS = [
    "cod_eve",
    "semana",
    "ano",
    "edad",
    "uni_med",
    "nacionalidad",
    "cod_pais_o",
    "cod_dpto_o",
    "cod_mun_o",
    "area",
    "per_etn",
    "estrato",
    "sem_ges",
    "gp_discapa",
    "gp_desplaz",
    "gp_migrant",
    "gp_carcela",
    "gp_gestan",
    "gp_indigen",
    "gp_pobicfb",
    "gp_mad_com",
    "gp_desmovi",
    "gp_psiquia",
    "gp_vic_vio",
    "gp_otros",
    "fuente",
    "cod_pais_r",
    "cod_dpto_r",
    "cod_mun_r",
    "cod_dpto_n",
    "cod_mun_n",
    "tip_cas",
    "pac_hos",
    "con_fin",
    "ajuste",
    "confirmados",
    "estado_final_de_caso",
]

# Paso 4: divisores para llevar edad a anios segun el codigo de uni_med.
DIVISORES_EDAD = {1: 1, 2: 12, 3: 365, 4: 8760, 5: 525600}

# Paso 5b: codigo DIVIPOLA del departamento del Magdalena, alcance fijo del sistema.
COD_DPTO_MAGDALENA = 47

# Paso 6: correccion de codigos CIE-10 antes del join; los placeholders quedan nulos.
REEMPLAZOS_CODIGO_CIE10 = {
    "j15x": "j159",
    "i49x": "i499",
    "d65": "d65x",
    "8888": pd.NA,
    "9999": pd.NA,
    "none": pd.NA,
}


class DescartarColumnasSinValorAnalitico(BaseEstimator, TransformerMixin):
    """Paso 1: descarta las 29 columnas sin valor analitico o redundantes con su codigo."""

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        columnas_a_descartar = COLUMNAS_SIN_VALOR_ANALITICO + COLUMNAS_NO_TRANSITIVAS
        datos_descartados = datos.drop(columns=columnas_a_descartar, errors="ignore")
        return datos_descartados


class EstandarizarMinusculas(BaseEstimator, TransformerMixin):
    """Paso 2: nombres de columna y contenido de columnas de texto a minusculas."""

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        datos_estandarizados = datos.copy()
        datos_estandarizados.columns = datos_estandarizados.columns.str.lower()

        valores_nulos = {"nan": pd.NA, "none": pd.NA, "": pd.NA}
        for columna in COLUMNAS_TEXTO_A_MINUSCULAS:
            if columna not in datos_estandarizados.columns:
                continue
            texto_en_minusculas = datos_estandarizados[columna].astype(str)
            texto_en_minusculas = texto_en_minusculas.str.strip()
            texto_en_minusculas = texto_en_minusculas.str.lower()
            texto_en_minusculas = texto_en_minusculas.replace(valores_nulos)
            datos_estandarizados[columna] = texto_en_minusculas

        return datos_estandarizados


def _a_datetime(bloque_columnas):
    return bloque_columnas.apply(pd.to_datetime, errors="coerce")


def _a_float64(bloque_columnas):
    convertir_columna = lambda serie: pd.to_numeric(serie, errors="coerce").astype("Float64")
    return bloque_columnas.apply(convertir_columna)


def _a_int64(bloque_columnas):
    convertir_columna = lambda serie: pd.to_numeric(serie, errors="coerce").astype("Int64")
    return bloque_columnas.apply(convertir_columna)


class ConvertirTipos(BaseEstimator, TransformerMixin):
    """Paso 3: fechas a datetime, ocupacion a Float64, el resto de columnas listadas a Int64."""

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        columnas_originales = list(datos.columns)

        convertidor = ColumnTransformer(
            transformers=[
                ("fechas", FunctionTransformer(_a_datetime), COLUMNAS_FECHA),
                ("ocupacion", FunctionTransformer(_a_float64), ["ocupacion"]),
                ("enteras", FunctionTransformer(_a_int64), COLUMNAS_ENTERAS),
            ],
            remainder="passthrough",
            verbose_feature_names_out=False,
        )
        convertidor.set_output(transform="pandas")

        datos_convertidos = convertidor.fit_transform(datos)
        datos_en_orden_original = datos_convertidos[columnas_originales]
        return datos_en_orden_original


class ConstruirEdadAnios(BaseEstimator, TransformerMixin):
    """Paso 4: construye edad_anios desde edad y uni_med; imputa fuera de rango a nulo."""

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        datos_con_edad = datos.copy()

        divisor_por_registro = datos_con_edad["uni_med"].map(DIVISORES_EDAD)
        divisor_por_registro = divisor_por_registro.astype("Float64")
        edad_en_anios = (datos_con_edad["edad"] / divisor_por_registro).round(2)

        mayor_a_120 = (edad_en_anios > 120).fillna(False)
        menor_a_cero = (edad_en_anios < 0).fillna(False)
        edad_en_anios = edad_en_anios.mask(mayor_a_120)
        edad_en_anios = edad_en_anios.mask(menor_a_cero)

        datos_con_edad["edad_anios"] = edad_en_anios
        datos_con_edad = datos_con_edad.drop(columns=["edad", "uni_med"])
        return datos_con_edad


class ValidarGeografia(BaseEstimator, TransformerMixin):
    """Paso 5: construye cod_mun_completo y marca mun_valido contra el catalogo DIVIPOLA."""

    def __init__(self, ruta_referencias=DIR_REFERENCIAS):
        self.ruta_referencias = ruta_referencias

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        datos_con_geografia = datos.copy()

        codigo_departamento = datos_con_geografia["cod_dpto_o"].astype(str).str.strip()
        codigo_municipio = datos_con_geografia["cod_mun_o"].astype(str).str.strip()
        codigo_municipio = codigo_municipio.str.zfill(3)
        codigo_municipio_completo = codigo_departamento + codigo_municipio
        codigo_municipio_completo = pd.to_numeric(codigo_municipio_completo, errors="coerce")
        datos_con_geografia["cod_mun_completo"] = codigo_municipio_completo.astype("Int64")

        divipola = pd.read_excel(self.ruta_referencias / "Davipola.xlsx", dtype=str)
        codigos_municipio_validos = pd.to_numeric(divipola["cod_municipio"], errors="coerce")
        codigos_municipio_validos = codigos_municipio_validos.dropna()
        codigos_municipio_validos = codigos_municipio_validos.astype("Int64")
        conjunto_codigos_validos = set(codigos_municipio_validos.unique())

        cod_mun_completo = datos_con_geografia["cod_mun_completo"]
        datos_con_geografia["mun_valido"] = cod_mun_completo.isin(conjunto_codigos_validos)

        return datos_con_geografia


class FiltrarDepartamentoMagdalena(BaseEstimator, TransformerMixin):
    """Paso 5b: recorta el universo al departamento del Magdalena (cod_dpto_o = 47).

    El alcance del sistema es solo Magdalena (ver CLAUDE.md, "Alcance geografico y
    regla de tasas"); el recorte se aplica aqui de forma automatica, no como filtro
    manual del dashboard. Toda la geografia del sistema usa el campo de ocurrencia
    (cod_dpto_o/cod_mun_o); no se distingue residencia vs notificacion.
    """

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        es_magdalena = (datos["cod_dpto_o"] == COD_DPTO_MAGDALENA).fillna(False)
        datos_magdalena = datos[es_magdalena].copy()
        return datos_magdalena


class EnriquecerConReferencias(BaseEstimator, TransformerMixin):
    """Paso 6: enriquece con DIVIPOLA, paises, ocupaciones, aseguradoras y CIE-10 (left joins)."""

    def __init__(self, ruta_referencias=DIR_REFERENCIAS):
        self.ruta_referencias = ruta_referencias

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        filas_antes = len(datos)

        datos_enriquecidos = self._unir_departamento_ocurrencia(datos)
        datos_enriquecidos = self._unir_municipio_ocurrencia(datos_enriquecidos)
        datos_enriquecidos = self._unir_pais_ocurrencia(datos_enriquecidos)
        datos_enriquecidos = self._unir_ocupacion(datos_enriquecidos)
        datos_enriquecidos = self._unir_aseguradora(datos_enriquecidos)
        datos_enriquecidos = self._unir_cie10(datos_enriquecidos)

        filas_despues = len(datos_enriquecidos)
        if filas_despues != filas_antes:
            mensaje = f"Los joins de enriquecimiento cambiaron el numero de filas: {filas_antes} -> {filas_despues}"
            raise ValueError(mensaje)

        return datos_enriquecidos

    def _unir_departamento_ocurrencia(self, datos):
        davipola = pd.read_excel(self.ruta_referencias / "Davipola.xlsx", dtype=str)
        departamentos = davipola[["cod_departamento", "departamento"]].drop_duplicates()
        departamentos = departamentos.rename(
            columns={"cod_departamento": "cod_dpto_o", "departamento": "nom_dpto_o"}
        )
        departamentos["cod_dpto_o"] = pd.to_numeric(departamentos["cod_dpto_o"], errors="coerce")
        departamentos["cod_dpto_o"] = departamentos["cod_dpto_o"].astype("Int64")

        datos_unidos = datos.merge(departamentos, on="cod_dpto_o", how="left")
        return datos_unidos

    def _unir_municipio_ocurrencia(self, datos):
        davipola = pd.read_excel(self.ruta_referencias / "Davipola.xlsx", dtype=str)
        municipios = davipola[["cod_municipio", "municipio"]].drop_duplicates()
        municipios = municipios.rename(columns={"cod_municipio": "cod_mun_completo", "municipio": "nom_mun_o"})
        municipios["cod_mun_completo"] = pd.to_numeric(municipios["cod_mun_completo"], errors="coerce")
        municipios["cod_mun_completo"] = municipios["cod_mun_completo"].astype("Int64")

        datos_unidos = datos.merge(municipios, on="cod_mun_completo", how="left")
        return datos_unidos

    def _unir_pais_ocurrencia(self, datos):
        paises = pd.read_excel(self.ruta_referencias / "paises.xlsx", dtype=str)
        paises = paises[["codnumpais", "pais"]].drop_duplicates()
        paises = paises.rename(columns={"codnumpais": "cod_pais_o", "pais": "nom_pais_o"})
        paises["cod_pais_o"] = pd.to_numeric(paises["cod_pais_o"], errors="coerce")
        paises["cod_pais_o"] = paises["cod_pais_o"].astype("Int64")

        datos_unidos = datos.merge(paises, on="cod_pais_o", how="left")
        return datos_unidos

    def _unir_ocupacion(self, datos):
        ocupaciones = pd.read_excel(self.ruta_referencias / "ocupaciones.xlsx", dtype=str)
        ocupaciones = ocupaciones[["cod_ocu", "cod_antiguo", "nombre_vigente_ocupacion"]]
        ocupaciones = ocupaciones.rename(columns={"nombre_vigente_ocupacion": "nom_ocu"})
        ocupaciones = ocupaciones.drop_duplicates(subset="cod_ocu", keep="first")

        ocupaciones_por_codigo_nuevo = ocupaciones[["cod_ocu", "nom_ocu"]].copy()
        ocupaciones_por_codigo_nuevo["cod_ocu"] = pd.to_numeric(
            ocupaciones_por_codigo_nuevo["cod_ocu"], errors="coerce"
        )
        ocupaciones_por_codigo_nuevo["cod_ocu"] = ocupaciones_por_codigo_nuevo["cod_ocu"].astype("Float64")
        ocupaciones_por_codigo_nuevo = ocupaciones_por_codigo_nuevo.rename(
            columns={"cod_ocu": "ocupacion", "nom_ocu": "nom_ocupacion"}
        )
        ocupaciones_por_codigo_nuevo = ocupaciones_por_codigo_nuevo.drop_duplicates(
            subset="ocupacion", keep="first"
        )

        datos_unidos = datos.merge(ocupaciones_por_codigo_nuevo, on="ocupacion", how="left")

        ocupaciones_por_codigo_antiguo = ocupaciones[["cod_antiguo", "nom_ocu"]].copy()
        ocupaciones_por_codigo_antiguo["cod_antiguo"] = pd.to_numeric(
            ocupaciones_por_codigo_antiguo["cod_antiguo"], errors="coerce"
        )
        ocupaciones_por_codigo_antiguo["cod_antiguo"] = ocupaciones_por_codigo_antiguo["cod_antiguo"].astype(
            "Float64"
        )
        ocupaciones_por_codigo_antiguo = ocupaciones_por_codigo_antiguo.dropna(subset=["cod_antiguo"])
        ocupaciones_por_codigo_antiguo = ocupaciones_por_codigo_antiguo.drop_duplicates(
            subset="cod_antiguo", keep="first"
        )
        mapeo_codigo_antiguo = ocupaciones_por_codigo_antiguo.set_index("cod_antiguo")["nom_ocu"]

        sin_nombre_ocupacion = datos_unidos["nom_ocupacion"].isna()
        codigo_ocupacion_sin_nombre = datos_unidos.loc[sin_nombre_ocupacion, "ocupacion"]
        datos_unidos.loc[sin_nombre_ocupacion, "nom_ocupacion"] = codigo_ocupacion_sin_nombre.map(
            mapeo_codigo_antiguo
        )

        return datos_unidos

    def _unir_aseguradora(self, datos):
        aseguradoras = pd.read_excel(self.ruta_referencias / "aseguradoras.xls", dtype=str, engine="xlrd")
        aseguradoras = aseguradoras[["cod_ase", "nom_ase"]].drop_duplicates(subset="cod_ase", keep="first")
        aseguradoras["cod_ase"] = aseguradoras["cod_ase"].astype(str).str.strip().str.lower()

        datos_unidos = datos.merge(aseguradoras, on="cod_ase", how="left")
        return datos_unidos

    def _unir_cie10(self, datos):
        datos_con_codigo_corregido = datos.copy()
        cbmte_corregido = datos_con_codigo_corregido["cbmte"].replace(REEMPLAZOS_CODIGO_CIE10)
        datos_con_codigo_corregido["cbmte"] = cbmte_corregido

        cie10 = pd.read_excel(self.ruta_referencias / "TablaReferencia_CIE10__1.xlsx", dtype=str)
        cie10 = cie10[["Codigo", "Nombre"]].drop_duplicates(subset="Codigo", keep="first")
        cie10["Codigo"] = cie10["Codigo"].astype(str).str.strip().str.lower()
        cie10 = cie10.rename(columns={"Codigo": "cbmte", "Nombre": "nom_cbmte"})

        datos_unidos = datos_con_codigo_corregido.merge(cie10, on="cbmte", how="left")
        return datos_unidos


class ConsolidarGrupoEtnico(BaseEstimator, TransformerMixin):
    """Paso 7: consolida nom_grupo y gru_pob en una sola variable; descarta gru_pob."""

    def __init__(self, ruta_referencias=DIR_REFERENCIAS):
        self.ruta_referencias = ruta_referencias

    def fit(self, datos, y=None):
        return self

    def transform(self, datos):
        datos_consolidados = datos.copy()

        gruposetnicos = pd.read_excel(self.ruta_referencias / "gruposetnicos.xlsx", dtype=str)
        gruposetnicos = gruposetnicos[["cod_grupo", "nom_grupo"]].drop_duplicates(
            subset="cod_grupo", keep="first"
        )
        gruposetnicos["cod_grupo"] = gruposetnicos["cod_grupo"].astype(str).str.strip().str.zfill(3)
        gruposetnicos["nom_grupo"] = gruposetnicos["nom_grupo"].astype(str).str.strip().str.lower()
        mapeo_grupo_etnico = gruposetnicos.set_index("cod_grupo")["nom_grupo"]

        codigo_grupo_poblacional = datos_consolidados["gru_pob"].astype(str).str.strip()
        codigo_grupo_poblacional = codigo_grupo_poblacional.str.zfill(3)
        nombre_grupo_desde_codigo = codigo_grupo_poblacional.map(mapeo_grupo_etnico)

        sin_nom_grupo = datos_consolidados["nom_grupo"].isna()
        datos_consolidados.loc[sin_nom_grupo, "nom_grupo"] = nombre_grupo_desde_codigo[sin_nom_grupo]

        datos_consolidados = datos_consolidados.drop(columns=["gru_pob"])
        return datos_consolidados


def construir_pipeline_limpieza(ruta_referencias=DIR_REFERENCIAS):
    """Construye el pipeline de limpieza de dengue con los 7 pasos de la spec, en orden."""
    pipeline = Pipeline(
        steps=[
            ("descartar_columnas", DescartarColumnasSinValorAnalitico()),
            ("estandarizar_minusculas", EstandarizarMinusculas()),
            ("convertir_tipos", ConvertirTipos()),
            ("construir_edad_anios", ConstruirEdadAnios()),
            ("validar_geografia", ValidarGeografia(ruta_referencias=ruta_referencias)),
            ("filtrar_departamento_magdalena", FiltrarDepartamentoMagdalena()),
            ("enriquecer_con_referencias", EnriquecerConReferencias(ruta_referencias=ruta_referencias)),
            ("consolidar_grupo_etnico", ConsolidarGrupoEtnico(ruta_referencias=ruta_referencias)),
        ]
    )
    return pipeline


def limpiar(datos_crudos):
    """Punto de entrada del worker: aplica el pipeline completo de limpieza a una pieza cruda."""
    pipeline = construir_pipeline_limpieza()
    datos_limpios = pipeline.fit_transform(datos_crudos)
    return datos_limpios
