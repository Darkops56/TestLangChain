# Prompts para modificar el template de Google Slides

Usá estos 3 prompts en Gemini (uno por slide) para modificar el template existente.

---

## PROMPT 1 — Slide 2: Resumen del Mes

```
Modify slide 2 of the "AI Radar by Novit" presentation. Keep the same design system (OpenSans font, same colors, same spacing).

SLIDE 2 — RESUMEN DEL MES:
- White background (#FFFFFF)
- Top-left: section label "LO QUE CAMBIÓ ESTE MES" in #0A0089, 11pt, OpenSans Bold, letter-spacing 2px
- Below: horizontal line in #0A0089 (full width, 2px)
- Main area: executive summary text
  - "{{executive_summary}}" in #1F2430, 14pt, OpenSans Regular, line-height 1.6
  - Max 3-4 sentences, concise and actionable
- Below: 3 key bullet points (the most important changes this month)
  - Each bullet: small colored dot (#0A0089) + text in 12pt OpenSans Regular
  - Bullets should be brief (1 line each)
- Bottom-right: "NOVIT" in #0A0089, 9pt, OpenSans Bold

DESIGN NOTES:
- Clean, minimal, easy to scan
- Executive summary is the hero content
- Bullets provide quick takeaways
- No metrics cards (removed - too data-heavy for monthly content)

Modify this slide now. Reply only with the slide, no explanations.
```

---

## PROMPT 2 — Slide 3: Secciones Geográficas

```
Modify slide 3 of the "AI Radar by Novit" presentation. Keep the same design system (OpenSans font, same colors, same spacing).

SLIDE 3 — SECCIONES GEOGRÁFICAS (3 columns):
- White background (#FFFFFF)
- Top-left: section label "NOVEDADES POR REGIÓN" in #0A0089, 11pt, OpenSans Bold, letter-spacing 2px
- Below: horizontal line in #0A0089 (full width, 2px)
- 3 equal columns below, each with a card:

  COLUMN 1 — ARGENTINA:
  - Top: pill/badge shape (rounded rectangle 16px) in #BA08A8, white text "ARGENTINA" in 9pt OpenSans Bold
  - Headline: "{{argentina_headline}}" in 14pt #1F2430 OpenSans Bold
  - Content: "{{argentina_content}}" in 11pt #1F2430 OpenSans Regular, 3-4 lines max
  - Action label: "Qué hacer:" in 10pt #0A0089 OpenSans Bold
  - Action text: "{{argentina_action}}" in 10pt #1F2430 OpenSans Regular
  - Source: "{{argentina_source}}" in 9pt #3DB0E4, underline

  COLUMN 2 — ESPAÑA:
  - Top: pill/badge in #3DB0E4, white text "ESPAÑA" in 9pt OpenSans Bold
  - Same structure with {{espana_*}} placeholders
  - Note: Can include EU/European context

  COLUMN 3 — INTERNACIONAL:
  - Top: pill/badge in #0A0089, white text "INTERNACIONAL" in 9pt OpenSans Bold
  - Same structure with {{internacional_*}} placeholders
  - Note: USA, China, Japan, global trends

- Bottom-right: "NOVIT" in #0A0089, 9pt, OpenSans Bold

DESIGN NOTES:
- Each column is a self-contained regional update
- "Qué hacer" section makes it actionable
- Sources are visible for credibility
- Cards should feel like mini-briefings

Modify this slide now. Reply only with the slide, no explanations.
```

---

## PROMPT 3 — Slide 4: Secciones Variables + Recomendación

```
Modify slide 4 of the "AI Radar by Novit" presentation. Keep the same design system (OpenSans font, same colors, same spacing).

SLIDE 4 — SECCIONES VARIABLES + RECOMENDACIÓN:
- White background (#FFFFFF)

TOP SECTION — Variable Topics (top 55% of slide):
- Top-left: section label "CAMBIOS RELEVANTES" in #0A0089, 11pt, OpenSans Bold, letter-spacing 2px
- Below: horizontal line in #0A0089 (full width, 2px)
- 2x2 grid of small cards (or 1x3 if only 3 topics):
  - Each card: rounded rectangle #F6F8FC, 8px radius, subtle shadow
  - Inside each card:
    - Topic title: "{{variable_title}}" in 12pt #0A0089 OpenSans Bold
    - Headline: "{{variable_headline}}" in 11pt #1F2430 OpenSans Bold
    - Content: "{{variable_content}}" in 10pt #1F2430 OpenSans Regular (2-3 lines max)
    - Source: "{{variable_source}}" in 9pt #3DB0E4

BOTTOM SECTION — Recommendation (bottom 35% of slide):
- Background: #0A0089 (full width block, rounded top corners 12px)
- Centered text: "RECOMENDACIÓN DEL MES" in #3DB0E4, 10pt, OpenSans Bold, letter-spacing 2px
- Main recommendation: "{{recommendation}}" in white, 14pt, OpenSans Regular
- Below: small text "AI Radar by Novit | Novit Software" in white, 9pt, 50% opacity

DESIGN NOTES:
- Variable sections are optional (0-4 topics)
- Grid should adapt: 2x2 for 4 topics, 1x3 for 3, 1x2 for 2
- If fewer topics, cards should be larger to fill space
- Recommendation is the call-to-action takeaway
- Bottom section feels like a "verdict" or "executive decision"

Modify this slide now. Reply only with the slide, no explanations.
```

---

## Notas importantes para Gemini

1. **Placeholders**: Los placeholders usan doble llave `{{nombre}}` para ser reemplazados después
2. **Colores**: Siempre usar la paleta Novit (#0A0089, #3DB0E4, #BA08A8, #1F2430)
3. **Fuente**: Siempre OpenSans
4. **Estilo**: Premium consulting, limpio, ejecutivo
5. **Adaptabilidad**: El slide 4 debe adaptarse a la cantidad de secciones variables (0-4)
