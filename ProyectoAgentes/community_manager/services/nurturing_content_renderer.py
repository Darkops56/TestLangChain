"""Nurturing content renderer - email HTML template.

Ported from NurturingContentRenderer.cs.
"""

from __future__ import annotations

import html
import re


def wrap_in_html_email(
    html_body: str,
    first_name: str | None = None,
    personal_closing: str | None = None,
) -> str:
    """Wrap newsletter HTML body in the full email template with Novit signature."""
    greeting = f"Hola {first_name.strip()}," if first_name and first_name.strip() else "Hola,"

    closing_html = (
        f'\n            <p style="margin-top:20px;">{personal_closing}</p>'
        if personal_closing and personal_closing.strip()
        else ""
    )

    logo_url = "https://ia.novitsoftware.com/assets/images/novit-logo.png"

    return f"""\
<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background-color:#ffffff;font-family:'Open Sans',Arial,Helvetica,sans-serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;">
<tr><td style="padding:20px 24px;max-width:600px;font-size:15px;line-height:1.6;color:#222222;">

<p style="margin-top:0;">{greeting}</p>

{html_body}
{closing_html}

<!-- Separator -->
<hr style="border:none;border-top:1px solid #dddddd;margin:28px 0 20px 0;">

<!-- Signature -->
<table role="presentation" cellpadding="0" cellspacing="0" style="max-width:420px;">
<tr>
  <td style="padding:4px 0;">
    <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
    <tr>
      <!-- Logo -->
            <td style="vertical-align:middle;padding-right:14px;border-right:2px solid #0A0089;" width="110">
        <img src="{logo_url}" alt="Novit" width="100" style="display:block;border:0;">
      </td>
      <!-- Contact info -->
            <td style="vertical-align:middle;padding-left:14px;font-family:'Open Sans',Arial,Helvetica,sans-serif;font-size:12px;color:#555555;line-height:1.6;">
        <b style="font-size:14px;color:#222222;">Nicolás Piccardo,</b><br>
        Director comercial<br>
        <a href="tel:+5491136895431" style="color:#1a73e8;text-decoration:none;">+54 9 11 3689 5431</a><br>
        <a href="mailto:nicolasp@novitsoftware.com" style="color:#1a73e8;text-decoration:none;">nicolasp@novitsoftware.com</a><br>
        <a href="https://www.novitsoftware.com" style="color:#1a73e8;text-decoration:none;">www.novitsoftware.com</a><br>
        <span style="color:#888888;">Av. Córdoba 1351, piso #3. CABA, Argentina</span>
      </td>
    </tr>
    </table>
  </td>
</tr>
</table>

</td></tr>
</table>
</body>
</html>"""


def build_newsletter_reference_summary(html_body: str) -> str:
    """Strip HTML and truncate to 220 chars for reference text."""
    if not html_body:
        return ""

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", html_body)
    # Decode HTML entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()

    if len(text) > 220:
        return text[:220] + "..."

    return text
