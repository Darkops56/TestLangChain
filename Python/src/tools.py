import os
import time
from abc import ABC, abstractmethod
import concurrent.futures
from typing import Dict, List

class PlataformaPublicacion(ABC):
    @abstractmethod
    def publicar(self, texto: str, image_path: str = "") -> bool:
        """
        Publica el contenido generado en la plataforma correspondiente.
        
        Args:
            texto: El contenido textual a publicar.
            image_path: Ruta al archivo local de la imagen generada.
            
        Returns:
            bool: True si la publicación fue exitosa, False en caso contrario.
        """
        pass

class AdaptadorGmail(PlataformaPublicacion):
    def publicar(self, texto: str, image_path: str = "") -> bool:
        print(f"\n[AdaptadorGmail] Simulando envío de correo...")
        print(f"  Contenido: {texto}")
        if image_path:
            print(f"  [Gmail] Adjuntando imagen desde: {image_path}")
        else:
            print("  [Gmail] Sin imagen adjunta.")
        print("[AdaptadorGmail] Correo enviado exitosamente.")
        return True

class AdaptadorTikTok(PlataformaPublicacion):
    def publicar(self, texto: str, image_path: str = "") -> bool:
        print(f"\n[AdaptadorTikTok] Validando restricciones de plataforma...")
        longitud = len(texto)
        if longitud > 150:
            print(f"  [AdaptadorTikTok] ERROR: El texto supera los 150 caracteres permitidos (Longitud: {longitud}).")
            return False
            
        print(f"[AdaptadorTikTok] Simulando subida de video en formato vertical...")
        print(f"  Texto / Subtítulo: {texto}")
        if image_path:
            print(f"  [TikTok] Usando imagen como miniatura del video: {image_path}")
        else:
            print("  [TikTok] Sin miniatura de imagen.")
        print("[AdaptadorTikTok] Publicación en TikTok realizada con éxito.")
        return True

class AdaptadorInstagram(PlataformaPublicacion):
    def publicar(self, texto: str, image_path: str = "") -> bool:
        print(f"\n[AdaptadorInstagram] Validando restricciones de plataforma...")
        longitud = len(texto)
        if longitud > 220:
            print(f"  [AdaptadorInstagram] ERROR: El texto supera los 220 caracteres permitidos en modo test (Longitud: {longitud}).")
            return False
            
        print(f"[AdaptadorInstagram] Simulando publicación de post con imagen...")
        print(f"  Caption: {texto}")
        if image_path:
            print(f"  [Instagram] Subiendo publicación con archivo de imagen: {image_path}")
        else:
            print("  [Instagram] Advertencia: Se publica post sin imagen (solo texto).")
        print("[AdaptadorInstagram] Publicación en Instagram realizada con éxito.")
        return True

class AdaptadorWhatsApp(PlataformaPublicacion):
    def publicar(self, texto: str, image_path: str = "") -> bool:
        print(f"\n[AdaptadorWhatsApp] Validando restricciones de plataforma...")
        longitud = len(texto)
        if longitud > 500:
            print(f"  [AdaptadorWhatsApp] ERROR: El texto supera los 500 caracteres permitidos (Longitud: {longitud}).")
            return False
        
        # WhatsApp no permite HTML
        if "<" in texto and ">" in texto:
            print(f"  [AdaptadorWhatsApp] ERROR: WhatsApp no soporta etiquetas HTML.")
            return False
            
        print(f"[AdaptadorWhatsApp] Simulando envío de mensaje...")
        print(f"  Mensaje: {texto}")
        if image_path:
            print(f"  [WhatsApp] Enviando mensaje con imagen adjunta: {image_path}")
        else:
            print("  [WhatsApp] Enviando mensaje de solo texto.")
        print("[AdaptadorWhatsApp] Mensaje de WhatsApp enviado con éxito.")
        return True


def generar_imagen(prompt: str, plat: str) -> str:
    """
    Genera una imagen basada en un prompt.
    Intenta conectarse con APIs reales si las credenciales están configuradas.
    Caso contrario, utiliza Pillow para generar una imagen local descriptiva de fallback.
    Retorna la ruta absoluta del archivo generado.
    """
    output_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../images"))
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = int(time.time() * 1000)
    filename = f"{plat}_{timestamp}.png"
    file_path = os.path.join(output_dir, filename)
    
    # 1. Intentar con Replicate si existe una key configurada (Prioridad sobre DALL-E)
    replicate_key = os.getenv("REPLICATE_KEY") or os.getenv("REPLICATE_API_TOKEN")
    if replicate_key and replicate_key != "mock_api_key_for_testing":
        try:
            print(f"[generar_imagen] Intentando generación real con Replicate para {plat}...")
            # Asegurar propagación de clave
            os.environ["REPLICATE_API_TOKEN"] = replicate_key
            from src.image_generator import generate_image_replicate
            
            # Mapear relaciones de aspecto por plataforma
            plat_lower = plat.lower()
            if "tiktok" in plat_lower:
                aspect_ratio = "9:16"
            elif "gmail" in plat_lower:
                aspect_ratio = "16:9"
            else:
                aspect_ratio = "1:1"
                
            res = generate_image_replicate(
                prompt=prompt,
                aspect_ratio=aspect_ratio,
                plat=plat
            )
            if res.get("local_paths"):
                print(f"[generar_imagen] Imagen real de Replicate guardada exitosamente en {res['local_paths'][0]}")
                return res["local_paths"][0]
        except Exception as e:
            print(f"[generar_imagen] Falló Replicate ({e}). Continuando con otros proveedores...")

    # 2. Intentar con OpenAI DALL-E si existe una key configurada
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key != "mock_api_key_for_testing":
        try:
            from openai import OpenAI
            import requests
            print(f"[generar_imagen] Intentando generación real con DALL-E 3 para {plat}...")
            client = OpenAI(api_key=openai_key)
            response = client.images.generate(
                model="dall-e-3",
                prompt=prompt,
                size="1024x1024",
                quality="standard",
                n=1,
            )
            image_url = response.data[0].url
            img_data = requests.get(image_url).content
            with open(file_path, "wb") as f:
                f.write(img_data)
            print(f"[generar_imagen] Imagen real de DALL-E 3 guardada exitosamente en {file_path}")
            return file_path
        except Exception as e:
            print(f"[generar_imagen] Falló DALL-E 3 ({e}). Continuando con fallback local...")
            
    # 3. Fallback de diseño estético local utilizando Pillow (PIL)
    try:
        from PIL import Image, ImageDraw
        print(f"[generar_imagen] Generando imagen de fallback estético (Pillow) para {plat}...")
        
        # Paletas de color premium según la plataforma
        paletas = {
            "gmail": (220, 38, 38),       # Rojo Gmail
            "tiktok": (18, 18, 18),        # Gris oscuro TikTok
            "instagram": (225, 48, 108),   # Rosa Instagram
            "whatsapp": (37, 211, 102)     # Verde WhatsApp
        }
        bg_color = paletas.get(plat.lower(), (30, 41, 59))
        
        # Crear imagen premium
        img = Image.new("RGB", (800, 800), color=bg_color)
        draw = ImageDraw.Draw(img)
        
        # Dibujar bordes estéticos
        draw.rectangle([20, 20, 780, 780], outline=(255, 255, 255), width=8)
        draw.rectangle([40, 40, 760, 760], outline=(0, 0, 0), width=2)
        
        # Dibujar un círculo/elemento abstracto en el fondo
        draw.ellipse([250, 250, 550, 550], fill=(255, 255, 255, 30), outline=(255, 255, 255))
        
        # Título de cabecera
        draw.text((60, 60), f"SOCIAL POST FOR: {plat.upper()}", fill=(255, 255, 255))
        
        # Envolver texto del prompt para ajustarse
        wrapped_text = ""
        words = prompt.split()
        line = ""
        for word in words:
            if len(line + " " + word) > 30:
                wrapped_text += line + "\n"
                line = word
            else:
                line = line + " " + word if line else word
        wrapped_text += line
        
        # Texto del prompt en el centro
        draw.text((80, 300), f"Prompt:\n{wrapped_text}", fill=(255, 255, 255))
        
        # Pie de página
        draw.text((60, 700), "PROCESADO CON AGENTES INTELIGENTES (IA)", fill=(255, 255, 255))
        
        img.save(file_path)
        print(f"[generar_imagen] Imagen de fallback local guardada en: {file_path}")
        return file_path
    except Exception as e:
        print(f"[generar_imagen] Error al generar con Pillow ({e}). Escribiendo archivo mock básico...")
        try:
            with open(file_path, "w") as f:
                f.write(f"MOCK IMAGE DATA FOR {plat}\nPrompt: {prompt}")
            return file_path
        except Exception as write_err:
            print(f"[generar_imagen] Error de escritura crítico: {write_err}")
            raise write_err


def publicar_multiplataforma(
    outputs: Dict[str, dict], 
    platforms: List[str], 
    image_paths: Dict[str, str] = None
) -> Dict[str, bool]:
    """
    Ejecuta las publicaciones en paralelo utilizando un ThreadPoolExecutor.
    """
    adaptadores = {
        "gmail": AdaptadorGmail(),
        "tiktok": AdaptadorTikTok(),
        "instagram": AdaptadorInstagram(),
        "whatsapp": AdaptadorWhatsApp()
    }
    
    resultados = {}
    image_paths = image_paths or {}
    
    def ejecutar_una(plat: str):
        content = outputs.get(plat)
        if not content:
            return plat, False
        
        adaptador = adaptadores.get(plat)
        if not adaptador:
            print(f"  ⚠️ No hay adaptador registrado para la plataforma: {plat}")
            return plat, False
            
        img_path = image_paths.get(plat, "")
        exito = adaptador.publicar(
            texto=content.get("text", ""),
            image_path=img_path
        )
        return plat, exito

    print(f"\n>>> Iniciando publicación paralela en plataformas: {platforms}")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = {executor.submit(ejecutar_una, plat): plat for plat in platforms}
        for future in concurrent.futures.as_completed(futures):
            plat = futures[future]
            try:
                _, exito = future.result()
                resultados[plat] = exito
            except Exception as e:
                print(f"  ⚠️ Error publicando en {plat}: {e}")
                resultados[plat] = False
                
    return resultados
