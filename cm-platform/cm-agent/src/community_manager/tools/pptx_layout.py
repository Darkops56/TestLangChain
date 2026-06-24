"""Slide layout metadata extracted from the PPTX template.

Exposes measurements (in pixels @ 96 DPI) for each slide's text
content box, so the writer can make informed decisions about how
much text to produce per slide.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlideLayout:
    """Measurements for a single slide's content area.

    All values are pre-computed from the PPTX template's placeholder
    positions (see ``newsletter_pptx_template.py``).
    """

    name: str
    width_px: int
    height_px: int
    content_box: tuple  # (x, y, w, h) in pixels
    body_font_pt: int
    title_font_pt: int
    min_chars: int
    max_chars: int
    line_height_px: float
    chars_per_line: int
    max_lines: int

    def fill_ratio(self, text: str) -> float:
        """Return how full the slide is (0.0 = empty, 1.0+ = overflowing)."""
        if self.max_chars <= 0:
            return 0.0
        return len(text) / self.max_chars


# Template constants (matches newsletter_pptx_template.py SLIDE_W/H)
SLIDE_W = 1280
SLIDE_H = 720

# Computed from real placeholder positions in NewsletterTemplateBuilder
# at 96 DPI (1 inch = 96 px, 1 pt ≈ 1.33 px at 96 DPI for line height).
_LAYOUTS: dict[str, SlideLayout] = {
    "slide_1": SlideLayout(
        name="slide_1",
        width_px=SLIDE_W,
        height_px=SLIDE_H,
        # Box tightened to match the bottom of the chart_pricing
        # placeholder (y=5.05 + h=1.75 = 6.80). Previous box (3.8" tall)
        # overflowed and visually conflicted with the chart.
        content_box=(48, 307, 720, 346),  # Inches(0.5, 3.20, 7.5, 3.6)
        body_font_pt=12,  # user reduced from 13 → 12, "quedó joya"
        title_font_pt=64,
        # Max reduced from 1500 → 900: previous text (1520 chars) overflowed
        # the box and looked crammed. 900 chars = 3 short paragraphs at
        # 12pt with 1.5 line spacing, fits cleanly with breathing room.
        min_chars=600,
        max_chars=900,
        line_height_px=18.5,  # 12pt × 1.5 line spacing
        chars_per_line=85,
        max_lines=18,
    ),
    "slide_2": SlideLayout(
        name="slide_2",
        width_px=SLIDE_W,
        height_px=SLIDE_H,
        content_box=(576, 149, 653, 480),  # Inches(6.0, 1.55, 6.8, 5.0)
        body_font_pt=12,
        title_font_pt=28,
        min_chars=800,
        max_chars=1900,
        line_height_px=18.5,  # 12pt × 1.5 line spacing
        chars_per_line=90,
        max_lines=25,
    ),
    "slide_3": SlideLayout(
        name="slide_3",
        width_px=SLIDE_W,
        height_px=SLIDE_H,
        content_box=(48, 149, 653, 480),  # Inches(0.5, 1.55, 6.8, 5.0)
        body_font_pt=12,
        title_font_pt=28,
        min_chars=800,
        max_chars=1900,
        line_height_px=18.5,
        chars_per_line=90,
        max_lines=25,
    ),
    "slide_4": SlideLayout(
        name="slide_4",
        width_px=SLIDE_W,
        height_px=SLIDE_H,
        content_box=(48, 110, 624, 250),  # Inches(0.5, 1.15, 6.5, 2.6)
        body_font_pt=12,
        title_font_pt=20,
        min_chars=450,
        max_chars=900,
        line_height_px=18.5,
        chars_per_line=85,
        max_lines=13,
    ),
}


def get_slide_layouts() -> dict[str, SlideLayout]:
    """Return a copy of the slide layout dict.

    Safe to mutate (returns a new dict every call).
    """
    return dict(_LAYOUTS)


def get_layout(slide_name: str) -> SlideLayout | None:
    """Return the layout for a single slide, or None if unknown."""
    return _LAYOUTS.get(slide_name)
