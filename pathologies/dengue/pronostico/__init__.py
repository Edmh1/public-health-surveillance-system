"""Pronostico semanal de casos de dengue a nivel departamental (Magdalena).

Estructura:
- configuracion.py: familias, horizonte y constantes de la evaluacion.
- serie.py: construccion y recorte de la serie semanal departamental.
- recursivo.py: utilidades del pronostico recursivo multipaso con rezagos.
- evaluacion.py: metricas y validacion walk-forward por horizonte.
- inferencia.py: pronostico desde la ultima semana de la serie.
- catalogo.py: descubre los modelos de modelos/ (un archivo por modelo).
- modelos/: implementaciones del contrato core.registry.ModeloPronostico.

Modulo de calculo puro: sin Streamlit. Lo usan el worker, la pestana Pronostico
y los notebooks del repositorio de experimentacion (que importan este mismo
codigo para que un modelo entrenado afuera cargue igual aqui).
"""
