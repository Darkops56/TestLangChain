import os
import sys
import sqlite3
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from src.state import MultiPlatformState
from src.nodes import generator_node, nodo_corrector_economico, image_generator_node
from src.tools import publicar_multiplataforma

def enrutador_condicional(state: MultiPlatformState) -> str:
    """
    Enruta de regreso a generator_node si hay fallas en la validación local
    y aún no se ha alcanzado el límite de 3 reintentos.
    Caso contrario, avanza hacia el paso de generación de imágenes.
    """
    retry_count = state.get("retry_count", 0)
    outputs = state.get("outputs", {}) or {}
    
    print(f"\n[enrutador_condicional] Decidiendo siguiente paso...")
    print(f"  Intentos: {retry_count}/3")
    
    hay_rechazos = any(
        not val.get("is_valid", False)
        for val in outputs.values()
    )
    
    if hay_rechazos and retry_count < 3:
        print("  Resultado enrutador: reintentar con el generador.")
        return "generador"
    
    print("  Resultado enrutador: avanzar a generación de imágenes.")
    return "image_generator"

def nodo_publicar(state: MultiPlatformState) -> dict:
    """
    Nodo que ejecuta de forma paralela los adaptadores si el usuario
    aprobó el contenido (is_approved es True). Evita re-publicar en
    plataformas que ya se publicaron con éxito previamente.
    """
    is_approved = state.get("is_approved", False)
    publication_results = dict(state.get("publication_results", {}) or {})
    publication_errors = dict(state.get("publication_errors", {}) or {})
    
    if is_approved:
        print("\n--- [Grafo - Nodo Publicar] Aprobación confirmada. Publicando... ---")
        outputs = state.get("outputs", {}) or {}
        platforms = state.get("platforms", [])
        image_paths = state.get("image_paths", {}) or {}
        
        # Solo publicar las plataformas que no tengan un estado exitoso
        plataformas_a_publicar = [
            plat for plat in platforms 
            if not publication_results.get(plat, False)
        ]
        
        if plataformas_a_publicar:
            res = publicar_multiplataforma(outputs, plataformas_a_publicar, image_paths)
            for plat, exito in res.items():
                publication_results[plat] = exito
                if not exito:
                    if plat not in publication_errors:
                        publication_errors[plat] = []
                    publication_errors[plat].append("Fallo en la publicación de la plataforma.")
        else:
            print("  [Grafo - Nodo Publicar] Todas las plataformas seleccionadas ya están publicadas.")
    else:
        print("\n--- [Grafo - Nodo Publicar] Publicación cancelada / rechazada por el usuario. ---")
        
    return {"publication_results": publication_results, "publication_errors": publication_errors}

# Mantener referencia global a la conexión para evitar recolección de basura
_db_conn = None

def create_app_graph() -> StateGraph:
    global _db_conn
    workflow = StateGraph(MultiPlatformState)
    
    workflow.add_node("generador", generator_node)
    workflow.add_node("corrector", nodo_corrector_economico)
    workflow.add_node("image_generator", image_generator_node)
    workflow.add_node("publish", nodo_publicar)
    
    workflow.add_edge(START, "generador")
    workflow.add_edge("generador", "corrector")
    
    workflow.add_conditional_edges(
        "corrector",
        enrutador_condicional,
        {
            "generador": "generador",
            "image_generator": "image_generator"
        }
    )
    
    workflow.add_edge("image_generator", "publish")
    workflow.add_edge("publish", END)
    
    # Detectar si estamos bajo un entorno de pruebas pytest para usar base de datos en memoria
    is_testing = "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ
    if is_testing:
        print("[INFO Grafo] Ejecutando en modo test: Usando checkpointer en memoria SQLite.")
        _db_conn = sqlite3.connect(":memory:", check_same_thread=False)
    else:
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../state_db.sqlite"))
        print(f"[INFO Grafo] Ejecutando en modo producción: Usando checkpointer persistente SQLite en {db_path}")
        _db_conn = sqlite3.connect(db_path, check_same_thread=False)
        
    checkpointer = SqliteSaver(_db_conn)
    
    return workflow.compile(
        checkpointer=checkpointer,
        interrupt_before=["publish"]
    )

# Grafo compilado listo para usar con SqliteSaver
app_grafo = create_app_graph()
