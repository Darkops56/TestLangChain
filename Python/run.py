import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.graph import app_grafo
from src.tools import AdaptadorGmail, AdaptadorTikTok

def main():
    load_dotenv()

    if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"].strip().strip('"').strip("'")

    print("=" * 70)
    print("   LangGraph + Gemini + Contrato Segregado Multiplataforma")
    print("=" * 70)

    config = {"configurable": {"thread_id": "thread-publicacion-1"}}

    estado_inicial = {
        "prompt_usuario": "Escribir código limpio y desacoplado con Python y Arquitectura Hexagonal",
        "plataformas_destino": ["gmail", "tiktok"],
        "publicaciones": {},
        "intentos": 0,
        "aprobado_por_humano": False
    }

    print(f"\nPrompt: {estado_inicial['prompt_usuario']}")
    print(f"Plataformas: {estado_inicial['plataformas_destino']}\n")

    print(">>> Iniciando grafo cognitivo (auto-corrección autónoma)...")
    app_grafo.invoke(estado_inicial, config)

    state_info = app_grafo.get_state(config)
    valores = state_info.values

    print("\n" + "=" * 70)
    print("   REVISIÓN HUMANA — Contenido generado por plataforma")
    print("=" * 70)

    publicaciones = valores.get("publicaciones", {})
    for plat, contenido in publicaciones.items():
        estado_ia = "✅ APROBADO" if contenido.get("aprobado_por_ia") else "❌ RECHAZADO"
        print(f"\n  [{plat.upper()}] {estado_ia} (Intento {valores.get('intentos')}/3)")
        print(f"  Texto   : {contenido.get('texto', '')}")
        print(f"  Imagen  : {contenido.get('prompt_imagen', '')}")
        if contenido.get("errores"):
            print(f"  Errores : {contenido.get('errores')}")
    print("=" * 70)

    aprobacion = input("¿Aprobás el contenido para publicar? (si/no): ").strip().lower()
    if aprobacion == "si":
        print("\n>>> Contenido APROBADO. Publicando...")
        app_grafo.update_state(config, {"aprobado_por_humano": True})
        app_grafo.invoke(None, config)
    else:
        print("\n>>> Publicación cancelada por el usuario.")
        return

    estado_final = app_grafo.get_state(config).values
    publicaciones_finales = estado_final.get("publicaciones", {})

    print("\n>>> Publicando en plataformas...")
    adaptadores = {
        "gmail": AdaptadorGmail(),
        "tiktok": AdaptadorTikTok()
    }

    for plataforma in estado_final.get("plataformas_destino", []):
        contenido = publicaciones_finales.get(plataforma, {})
        adaptador = adaptadores.get(plataforma)
        if adaptador:
            exito = adaptador.publicar(
                texto=contenido.get("texto", ""),
                prompt_imagen=contenido.get("prompt_imagen", "")
            )
            if not exito:
                print(f"  ⚠️  Fallo al publicar en {plataforma}.")
        else:
            print(f"  ⚠️  No hay adaptador para: {plataforma}")

    print("\n" + "=" * 70)
    print("   Ejecución completada")
    print("=" * 70)

if __name__ == "__main__":
    main()
