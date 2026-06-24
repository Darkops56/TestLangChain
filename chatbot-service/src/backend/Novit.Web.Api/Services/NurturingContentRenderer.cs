using System.Net;
using System.Text.RegularExpressions;

namespace Novit.Web.Api.Services;

/// <summary>
/// Backend-side rendering helpers for nurturing content.
/// Keeps email/presentation formatting local to .NET while AI generation moves to the Python agent.
/// </summary>
public static class NurturingContentRenderer
{
    private const string LogoUrl = "https://ia.novitsoftware.com/assets/images/novit-logo.png";

    public static string WrapInHtmlEmail(string htmlBody, string? firstName = null, string? personalClosing = null)
    {
        var greeting = string.IsNullOrWhiteSpace(firstName) ? "Hola," : $"Hola {firstName.Trim()},";
        var personalIntroHtml = string.IsNullOrWhiteSpace(personalClosing)
            ? ""
            : $"\n            <p style=\"margin-top:0;margin-bottom:20px;\">{personalClosing}</p>";

        return $$"""
            <!DOCTYPE html>
            <html lang="es">
            <head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
            <body style="margin:0;padding:0;background-color:#ffffff;font-family:Arial,Helvetica,sans-serif;">
            <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#ffffff;">
            <tr><td style="padding:20px 24px;max-width:600px;font-size:15px;line-height:1.6;color:#222222;">

            <p style="margin-top:0;">{{greeting}}</p>
            {{personalIntroHtml}}

            {{htmlBody}}

            <hr style="border:none;border-top:1px solid #dddddd;margin:28px 0 20px 0;">

            <table role="presentation" cellpadding="0" cellspacing="0" style="max-width:420px;">
            <tr>
              <td style="padding:4px 0;">
                <table role="presentation" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="vertical-align:middle;padding-right:14px;border-right:2px solid #3b82f6;" width="110">
                    <img src="{{LogoUrl}}" alt="Novit" width="100" style="display:block;border:0;">
                  </td>
                  <td style="vertical-align:middle;padding-left:14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;color:#555555;line-height:1.6;">
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
            </html>
            """;
    }

    public static string BuildNewsletterReferenceSummary(string htmlBody)
    {
        if (string.IsNullOrWhiteSpace(htmlBody))
            return string.Empty;

        var text = htmlBody;
        text = Regex.Replace(text, @"<br\s*/?>", "\n", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"</(?:p|div|tr|li|h[1-6])>", "\n", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"<[^>]+>", " ");
        text = WebUtility.HtmlDecode(text);
        text = Regex.Replace(text, @"\s+", " ").Trim();

        if (text.Length <= 220)
            return text;

        return text[..220].Trim() + "...";
    }
}