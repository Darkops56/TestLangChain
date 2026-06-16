from src.tools import AdaptadorGmail, AdaptadorTikTok

def test_adaptador_gmail():
    gmail = AdaptadorGmail()
    res = gmail.publicar("Contenido de prueba para Gmail", "concepto de imagen")
    assert res is True

def test_adaptador_tiktok_bajo_limite():
    tiktok = AdaptadorTikTok()
    res = tiktok.publicar("Este texto tiene menos de 150 caracteres.", "concepto de imagen")
    assert res is True

def test_adaptador_tiktok_sobre_limite():
    tiktok = AdaptadorTikTok()
    # Crear un texto de 151 caracteres
    texto_largo = "a" * 151
    res = tiktok.publicar(texto_largo, "concepto de imagen")
    assert res is False
