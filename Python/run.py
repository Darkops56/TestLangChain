import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.graph import app_grafo

def check_keys():
    """
    Verifica si las claves de API necesarias están configuradas.
    """
    google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if not google_key and not openai_key:
        print("\n" + "!" * 70)
        print("   [ADVERTENCIA]: No se detecto ninguna API Key valida (Gemini o OpenAI).")
        print("   La aplicacion se ejecutara en modo DEMO con fallbacks locales y mocks.")
        print("!" * 70 + "\n")
    else:
        active_apis = []
        if google_key and google_key != "mock_api_key_for_testing":
            active_apis.append("Gemini")
        if openai_key:
            active_apis.append("OpenAI")
        print(f"\n[INFO] APIs activas detectadas: {', '.join(active_apis)}")

def check_ollama():
    """
    Verifica si el servidor de Ollama local está activo y tiene cargado
    el modelo gemma4:e2b, imprimiendo un aviso si arrancó con él.
    """
    try:
        import requests
        res = requests.get("http://localhost:11434/api/tags", timeout=1.5)
        if res.status_code == 200:
            models = res.json().get("models", [])
            for model_info in models:
                name = model_info.get("name", "")
                if name == "gemma4:e2b" or name.startswith("gemma4:e2b"):
                    print("\n" + "*" * 72)
                    print("   [AVISO]: ¡El agente arrancó con Gemma 4 e2b de Ollama (local) activo!")
                    print("*" * 72 + "\n")
                    return True
    except Exception:
        pass
    return False

def main():
    load_dotenv()
    check_ollama()
    check_keys()

    # Asegurar compatibilidad de variables de entorno de autenticación
    if "GEMINI_API_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"].strip().strip('"').strip("'")
    if "GEMINI_KEY" in os.environ and "GOOGLE_API_KEY" not in os.environ:
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_KEY"].strip().strip('"').strip("'")

    # Asegurar la existencia de la carpeta de imágenes
    os.makedirs(os.path.abspath(os.path.join(os.path.dirname(__file__), "output_images")), exist_ok=True)

    print("=" * 70)
    print("   LangGraph + Gemini + Contrato Segregado Multiplataforma (HITL)")
    print("=" * 70)

    thread_id = "thread-publicacion-multiplatform-1"
    config = {"configurable": {"thread_id": thread_id}}

    # Consultar si ya existe un estado en base de datos SQLite para este hilo
    state_info = app_grafo.get_state(config)
    valores_previos = state_info.values
    is_interrupted = len(state_info.next) > 0

    iniciar_nuevo = True

    if valores_previos:
        print(f"\n[Persistencia SQLite] Se encontró una ejecución previa para el hilo '{thread_id}'.")
        print(f"  Prompt anterior: '{valores_previos.get('user_prompt')}'")
        print(f"  Plataformas    : {valores_previos.get('platforms')}")
        print(f"  Intentos LLM   : {valores_previos.get('retry_count', 0)}/3")
        pub_res = valores_previos.get("publication_results", {})
        if pub_res:
            print(f"  Publicaciones  : {pub_res}")

        if is_interrupted:
            opcion = input("\n¿Deseas (r)eanudar la ejecución anterior o (i)niciar una nueva desde cero? (r/i): ").strip().lower()
            if opcion == 'r':
                iniciar_nuevo = False
        else:
            opcion = input("\nLa ejecución anterior está completa. ¿Deseas (i)niciar una nueva sobreescribiendo el estado? (i/n): ").strip().lower()
            if opcion != 'i':
                print("Finalizando ejecución.")
                return

    if iniciar_nuevo:
        print("\n--- INICIANDO NUEVA PUBLICACIÓN ---")
        prompt = input("Ingresa la idea del post a generar: ").strip()
        if not prompt:
            prompt = "Escribir código limpio y desacoplado con Python y Arquitectura Hexagonal y agregar que se usó IA."
            print(f"Usando prompt por defecto: '{prompt}'")

        estado_inicial = {
            "user_prompt": prompt,
            "platforms": ["gmail", "tiktok", "instagram", "whatsapp"],
            "outputs": {},
            "retry_count": 0,
            "platform_feedback": {},
            "is_approved": False,
            "image_paths": {},
            "publication_results": {},
            "publication_errors": {}
        }

        print(f"\nPrompt: {estado_inicial['user_prompt']}")
        print(f"Plataformas solicitadas: {estado_inicial['platforms']}\n")

        print(">>> Iniciando grafo cognitivo (generación de textos y auto-corrección)...")
        app_grafo.invoke(estado_inicial, config)
    else:
        print("\n>>> Recuperando el estado interrumpido del grafo...")

    # Bucle de interacción con el usuario en el paso de revisión (HITL)
    while True:
        state_info = app_grafo.get_state(config)
        valores = state_info.values
        
        # Si ya no está interrumpido, salimos del bucle
        if not state_info.next:
            break

        print("\n" + "=" * 70)
        print("   REVISIÓN HUMANA — Contenido y Recursos Generados por Plataforma")
        print("=" * 70)

        outputs = valores.get("outputs", {}) or {}
        image_paths = valores.get("image_paths", {}) or {}
        publication_results = valores.get("publication_results", {}) or {}

        for plat, contenido in outputs.items():
            estado_ia = "[OK] APROBADO por IA" if contenido.get("is_valid") else "[FAIL] RECHAZADO por IA"
            estado_pub = "[PUBLISHED] PUBLICADO" if publication_results.get(plat) else "[PENDING] PENDIENTE DE PUBLICAR"
            
            print(f"\n  [{plat.upper()}] {estado_ia} | {estado_pub}")
            print(f"  Texto   : {contenido.get('text', '')}")
            
            prompt_img = contenido.get('image_prompt', '')
            if prompt_img:
                print(f"  Prompt Imagen: {prompt_img}")
                
            img_path = image_paths.get(plat, "")
            if img_path:
                print(f"  Imagen  : {img_path} (Generada y guardada)")
            else:
                print("  Imagen  : No generada")
                
            if contenido.get("errors"):
                print(f"  Errores de Validacion: {contenido.get('errors')}")
        
        print("\n" + "=" * 70)

        aprobacion = input("\n¿Aprobás el contenido para publicar? (si/no/regenerar): ").strip().lower()
        
        if aprobacion == "si":
            print("\n>>> Enviando aprobación al grafo y reanudando ejecución...")
            app_grafo.update_state(config, {"is_approved": True})
            app_grafo.invoke(None, config)
            break
        elif aprobacion == "regenerar":
            feedback = input("Introduce feedback/directivas para regenerar el contenido: ").strip()
            if not feedback:
                feedback = "Por favor, corrige los errores y ajusta los textos a las restricciones."
            
            # Resetear intentos y configurar el feedback del usuario en la plataforma
            feedbacks = {plat: feedback for plat in valores.get("platforms", [])}
            app_grafo.update_state(config, {
                "retry_count": 0, 
                "platform_feedback": feedbacks,
                "is_approved": False
            })
            
            # Apuntar la ejecución de vuelta al generador
            app_grafo.update_state(config, {}, as_node="generador")
            print("\n>>> Enviando feedback y re-ejecutando generador...")
            app_grafo.invoke(None, config)
        else:
            print("\n>>> Abortando publicación...")
            app_grafo.update_state(config, {"is_approved": False})
            app_grafo.invoke(None, config)
            break

    # Mostrar estado final
    estado_final = app_grafo.get_state(config).values
    aprobado_final = estado_final.get("is_approved", False)
    pub_res = estado_final.get("publication_results", {})
    pub_err = estado_final.get("publication_errors", {})
    
    print("\n" + "=" * 70)
    if aprobado_final:
        print("   RESUMEN FINAL DE PUBLICACIONES:")
        for plat, exito in pub_res.items():
            result_str = "[SUCCESS] PUBLICADO CON EXITO" if exito else "[FAIL] FALLO"
            err_str = f" (Error: {pub_err.get(plat)})" if not exito and pub_err.get(plat) else ""
            print(f"   - {plat.upper()}: {result_str}{err_str}")
            
        # Si hubo fallos de publicación, permitir reintento único para las fallidas
        plataformas_fallidas = [plat for plat, exito in pub_res.items() if not exito]
        if plataformas_fallidas:
            reintentar = input("\n¿Deseas reintentar publicar UNICAMENTE en las plataformas fallidas? (si/no): ").strip().lower()
            if reintentar == "si":
                print("\n>>> Configurando reintento de publicación...")
                # Apuntar de nuevo al nodo de publicar
                app_grafo.update_state(config, {}, as_node="publish")
                app_grafo.invoke(None, config)
                
                # Cargar el estado final actualizado
                estado_reintento = app_grafo.get_state(config).values
                pub_res_re = estado_reintento.get("publication_results", {})
                print("\n   RESUMEN FINAL POST-REINTENTO:")
                for plat, exito in pub_res_re.items():
                    result_str = "[SUCCESS] PUBLICADO CON EXITO" if exito else "[FAIL] FALLO"
                    print(f"   - {plat.upper()}: {result_str}")
    else:
        print("   Ejecución finalizada. Publicación abortada.")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
