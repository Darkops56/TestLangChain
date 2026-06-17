from abc import ABC, abstractmethod
import concurrent.futures
from typing import Dict, List

class PlataformaPublicacion(ABC):
    @abstractmethod
    def publicar(self, texto: str, prompt_imagen: str = "") -> bool:
        """
        Publica el contenido generado en la plataforma correspondiente.
        
        Args:
            texto: El contenido textual a publicar.
            
        Returns:
            bool: True si la publicación fue exitosa, False en caso contrario.
        """
        pass

class AdaptadorGmail(PlataformaPublicacion):
    def publicar(self, texto: str, prompt_imagen: str = "") -> bool:
        print(f"\n[AdaptadorGmail] Simulando envío de correo...")
        print(f"  Contenido: {texto}")
        # print(f"  Concepto de Imagen: {prompt_imagen}")  # Comentado por requerimiento de texto plano únicamente
        print("[AdaptadorGmail] Correo enviado exitosamente.")
        return True

class AdaptadorTikTok(PlataformaPublicacion):
    def publicar(self, texto: str, prompt_imagen: str = "") -> bool:
        print(f"\n[AdaptadorTikTok] Validando restricciones de plataforma...")
        longitud = len(texto)
        if longitud > 150:
            print(f"  [AdaptadorTikTok] ERROR: El texto supera los 150 caracteres permitidos (Longitud: {longitud}).")
            return False
            
        print(f"[AdaptadorTikTok] Simulando subida de video en formato vertical...")
        print(f"  Texto / Subtítulo: {texto}")
        # print(f"  Concepto de Miniatura: {prompt_imagen}")  # Comentado por requerimiento de texto plano únicamente
        print("[AdaptadorTikTok] Publicación en TikTok realizada con éxito.")
        return True

class AdaptadorInstagram(PlataformaPublicacion):
    def publicar(self, texto: str, prompt_imagen: str = "") -> bool:
        print(f"\n[AdaptadorInstagram] Validando restricciones de plataforma...")
        longitud = len(texto)
        if longitud > 220:
            print(f"  [AdaptadorInstagram] ERROR: El texto supera los 220 caracteres permitidos en modo test (Longitud: {longitud}).")
            return False
            
        print(f"[AdaptadorInstagram] Simulando publicación de post con imagen...")
        print(f"  Caption: {texto}")
        # print(f"  Concepto de Imagen: {prompt_imagen}")  # Comentado por requerimiento de texto plano únicamente
        print("[AdaptadorInstagram] Publicación en Instagram realizada con éxito.")
        return True

class AdaptadorWhatsApp(PlataformaPublicacion):
    def publicar(self, texto: str, prompt_imagen: str = "") -> bool:
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
        # print(f"  Concepto de Imagen: {prompt_imagen}")  # Comentado por requerimiento de texto plano únicamente
        print("[AdaptadorWhatsApp] Mensaje de WhatsApp enviado con éxito.")
        return True

def publicar_multiplataforma(outputs: Dict[str, dict], platforms: List[str]) -> Dict[str, bool]:
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
    
    def ejecutar_una(plat: str):
        content = outputs.get(plat)
        if not content:
            return plat, False
        
        adaptador = adaptadores.get(plat)
        if not adaptador:
            print(f"  ⚠️ No hay adaptador registrado para la plataforma: {plat}")
            return plat, False
            
        exito = adaptador.publicar(
            texto=content.get("text", "")
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
