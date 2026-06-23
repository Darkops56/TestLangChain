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


@patch("src.nodes.generar_imagen")
def test_image_generator_node(mock_generar_imagen):
    mock_generar_imagen.return_value = "/path/to/mock_image.png"
    
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
    mock_generar_imagen.assert_called_once_with("Una imagen formal de IA.", "gmail")

