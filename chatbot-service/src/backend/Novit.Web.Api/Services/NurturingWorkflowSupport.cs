namespace Novit.Web.Api.Services;

public static class NurturingWorkflowSupport
{
    private static readonly string[] HoldKeywords =
        ["no enviar", "no se envíe", "no se envie", "standby", "pausar", "suspender", "en espera", "detener"];

    private static readonly string[] ResumeKeywords =
        ["reanudar", "enviar", "aprobar", "aprobado", "dale", "retomar", "activar"];

    private static readonly Random DelayRng = new();

    public static string StripQuotedReply(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
            return body;

        string[] separators =
        [
            "-----Original Message-----",
            "-----Mensaje original-----",
            "---------- Forwarded message",
            "---------- Mensaje reenviado",
            "On ",
            "El ",
            "<blockquote",
            "<div class=\"gmail_quote\"",
            "-- \r\n",
            "-- \n",
        ];

        var idx = body.Length;
        foreach (var separator in separators)
        {
            var pos = body.IndexOf(separator, StringComparison.OrdinalIgnoreCase);
            if (pos >= 0 && pos < idx)
                idx = pos;
        }

        var lines = body[..idx].Split('\n');
        var freshLines = lines.Where(line => !line.TrimStart().StartsWith('>'));
        return string.Join('\n', freshLines).Trim();
    }

    public static bool IsHoldRequest(string body)
    {
        var fresh = StripQuotedReply(body).ToLowerInvariant();
        return HoldKeywords.Any(keyword => fresh.Contains(keyword));
    }

    public static bool IsResumeRequest(string body)
    {
        var fresh = StripQuotedReply(body).ToLowerInvariant();
        if (HoldKeywords.Any(keyword => fresh.Contains(keyword)))
            return false;

        return ResumeKeywords.Any(keyword => fresh.Contains(keyword));
    }

    public static int GetHumanLikeDelay()
    {
        var roll = DelayRng.Next(100);

        var baseDelay = roll switch
        {
            < 60 => DelayRng.Next(10, 26),
            < 78 => DelayRng.Next(26, 46),
            < 88 => DelayRng.Next(55, 76),
            < 93 => DelayRng.Next(165, 196),
            < 96 => DelayRng.Next(270, 331),
            < 98 => DelayRng.Next(1080, 1261),
            _ => DelayRng.Next(35, 66),
        };

        var jitter = (int)(baseDelay * 0.05);
        return baseDelay + DelayRng.Next(-jitter, jitter + 1);
    }

    public static string? ExtractFirstName(string? fullName)
    {
        if (string.IsNullOrWhiteSpace(fullName))
            return null;

        var first = fullName.Trim().Split(' ', StringSplitOptions.RemoveEmptyEntries)[0];
        return char.ToUpper(first[0]) + first[1..].ToLower();
    }

    public static string BuildPersonalClosing(string? firstName, string? orgName)
    {
        if (!string.IsNullOrWhiteSpace(orgName))
            return $"Te lo comparto por si suma mirarlo con el equipo de {orgName}. Abrazo!";

        return "Te lo comparto por si suma mirarlo con calma. Abrazo!";
    }
}