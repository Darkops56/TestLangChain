namespace CmPlatform.Api.Services;

public static class NurturingContentRenderer
{
    public static string WrapInHtmlEmail(string body)
    {
        return $"""
<!doctype html>
<html lang="es">
<head><meta charset="utf-8" /></head>
<body style="font-family:Arial,sans-serif;background:#f4f7fb;color:#102033;padding:24px;">
<div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;padding:24px;">
{body}
</div>
</body>
</html>
""";
    }
}
