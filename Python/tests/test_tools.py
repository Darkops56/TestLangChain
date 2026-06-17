from src.tools import (
    AdaptadorGmail, 
    AdaptadorTikTok, 
    AdaptadorInstagram, 
    AdaptadorWhatsApp, 
    publicar_multiplataforma
)

def test_gmail_adapter():
    gmail = AdaptadorGmail()
    res = gmail.publicar("Test mail content", "image concept")
    assert res is True

def test_tiktok_adapter_under_limit():
    tiktok = AdaptadorTikTok()
    res = tiktok.publicar("This is under 150 characters.", "image concept")
    assert res is True

def test_tiktok_adapter_over_limit():
    tiktok = AdaptadorTikTok()
    long_text = "a" * 151
    res = tiktok.publicar(long_text, "image concept")
    assert res is False

def test_instagram_adapter_under_limit():
    instagram = AdaptadorInstagram()
    res = instagram.publicar("Under 220 chars.", "image concept")
    assert res is True

def test_instagram_adapter_over_limit():
    instagram = AdaptadorInstagram()
    long_text = "a" * 221
    res = instagram.publicar(long_text, "image concept")
    assert res is False

def test_whatsapp_adapter_valid():
    whatsapp = AdaptadorWhatsApp()
    res = whatsapp.publicar("Simple message without html", "image concept")
    assert res is True

def test_whatsapp_adapter_invalid_html():
    whatsapp = AdaptadorWhatsApp()
    res = whatsapp.publicar("Message with <b>bold</b> tags", "image concept")
    assert res is False

def test_whatsapp_adapter_over_limit():
    whatsapp = AdaptadorWhatsApp()
    long_text = "a" * 501
    res = whatsapp.publicar(long_text, "image concept")
    assert res is False

def test_publish_multiplatform_parallel():
    outputs = {
        "gmail": {"text": "Gmail post content", "image_prompt": "concept 1"},
        "tiktok": {"text": "Short copy #tiktok", "image_prompt": "concept 2"},
        "instagram": {"text": "Insta copy #insta", "image_prompt": "concept 3"},
        "whatsapp": {"text": "Simple WA msg", "image_prompt": "concept 4"}
    }
    platforms = ["gmail", "tiktok", "instagram", "whatsapp"]
    
    results = publicar_multiplataforma(outputs, platforms)
    assert len(results) == 4
    assert results["gmail"] is True
    assert results["tiktok"] is True
    assert results["instagram"] is True
    assert results["whatsapp"] is True
