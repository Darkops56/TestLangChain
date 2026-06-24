"""Structured editorial preference memory for the Community Manager agent.

This layer captures what Novit should talk about, from which angle,
and with what editorial priorities. It is intentionally separate from
visual taste so strategy, copy and evaluation can reason about content
without confusing it with art direction.
"""

from __future__ import annotations

CONTENT_PREFERENCE_PROFILE: dict[str, dict[str, tuple[str, ...]]] = {
    "editorial_core": {
        "always": (
            "Hablar de problemas reales de empresas, decisiones, tradeoffs, implementacion y consecuencias.",
            "Bajar IA y software a impacto operativo, productividad, costo, calidad de ejecucion y ventaja competitiva.",
            "Mostrar a Novit como un aliado serio que entiende tanto negocio como implementacion.",
            "Priorizar piezas explicativas que ensenen a pensar, no solo a repetir slogans.",
        ),
        "prefer": (
            "Insight accionable, criterio practico y traduccion de complejidad tecnica a lenguaje empresarial.",
            "Explicar como tomar mejores decisiones, no solo que herramienta usar.",
        ),
        "avoid": (
            "Contenido vacio, demasiado marketinero, abstracto o puramente aspiracional.",
        ),
    },
    "audience_modes": {
        "primary": (
            "Founders, duenos de pyme, CTOs, gerentes operativos, lideres comerciales y responsables de innovacion.",
        ),
        "secondary": (
            "Perfiles tecnicos que ayudan a validar si Novit realmente sabe de arquitectura, implementacion y criterio tecnico.",
        ),
        "sometimes_use": (
            "Contenido mas tecnico para developers o arquitectos cuando sirva para validar solidez tecnica de Novit.",
        ),
        "avoid": (
            "Piezas tan low-level que pierdan al lector de negocio o no expliquen por que eso importa.",
        ),
    },
    "topic_priorities": {
        "high_priority": (
            "Agentes de IA.",
            "Como implementar agentes de IA en empresas sin improvisar.",
            "Tradeoffs comunes en agentes de IA.",
            "Como tomar decisiones de arquitectura en sistemas con agentes.",
            "Arquitecturas clasicas de agentes y multiagentes, y cuando conviene cada una.",
            "IA aplicada a procesos concretos.",
            "Automatizacion util.",
            "Eficiencia operativa y productividad.",
            "Estrategia corporativa de IA, gobierno y estandarizacion.",
            "Noticias relevantes del mundo IA o tecnologia usadas como disparador editorial.",
        ),
        "medium_priority": (
            "Integracion entre sistemas.",
            "Adopcion interna y madurez organizacional.",
            "Datos, reporting, trazabilidad y costo total de operacion.",
            "El miedo de quedarse atras por no arrancar IA a tiempo.",
            "El miedo de implementar mal, sin estructura global, con herramientas atadas con alambre y costos inflados.",
        ),
        "occasional": (
            "Behind the scenes.",
            "Storytelling corto si ayuda a entender un punto.",
            "Opinion de industria con fundamento.",
        ),
    },
    "current_event_triggers": {
        "high_priority": (
            "Noticias relevantes de IA que cambian el contexto competitivo.",
            "Noticias tecnologicas que habilitan explicar riesgos, oportunidades o decisiones empresariales.",
            "Lanzamientos o movimientos de grandes jugadores que sirvan para explicar estrategia, arquitectura o tradeoffs.",
        ),
        "rule": (
            "La noticia no es el fin; usarla como excusa para hablar de criterio, implementacion, riesgo, oportunidad o decision.",
            "Evitar reaccionar a cualquier noticia si no habilita un insight util para una empresa real.",
        ),
    },
    "strategic_fears": {
        "prefer": (
            "El miedo de quedarse atras frente a empresas que ya estan mejorando su productividad con IA.",
            "El miedo de implementar tarde y perder ventaja competitiva.",
            "El miedo de hacerlo mal, sin estrategia corporativa de IA.",
            "El miedo de terminar con herramientas desconectadas, arquitecturas distintas y costos innecesariamente altos.",
        ),
        "rule": (
            "Usar estos miedos con sintomas, consecuencias y ejemplos reales; no convertir toda pieza en fear marketing.",
        ),
    },
    "content_angles": {
        "always": (
            "Problema, consecuencia y enfoque recomendado.",
            "Tradeoff real entre dos o mas caminos posibles.",
            "Error frecuente que parece razonable pero termina costando caro.",
        ),
        "prefer": (
            "Explicacion de arquitectura o implementacion traducida a negocio.",
            "Noticia actual transformada en lectura estrategica.",
            "Comparativa entre improvisar, hacer bien y escalar.",
        ),
        "sometimes_use": (
            "Opinion fuerte o mini manifiesto si esta bien fundamentado.",
        ),
        "avoid": (
            "Definicion de diccionario, lista obvia de beneficios o contenido educativo sin insight.",
        ),
    },
    "technical_authority_layer": {
        "sometimes_use": (
            "Posts mas tecnicos para mostrar solidez real en arquitectura, implementacion, orquestacion, observabilidad, costos y limites.",
            "Explicaciones de patrones, decisiones de implementacion y criterios de arquitectura para validar expertise.",
        ),
        "rule": (
            "No tratar el contenido tecnico para developers como un hard avoid; usarlo poco, pero a veces suma para validacion tecnica.",
            "Incluso cuando la pieza sea mas tecnica, dejar claro por que eso importa para una empresa.",
        ),
    },
    "tone_and_voice": {
        "always": (
            "Autoridad tranquila, criterio ejecutivo y lenguaje claro.",
            "Sonar humano, sobrio, seguro y tecnicamente serio.",
        ),
        "prefer": (
            "Tono explicativo y seguro.",
            "Frases cortas y conceptos complejos bien traducidos.",
            "Eliminar frases puente que no agregan informacion nueva en lugar de inflar el texto con bajadas de manual.",
        ),
        "sometimes_use": (
            "Tono desafiante si el insight lo justifica.",
        ),
        "avoid": (
            "Hype, grandilocuencia, tono de guru, miedo exagerado o vendehumo.",
            "Frases neutras o acartonadas de manual como 'Aqui te explicamos como lograrlo', 'En este post te contamos' o 'A continuacion te mostramos'.",
            "Usar 'aqui' como muletilla neutra cuando en rioplatense conviene 'aca' o directamente reescribir la frase.",
        ),
    },
    "cta_preferences": {
        "always": (
            "Invitar a pensar, responder o conversar.",
        ),
        "prefer": (
            "Abrir discusion sobre decisiones, prioridades o experiencias reales.",
        ),
        "sometimes_use": (
            "CTA comercial suave si el contenido ya entrego valor.",
        ),
        "avoid": (
            "Venta directa brusca o CTA generica de manual.",
        ),
    },
    "anti_patterns": {
        "avoid": (
            "Parecer una cuenta de noticias por si sola.",
            "Parecer una cuenta solo tecnica sin lectura empresarial.",
            "Parecer una cuenta comercial sin sustancia tecnica.",
            "Hablar de IA sin hablar de implementacion, criterio o consecuencias.",
            "Piezas que podria firmar cualquier agencia sin mostrar una mirada propia.",
        ),
    },
}


SECTION_LABELS = {
    "editorial_core": "editorial_core (que debe sentirse en casi cualquier publicacion)",
    "audience_modes": "audience_modes (para quien se escribe de verdad)",
    "topic_priorities": "topic_priorities (temas a insistir y temas secundarios)",
    "current_event_triggers": "current_event_triggers (actualidad usada como disparador)",
    "strategic_fears": "strategic_fears (miedos empresariales que conviene activar con criterio)",
    "content_angles": "content_angles (angulos desde los que conviene atacar un tema)",
    "technical_authority_layer": "technical_authority_layer (validacion tecnica de baja frecuencia)",
    "tone_and_voice": "tone_and_voice (como debe sonar la pieza)",
    "cta_preferences": "cta_preferences (como conviene cerrar)",
    "anti_patterns": "anti_patterns (derivas editoriales a evitar)",
}

GROUP_LABELS = {
    "always": "always (criterios que deberian aparecer casi siempre)",
    "prefer": "prefer (decisiones a priorizar cuando suman)",
    "sometimes_use": "sometimes_use (recursos de baja frecuencia pero utiles)",
    "avoid": "avoid (cosas a evitar)",
    "primary": "primary (audiencia principal)",
    "secondary": "secondary (audiencia secundaria)",
    "high_priority": "high_priority (prioridad alta)",
    "medium_priority": "medium_priority (prioridad media)",
    "occasional": "occasional (uso ocasional)",
    "rule": "rules (condiciones de uso)",
}


def render_content_preference_prompt() -> str:
    """Render the editorial preference profile into prompt-ready guidance."""

    lines = [
        "Preferencias editoriales persistentes del decisor humano:",
        "Esta capa define que conviene decir, desde que angulo, con que prioridad y con que tono.",
        "No confundir actualidad con oportunismo, ni validacion tecnica con hablar solo para developers.",
    ]

    for section_key, groups in CONTENT_PREFERENCE_PROFILE.items():
        lines.append(f"{SECTION_LABELS[section_key]}:")
        for group_key, items in groups.items():
            lines.append(f"{GROUP_LABELS[group_key]}:")
            lines.extend(f"- {item}" for item in items)

    return "\n".join(lines)


CONTENT_PREFERENCE_PROMPT = render_content_preference_prompt()