from abc import ABC, abstractmethod

class PlataformaPublicacion(ABC):
    @abstractmethod
    def publicar(self, texto: str, prompt_imagen: str) -> bool:
        """
        Publica el contenido generado en la plataforma correspondiente.
        
        Args:
            texto: El contenido textual a publicar.
            prompt_imagen: El prompt de la imagen asociada.
            
        Returns:
            bool: True si la publicación fue exitosa, False en caso contrario.
        """
        pass

class AdaptadorGmail(PlataformaPublicacion):
    def publicar(self, texto: str, prompt_imagen: str) -> bool:
        print(f"\n[AdaptadorGmail] Simulando envío de correo...")
        print(f"  Contenido: {texto}")
        print(f"  Concepto de Imagen: {prompt_imagen}")
        print("[AdaptadorGmail] Correo enviado exitosamente.")
        return True

class AdaptadorTikTok(PlataformaPublicacion):
    def publicar(self, texto: str, prompt_imagen: str) -> bool:
        print(f"\n[AdaptadorTikTok] Validando restricciones de plataforma...")
        longitud = len(texto)
        if longitud > 150:
            print(f"  [AdaptadorTikTok] ERROR: El texto supera los 150 caracteres permitidos (Longitud: {longitud}).")
            return False
            
        print(f"[AdaptadorTikTok] Simulando subida de video en formato vertical...")
        print(f"  Texto / Subtítulo: {texto}")
        print(f"  Concepto de Miniatura: {prompt_imagen}")
        print("[AdaptadorTikTok] Publicación en TikTok realizada con éxito.")
        return True
