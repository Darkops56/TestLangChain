"""Shared chart rendering utilities.

Extracted from nurturing/workflow.py to enable reuse.
Uses Pillow to render bar charts as PNG images.
"""

from __future__ import annotations

import logging
import uuid
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

NOVIT_DEEP_BLUE = "#0A0089"
NOVIT_CYAN = "#3DB0E4"
NOVIT_MAGENTA = "#BA08A8"
NOVIT_TEXT = "#1F2430"

CHART_WIDTH = 1400
CHART_HEIGHT = 820


def _load_font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    """Load a font, falling back to default if not found."""
    candidates = [
        "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        "arialbd.ttf" if bold else "arial.ttf",
        "OpenSans-Bold.ttf" if bold else "OpenSans-Regular.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def render_chart_png(
    chart_items: list,
    *,
    chart_title: str = "",
    chart_subtitle: str = "",
) -> bytes | None:
    """Render a bar chart as PNG bytes.

    Parameters
    ----------
    chart_items : list
        List of objects with label, value, unit, source_title fields.
    chart_title : str
        Title for the chart.
    chart_subtitle : str
        Subtitle for the chart.

    Returns
    -------
    bytes | None
        PNG image bytes, or None if no items.
    """
    items = chart_items[:4]
    if not items:
        return None

    image = Image.new("RGB", (CHART_WIDTH, CHART_HEIGHT), color="#F6F8FC")
    draw = ImageDraw.Draw(image)

    title_font = _load_font(54, bold=True)
    subtitle_font = _load_font(28)
    label_font = _load_font(26, bold=True)
    value_font = _load_font(34, bold=True)
    footnote_font = _load_font(22)

    margin_x = 110
    chart_top = 250
    chart_bottom = 640
    bar_height = 78
    bar_gap = 34

    # Get max value for scaling
    max_value = 0
    for item in items:
        value = getattr(item, "value", None) or (item.get("value") if isinstance(item, dict) else 0)
        if value > max_value:
            max_value = value
    max_value = max_value or 1

    palette = [NOVIT_DEEP_BLUE, NOVIT_CYAN, NOVIT_MAGENTA, "#5468FF"]

    # Draw title
    draw.text((margin_x, 70), chart_title or "Señal cuantitativa destacada", fill=NOVIT_DEEP_BLUE, font=title_font)
    if chart_subtitle:
        draw.text((margin_x, 140), chart_subtitle, fill=NOVIT_TEXT, font=subtitle_font)

    # Draw bars
    for index, item in enumerate(items):
        top = chart_top + index * (bar_height + bar_gap)

        label = getattr(item, "label", "") or (item.get("label", "") if isinstance(item, dict) else "")
        label = label.strip()[:28]
        draw.text((margin_x, top - 36), label, fill=NOVIT_TEXT, font=label_font)

        value = getattr(item, "value", 0) or (item.get("value", 0) if isinstance(item, dict) else 0)
        bar_left = margin_x
        bar_right = margin_x + int(((CHART_WIDTH - margin_x * 2) * value) / max_value)
        draw.rounded_rectangle((bar_left, top, bar_right, top + bar_height), radius=22, fill=palette[index % len(palette)])

        unit = getattr(item, "unit", "") or (item.get("unit", "") if isinstance(item, dict) else "")
        value_text = f"{value:g} {unit}".strip()
        draw.text((bar_right + 18, top + 16), value_text, fill=NOVIT_TEXT, font=value_font)

        source_title = getattr(item, "source_title", "") or (item.get("source_title", "") if isinstance(item, dict) else "")
        source_text = source_title.strip()[:60]
        draw.text((margin_x, top + bar_height + 6), source_text, fill="#586174", font=footnote_font)

    # Footer
    footer = "AI Radar by Novit | Fuentes verificadas y seleccionadas para líderes de negocio"
    draw.text((margin_x, CHART_HEIGHT - 70), footer, fill="#586174", font=footnote_font)

    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def generate_chart_filename() -> str:
    """Generate a unique filename for a chart image."""
    return f"chart-{uuid.uuid4().hex[:8]}.png"
