"""Structured visual preference memory for the Community Manager agent.

This file captures persistent aesthetic preferences from the human decision-maker.
It is intentionally separate from fixed brandbook rules so the agent can distinguish
between hard brand constraints and preferred creative resources.
"""

from __future__ import annotations

VISUAL_PREFERENCE_PROFILE: dict[str, tuple[str, ...]] = {
    "always": (
        "Toda pieza debe sentirse sobria, premium, clara y orientada a empresas medianas con criterio de negocio.",
        "La percepción buscada es la de un aliado confiable: cercano en lo visual, experto, intelectual y profesional.",
        "Respetar brandbook: familia tipográfica Effra, logo intacto, tonos fríos y paleta Novit usada con control.",
        "Priorizar lectura fácil, frases cortas, aire visual y una idea fuerte por bloque o escena.",
        "En video, la prioridad número uno es que se vea real: personas naturales, situaciones plausibles y tono no actuado.",
    ),
    "prefer": (
        "Bases neutras o degradés sobrios con 1 o 2 colores de acento; preferir cyan como acento principal y dejar magenta para usos más esporádicos.",
        "Carruseles text-first con portada gancho: frase incompleta, conclusión a medias o afirmación fuerte que se desarrolla después.",
        "Inteligencia visual tranquila: diseño que sostiene una idea potente sin gritar ni sobrecargar.",
        "Para video, ritmo medio o medio-rápido con cortes cuando cambia la idea, no por ansiedad ni sobreedición.",
        "Subtítulos limpios con una palabra resaltada para retención, sin volverse gritones.",
        "Charla informal inteligente o podcast serio como formato dominante para transmitir autoridad.",
        "En videos técnicos, preferir formato tutorial o screencast: pantalla principal con código, documentación o grafo de agentes, y no escenas inventadas de oficina.",
        "Si un video usa rostro, que sea pequeño y superpuesto en la esquina inferior izquierda como picture-in-picture sobre la demo principal.",
    ),
    "sometimes_use": (
        "B-roll elegante de oficina, ciudad, manos, detalles de trabajo o pantallas reales cuando ayude a sostener atención.",
        "Tomas aéreas o vistas de ciudad como recurso secundario para transmitir estatus y visión global, idealmente Buenos Aires o Madrid.",
        "Visuales de IA casi invisibles y realistas para demostrar capacidad sin que la pieza parezca una demo artificial.",
        "Cinematografía cotidiana: una situación normal filmada con intención, misterio o tensión suave para abrir interés.",
        "Esquemas simples, gráficos mínimos o sketches sobrios para acompañar posts educativos sin volverlos complejos.",
        "Glow/neón muy sutil y ocasional, solo como detalle compatible con la marca, nunca como lenguaje dominante.",
        "Bloques visuales simples tipo servicio o tutorial cuando haya que explicar una oferta concreta, siempre anclados en un caso real.",
        "Tutoriales visuales de LangChain, LangGraph, OpenClaw o flujos multiagente con nodos, pasos y código Python visibles cuando el tema lo justifique.",
    ),
    "avoid": (
        "Estética cripto bro, startup vendehumo o publicidad gritona.",
        "Exceso de color, contrastes exagerados o piezas colorinches que parezcan compensar falta de contenido.",
        "Tipografías raras, layouts cargados, motion genérico o recursos visuales que se sientan de agencia antes que de criterio.",
        "Stock corporativo genérico, personas actuadas o escenas que parezcan una publicidad demasiado armada.",
        "Interfaces sci-fi, overlays complejos, UI oscura abstracta o futurismo obvio sin utilidad narrativa.",
        "Usar todos los recursos a la vez: entrevista, aérea, IA, subtítulos fuertes y B-roll en la misma pieza si no suman al mensaje.",
        "Rostros grandes con fondos sintéticos intentando parecer oficinas reales o sets de estudio realistas.",
    ),
}


def render_visual_preference_prompt() -> str:
    """Render the structured preference profile into prompt-ready guidance."""

    section_labels = {
        "always": "always (prioridades que deberían aparecer casi siempre)",
        "prefer": "prefer (recursos o decisiones que conviene priorizar si suman)",
        "sometimes_use": "sometimes_use (recursos opcionales o situacionales, no obligatorios)",
        "avoid": "avoid (anti-patrones y decisiones a evitar)",
    }

    lines = [
        "Preferencias visuales persistentes del decisor humano:",
        "No son templates obligatorios; son una biblioteca de recursos y criterios de gusto para elegir según la pieza.",
    ]

    for key in ("always", "prefer", "sometimes_use", "avoid"):
        lines.append(f"{section_labels[key]}:")
        lines.extend(f"- {item}" for item in VISUAL_PREFERENCE_PROFILE[key])

    return "\n".join(lines)


VISUAL_PREFERENCE_PROMPT = render_visual_preference_prompt()