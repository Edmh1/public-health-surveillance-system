"""Punto de entrada del dashboard Streamlit."""

from dotenv import load_dotenv

from core.dashboard_base.layout import ejecutar_dashboard
from core.registry import registrar_patologia
from pathologies.dengue.plugin import DenguePathologyPlugin

load_dotenv()


def registrar_patologias_disponibles() -> None:
    registrar_patologia(DenguePathologyPlugin())


registrar_patologias_disponibles()
ejecutar_dashboard()
