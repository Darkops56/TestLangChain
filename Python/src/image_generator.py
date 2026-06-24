import os
import uuid
import warnings
from pathlib import Path
from dotenv import load_dotenv
import requests
import replicate
from typing import Dict, Any, Callable, Optional

# Load environment variables
load_dotenv()

# Directory where generated images are saved locally
IMAGES_DIR = Path(__file__).resolve().parent.parent / "images"

# Propagate REPLICATE_KEY to REPLICATE_API_TOKEN for replicate library compatibility
replicate_key = os.getenv("REPLICATE_KEY")
if replicate_key:
    os.environ["REPLICATE_API_TOKEN"] = replicate_key

def generate_image_replicate(
    prompt: str,
    aspect_ratio: str = "1:1",
    safety_filter_level: str = "block_medium_and_above",
    model_id: str = "google/imagen-4",
    plat: str = "general",
    **kwargs
) -> Dict[str, Any]:
    """
    Genera una imagen usando el modelo de Replicate (por defecto google/imagen-4).
    
    Args:
        prompt: El prompt de texto descriptivo para la imagen.
        aspect_ratio: Relación de aspecto (ej. '16:9', '1:1', '9:16').
        safety_filter_level: Nivel del filtro de seguridad.
        model_id: ID del modelo en Replicate.
        plat: Plataforma para nombrar el archivo.
        **kwargs: Parámetros adicionales para la llamada.
        
    Returns:
        Diccionario con el resultado (clave 'images' con URL y 'local_paths' con la ruta local).
    """
    if not os.environ.get("REPLICATE_API_TOKEN"):
        raise ValueError("La variable de entorno REPLICATE_KEY (o REPLICATE_API_TOKEN) no está configurada.")
        
    input_data = {
        "prompt": prompt,
        "aspect_ratio": aspect_ratio,
        "safety_filter_level": safety_filter_level
    }
    input_data.update(kwargs)
    
    print(f"[Replicate] Generando imagen para {plat} usando {model_id}...")
    
    # Executing the replicate command
    output = replicate.run(
        model_id,
        input=input_data
    )
    
    # Extract url and read function
    url = None
    if hasattr(output, "url"):
        url = output.url
    elif isinstance(output, str) and output.startswith("http"):
        url = output
    elif isinstance(output, list) and len(output) > 0:
        first = output[0]
        if hasattr(first, "url"):
            url = first.url
        elif isinstance(first, str) and first.startswith("http"):
            url = first
            
    result = {
        "images": [{"url": url or ""}],
        "model": model_id
    }
    
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    safe_prompt = "".join(c for c in prompt if c.isalnum() or c in (" ", "-", "_"))[:40]
    filename = f"{plat}_{safe_prompt}_{uuid.uuid4().hex[:8]}.png"
    filepath = IMAGES_DIR / filename
    
    saved = False
    try:
        # Try reading output stream using output.read() as shown in replicate docs
        if hasattr(output, "read"):
            data = output.read()
            filepath.write_bytes(data)
            saved = True
        elif url and url.startswith("http"):
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            saved = True
    except Exception as e:
        print(f"[Replicate] Error al descargar/guardar imagen: {e}")
        
    if saved:
        result["local_paths"] = [str(filepath.resolve())]
        print(f"[Replicate] Imagen guardada localmente: {filepath.resolve()}")
    else:
        result["local_paths"] = []
        
    return result

# --- Deprecated Fal.ai compatibility stubs ---

def default_on_queue_update(update: Any) -> None:
    warnings.warn(
        "default_on_queue_update está deprecado debido al reemplazo de Fal.ai por Replicate.",
        DeprecationWarning,
        stacklevel=2
    )

def _save_images_locally(result: Dict[str, Any], prompt: str) -> list:
    warnings.warn(
        "_save_images_locally está deprecado debido al reemplazo de Fal.ai por Replicate.",
        DeprecationWarning,
        stacklevel=2
    )
    # Serves as a helper to download/save list of image dicts
    saved_paths = []
    images = result.get("images", [])
    if not images:
        return saved_paths

    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for i, img in enumerate(images):
        url = img.get("url")
        if not url:
            continue
        safe_prompt = "".join(c for c in prompt if c.isalnum() or c in (" ", "-", "_"))[:40]
        filename = f"deprecated_fal_{safe_prompt}_{uuid.uuid4().hex[:8]}.png"
        filepath = IMAGES_DIR / filename
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            saved_paths.append(str(filepath.resolve()))
        except Exception as e:
            print(f"[Fal.ai Deprecated] Error al descargar imagen desde {url}: {e}")
    return saved_paths

def generate_image_krea_turbo(
    prompt: str,
    image_size: str = "square_hd",
    on_queue_update: Optional[Callable[[Any], None]] = None,
    with_logs: bool = True,
    **kwargs
) -> Dict[str, Any]:
    """
    [DEPRECATED] Genera una imagen usando Replicate como backend.
    """
    warnings.warn(
        "generate_image_krea_turbo está deprecado. Use generate_image_replicate en su lugar.",
        DeprecationWarning,
        stacklevel=2
    )
    # Map Fal.ai sizes to Replicate aspect ratios
    size_mapping = {
        "square_hd": "1:1",
        "square": "1:1",
        "landscape_4_3": "4:3",
        "landscape_16_9": "16:9",
        "portrait_16_9": "9:16",
        "portrait_4_3": "3:4"
    }
    ratio = size_mapping.get(image_size, "1:1")
    return generate_image_replicate(prompt=prompt, aspect_ratio=ratio, **kwargs)

def submit_image_krea_turbo(
    prompt: str,
    image_size: str = "square_hd",
    webhook_url: Optional[str] = None,
    **kwargs
) -> Any:
    warnings.warn(
        "submit_image_krea_turbo está deprecado debido al reemplazo de Fal.ai por Replicate.",
        DeprecationWarning,
        stacklevel=2
    )
    # Mock submission handler for compatibility
    class MockHandler:
        def __init__(self):
            self.request_id = f"deprecated-replicate-sub-{uuid.uuid4().hex[:8]}"
    return MockHandler()

def get_submission_status(
    request_id: str,
    with_logs: bool = True
) -> Any:
    warnings.warn(
        "get_submission_status está deprecado debido al reemplazo de Fal.ai por Replicate.",
        DeprecationWarning,
        stacklevel=2
    )
    class MockStatus:
        def __init__(self):
            self.status = "COMPLETED"
    return MockStatus()

def get_submission_result(
    request_id: str
) -> Any:
    warnings.warn(
        "get_submission_result está deprecado debido al reemplazo de Fal.ai por Replicate.",
        DeprecationWarning,
        stacklevel=2
    )
    return {"images": [{"url": "https://replicate.delivery/deprecated-stub.png"}]}
