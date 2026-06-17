from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import MultiPlatformState
from src.nodes import generator_node, nodo_corrector_economico
from src.tools import publicar_multiplataforma

def enrutador_condicional(state: MultiPlatformState) -> str:
    """
    Enruta de regreso a generator_node si hay fallas en la validación local
    y aún no se ha alcanzado el límite de 3 reintentos.
    Caso contrario, avanza hacia el paso de publicación (HITL).
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
    
    print("  Resultado enrutador: avanzar a revisión humana (publish).")
    return "publish"

def nodo_publicar(state: MultiPlatformState) -> dict:
    """
    Nodo que ejecuta de forma paralela los adaptadores si el usuario
    aprobó el contenido (is_approved es True).
    """
    is_approved = state.get("is_approved", False)
    if is_approved:
        print("\n--- [Grafo - Nodo Publicar] Aprobación confirmada. Publicando en paralelo... ---")
        outputs = state.get("outputs", {}) or {}
        platforms = state.get("platforms", [])
        publicar_multiplataforma(outputs, platforms)
    else:
        print("\n--- [Grafo - Nodo Publicar] Publicación cancelada / rechazada por el usuario. ---")
    return {}

def create_app_graph() -> StateGraph:
    workflow = StateGraph(MultiPlatformState)
    
    workflow.add_node("generador", generator_node)
    workflow.add_node("corrector", nodo_corrector_economico)
    workflow.add_node("publish", nodo_publicar)
    
    workflow.add_edge(START, "generador")
    workflow.add_edge("generador", "corrector")
    
    workflow.add_conditional_edges(
        "corrector",
        enrutador_condicional,
        {
            "generador": "generador",
            "publish": "publish"
        }
    )
    
    workflow.add_edge("publish", END)
    
    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["publish"]
    )

# Grafo compilado listo para usar con MemorySaver
app_grafo = create_app_graph()
