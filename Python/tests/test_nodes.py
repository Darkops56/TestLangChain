from unittest.mock import MagicMock, patch
from src.nodes import nodo_generador_creativo, nodo_corrector_economico
from src.state import EstadoProyecto, ContenidoPlataforma

@patch("src.nodes.llm_creativo")
def test_nodo_generador_creativo_incrementa_intentos(mock_llm_creativo):
    mock_response = MagicMock()
    mock_response.content = '{"gmail": {"texto": "Diseño hexagonal en IA", "prompt_imagen": "imagen de engranajes"}}'
    mock_llm_creativo.invoke.return_value = mock_response

    state_inicial: EstadoProyecto = {
        "prompt_usuario": "Diseño hexagonal",
        "plataformas_destino": ["gmail"],
        "publicaciones": {},
        "intentos": 0,
        "aprobado_por_humano": False
    }

    output = nodo_generador_creativo(state_inicial)
    assert output["intentos"] == 1
    assert "gmail" in output["publicaciones"]
    assert output["publicaciones"]["gmail"]["texto"] == "Diseño hexagonal en IA"
    assert output["publicaciones"]["gmail"]["prompt_imagen"] == "imagen de engranajes"
    assert output["publicaciones"]["gmail"]["aprobado_por_ia"] is False
    assert output["publicaciones"]["gmail"]["errores"] == []
    mock_llm_creativo.invoke.assert_called_once()


def test_nodo_corrector_economico_aprueba():
    state: EstadoProyecto = {
        "prompt_usuario": "Test",
        "plataformas_destino": ["gmail", "tiktok"],
        "publicaciones": {
            "gmail": ContenidoPlataforma(
                texto="Texto válido con IA para Gmail.",
                prompt_imagen="imagen",
                aprobado_por_ia=False,
                errores=[]
            ),
            "tiktok": ContenidoPlataforma(
                texto="IA es genial",
                prompt_imagen="imagen",
                aprobado_por_ia=False,
                errores=[]
            )
        },
        "intentos": 1,
        "aprobado_por_humano": False
    }

    output = nodo_corrector_economico(state)
    assert output["publicaciones"]["gmail"]["aprobado_por_ia"] is True
    assert len(output["publicaciones"]["gmail"]["errores"]) == 0
    assert output["publicaciones"]["tiktok"]["aprobado_por_ia"] is True
    assert len(output["publicaciones"]["tiktok"]["errores"]) == 0


def test_nodo_corrector_economico_rechaza():
    state: EstadoProyecto = {
        "prompt_usuario": "Test",
        "plataformas_destino": ["gmail", "tiktok"],
        "publicaciones": {
            "gmail": ContenidoPlataforma(
                texto="Texto sin palabra clave",
                prompt_imagen="imagen",
                aprobado_por_ia=False,
                errores=[]
            ),
            "tiktok": ContenidoPlataforma(
                texto="a" * 200,
                prompt_imagen="imagen",
                aprobado_por_ia=False,
                errores=[]
            )
        },
        "intentos": 1,
        "aprobado_por_humano": False
    }

    output = nodo_corrector_economico(state)
    assert output["publicaciones"]["gmail"]["aprobado_por_ia"] is False
    assert any("IA" in e for e in output["publicaciones"]["gmail"]["errores"])
    assert output["publicaciones"]["tiktok"]["aprobado_por_ia"] is False
    assert any("150" in e for e in output["publicaciones"]["tiktok"]["errores"])
