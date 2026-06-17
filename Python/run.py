import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.graph import app_grafo

def main():
    load_dotenv()

    # Asegurar compatibilidad de variables de entorno de autenticación
    if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"].strip().strip('"').strip("'")

    print("=" * 70)
    print("   LangGraph + Gemini + Contrato Segregado Multiplataforma (HITL)")
    print("=" * 70)

    config = {"configurable": {"thread_id": "thread-publicacion-multiplatform-1"}}

    estado_inicial = {
        "user_prompt": "Escribir código limpio y desacoplado con Python y Arquitectura Hexagonal y agregar que se usó IA.",
        "platforms": ["gmail", "tiktok", "instagram", "whatsapp"],
        "outputs": {},
        "retry_count": 0,
        "platform_feedback": {},
        "is_approved": False
    }

    print(f"\nPrompt: {estado_inicial['user_prompt']}")
    print(f"Plataformas solicitadas: {estado_inicial['platforms']}\n")

    print(">>> Iniciando grafo cognitivo (generación estructurada + auto-corrección autónoma)...")
    app_grafo.invoke(estado_inicial, config)

    # El grafo se interrumpe justo antes de 'publish'
    state_info = app_grafo.get_state(config)
    valores = state_info.values

    print("\n" + "=" * 70)
    print("   REVISIÓN HUMANA — Contenido generado por plataforma")
    print("=" * 70)

    outputs = valores.get("outputs", {}) or {}
    for plat, contenido in outputs.items():
        estado_ia = "✅ APROBADO por IA" if contenido.get("is_valid") else "❌ RECHAZADO por IA"
        print(f"\n  [{plat.upper()}] {estado_ia} (Intentos realizados: {valores.get('retry_count')}/3)")
        print(f"  Texto   : {contenido.get('text', '')}")
        # print(f"  Imagen  : {contenido.get('image_prompt', '')}") # Comentado por requerimiento de texto plano únicamente
        if contenido.get("errors"):
            print(f"  Errores : {contenido.get('errors')}")
    print("=" * 70)

    aprobacion = input("\n¿Aprobás el contenido para publicar? (si/no): ").strip().lower()
    if aprobacion == "si":
        print("\n>>> Enviando aprobación al grafo y reanudando ejecución...")
        app_grafo.update_state(config, {"is_approved": True})
        app_grafo.invoke(None, config)
    else:
        print("\n>>> Enviando rechazo/cancelación al grafo y reanudando ejecución...")
        app_grafo.update_state(config, {"is_approved": False})
        app_grafo.invoke(None, config)

    # Mostrar estado final
    estado_final = app_grafo.get_state(config).values
    aprobado_final = estado_final.get("is_approved", False)
    
    print("\n" + "=" * 70)
    if aprobado_final:
        print("   Ejecución completada con éxito. Publicaciones enviadas.")
    else:
        print("   Ejecución finalizada. Publicación abortada.")
    print("=" * 70)

if __name__ == "__main__":
    main()
