from unittest.mock import MagicMock, patch
from src.nodes import (
    generator_node, 
    nodo_corrector_economico, 
    image_generator_node,
    MultiPlatformOutput, 
    GmailOutput
)
from src.state import MultiPlatformState, PlatformContent

@patch("src.nodes.llm_estructurado")
def test_generator_node_increments_retry_count(mock_llm_structured):
    # Setup mock response matching the new Pydantic schema
    mock_response = MultiPlatformOutput(
        gmail=GmailOutput(text="Hexagonal design in IA", image_prompt="image of gears")
    )
    mock_llm_structured.invoke.return_value = mock_response

    initial_state: MultiPlatformState = {
        "user_prompt": "Hexagonal design",
        "platforms": ["gmail"],
        "outputs": {},
        "retry_count": 0,
        "platform_feedback": {},
        "is_approved": False
    }

    output = generator_node(initial_state)
    assert output["retry_count"] == 1
    assert "gmail" in output["outputs"]
    assert output["outputs"]["gmail"]["text"] == "Hexagonal design in IA"
    assert output["outputs"]["gmail"]["image_prompt"] == "image of gears"
    assert output["outputs"]["gmail"]["is_valid"] is False
    assert output["outputs"]["gmail"]["errors"] == []
    mock_llm_structured.invoke.assert_called_once()


def test_economic_corrector_node_approves():
    state: MultiPlatformState = {
        "user_prompt": "Test",
        "platforms": ["gmail", "tiktok"],
        "outputs": {
            "gmail": PlatformContent(
                text="Valid text with IA for Gmail.",
                image_prompt="image concept",
                is_valid=False,
                errors=[]
            ),
            "tiktok": PlatformContent(
                text="IA is cool #tiktok",
                image_prompt="image concept",
                is_valid=False,
                errors=[]
            )
        },
        "retry_count": 1,
        "platform_feedback": {"gmail": "Falta la palabra IA", "tiktok": "Falta hashtag"},
        "is_approved": False
    }

    output = nodo_corrector_economico(state)
    assert output["outputs"]["gmail"]["is_valid"] is True
    assert len(output["outputs"]["gmail"]["errors"]) == 0
    assert output["outputs"]["tiktok"]["is_valid"] is True
    assert len(output["outputs"]["tiktok"]["errors"]) == 0
    assert "gmail" not in output["platform_feedback"]
    assert "tiktok" not in output["platform_feedback"]


def test_economic_corrector_node_rejects():
    state: MultiPlatformState = {
        "user_prompt": "Test",
        "platforms": ["gmail", "tiktok", "whatsapp"],
        "outputs": {
            "gmail": PlatformContent(
                text="Text without the required keyword.",
                image_prompt="image concept",
                is_valid=False,
                errors=[]
            ),
            "tiktok": PlatformContent(
                text="a" * 200, # Too long
                image_prompt="image concept",
                is_valid=False,
                errors=[]
            ),
            "whatsapp": PlatformContent(
                text="Message containing <p>HTML tags</p>", # HTML tags not allowed
                image_prompt="image concept",
                is_valid=False,
                errors=[]
            )
        },
        "retry_count": 1,
        "platform_feedback": {},
        "is_approved": False
    }

    output = nodo_corrector_economico(state)
    # gmail validation checks
    assert output["outputs"]["gmail"]["is_valid"] is False
    assert "gmail" in output["platform_feedback"]
    assert "Falta la palabra" in output["platform_feedback"]["gmail"]

    # tiktok validation checks
    assert output["outputs"]["tiktok"]["is_valid"] is False
    assert "tiktok" in output["platform_feedback"]
    assert "límite de 150" in output["platform_feedback"]["tiktok"]
    assert "hashtag" in output["platform_feedback"]["tiktok"]

    # whatsapp validation checks
    assert output["outputs"]["whatsapp"]["is_valid"] is False
    assert "whatsapp" in output["platform_feedback"]
    assert "HTML" in output["platform_feedback"]["whatsapp"]


@patch("src.nodes.ChatOllama")
@patch("src.nodes.generar_imagen")
def test_image_generator_node(mock_generar_imagen, mock_chat_ollama):
    mock_generar_imagen.return_value = "/path/to/mock_image.png"
    # Mockear ChatOllama para que falle (simula que Ollama no está disponible)
    mock_llm_instance = MagicMock()
    mock_llm_instance.invoke.side_effect = Exception("Ollama no disponible en test")
    mock_chat_ollama.return_value = mock_llm_instance
    
    state: MultiPlatformState = {
        "user_prompt": "Test image generator",
        "platforms": ["gmail", "tiktok"],
        "outputs": {
            "gmail": PlatformContent(
                text="Texto válido con IA.",
                image_prompt="Una imagen formal de IA.",
                is_valid=True,
                errors=[]
            ),
            "tiktok": PlatformContent(
                text="Texto inválido sin hashtag.",
                image_prompt="Imagen tiktok.",
                is_valid=False,
                errors=["Falta hashtag"]
            )
        },
        "retry_count": 1,
        "platform_feedback": {},
        "is_approved": False,
        "image_paths": {},
        "publication_results": {},
        "publication_errors": {}
    }
    
    output = image_generator_node(state)
    
    # Debe generar imagen solo para gmail, ya que su texto es válido
    assert "gmail" in output["image_paths"]
    assert output["image_paths"]["gmail"] == "/path/to/mock_image.png"
    assert "tiktok" not in output["image_paths"]
    # Al fallar ChatOllama, usa el image_prompt base como fallback
    mock_generar_imagen.assert_called_once_with("Una imagen formal de IA.", "gmail")


# ---------------------------------------------------------------------------
# Tests de Headroom-AI
# ---------------------------------------------------------------------------

def test_headroom_compress_messages_called_on_llm_invoke(monkeypatch):
    """
    Verifica que compress_messages es invocado EXACTAMENTE una vez
    por cada llamada a invoke_with_fallback.
    """
    import src.nodes as nodes_module

    llamadas = []

    def mock_compress(messages, token_budget=None):
        llamadas.append(messages)
        return messages  # sin compresión real en tests

    monkeypatch.setattr(nodes_module, "compress_messages", mock_compress)

    # Configurar API key de prueba para que intente usar Gemini
    monkeypatch.setenv("GOOGLE_API_KEY", "dummy_key_for_testing")

    # Mockear ChatOllama y Ollama para evitar llamadas reales
    mock_llm_ollama = MagicMock()
    monkeypatch.setattr("src.nodes.ChatOllama", MagicMock(return_value=MagicMock(with_structured_output=MagicMock(return_value=mock_llm_ollama))))
    monkeypatch.setattr("src.nodes.Ollama", MagicMock())

    # Mockear ChatGoogleGenerativeAI para evitar llamadas reales
    mock_llm = MagicMock()
    monkeypatch.setattr("src.nodes.ChatGoogleGenerativeAI", MagicMock(return_value=MagicMock(with_structured_output=MagicMock(return_value=mock_llm))))

    # Mockear la respuesta del LLM
    mock_response = MultiPlatformOutput(
        gmail=GmailOutput(text="Test IA content", image_prompt="test image")
    )
    monkeypatch.setattr(nodes_module, "invoke_llm_with_retry", MagicMock(return_value=mock_response))

    # Invocar invoke_with_fallback directamente
    resultado = nodes_module.invoke_with_fallback(
        prompt_sistema="Sos un copywriter",
        prompt_human="Genera contenido sobre IA",
        schema=MultiPlatformOutput
    )

    assert resultado == mock_response
    # compress_messages debe haberse llamado exactamente una vez
    assert len(llamadas) == 1, f"Se esperaba 1 llamada a compress_messages, se obtuvieron {len(llamadas)}"
    # El primer mensaje debe ser el system prompt
    assert llamadas[0][0][0] == "system"
    assert llamadas[0][0][1] == "Sos un copywriter"
    # El segundo mensaje debe ser el human prompt
    assert llamadas[0][1][0] == "human"
    assert llamadas[0][1][1] == "Genera contenido sobre IA"


def test_headroom_fallback_when_disabled(monkeypatch):
    """
    Verifica que cuando HEADROOM_ENABLED=false, compress_messages
    retorna los mensajes originales sin modificación.
    """
    monkeypatch.setenv("HEADROOM_ENABLED", "false")

    # Re-importar para que tome el nuevo env var
    import importlib
    import src.headroom_compressor as hc_module
    importlib.reload(hc_module)

    original_messages = [
        ("system", "Sos un copywriter profesional"),
        ("human", "Genera contenido sobre IA para Instagram")
    ]

    result = hc_module.compress_messages(original_messages)

    assert result == original_messages, "Con HEADROOM_ENABLED=false los mensajes no deben modificarse"

    # Restaurar
    monkeypatch.setenv("HEADROOM_ENABLED", "true")
    importlib.reload(hc_module)


def test_headroom_savings_summary(tmp_path, monkeypatch):
    """
    Verifica que get_savings_summary lee correctamente el CSV actualizado
    con las columnas input_tokens_before, input_tokens_after, output_tokens,
    total_tokens y retorna métricas acumuladas correctas.
    """
    import src.headroom_compressor as hc_module
    import importlib

    # Apuntar el CSV a un directorio temporal para el test
    fake_logs = tmp_path / "logs"
    fake_logs.mkdir()
    fake_csv = fake_logs / "headroom_savings.csv"

    # Escribir datos de prueba con el nuevo formato de columnas
    import csv
    with open(fake_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "timestamp", "input_tokens_before", "input_tokens_after",
            "input_saved_tokens", "input_savings_pct",
            "output_tokens", "total_tokens", "token_budget"
        ])
        writer.writerow(["2026-06-23T10:00:00", 3000, 900, 2100, 70.0, 150, 1050, 2000])
        writer.writerow(["2026-06-23T10:01:00", 2500, 750, 1750, 70.0, 120, 870, 2000])

    # Parchear la ruta del CSV en el módulo
    monkeypatch.setattr(hc_module, "_SAVINGS_CSV", fake_csv)

    summary = hc_module.get_savings_summary()

    assert summary["total_calls"] == 2
    assert summary["total_input_before"] == 5500
    assert summary["total_input_after"] == 1650
    assert summary["total_input_saved"] == 3850
    assert summary["total_output_tokens"] == 270
    assert summary["total_tokens"] == 1920
    assert summary["avg_input_savings_pct"] == 70.0

