import os
import json
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from src.state import EstadoProyecto, ContenidoPlataforma

load_dotenv()

# Asegurar compatibilidad de variables de entorno
if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
    os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"].strip().strip('"').strip("'")

if not os.getenv("GOOGLE_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = "mock_api_key_for_testing"

# Inicializar modelos
llm_creativo = ChatGoogleGenerativeAI(
    model="models/gemini-2.5-flash",
    temperature=0.7,
    model_kwargs={"response_mime_type": "application/json"}
)

llm_corrector = ChatGoogleGenerativeAI(
    model="models/gemini-2.5-flash",
    temperature=0.0
)

# Reglas de validación por plataforma (evaluadas localmente en Python, sin costo de tokens)
REGLAS_PLATAFORMA = {
    "gmail":  {"max_len": 2000, "required": "IA"},
    "tiktok": {"max_len": 150,  "required": "IA"},
}

def nodo_generador_creativo(state: EstadoProyecto) -> dict:
    intentos = state.get("intentos", 0) + 1
    plataformas = state.get("plataformas_destino", [])
    publicaciones_previas = state.get("publicaciones", {})

    print(f"\n--- [IA] Generando Contenido Multiplataforma (Iteración {intentos}) ---")

    # Construir feedback específico por plataforma (si existen errores previos)
    feedback_plataformas = []
    for plat in plataformas:
        pub = publicaciones_previas.get(plat, {})
        errores = pub.get("errores", [])
        if errores:
            feedback_plataformas.append(
                f"- {plat.upper()}: Hubo los siguientes errores en la versión anterior que DEBES corregir: {errores}"
            )

    feedback_str = ""
    if feedback_plataformas:
        feedback_str = "\n\nFEEDBACK DE CORRECCIÓN (OBLIGATORIO):\n" + "\n".join(feedback_plataformas)

    # Construir restricciones específicas por plataforma
    restricciones = []
    for plat in plataformas:
        reglas = REGLAS_PLATAFORMA.get(plat, {})
        max_len = reglas.get("max_len", 500)
        required = reglas.get("required", "")
        restricciones.append(
            f"- {plat.upper()}: texto de máximo {max_len} caracteres, debe incluir la sigla o palabra '{required}'."
        )

    prompt_sistema = (
        "Sos un copywriter experto en redes sociales. Generá contenido de marketing creativo "
        "basado en la idea del usuario para las siguientes plataformas:\n"
        + "\n".join(restricciones)
        + "\n\nTu respuesta DEBE ser un JSON puro con exactamente una llave por cada plataforma solicitada. "
        "Cada valor debe ser un objeto con exactamente dos campos:\n"
        "  - 'texto': el mensaje para esa plataforma.\n"
        "  - 'prompt_imagen': un prompt en inglés para generar una imagen que acompañe el post.\n"
        "No agregues texto extra, solo el JSON."
    )

    respuesta = llm_creativo.invoke([
        ("system", prompt_sistema),
        ("human", f"Idea: {state['prompt_usuario']}.{feedback_str}")
    ])

    content = respuesta.content.strip()
    # Limpiar posibles bloques markdown del LLM
    if content.startswith("```"):
        lines = content.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        lines = lines[:-1] if lines[-1].startswith("```") else lines
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
    except Exception as e:
        print(f"[WARN] Error parseando JSON del LLM: {e}. Usando fallback.")
        data = {plat: {"texto": content, "prompt_imagen": "abstract technology design"} for plat in plataformas}

    # Construir publicaciones actualizadas manteniendo las plataformas ya aprobadas sin cambios
    publicaciones_actualizadas: dict[str, ContenidoPlataforma] = {}
    for plat in plataformas:
        pub_previa = publicaciones_previas.get(plat, {})
        # No regenerar una plataforma que ya fue aprobada por la IA
        if pub_previa.get("aprobado_por_ia", False):
            publicaciones_actualizadas[plat] = pub_previa
            print(f"  [{plat.upper()}] Ya aprobada, omitiendo regeneración.")
        else:
            plat_data = data.get(plat, {})
            publicaciones_actualizadas[plat] = ContenidoPlataforma(
                texto=plat_data.get("texto", ""),
                prompt_imagen=plat_data.get("prompt_imagen", ""),
                aprobado_por_ia=False,
                errores=[]
            )
            print(f"  [{plat.upper()}] Texto generado: '{publicaciones_actualizadas[plat]['texto'][:80]}...'")

    return {"publicaciones": publicaciones_actualizadas, "intentos": intentos}


def nodo_corrector_economico(state: EstadoProyecto) -> dict:
    publicaciones = state.get("publicaciones", {})
    print(f"\n--- [Corrector Python] Evaluando Publicaciones ---")

    publicaciones_evaluadas: dict[str, ContenidoPlataforma] = {}
    for plat, contenido in publicaciones.items():
        # Si ya fue aprobada, no re-evaluar
        if contenido.get("aprobado_por_ia", False):
            publicaciones_evaluadas[plat] = contenido
            print(f"  [{plat.upper()}] Ya aprobada por IA, omitiendo evaluación.")
            continue

        reglas = REGLAS_PLATAFORMA.get(plat, {})
        max_len = reglas.get("max_len", 500)
        required = reglas.get("required", "")
        texto = contenido.get("texto", "")
        errores = []

        if len(texto) > max_len:
            errores.append(
                f"El texto tiene {len(texto)} caracteres, supera el máximo de {max_len} para {plat.upper()}."
            )
        if required and required.upper() not in texto.upper():
            errores.append(
                f"Falta la palabra/sigla obligatoria '{required}' en el texto de {plat.upper()}."
            )

        aprobado = len(errores) == 0
        publicaciones_evaluadas[plat] = ContenidoPlataforma(
            texto=texto,
            prompt_imagen=contenido.get("prompt_imagen", ""),
            aprobado_por_ia=aprobado,
            errores=errores
        )
        status = "✅ APROBADO" if aprobado else f"❌ RECHAZADO ({errores})"
        print(f"  [{plat.upper()}] {status}")

    return {"publicaciones": publicaciones_evaluadas}


def nodo_revision_humana(state: EstadoProyecto) -> dict:
    """Nodo de paso que sirve como punto de freno para la intervención humana."""
    print("\n--- [Revisión Humana] Flujo autónomo completado. Esperando aprobación... ---")
    return {}
