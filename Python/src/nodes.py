import os
import json
import re
from typing import Dict, List, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from src.state import MultiPlatformState, PlatformContent
from src.tools import generar_imagen

load_dotenv()

# Forzar la versión de la API de Google a "v1"
os.environ["GOOGLE_API_VERSION"] = "v1"

# Asegurar compatibilidad de variables de entorno de autenticación
if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"].strip().strip('"').strip("'")

# Clave mock para entornos de prueba
if not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = "mock_api_key_for_testing"


# --- Restricciones específicas a nivel de modelos Pydantic con soporte de Imagen ---

class GmailOutput(BaseModel):
    text: str = Field(
        ...,
        description="El cuerpo del correo electrónico. Debe ser formal y descriptivo. "
                    "Límite máximo de 2000 caracteres. "
                    "DEBE contener obligatoriamente la sigla o palabra 'IA' en el texto. "
                    "Se permite formato HTML básico (como <p>, <a>, <strong>)."
    )
    image_prompt: Optional[str] = Field(
        default="", 
        description="Propuesta de imagen detallada y formal para adjuntar al correo sobre el tema."
    )

class TikTokOutput(BaseModel):
    text: str = Field(
        ...,
        description="El texto de subtítulo para TikTok. Debe ser corto y enganchador. "
                    "Límite máximo de 150 caracteres. "
                    "DEBE incluir de forma obligatoria al menos un hashtag (#) y la sigla o palabra 'IA' en el texto."
    )
    image_prompt: Optional[str] = Field(
        default="", 
        description="Descripción de la imagen o miniatura de alta retención visual en formato vertical para TikTok."
    )

class InstagramOutput(BaseModel):
    text: str = Field(
        ...,
        description="El texto de descripción para Instagram. Debe ser amigable y persuasivo. "
                    "Límite máximo de 220 caracteres. "
                    "DEBE incluir de forma obligatoria al menos un hashtag (#) y la sigla o palabra 'IA' en el texto."
    )
    image_prompt: Optional[str] = Field(
        default="", 
        description="Detalle visual estético para el post de Instagram (fotografía, carrusel, infografía)."
    )

class WhatsAppOutput(BaseModel):
    text: str = Field(
        ...,
        description="El texto del mensaje para WhatsApp. Debe ser directo y claro. "
                    "Límite máximo de 500 caracteres. "
                    "DEBE incluir de forma obligatoria la sigla o palabra 'IA' en el texto. "
                    "NO debe incluir etiquetas HTML (como <p>, <a>, etc.) bajo ninguna circunstancia."
    )
    image_prompt: Optional[str] = Field(
        default="", 
        description="Idea o descripción de la tarjeta gráfica/imagen para adjuntar al mensaje de WhatsApp."
    )

class SinglePlatformOutput(BaseModel):
    text: str
    image_prompt: Optional[str] = ""

class MultiPlatformOutput(BaseModel):
    gmail: Optional[GmailOutput] = Field(None, description="Contenido estructurado para Gmail si ha sido solicitado.")
    tiktok: Optional[TikTokOutput] = Field(None, description="Contenido estructurado para TikTok si ha sido solicitado.")
    instagram: Optional[InstagramOutput] = Field(None, description="Contenido estructurado para Instagram si ha sido solicitado.")
    whatsapp: Optional[WhatsAppOutput] = Field(None, description="Contenido estructurado para WhatsApp si ha sido solicitado.")


# Función de invocación decorada con Tenacity para reintentos exponenciales resilientes
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(Exception),
    reraise=True
)
def invoke_llm_with_retry(llm, prompt_sistema: str, prompt_human: str):
    return llm.invoke([
        ("system", prompt_sistema),
        ("human", prompt_human)
    ])


# Vincular salida estructurada con fallback dinámico y reintentos
def invoke_with_fallback(prompt_sistema: str, prompt_human: str, schema) -> MultiPlatformOutput:
    errors = []
    
    # 1. Intentar con Gemini
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if google_key and google_key != "mock_api_key_for_testing":
        try:
            print("[INFO] Intentando generación estructurada con Gemini (models/gemini-2.5-flash)...")
            llm_gemini = ChatGoogleGenerativeAI(
                model="models/gemini-2.5-flash",
                temperature=0.7,
            ).with_structured_output(schema)
            # Llamada con reintento resiliente
            resultado = invoke_llm_with_retry(llm_gemini, prompt_sistema, prompt_human)
            return resultado
        except Exception as e:
            error_msg = f"Gemini falló después de reintentos: {e}"
            print(f"[WARN] {error_msg}")
            errors.append(error_msg)
            
    # 2. Intentar con OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        try:
            print("[INFO] Intentando generación estructurada con OpenAI (gpt-4o-mini)...")
            llm_openai = ChatOpenAI(
                model="gpt-4o-mini",
                temperature=0.7,
                api_key=openai_key
            ).with_structured_output(schema)
            # Llamada con reintento resiliente
            resultado = invoke_llm_with_retry(llm_openai, prompt_sistema, prompt_human)
            return resultado
        except Exception as e:
            error_msg = f"OpenAI falló después de reintentos: {e}"
            print(f"[WARN] {error_msg}")
            errors.append(error_msg)
            
    # 3. Si ambos fallan, levantar excepción para gatillar el fallback estático
    raise RuntimeError(f"No se pudo completar la generación estructurada con ningún LLM disponible. Errores: {errors}")


class StructuredLLMFallbackWrapper:
    def invoke(self, messages, *args, **kwargs):
        prompt_sistema = ""
        prompt_human = ""
        for role, content in messages:
            if role == "system":
                prompt_sistema = content
            elif role == "human":
                prompt_human = content
        return invoke_with_fallback(prompt_sistema, prompt_human, MultiPlatformOutput)

llm_estructurado = StructuredLLMFallbackWrapper()

# Reglas locales deterministas
PLATFORM_RULES = {
    "gmail": {
        "max_len": 2000,
        "required_word": "IA",
        "no_html": False,
        "require_hashtag": False
    },
    "tiktok": {
        "max_len": 150,
        "required_word": "IA",
        "no_html": True,
        "require_hashtag": True
    },
    "instagram": {
        "max_len": 220,
        "required_word": "IA",
        "no_html": True,
        "require_hashtag": True
    },
    "whatsapp": {
        "max_len": 500,
        "required_word": "IA",
        "no_html": True,
        "require_hashtag": False
    }
}

def generator_node(state: MultiPlatformState) -> dict:
    """
    Genera contenido multiplataforma respetando las restricciones de los modelos Pydantic
    e inyectando de forma matemática y agresiva el feedback anterior para romper bucles sordos.
    """
    retry_count = state.get("retry_count", 0) + 1
    platforms = state.get("platforms", [])
    outputs = state.get("outputs", {}) or {}
    platform_feedback = state.get("platform_feedback", {}) or {}

    # Identificar plataformas que necesitan generarse o corregirse
    platforms_to_generate = []
    for plat in platforms:
        out = outputs.get(plat, {})
        if not out or not out.get("is_valid", False):
            platforms_to_generate.append(plat)

    if not platforms_to_generate:
        return {"retry_count": retry_count}

    print(f"\n--- [IA] Generando Contenido Multiplataforma para {platforms_to_generate} (Intento {retry_count}/3) ---")

    # --- Prompt de Sistema Agresivo con el Feedback ---
    feedback_lines = []
    for plat in platforms_to_generate:
        error_msg = platform_feedback.get(plat)
        if error_msg:
            feedback_lines.append(
                f"- PLATAFORMA: {plat.upper()}\n"
                f"  ERROR EN EL INTENTO PREVIO: {error_msg}\n"
                f"  DIRECTIVA CRÍTICA: Reescribe la salida para corregir este error de inmediato. "
                f"Si el error menciona que falta la palabra 'IA', colócala en el texto. "
                f"Si falta un hashtag, incluye al menos un '#'. Si supera caracteres, acorta drásticamente."
            )

    feedback_str = ""
    if feedback_lines:
        feedback_str = (
            "\n\n⚠️⚠️⚠️ INSTRUCCIÓN DE CORRECCIÓN DE ERRORES (MÁXIMA PRIORIDAD) ⚠️⚠️⚠️\n"
            "El corrector automático de la aplicación ha rechazado tu salida anterior para las siguientes plataformas. "
            "Debes modificar matemáticamente el contenido para subsanar los errores señalados a continuación:\n"
            + "\n".join(feedback_lines)
            + "\n\nCualquier texto que no corrija estos fallos específicos será rechazado de nuevo."
        )

    # Describir restricciones básicas por plataforma en el prompt de sistema
    restricciones = []
    for plat in platforms_to_generate:
        rules = PLATFORM_RULES.get(plat, {})
        max_len = rules.get("max_len", 500)
        target_len = int(max_len * 0.90)  # Buffer de seguridad del 10%
        req = rules.get("required_word", "IA")
        
        restriccion = f"- {plat.upper()}: límite real máximo de {max_len} caracteres. DIRECTIVA ESTRICTA: Apunta a un buffer de seguridad del 10% por debajo del límite, redactando pensando en un máximo de {target_len} caracteres. Debe incluir '{req}'."
        if rules.get("require_hashtag"):
            restriccion += " Debe incluir hashtags (#)."
        if rules.get("no_html"):
            restriccion += " NO debe contener HTML."
        else:
            restriccion += " Se permite formato HTML."
        
        restricciones.append(restriccion)

    few_shot_examples = (
        "EJEMPLOS DE APRENDIZAJE DE POCOS DISPAROS (FEW-SHOT) PARA REDUCCIÓN DE TEXTO POR FEEDBACK:\n"
        "Cuando el corrector de la aplicación rechace tu salida por exceder el límite de caracteres, debes acortar drásticamente el texto manteniendo el gancho comercial, las siglas o palabra 'IA' y los hashtags necesarios.\n\n"
        "Ejemplo 1:\n"
        "- Input Feedback: \"INSTAGRAM ❌ RECHAZADO: El texto supera el límite de 220 caracteres (tiene 250).\"\n"
        "- Output Solución: \"¡Código Python limpio! 🚀 Con la Arquitectura Hexagonal y el poder de la IA, escala tus proyectos y desacopla componentes sin fricciones. #Python #IA #CleanCode\" (175 caracteres - Seguro y compacto).\n\n"
        "Ejemplo 2:\n"
        "- Input Feedback: \"TIKTOK ❌ RECHAZADO: El texto supera el límite de 150 caracteres (tiene 158).\"\n"
        "- Output Solución: \"¡Limpia tu Python con Arquitectura Hexagonal! 🐍 Desacopla módulos y escala con el poder de la IA. #Python #IA #CleanArchitecture\" (128 caracteres - Seguro y compacto).\n"
    )

    prompt_sistema = (
        "Sos un copywriter profesional experto en redes sociales. Tu tarea es generar "
        "contenido de marketing y conceptos de imágenes adaptados a las siguientes plataformas solicitadas:\n"
        + "\n".join(restricciones)
        + "\n\n"
        + few_shot_examples
        + "\nResponde llenando los campos de texto e image_prompt correspondientes del formato estructurado. "
        "Debes prestar especial atención a los requisitos de caracteres, hashtags (#), etiquetas HTML y "
        "palabras clave obligatorias definidos en los esquemas Pydantic. Recuerda siempre respetar el buffer de seguridad del 10%."
    )

    prompt_human = f"Idea del usuario: {state['user_prompt']}.{feedback_str}"

    try:
        resultado = llm_estructurado.invoke([
            ("system", prompt_sistema),
            ("human", prompt_human)
        ])
        
        # Mapear la respuesta de Pydantic a un diccionario interno
        dict_respuesta = {}
        if resultado.gmail:
            dict_respuesta["gmail"] = resultado.gmail
        if resultado.tiktok:
            dict_respuesta["tiktok"] = resultado.tiktok
        if resultado.instagram:
            dict_respuesta["instagram"] = resultado.instagram
        if resultado.whatsapp:
            dict_respuesta["whatsapp"] = resultado.whatsapp
            
    except Exception as e:
        print(f"[WARN] Error en la generación estructurada: {e}. Usando fallback.")
        dict_respuesta = {}
        for plat in platforms_to_generate:
            text_fb = f"Contenido de fallback para {plat} sobre: {state['user_prompt']}. IA."
            if plat in ["tiktok", "instagram"]:
                text_fb += " #tech"
            dict_respuesta[plat] = SinglePlatformOutput(
                text=text_fb,
                image_prompt=f"Ilustración digital sobre {state['user_prompt']}"
            )

    # Actualizar salidas manteniendo las aprobadas anteriormente intactas
    outputs_actualizados = dict(outputs)
    for plat in platforms:
        if plat in outputs and outputs[plat].get("is_valid", False):
            print(f"  [{plat.upper()}] Ya aprobada en iteración anterior, se conserva sin cambios.")
            continue
        
        plat_data = dict_respuesta.get(plat)
        if plat_data:
            outputs_actualizados[plat] = PlatformContent(
                text=plat_data.text,
                image_prompt=getattr(plat_data, "image_prompt", "") or "",
                is_valid=False,
                errors=[]
            )
            try:
                print(f"  [{plat.upper()}] Generado: '{plat_data.text[:75]}...'")
            except UnicodeEncodeError:
                texto_seguro = plat_data.text[:75].encode('ascii', 'ignore').decode('ascii')
                print(f"  [{plat.upper()}] Generado: '{texto_seguro}...'")
        else:
            outputs_actualizados[plat] = PlatformContent(
                text="",
                image_prompt="",
                is_valid=False,
                errors=["No se generó contenido para esta plataforma o falló el formato."]
            )

    return {"outputs": outputs_actualizados, "retry_count": retry_count}


def nodo_corrector_economico(state: MultiPlatformState) -> dict:
    """
    Evalúa localmente de forma determinista el contenido generado para cada plataforma.
    """
    outputs = state.get("outputs", {}) or {}
    platform_feedback = dict(state.get("platform_feedback", {}) or {})
    
    print(f"\n--- [Corrector Local Python] Evaluando restricciones ---")
    
    outputs_evaluados = {}
    for plat, contenido in outputs.items():
        if contenido.get("is_valid", False):
            outputs_evaluados[plat] = contenido
            print(f"  [{plat.upper()}] Ya validada previamente.")
            continue

        rules = PLATFORM_RULES.get(plat)
        if not rules:
            outputs_evaluados[plat] = PlatformContent(
                text=contenido.get("text", ""),
                image_prompt=contenido.get("image_prompt", ""),
                is_valid=True,
                errors=[]
            )
            if plat in platform_feedback:
                del platform_feedback[plat]
            print(f"  [{plat.upper()}] [OK] Aprobada (sin reglas de validación)")
            continue

        texto = contenido.get("text", "")
        max_len = rules["max_len"]
        required = rules["required_word"]
        no_html = rules["no_html"]
        require_hashtag = rules["require_hashtag"]
        
        errores = []

        # Validación de longitud
        if len(texto) > max_len:
            errores.append(f"El texto supera el límite de {max_len} caracteres (tiene {len(texto)}).")
        
        # Validación de palabra obligatoria
        if required and required.lower() not in texto.lower():
            errores.append(f"Falta la palabra/sigla obligatoria '{required}'.")
            
        # Validación de hashtags
        if require_hashtag and "#" not in texto:
            errores.append("Debe incluir al menos un hashtag (#).")
            
        # Validación de no HTML
        if no_html:
            html_tags = re.findall(r"<[^>]+>", texto)
            if html_tags:
                errores.append(f"Contiene etiquetas HTML no permitidas: {html_tags}")

        is_valid = len(errores) == 0
        
        outputs_evaluados[plat] = PlatformContent(
            text=texto,
            image_prompt=contenido.get("image_prompt", ""),
            is_valid=is_valid,
            errors=errores
        )

        if is_valid:
            if plat in platform_feedback:
                del platform_feedback[plat]
            print(f"  [{plat.upper()}] [OK] APROBADO")
        else:
            platform_feedback[plat] = "; ".join(errores)
            print(f"  [{plat.upper()}] [FAIL] RECHAZADO: {errores}")

    return {"outputs": outputs_evaluados, "platform_feedback": platform_feedback}


def image_generator_node(state: MultiPlatformState) -> dict:
    """
    Nodo que recorre las plataformas y, para cada una con contenido de texto validado,
    genera la imagen correspondiente si aún no se ha generado en esta sesión.
    """
    outputs = state.get("outputs", {}) or {}
    image_paths = dict(state.get("image_paths", {}) or {})
    publication_errors = dict(state.get("publication_errors", {}) or {})
    
    print(f"\n--- [Generador de Imágenes] Procesando imágenes para plataformas validadas ---")
    
    for plat, contenido in outputs.items():
        # Solo generar si el texto fue validado localmente
        if not contenido.get("is_valid", False):
            print(f"  [{plat.upper()}] Omitido (texto no validado).")
            continue
            
        # Si ya existe una ruta de imagen válida en el estado, la conservamos
        if plat in image_paths and image_paths[plat] and os.path.exists(image_paths[plat]):
            print(f"  [{plat.upper()}] Ya cuenta con imagen: {image_paths[plat]}")
            continue
            
        image_prompt = contenido.get("image_prompt", "")
        if not image_prompt:
            print(f"  [{plat.upper()}] Advertencia: No hay prompt de imagen.")
            continue
            
        try:
            print(f"  [{plat.upper()}] Generando imagen...")
            path = generar_imagen(image_prompt, plat)
            image_paths[plat] = path
            print(f"  [{plat.upper()}] Imagen generada en: {path}")
        except Exception as e:
            err_str = f"Error al generar imagen para {plat}: {e}"
            print(f"  ❌ {err_str}")
            if plat not in publication_errors:
                publication_errors[plat] = []
            publication_errors[plat].append(err_str)
            
    return {"image_paths": image_paths, "publication_errors": publication_errors}
