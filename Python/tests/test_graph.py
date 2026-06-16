from unittest.mock import MagicMock, patch
from src.graph import app_grafo
from src.state import EstadoProyecto

@patch("src.nodes.llm_creativo")
def test_graph_resolves_on_second_attempt(mock_creativo):
    resp_1 = MagicMock()
    resp_1.content = '{"gmail": {"texto": "Post creativo sin aprobacion", "prompt_imagen": "imagen 1"}}'

    resp_2 = MagicMock()
    resp_2.content = '{"gmail": {"texto": "Post creativo usando IA generativa", "prompt_imagen": "imagen 2"}}'

    mock_creativo.invoke.side_effect = [resp_1, resp_2]

    config = {"configurable": {"thread_id": "thread-test-1"}}
    inputs: EstadoProyecto = {
        "prompt_usuario": "Python",
        "plataformas_destino": ["gmail"],
        "publicaciones": {},
        "intentos": 0,
        "aprobado_por_humano": False
    }

    app_grafo.invoke(inputs, config)

    state_info = app_grafo.get_state(config)
    assert len(state_info.next) > 0
    assert state_info.values["intentos"] == 2
    assert state_info.values["publicaciones"]["gmail"]["aprobado_por_ia"] is True
    assert len(state_info.values["publicaciones"]["gmail"]["errores"]) == 0

    app_grafo.update_state(config, {"aprobado_por_humano": True})
    app_grafo.invoke(None, config)

    state_info_final = app_grafo.get_state(config)
    assert len(state_info_final.next) == 0
    assert state_info_final.values["intentos"] == 2
    assert state_info_final.values["aprobado_por_humano"] is True


@patch("src.nodes.llm_creativo")
def test_graph_stops_at_max_attempts_anti_loop(mock_creativo):
    resp = MagicMock()
    resp.content = '{"gmail": {"texto": "Contenido defectuoso", "prompt_imagen": "imagen"}}'
    mock_creativo.invoke.return_value = resp

    config = {"configurable": {"thread_id": "thread-test-2"}}
    inputs: EstadoProyecto = {
        "prompt_usuario": "test",
        "plataformas_destino": ["gmail"],
        "publicaciones": {},
        "intentos": 0,
        "aprobado_por_humano": False
    }

    app_grafo.invoke(inputs, config)

    state_info_final = app_grafo.get_state(config)
    assert len(state_info_final.next) > 0
    assert state_info_final.values["intentos"] == 3
    assert state_info_final.values["publicaciones"]["gmail"]["aprobado_por_ia"] is False
    assert len(state_info_final.values["publicaciones"]["gmail"]["errores"]) > 0
