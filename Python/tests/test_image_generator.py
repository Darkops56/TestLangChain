import os
from pathlib import Path
from unittest.mock import patch, MagicMock, ANY
import pytest
import replicate
from src.image_generator import (
    generate_image_replicate,
    generate_image_krea_turbo,
    submit_image_krea_turbo,
    get_submission_status,
    get_submission_result,
    default_on_queue_update,
    _save_images_locally,
    IMAGES_DIR
)

# Ensure environment variables are loaded
from dotenv import load_dotenv
load_dotenv()

# Propagate REPLICATE_KEY to REPLICATE_API_TOKEN if available
if "REPLICATE_KEY" in os.environ and "REPLICATE_API_TOKEN" not in os.environ:
    os.environ["REPLICATE_API_TOKEN"] = os.environ["REPLICATE_KEY"]

def test_generate_image_replicate_mocked(tmp_path):
    """
    Evalúa que la función llame correctamente a replicate.run
    con los parámetros esperados usando un mock.
    """
    mock_output = MagicMock()
    mock_output.url = "https://replicate.delivery/files/test-image.png"
    mock_output.read.return_value = b"fake_image_bytes"
    
    with patch("replicate.run") as mock_run:
        mock_run.return_value = mock_output
        
        prompt = "Un perro astronauta en Marte estilo cyberpunk"
        result = generate_image_replicate(prompt=prompt, aspect_ratio="16:9", model_id="google/imagen-4", plat="gmail")
        
        # Validar que se llamó al suscriptor con los argumentos esperados
        mock_run.assert_called_once_with(
            "google/imagen-4",
            input={
                "prompt": prompt,
                "aspect_ratio": "16:9",
                "safety_filter_level": "block_medium_and_above"
            }
        )
        
        # Validar que el resultado devuelto coincide con la estructura
        assert "images" in result
        assert len(result["images"]) == 1
        assert result["images"][0]["url"] == "https://replicate.delivery/files/test-image.png"
        assert "local_paths" in result
        assert len(result["local_paths"]) == 1
        
        # Cleanup saved file
        saved_path = Path(result["local_paths"][0])
        assert saved_path.exists()
        assert saved_path.read_bytes() == b"fake_image_bytes"
        saved_path.unlink()

def test_deprecated_fal_compatibility_generate_mocked():
    """
    Evalúa que la función deprecada generate_image_krea_turbo llame internamente
    a generate_image_replicate convirtiendo los parámetros correctamente.
    """
    mock_output = MagicMock()
    mock_output.url = "https://replicate.delivery/deprecated-stub.png"
    mock_output.read.return_value = b"deprecated_bytes"
    
    with patch("replicate.run") as mock_run:
        mock_run.return_value = mock_output
        
        prompt = "Un gato espacial"
        with pytest.deprecated_call():
            result = generate_image_krea_turbo(prompt=prompt, image_size="landscape_4_3")
            
        mock_run.assert_called_once_with(
            "google/imagen-4",
            input={
                "prompt": prompt,
                "aspect_ratio": "4:3",
                "safety_filter_level": "block_medium_and_above"
            }
        )
        
        # Cleanup
        if result.get("local_paths"):
            Path(result["local_paths"][0]).unlink()

def test_deprecated_default_on_queue_update():
    with pytest.deprecated_call():
        default_on_queue_update(None)

def test_deprecated_save_images_locally(tmp_path):
    mock_url = "https://replicate.delivery/test-image-deprecated.png"
    result = {
        "images": [
            {
                "url": mock_url
            }
        ]
    }
    
    with patch("requests.get") as mock_get, pytest.deprecated_call():
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b"old_compat_bytes"
        mock_get.return_value = mock_response
        
        saved = _save_images_locally(result, "test_prompt")
        assert len(saved) == 1
        saved_path = Path(saved[0])
        assert saved_path.exists()
        assert saved_path.read_bytes() == b"old_compat_bytes"
        saved_path.unlink()

def test_deprecated_submit_image_mocked():
    with pytest.deprecated_call():
        handler = submit_image_krea_turbo(prompt="Mars travel", image_size="square_hd")
    assert hasattr(handler, "request_id")
    
    with pytest.deprecated_call():
        status = get_submission_status(handler.request_id)
    assert hasattr(status, "status")
    
    with pytest.deprecated_call():
        res = get_submission_result(handler.request_id)
    assert "images" in res

# Ejecutar test real en vivo solo si REPLICATE_KEY o REPLICATE_API_TOKEN están configurados
has_replicate_key = bool(os.environ.get("REPLICATE_KEY") or os.environ.get("REPLICATE_API_TOKEN"))

@pytest.mark.skipif(not has_replicate_key, reason="REPLICATE_KEY/REPLICATE_API_TOKEN no está configurado en las variables de entorno.")
def test_generate_image_replicate_live():
    """
    Evalúa la comunicación en vivo con la API de Replicate usando google/imagen-4.
    """
    prompt = "A simple white coffee cup on a wooden table, high quality, realistic"
    try:
        result = generate_image_replicate(prompt=prompt, aspect_ratio="1:1", model_id="google/imagen-4", plat="test_live")
        
        # Validaciones de respuesta real
        assert isinstance(result, dict), "El resultado debe ser un diccionario"
        assert "images" in result, "El resultado debe contener la clave 'images'"
        assert len(result["images"]) > 0, "Debe haberse generado al menos una imagen"
        
        image_info = result["images"][0]
        assert "url" in image_info, "La información de la imagen debe contener un campo 'url'"
        assert image_info["url"].startswith("http"), "La URL de la imagen debe ser válida"
        
        assert "local_paths" in result, "El resultado debe contener 'local_paths'"
        assert len(result["local_paths"]) > 0, "La imagen debe haberse guardado localmente"
        
        # Limpiar archivo generado
        saved_path = Path(result["local_paths"][0])
        assert saved_path.exists()
        saved_path.unlink()
        print(f"\n[Test Live OK] Imagen generada y verificada exitosamente con Replicate: {image_info['url']}")
    except Exception as e:
        pytest.fail(f"Error en la llamada en vivo a Replicate: {e}")
