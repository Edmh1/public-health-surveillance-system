"""Constantes del pronostico de dengue.

Familias: la pestana muestra el mejor modelo de cada una (lineamiento de la
tutoria). Que modelo ocupa cada familia lo decide la experimentacion y lo activa
el perfil de administracion; aqui solo se declaran las familias.
"""

CODIGOS_CASOS = {210, 220}

# La serie usa los casos NOTIFICADOS (probables y confirmados), igual que el
# resto del sistema y que los indicadores del protocolo INS. No se filtra por la
# columna confirmados: el pronostico es alerta temprana sobre lo que ve la
# vigilancia; la confirmacion de laboratorio llega con semanas de retraso (la
# serie confirmada se ve artificialmente baja en las ultimas semanas, desde donde
# se pronostica) y su cobertura varia mucho entre anios (13 % en 2010).
#
# Definicion que se guarda en el manifest de cada version. Un paquete .zip
# entrenado con otra serie se rechaza al subirlo.
DEFINICION_SERIE = (
    "Casos notificados de dengue y dengue grave (210+220, probables y confirmados) por semana "
    "epidemiologica, departamento del Magdalena"
)

FAMILIA_ESTADISTICO = "estadistico"
FAMILIA_APRENDIZAJE_AUTOMATICO = "aprendizaje_automatico"
FAMILIA_APRENDIZAJE_PROFUNDO = "aprendizaje_profundo"

# Orden en que se muestran en la pestana y en Gestion.
FAMILIAS = {
    FAMILIA_ESTADISTICO: "Estadístico",
    FAMILIA_APRENDIZAJE_AUTOMATICO: "Aprendizaje automático",
    FAMILIA_APRENDIZAJE_PROFUNDO: "Aprendizaje profundo",
}

HORIZONTE_MAXIMO_SEMANAS = 6
HORIZONTE_RECOMENDADO_SEMANAS = 4

# Prophet necesita historia suficiente para estimar una estacionalidad ANUAL
# confiable. El span real de entrenamiento es MENOR que esta cantidad de
# semanas, porque los modelos con rezagos descartan las primeras filas y el span
# de N puntos semanales es (N-1)*7 dias, no N*7. Prophet advierte por debajo de
# 730 dias; 120 semanas deja margen comodo despues de ambos descuentos.
SEMANAS_MINIMAS_ENTRENAMIENTO = 120

# Fraccion final del rango elegido que se reserva como conjunto de prueba: el
# modelo de evaluacion se entrena con el 85 % anterior y nunca la ve. No
# confundir con la validacion interna de las redes (fraccion_validacion en sus
# hiperparametros), que es un tramo DENTRO del entrenamiento para la parada
# temprana.
FRACCION_PRUEBA = 0.15
