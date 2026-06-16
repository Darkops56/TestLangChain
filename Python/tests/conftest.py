import os
import sys
import pytest

# Agregar el directorio raíz de la app Python al path de python para asegurar importaciones correctas
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from src.graph import app_grafo

@pytest.fixture
def clean_graph():
    """Retorna la instancia del grafo compilado."""
    return app_grafo
