from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from src.state import EstadoProyecto
from src.nodes import nodo_generador_creativo, nodo_corrector_economico, nodo_revision_humana

def enrutador_condicional(state: EstadoProyecto) -> str:
    intentos = state.get("intentos", 0)
    publicaciones = state.get("publicaciones", {})
    
    print(f"\n[enrutador_condicional] Decidiendo siguiente paso...")
    print(f"  Intentos: {intentos}")
    
    hay_rechazos = any(
        not pub.get("aprobado_por_ia", False)
        for pub in publicaciones.values()
    )
    
    if hay_rechazos and intentos < 3:
        print("  Resultado enrutador: generador (Reintentar)")
        return "generador"
    
    print("  Resultado enrutador: revision_humana")
    return "revision_humana"

def create_app_graph() -> StateGraph:
    workflow = StateGraph(EstadoProyecto)
    
    workflow.add_node("generador", nodo_generador_creativo)
    workflow.add_node("corrector", nodo_corrector_economico)
    workflow.add_node("revision_humana", nodo_revision_humana)
    
    workflow.add_edge(START, "generador")
    workflow.add_edge("generador", "corrector")
    
    workflow.add_conditional_edges(
        "corrector",
        enrutador_condicional,
        {
            "generador": "generador",
            "revision_humana": "revision_humana"
        }
    )
    
    workflow.add_edge("revision_humana", END)
    
    return workflow.compile(
        checkpointer=MemorySaver(),
        interrupt_before=["revision_humana"]
    )

# Grafo compilado listo para usar
app_grafo = create_app_graph()
