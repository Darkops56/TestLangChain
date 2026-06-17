from unittest.mock import MagicMock, patch
from src.graph import app_grafo
from src.state import MultiPlatformState
from src.nodes import MultiPlatformOutput, GmailOutput

@patch("src.nodes.llm_estructurado")
def test_graph_resolves_on_second_attempt(mock_llm_structured):
    # Setup mocks for 1st and 2nd attempts with specific Pydantic output classes
    resp_1 = MultiPlatformOutput(
        gmail=GmailOutput(text="Creative post without required keyword", image_prompt="image 1")
    )
    resp_2 = MultiPlatformOutput(
        gmail=GmailOutput(text="Creative post using generative IA", image_prompt="image 2")
    )
    mock_llm_structured.invoke.side_effect = [resp_1, resp_2]

    config = {"configurable": {"thread_id": "thread-test-1"}}
    inputs: MultiPlatformState = {
        "user_prompt": "Python",
        "platforms": ["gmail"],
        "outputs": {},
        "retry_count": 0,
        "platform_feedback": {},
        "is_approved": False
    }

    # Run the graph until the human review interrupt
    app_grafo.invoke(inputs, config)

    state_info = app_grafo.get_state(config)
    assert len(state_info.next) > 0  # Should be interrupted
    assert state_info.values["retry_count"] == 2
    assert state_info.values["outputs"]["gmail"]["is_valid"] is True
    assert len(state_info.values["outputs"]["gmail"]["errors"]) == 0

    # Resume the graph with approval
    app_grafo.update_state(config, {"is_approved": True})
    app_grafo.invoke(None, config)

    state_info_final = app_grafo.get_state(config)
    assert len(state_info_final.next) == 0  # Graph completed execution
    assert state_info_final.values["retry_count"] == 2
    assert state_info_final.values["is_approved"] is True


@patch("src.nodes.llm_estructurado")
def test_graph_stops_at_max_attempts_anti_loop(mock_llm_structured):
    # Setup mock that always returns defective text (violates rules)
    resp = MultiPlatformOutput(
        gmail=GmailOutput(text="Defective content", image_prompt="image")
    )
    mock_llm_structured.invoke.return_value = resp

    config = {"configurable": {"thread_id": "thread-test-2"}}
    inputs: MultiPlatformState = {
        "user_prompt": "test",
        "platforms": ["gmail"],
        "outputs": {},
        "retry_count": 0,
        "platform_feedback": {},
        "is_approved": False
    }

    # Run the graph
    app_grafo.invoke(inputs, config)

    state_info_final = app_grafo.get_state(config)
    assert len(state_info_final.next) > 0  # Interrupted due to max retries hit
    assert state_info_final.values["retry_count"] == 3
    assert state_info_final.values["outputs"]["gmail"]["is_valid"] is False
    assert len(state_info_final.values["outputs"]["gmail"]["errors"]) > 0
