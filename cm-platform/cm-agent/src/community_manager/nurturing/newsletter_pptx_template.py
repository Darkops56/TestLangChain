"""Newsletter PPTX Template — Professional master template with Novit branding.

Generates a reusable .pptx template with:
  • Complex gradient backgrounds (radial, angular) via PIL
  • Radar sweep watermark patterns
  • Glassmorphism panels
  • Correct logo usage (white on dark, blue on light)
  • 4 optimized slides: Cover+Summary, Insights, Chart, Info+CTA

The template is cloned and populated per-newsletter.
"""

from __future__ import annotations

import io
import logging
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

logger = logging.getLogger(__name__)

# ── Novit colour palette ───────────────────────────────────────
DEEP_NAVY = (13, 11, 74)          # #0d0b4a
MID_NAVY = (26, 24, 117)         # #1a1875
CYAN = (61, 176, 228)            # #3DB0E4
MAGENTA = (186, 8, 168)          # #BA08A8
WHITE = (255, 255, 255)
OFF_WHITE = (248, 249, 250)
TEXT_DARK = (26, 26, 46)
TEXT_MID = (102, 102, 102)
LIGHT_GREY = (220, 220, 220)

# Slide dimensions (16:9 @ 96 DPI for high-res assets)
SLIDE_W = 1280
SLIDE_H = 720

ASSETS_DIR = Path("/tmp/novit_pptx_assets")


def ensure_assets() -> Path:
    """Create assets directory."""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    return ASSETS_DIR


# ═══════════════════════════════════════════════════════════════
#  BACKGROUND GENERATORS  (PIL-based, high-quality)
# ═══════════════════════════════════════════════════════════════

def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _lerp_color(c1: tuple, c2: tuple, t: float) -> tuple:
    return tuple(int(_lerp(c1[i], c2[i], t)) for i in range(3))


def _radial_gradient(width: int, height: int, center_color: tuple, edge_color: tuple,
                     center: tuple | None = None) -> Image.Image:
    """Radial gradient from center to edges."""
    img = Image.new("RGB", (width, height))
    cx, cy = center or (width // 2, height // 2)
    max_dist = math.sqrt(max(cx, width - cx) ** 2 + max(cy, height - cy) ** 2)

    for y in range(height):
        for x in range(width):
            dist = math.sqrt((x - cx) ** 2 + (y - cy) ** 2)
            t = min(dist / max_dist, 1.0)
            img.putpixel((x, y), _lerp_color(center_color, edge_color, t))
    return img


def _angular_gradient(width: int, height: int, colors: list[tuple]) -> Image.Image:
    """Angular (conic) gradient sweeping around center."""
    img = Image.new("RGB", (width, height))
    cx, cy = width // 2, height // 2
    n = len(colors)
    for y in range(height):
        for x in range(width):
            angle = (math.atan2(y - cy, x - cx) + math.pi) / (2 * math.pi)
            idx = angle * n
            i = int(idx) % n
            j = (i + 1) % n
            t = idx - int(idx)
            img.putpixel((x, y), _lerp_color(colors[i], colors[j], t))
    return img


def _radar_sweep_overlay(width: int, height: int, color: tuple, opacity: float = 0.03,
                         lines: int = 24, rings: int = 8) -> Image.Image:
    """Professional radar screen watermark with rings, grid, sweep wedge and center."""
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    cx, cy = width // 2, height // 2
    max_r = min(cx, cy) * 0.92

    # Concentric rings — more rings, fading outward
    for i in range(1, rings + 1):
        r = max_r * (i / rings)
        alpha = int(255 * opacity * (1.0 - (i - 1) / rings))
        ring_color = (*color, max(alpha, 8))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=ring_color, width=1)

    # Radial grid lines
    for i in range(lines):
        angle = 2 * math.pi * i / lines
        x2 = cx + max_r * math.cos(angle)
        y2 = cy + max_r * math.sin(angle)
        alpha = int(255 * opacity * 0.4)
        draw.line([(cx, cy), (x2, y2)], fill=(*color, max(alpha, 6)), width=1)

    # Sweep wedge (filled sector with gradient opacity)
    wedge_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    wedge_draw = ImageDraw.Draw(wedge_overlay)
    sweep_start, sweep_end = -25, 55
    wedge_alpha = int(255 * opacity * 0.35)
    wedge_draw.pieslice([cx - max_r * 0.78, cy - max_r * 0.78,
                         cx + max_r * 0.78, cy + max_r * 0.78],
                        start=sweep_start, end=sweep_end,
                        fill=(*color, max(wedge_alpha, 10)))
    overlay = Image.alpha_composite(overlay, wedge_overlay)

    # Sweep arc line on top of wedge
    arc_alpha = int(255 * opacity * 1.2)
    draw = ImageDraw.Draw(overlay)
    draw.arc([cx - max_r * 0.78, cy - max_r * 0.78,
              cx + max_r * 0.78, cy + max_r * 0.78],
             start=sweep_start, end=sweep_end,
             fill=(*color, max(arc_alpha, 15)), width=2)

    # Center dot
    dot_r = 4
    dot_alpha = int(255 * opacity * 2.0)
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r],
                 fill=(*color, max(dot_alpha, 20)))

    # Crosshair tick marks at cardinal directions
    tick = 8
    tick_alpha = int(255 * opacity * 0.8)
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        x1 = cx + dx * (max_r - tick)
        y1 = cy + dy * (max_r - tick)
        x2 = cx + dx * max_r
        y2 = cy + dy * max_r
        draw.line([(x1, y1), (x2, y2)], fill=(*color, max(tick_alpha, 10)), width=2)

    return overlay


def _glassmorphism_panel(width: int, height: int, base_color: tuple = WHITE,
                         blur_radius: int = 20, opacity: float = 0.15) -> Image.Image:
    """Glassmorphism-style translucent panel with blur edges."""
    img = Image.new("RGBA", (width, height), (*base_color, int(255 * opacity)))
    # Subtle border glow
    draw = ImageDraw.Draw(img)
    border_color = (*WHITE, int(255 * 0.3))
    draw.rectangle([0, 0, width - 1, height - 1], outline=border_color, width=1)
    img = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    return img


def _diagonal_stripes(width: int, height: int, color1: tuple, color2: tuple,
                      stripe_width: int = 4) -> Image.Image:
    """Subtle diagonal stripe texture. Returns RGBA."""
    img = Image.new("RGBA", (width, height), color1)
    draw = ImageDraw.Draw(img)
    for i in range(-height, width + height, stripe_width * 2):
        draw.polygon([
            (i, 0), (i + stripe_width, 0),
            (i + stripe_width + height, height), (i + height, height)
        ], fill=color2)
    return img


def _glow_orb(width: int, height: int, color: tuple, radius: int = 200,
              position: tuple | None = None) -> Image.Image:
    """Soft glow orb for accent lighting."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cx, cy = position or (width // 2, height // 2)
    for r in range(radius, 0, -1):
        alpha = int(255 * (1 - r / radius) ** 2 * 0.3)
        draw = ImageDraw.Draw(img)
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*color, alpha))
    return img


# ═══════════════════════════════════════════════════════════════
#  SLIDE BACKGROUND GENERATORS
# ═══════════════════════════════════════════════════════════════

def generate_cover_background(path: Path) -> Path:
    """Dark gradient with radar watermark and glow orbs."""
    ensure_assets()
    out = path if isinstance(path, Path) else Path(path)

    # Base: deep radial gradient
    base = _radial_gradient(SLIDE_W, SLIDE_H, MID_NAVY, DEEP_NAVY, center=(SLIDE_W // 3, SLIDE_H // 3))

    # Add cyan glow orb top-right
    glow = _glow_orb(SLIDE_W, SLIDE_H, CYAN, radius=280, position=(SLIDE_W * 0.75, SLIDE_H * 0.25))
    base = base.convert("RGBA")
    base = Image.alpha_composite(base, glow)

    # Add magenta glow orb bottom-left
    glow2 = _glow_orb(SLIDE_W, SLIDE_H, MAGENTA, radius=220, position=(SLIDE_W * 0.2, SLIDE_H * 0.8))
    base = Image.alpha_composite(base, glow2)

    # Radar watermark
    radar = _radar_sweep_overlay(SLIDE_W, SLIDE_H, CYAN, opacity=0.04, lines=16, rings=8)
    base = Image.alpha_composite(base, radar)

    # Subtle diagonal texture overlay
    stripes = _diagonal_stripes(SLIDE_W, SLIDE_H, (0, 0, 0, 0), (*DEEP_NAVY, 15))
    if stripes.size != base.size:
        stripes = stripes.resize(base.size, Image.LANCZOS)
    base = Image.alpha_composite(base, stripes)

    base.convert("RGB").save(str(out), quality=95)
    return out


def generate_cover_split_background(path: Path) -> Path:
    """Top 30% dark cover gradient, bottom 70% light background."""
    ensure_assets()
    out = path if isinstance(path, Path) else Path(path)

    # Generate both full backgrounds into temp files
    dark_path = ASSETS_DIR / "_tmp_dark.png"
    light_path = ASSETS_DIR / "_tmp_light.png"
    generate_cover_background(dark_path)
    generate_light_background(light_path, with_watermark=True)

    dark_img = Image.open(dark_path).convert("RGBA")
    light_img = Image.open(light_path).convert("RGBA")

    split_y = int(SLIDE_H * 0.30)  # 216 px

    result = Image.new("RGBA", (SLIDE_W, SLIDE_H))
    # Top 30% from dark
    result.paste(dark_img.crop((0, 0, SLIDE_W, split_y)), (0, 0))
    # Bottom 70% from light
    result.paste(light_img.crop((0, split_y, SLIDE_W, SLIDE_H)), (0, split_y))

    # Very subtle 4px blend zone — sharp but not jagged
    blend = 4
    for y in range(max(0, split_y - blend), min(SLIDE_H, split_y + blend)):
        t = (y - (split_y - blend)) / (blend * 2)
        for x in range(SLIDE_W):
            c_dark = dark_img.getpixel((x, y))
            c_light = light_img.getpixel((x, y))
            blended = tuple(int(c_dark[i] * (1 - t) + c_light[i] * t) for i in range(4))
            result.putpixel((x, y), blended)

    result.convert("RGB").save(str(out), quality=95)

    dark_path.unlink(missing_ok=True)
    light_path.unlink(missing_ok=True)
    return out


def generate_light_background(path: Path, with_watermark: bool = True) -> Path:
    """Clean light background with subtle radar watermark."""
    out = path if isinstance(path, Path) else Path(path)

    # Soft off-white with very subtle radial warmth
    base = _radial_gradient(SLIDE_W, SLIDE_H, (255, 255, 255), OFF_WHITE, center=(SLIDE_W // 2, 0))
    base = base.convert("RGBA")

    if with_watermark:
        radar = _radar_sweep_overlay(SLIDE_W, SLIDE_H, MID_NAVY, opacity=0.015, lines=20, rings=10)
        base = Image.alpha_composite(base, radar)

    base.convert("RGB").save(str(out), quality=95)
    return out


def generate_footer_background(path: Path) -> Path:
    """Dark gradient for footer/CTA slide with dramatic lighting."""
    out = path if isinstance(path, Path) else Path(path)

    # Angular gradient for drama
    base = _angular_gradient(SLIDE_W, SLIDE_H, [DEEP_NAVY, MID_NAVY, DEEP_NAVY, MID_NAVY])
    base = base.convert("RGBA")

    # Cyan accent glow bottom-center
    glow = _glow_orb(SLIDE_W, SLIDE_H, CYAN, radius=350, position=(SLIDE_W // 2, SLIDE_H * 0.85))
    base = Image.alpha_composite(base, glow)

    # Magenta accent glow top-right
    glow2 = _glow_orb(SLIDE_W, SLIDE_H, MAGENTA, radius=200, position=(SLIDE_W * 0.85, SLIDE_H * 0.2))
    base = Image.alpha_composite(base, glow2)

    # Radar watermark
    radar = _radar_sweep_overlay(SLIDE_W, SLIDE_H, WHITE, opacity=0.025, lines=12, rings=6)
    base = Image.alpha_composite(base, radar)

    base.convert("RGB").save(str(out), quality=95)
    return out


def generate_glass_panel(width: int, height: int, path: Path) -> Path:
    """Glassmorphism panel asset."""
    out = path if isinstance(path, Path) else Path(path)
    panel = _glassmorphism_panel(width, height, WHITE, blur_radius=15, opacity=0.12)
    panel.save(str(out))
    return out


# ═══════════════════════════════════════════════════════════════
#  LOGO HELPERS
# ═══════════════════════════════════════════════════════════════

# NOTE: The filenames are swapped vs their visual content:
#   novit-logo.png        = blue/dark version (for light backgrounds)
#   novit-logo-dark.png   = white version (for dark backgrounds)
NOVIT_LOGO_DARK_URL = "https://ia.novitsoftware.com/assets/images/novit-logo.png"
NOVIT_LOGO_WHITE_URL = "https://ia.novitsoftware.com/assets/images/novit-logo-dark.png"


def fetch_logo_bytes(url: str = NOVIT_LOGO_WHITE_URL, timeout: int = 10) -> io.BytesIO | None:
    """Fetch logo from URL and return as BytesIO.

    Validates the response is actually a valid image before returning.
    If the URL is unreachable, returns 404, or returns corrupted data,
    the function returns None and the caller skips the logo placement.
    """
    try:
        import requests
        from PIL import Image
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        # Validate that the content is actually a valid image
        try:
            img = Image.open(io.BytesIO(resp.content))
            img.verify()  # raises if not a valid image
        except Exception as exc:
            logger.warning(
                "Logo URL returned non-image content (%s): %s",
                exc, url[:80],
            )
            return None
        return io.BytesIO(resp.content)
    except Exception:
        logger.warning("Failed to fetch logo from %s", url)
        return None


# ═══════════════════════════════════════════════════════════════
#  TEMPLATE BUILDER
# ═══════════════════════════════════════════════════════════════

class NewsletterTemplateBuilder:
    """Builds the master PPTX template with all visual styles."""

    def __init__(self, output_path: str | Path = "/tmp/novit_newsletter_template.pptx") -> None:
        self.output_path = Path(output_path)
        self.assets_dir = ensure_assets()
        self._bg_paths: dict[str, Path] = {}
        self._logo_white: io.BytesIO | None = None
        self._logo_dark: io.BytesIO | None = None

    def build(self) -> Path:
        """Generate the complete template and return path."""
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        # Pre-fetch logos
        self._logo_white = fetch_logo_bytes(NOVIT_LOGO_WHITE_URL)
        self._logo_dark = fetch_logo_bytes(NOVIT_LOGO_DARK_URL)

        # Generate backgrounds
        self._bg_paths["cover"] = generate_cover_background(self.assets_dir / "bg_cover.png")
        self._bg_paths["cover_split"] = generate_cover_split_background(self.assets_dir / "bg_cover_split.png")
        self._bg_paths["light"] = generate_light_background(self.assets_dir / "bg_light.png")
        self._bg_paths["footer"] = generate_footer_background(self.assets_dir / "bg_footer.png")

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        # ── Slide 1: Cover + Panorama Global ─────────────────────
        self._build_slide_cover_summary(prs)

        # ── Slide 2: Hallazgos (3 columnas) ────────────────────────
        self._build_slide_insights(prs)

        # ── Slide 3: Señal Cuantitativa ────────────────────────────
        self._build_slide_chart(prs)

        # ── Slide 4: Info + Footer CTA ─────────────────────────────
        self._build_slide_footer(prs)

        prs.save(str(self.output_path))
        logger.info("Template saved to %s", self.output_path)
        return self.output_path

    # ── Slide builders ────────────────────────────────────────────

    def _build_slide_cover_summary(self, prs):
        """Slide 1: Top 30% = Dark cover with title. Bottom 70% = Light summary."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        blank = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank)

        # Split background: 30% dark top, 70% light bottom
        bg = slide.shapes.add_picture(str(self._bg_paths["cover_split"]), 0, 0,
                                       width=Inches(13.333), height=Inches(7.5))
        self._send_to_back(slide, bg)

        # ── Magenta dot with label ─────────────────────────────────
        radar_cx, radar_cy = Inches(10.8), Inches(1.1)
        dot = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                      radar_cx - Inches(0.04), radar_cy - Inches(0.04),
                                      Inches(0.08), Inches(0.08))
        dot.fill.solid()
        dot.fill.fore_color.rgb = RGBColor(*MAGENTA)
        dot.line.fill.background()

        hitl = slide.shapes.add_textbox(radar_cx + Inches(0.08), radar_cy - Inches(0.06),
                                         Inches(2.0), Inches(0.15))
        tf = hitl.text_frame
        p = tf.paragraphs[0]
        p.text = "humans in the loop"
        p.font.size = Pt(8)
        p.font.italic = True
        p.font.color.rgb = RGBColor(200, 200, 220)
        p.font.name = "Open Sans"

        # Logo top-right (white version on dark bg)
        if self._logo_white:
            slide.shapes.add_picture(self._logo_white, Inches(11.3), Inches(0.15), width=Inches(1.8))

        # AI Radar title (top dark area, white text)
        title_box = slide.shapes.add_textbox(Inches(0), Inches(0.30), Inches(13.333), Inches(0.75))
        tf = title_box.text_frame
        p = tf.paragraphs[0]
        p.text = "AI Radar"
        p.font.size = Pt(64)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*WHITE)
        p.font.name = "Open Sans"
        p.alignment = PP_ALIGN.CENTER

        # Subtitle
        sub_box = slide.shapes.add_textbox(Inches(0), Inches(1.20), Inches(13.333), Inches(0.30))
        tf = sub_box.text_frame
        p = tf.paragraphs[0]
        p.text = "by Novit"
        p.font.size = Pt(24)
        p.font.italic = True
        p.font.color.rgb = RGBColor(200, 200, 220)
        p.font.name = "Open Sans"
        p.alignment = PP_ALIGN.CENTER

        # Cyan accent line
        line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(5.9), Inches(1.62), Inches(1.5), Pt(3))
        line.fill.solid()
        line.fill.fore_color.rgb = RGBColor(*CYAN)
        line.line.fill.background()

        # Tagline
        tag = slide.shapes.add_textbox(Inches(0), Inches(1.85), Inches(13.333), Inches(0.28))
        tf = tag.text_frame
        p = tf.paragraphs[0]
        p.text = "Inteligencia Artificial aplicada a negocio"
        p.font.size = Pt(13)
        p.font.color.rgb = RGBColor(180, 180, 200)
        p.font.name = "Open Sans"
        p.alignment = PP_ALIGN.CENTER

        # ── Bottom section: Summary cards (light area) ─────────────
        # Section label
        lbl = slide.shapes.add_textbox(Inches(0.5), Inches(2.55), Inches(4), Inches(0.3))
        tf = lbl.text_frame
        p = tf.paragraphs[0]
        p.text = "PANORAMA GLOBAL"
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*MID_NAVY)
        p.font.name = "Open Sans"

        # Divider — slightly shorter than label text
        div = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(2.90), Inches(2.0), Pt(2))
        div.fill.solid()
        div.fill.fore_color.rgb = RGBColor(*CYAN)
        div.line.fill.background()

        # Placeholder text box for executive summary
        # Font size: 12pt (was 13 — user reduced 1pt, "quedó joya")
        # Box height: 3.6" (was 3.8") — bottom now matches chart_pricing
        # (y=5.05 + h=1.75 = 6.80), so the two visual blocks align.
        # Max chars: 900 (was 1500) — previous text overflowed the box
        # and read cramped; 900 = 3 short paragraphs fits comfortably.
        sum_box = slide.shapes.add_textbox(Inches(0.5), Inches(3.20), Inches(7.5), Inches(3.6))
        sum_box.name = "PLACEHOLDER_EXECUTIVE_SUMMARY"
        tf = sum_box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "{executive_summary}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(*TEXT_DARK)
        p.font.name = "Open Sans"
        p.line_spacing = 1.5

        # Right side: 2 native PPTX tables (benchmark, pricing) — PR B
        # Layout: label sits 0.05" above each table, with a 0.20" gap
        # between table 1 end and table 2 label. Tables are 1.75" tall
        # (was 1.85) to leave breathing room.
        table_x = Inches(8.3)
        table_w = Inches(4.5)
        table_h = Inches(1.75)
        table_titles = [
            # (label_y, table_y, lbl_name, table_name, lbl_text, color)
            (Inches(2.50), Inches(2.80),
             "PLACEHOLDER_METRIC_LABEL_0", "PLACEHOLDER_BENCHMARK_TABLE", "BENCHMARK  ·  MMLU Pro", CYAN),
            (Inches(4.75), Inches(5.05),
             "PLACEHOLDER_METRIC_LABEL_1", "PLACEHOLDER_PRICING_TABLE",   "COSTO  ·  x 1M tokens", MID_NAVY),
        ]
        for lbl_y, tbl_y, lbl_name, table_name, lbl_text, color in table_titles:
            # Title label (above the table)
            lbl = slide.shapes.add_textbox(table_x, lbl_y, table_w, Inches(0.22))
            lbl.name = lbl_name
            tf = lbl.text_frame
            p = tf.paragraphs[0]
            p.text = lbl_text
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = RGBColor(*color)
            p.font.name = "Open Sans"

            # Native PPTX table: 6 rows (1 header + 5 data) × 3 columns
            table_shape = slide.shapes.add_table(
                rows=6, cols=3,
                left=table_x,
                top=tbl_y,
                width=table_w,
                height=table_h,
            )
            table_shape.name = table_name
            table = table_shape.table

            # Column widths: # narrow, model wide, value medium
            table.columns[0].width = Inches(0.35)
            table.columns[1].width = Inches(2.55)
            table.columns[2].width = Inches(1.60)

            # Header row
            headers = ["#", "Modelo", lbl_text.split("·")[-1].strip() if "·" in lbl_text else lbl_text]
            for c, h in enumerate(headers):
                cell = table.cell(0, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(*color)
                tf = cell.text_frame
                tf.margin_left = Inches(0.05)
                tf.margin_right = Inches(0.05)
                tf.margin_top = Inches(0.02)
                tf.margin_bottom = Inches(0.02)
                p = tf.paragraphs[0]
                p.text = h
                p.font.size = Pt(9)
                p.font.bold = True
                p.font.color.rgb = RGBColor(*WHITE)
                p.font.name = "Open Sans"
                p.alignment = PP_ALIGN.CENTER

            # Data rows: empty by default, publisher fills them
            for r in range(1, 6):
                for c in range(3):
                    cell = table.cell(r, c)
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = RGBColor(245, 245, 250) if r % 2 == 1 else RGBColor(*WHITE)
                    tf = cell.text_frame
                    tf.margin_left = Inches(0.05)
                    tf.margin_right = Inches(0.05)
                    tf.margin_top = Inches(0.01)
                    tf.margin_bottom = Inches(0.01)
                    p = tf.paragraphs[0]
                    p.text = ""
                    p.font.size = Pt(9)
                    p.font.color.rgb = RGBColor(*TEXT_DARK)
                    p.font.name = "Open Sans"
                    if c == 0:
                        p.alignment = PP_ALIGN.CENTER
                    elif c == 2:
                        p.alignment = PP_ALIGN.RIGHT

    def _build_slide_insights(self, prs):
        """Slide 2: Argentina — full-width single insight layout."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        blank = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank)

        # Light background with watermark
        bg = slide.shapes.add_picture(str(self._bg_paths["light"]), 0, 0,
                                       width=Inches(13.333), height=Inches(7.5))
        self._send_to_back(slide, bg)

        # Logo top-right (dark version for light bg)
        if self._logo_dark:
            slide.shapes.add_picture(self._logo_dark, Inches(11.3), Inches(0.25), width=Inches(1.8))

        # Country title
        title = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(5), Inches(0.45))
        tf = title.text_frame
        p = tf.paragraphs[0]
        p.text = "ARGENTINA"
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*MID_NAVY)
        p.font.name = "Open Sans"

        # Cyan divider — wider than title for clean look
        div = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(0.78), Inches(2.50), Pt(3))
        div.fill.solid()
        div.fill.fore_color.rgb = RGBColor(*CYAN)
        div.line.fill.background()

        # Subtitle
        sub = slide.shapes.add_textbox(Inches(0.5), Inches(1.00), Inches(5), Inches(0.25))
        tf = sub.text_frame
        p = tf.paragraphs[0]
        p.text = "Informaci\u00f3n clave del mes"
        p.font.size = Pt(13)
        p.font.color.rgb = RGBColor(*TEXT_MID)
        p.font.name = "Open Sans"

        # ── Two-column layout ──────────────────────────────────────
        # Left 42%: Image
        img_left = Inches(0.5)
        img_top = Inches(1.40)
        img_w = Inches(5.2)
        img_h = Inches(4.95)

        frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                        img_left, img_top, img_w, img_h)
        frame.fill.solid()
        frame.fill.fore_color.rgb = RGBColor(235, 235, 240)
        frame.line.color.rgb = RGBColor(210, 210, 220)
        frame.line.width = Pt(1)
        if frame.adjustments:
            frame.adjustments[0] = 0.06
        frame.name = "PLACEHOLDER_AR_IMAGE_FRAME"

        ph_txt = slide.shapes.add_textbox(img_left, img_top + img_h / 2 - Inches(0.15),
                                           img_w, Inches(0.3))
        ph_txt.name = "PLACEHOLDER_AR_IMAGE_TEXT"
        tf = ph_txt.text_frame
        p = tf.paragraphs[0]
        p.text = "{image}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(180, 180, 190)
        p.font.name = "Open Sans"
        p.alignment = PP_ALIGN.CENTER

        # Right 58%: Single Markdown textbox for all AR content
        col_x = Inches(6.0)
        col_w = Inches(6.8)

        txt = slide.shapes.add_textbox(col_x, Inches(1.55), col_w, Inches(5.0))
        txt.name = "PLACEHOLDER_AR_TEXT"
        tf = txt.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "{ar_text}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(*TEXT_DARK)
        p.font.name = "Open Sans"
        p.line_spacing = 1.5

    def _build_slide_chart(self, prs):
        """Slide 3: España — full-width single insight layout."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        blank = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank)

        # Light background
        bg = slide.shapes.add_picture(str(self._bg_paths["light"]), 0, 0,
                                       width=Inches(13.333), height=Inches(7.5))
        self._send_to_back(slide, bg)

        # Dark version logo
        if self._logo_dark:
            slide.shapes.add_picture(self._logo_dark, Inches(11.3), Inches(0.25), width=Inches(1.8))

        # Country title
        title = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(5), Inches(0.45))
        tf = title.text_frame
        p = tf.paragraphs[0]
        p.text = "ESPAÑA"
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*MID_NAVY)
        p.font.name = "Open Sans"

        # Magenta divider — wider than title for clean look
        div = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(0.78), Inches(1.75), Pt(3))
        div.fill.solid()
        div.fill.fore_color.rgb = RGBColor(*MAGENTA)
        div.line.fill.background()

        # Subtitle
        sub = slide.shapes.add_textbox(Inches(0.5), Inches(1.00), Inches(5), Inches(0.25))
        tf = sub.text_frame
        p = tf.paragraphs[0]
        p.text = "Informaci\u00f3n clave del mes"
        p.font.size = Pt(13)
        p.font.color.rgb = RGBColor(*TEXT_MID)
        p.font.name = "Open Sans"

        # ── Two-column layout (mirrored: text left, image right) ───
        # Left 58%: Single Markdown textbox for all ES content
        col_x = Inches(0.5)
        col_w = Inches(6.8)

        txt = slide.shapes.add_textbox(col_x, Inches(1.55), col_w, Inches(5.0))
        txt.name = "PLACEHOLDER_ES_TEXT"
        tf = txt.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "{es_text}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(*TEXT_DARK)
        p.font.name = "Open Sans"
        p.line_spacing = 1.5

        # Right 42%: Image
        img_left = Inches(7.6)
        img_top = Inches(1.40)
        img_w = Inches(5.2)
        img_h = Inches(4.95)

        frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                        img_left, img_top, img_w, img_h)
        frame.fill.solid()
        frame.fill.fore_color.rgb = RGBColor(235, 235, 240)
        frame.line.color.rgb = RGBColor(210, 210, 220)
        frame.line.width = Pt(1)
        if frame.adjustments:
            frame.adjustments[0] = 0.06
        frame.name = "PLACEHOLDER_ES_IMAGE_FRAME"

        ph_txt = slide.shapes.add_textbox(img_left, img_top + img_h / 2 - Inches(0.15),
                                           img_w, Inches(0.3))
        ph_txt.name = "PLACEHOLDER_ES_IMAGE_TEXT"
        tf = ph_txt.text_frame
        p = tf.paragraphs[0]
        p.text = "{image}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(180, 180, 190)
        p.font.name = "Open Sans"
        p.alignment = PP_ALIGN.CENTER

    def _build_slide_footer(self, prs):
        """Slide 4: Top ~70% = Info on dark bg. Bottom ~30% = clean links footer."""
        from pptx.util import Inches, Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.dml.color import RGBColor
        from pptx.enum.shapes import MSO_SHAPE

        blank = prs.slide_layouts[6]
        slide = prs.slides.add_slide(blank)

        # Full dark background
        bg = slide.shapes.add_picture(str(self._bg_paths["footer"]), 0, 0,
                                       width=Inches(13.333), height=Inches(7.5))
        self._send_to_back(slide, bg)

        # White logo top-right (on dark bg)
        if self._logo_white:
            slide.shapes.add_picture(self._logo_white, Inches(11.3), Inches(0.25), width=Inches(1.8))

        # ── Top section: two columns ───────────────────────────────
        # Left 55%: Info / conclusions
        it = slide.shapes.add_textbox(Inches(0.5), Inches(0.45), Inches(6.5), Inches(0.4))
        it.name = "PLACEHOLDER_INFO_TITLE"
        tf = it.text_frame
        p = tf.paragraphs[0]
        p.text = "{info_title}"
        p.font.size = Pt(20)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*WHITE)
        p.font.name = "Open Sans"

        ib = slide.shapes.add_textbox(Inches(0.5), Inches(1.15), Inches(6.5), Inches(2.6))
        ib.name = "PLACEHOLDER_INFO_BODY"
        tf = ib.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = "{info_body}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(220, 220, 235)
        p.font.name = "Open Sans"
        p.line_spacing = 1.5

        # Right 40%: Supporting image
        img_left = Inches(7.5)
        img_top = Inches(1.58)
        img_w = Inches(5.2)
        img_h = Inches(3.2)

        frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                        img_left, img_top, img_w, img_h)
        frame.fill.solid()
        frame.fill.fore_color.rgb = RGBColor(235, 235, 240)
        frame.line.color.rgb = RGBColor(210, 210, 220)
        frame.line.width = Pt(1)
        if frame.adjustments:
            frame.adjustments[0] = 0.06
        frame.name = "PLACEHOLDER_FOOTER_IMAGE_FRAME"

        ph_txt = slide.shapes.add_textbox(img_left, img_top + img_h / 2 - Inches(0.15),
                                           img_w, Inches(0.3))
        ph_txt.name = "PLACEHOLDER_FOOTER_IMAGE_TEXT"
        tf = ph_txt.text_frame
        p = tf.paragraphs[0]
        p.text = "{image}"
        p.font.size = Pt(12)
        p.font.color.rgb = RGBColor(180, 180, 190)
        p.font.name = "Open Sans"
        p.alignment = PP_ALIGN.CENTER

        # ── Bottom CTA section (~30% from 4.5") ────────────────────
        # Cyan divider line above CTA
        div = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.5), Inches(4.4), Inches(2.5), Pt(2))
        div.fill.solid()
        div.fill.fore_color.rgb = RGBColor(*CYAN)
        div.line.fill.background()

        # CTA headline
        cta_title = slide.shapes.add_textbox(Inches(0.5), Inches(4.6), Inches(8), Inches(0.5))
        tf = cta_title.text_frame
        p = tf.paragraphs[0]
        p.text = "¿Listo para liderar con IA?"
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = RGBColor(*WHITE)
        p.font.name = "Open Sans"

        # Tagline below headline
        self._add_text_box(slide, Inches(0.5), Inches(5.05), Inches(8), Inches(0.25),
                           "Hacemos simple lo complejo con Agentes de IA de vanguardia.",
                           Pt(13), False, (200, 200, 220), "Open Sans")

        # ── Styled links ─────────────────────────────────────────
        # Magenta URLs (shape-level hyperlinks so theme doesn't force blue)
        MAGENTA_BRIGHT = (255, 20, 147)

        # Link 1: Calendar
        link1 = slide.shapes.add_textbox(Inches(0.5), Inches(5.45), Inches(9), Inches(0.28))
        tf = link1.text_frame
        p = tf.paragraphs[0]
        p.clear()
        r1 = p.add_run()
        r1.text = "\u25b6  Agend\u00e1 una reuni\u00f3n  "
        r1.font.size = Pt(13)
        r1.font.color.rgb = RGBColor(220, 220, 235)
        r1.font.name = "Open Sans"
        r2 = p.add_run()
        r2.text = "cal.novitsoftware.com/team/sales"
        r2.font.size = Pt(13)
        r2.font.color.rgb = RGBColor(*MAGENTA_BRIGHT)
        r2.font.name = "Open Sans"
        link1.click_action.hyperlink.address = "https://cal.novitsoftware.com/team/sales"

        # Link 2: AI assistant
        link2 = slide.shapes.add_textbox(Inches(0.5), Inches(5.72), Inches(9), Inches(0.28))
        tf = link2.text_frame
        p = tf.paragraphs[0]
        p.clear()
        r1 = p.add_run()
        r1.text = "\u25b6  Convers\u00e1 con nuestra IA para saber m\u00e1s y ver el Brochure  "
        r1.font.size = Pt(13)
        r1.font.color.rgb = RGBColor(220, 220, 235)
        r1.font.name = "Open Sans"
        r2 = p.add_run()
        r2.text = "ai.novitsoftware.com"
        r2.font.size = Pt(13)
        r2.font.color.rgb = RGBColor(*MAGENTA_BRIGHT)
        r2.font.name = "Open Sans"
        link2.click_action.hyperlink.address = "https://ai.novitsoftware.com"

        # Contact info — single aligned textbox, no hyperlinks (avoids blue theme color)
        contact = slide.shapes.add_textbox(Inches(0.5), Inches(6.05), Inches(8), Inches(0.25))
        tf = contact.text_frame
        p = tf.paragraphs[0]
        p.text = "novitsoftware.com  |  info@novitsoftware.com"
        p.font.size = Pt(11)
        p.font.color.rgb = RGBColor(160, 160, 180)
        p.font.name = "Open Sans"

    # ── Helpers ───────────────────────────────────────────────────

    def _send_to_back(self, slide, shape):
        spTree = slide.shapes._spTree
        sp = shape._element
        spTree.remove(sp)
        spTree.insert(2, sp)

    def _add_text_box(self, slide, left, top, width, height, text, font_size, bold, color, font_name, align=None):
        from pptx.util import Pt
        from pptx.enum.text import PP_ALIGN
        from pptx.dml.color import RGBColor

        box = slide.shapes.add_textbox(left, top, width, height)
        tf = box.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = font_size
        p.font.bold = bold
        p.font.color.rgb = RGBColor(*color)
        p.font.name = font_name
        if align:
            p.alignment = align
        return box

    def _add_oval(self, slide, left, top, width, height, line_color, line_width, fill_color=None, fill_alpha=0.0):
        from pptx.enum.shapes import MSO_SHAPE
        from pptx.dml.color import RGBColor

        oval = slide.shapes.add_shape(MSO_SHAPE.OVAL, left, top, width, height)
        if fill_color is None:
            oval.fill.background()
        else:
            oval.fill.solid()
            oval.fill.fore_color.rgb = RGBColor(*fill_color)
        oval.line.color.rgb = RGBColor(*line_color)
        oval.line.width = line_width
        return oval


# ═══════════════════════════════════════════════════════════════
#  PUBLIC API
# ═══════════════════════════════════════════════════════════════

def build_template(output_path: str | Path = "/tmp/novit_newsletter_template.pptx") -> Path:
    """Build and return the master template path."""
    builder = NewsletterTemplateBuilder(output_path)
    return builder.build()


def get_template_path() -> Path:
    """Return path to existing template, building if needed."""
    path = Path("/tmp/novit_newsletter_template.pptx")
    if not path.exists():
        return build_template(path)
    return path
