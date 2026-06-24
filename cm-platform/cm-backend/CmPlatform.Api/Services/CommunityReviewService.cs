using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Models;

namespace CmPlatform.Api.Services;

public sealed class CommunityReviewService(
    INurturingMailService mailService,
    IOptions<NurturingOptions> nurturingOptions,
    IConfiguration configuration,
    NovitDbContext db,
    ILogger<CommunityReviewService> logger)
{
    private static readonly string[] ApproveKeywords =
        ["aprobar", "aprobado", "ok para publicar", "publicar", "publicalo", "publÃ­quenlo", "publiquenlo"];

    private static readonly string[] RejectKeywords =
        ["rechazar", "rechazado", "descartar", "no publicar", "no postear", "cancelar publicacion", "cancelar publicaciÃ³n"];

    private sealed record FeedbackHistoryEntry(
        string From,
        string Action,
        string RevisionTarget,
        string Body,
        DateTimeOffset ReceivedAt);

    private sealed record ReviewerMemoryFact(
        string Body,
        string RevisionTarget,
        string Topic,
        DateTimeOffset SeenAt);

    private sealed record ReviewerMemoryRule(
        string Body,
        string RevisionTarget,
        string LastTopic,
        DateTimeOffset LastSeenAt,
        int SeenCount);

    private readonly string _publicBaseUrl =
        (configuration["PublicBaseUrl"] ?? "https://ia.novitsoftware.com").TrimEnd('/');

    public IReadOnlyList<string> GetReviewerList() => nurturingOptions.Value.GetReviewerList();

    public string CreateReviewToken() => Guid.NewGuid().ToString("N")[..10];

    public static string NormalizeReviewStage(string? reviewStage) =>
        string.Equals(reviewStage, CommunityReviewStage.PreMedia, StringComparison.OrdinalIgnoreCase)
            ? CommunityReviewStage.PreMedia
            : CommunityReviewStage.Final;

    public string BuildReviewThreadKey(CommunityPublicationEntity draft) => $"{draft.ReviewToken} v{draft.Version}";

    public string BuildReviewSubject(CommunityPublicationEntity draft) =>
        $"[REVISIÃ“N CM {draft.ReviewToken} v{draft.Version}] {draft.Topic}";

    public async Task<string> BuildReviewerMemoryAsync(CancellationToken ct = default)
    {
        var publications = await db.CommunityPublications
            .AsNoTracking()
            .Where(p => p.ReviewerFeedbackHistoryJson != "[]" || !string.IsNullOrWhiteSpace(p.LastReviewerFeedback))
            .OrderByDescending(p => p.UpdatedAt)
            .Select(p => new CommunityPublicationEntity
            {
                Topic = p.Topic,
                LastReviewerFeedback = p.LastReviewerFeedback,
                ReviewerFeedbackHistoryJson = p.ReviewerFeedbackHistoryJson,
                LastRevisionTarget = p.LastRevisionTarget,
                UpdatedAt = p.UpdatedAt,
            })
            .ToListAsync(ct);

        return BuildReviewerMemory(publications);
    }

    internal static string BuildReviewerMemory(IEnumerable<CommunityPublicationEntity> publications, int maxEntries = 50)
    {
        var learnedRules = publications
            .SelectMany(ExtractReviewerMemoryFacts)
            .GroupBy(
                fact => $"{NormalizeMemoryKey(fact.Body)}::{NormalizeRevisionTarget(fact.RevisionTarget)}",
                StringComparer.Ordinal)
            .Select(group =>
            {
                var latest = group
                    .OrderByDescending(fact => fact.SeenAt)
                    .First();

                return new ReviewerMemoryRule(
                    latest.Body,
                    latest.RevisionTarget,
                    latest.Topic,
                    latest.SeenAt,
                    group.Count());
            })
            .OrderByDescending(rule => rule.SeenCount)
            .ThenByDescending(rule => rule.LastSeenAt)
            .ThenBy(rule => rule.Body, StringComparer.OrdinalIgnoreCase)
            .Take(maxEntries)
            .ToList();

        if (learnedRules.Count == 0)
            return string.Empty;

        return string.Join("\n", learnedRules.Select(rule =>
            rule.SeenCount > 1
                ? $"- Regla aprendida: {rule.Body} (target: {rule.RevisionTarget}, visto {rule.SeenCount} veces, ultimo tema: {rule.LastTopic})."
                : $"- Regla aprendida: {rule.Body} (target: {rule.RevisionTarget}, ultimo tema: {rule.LastTopic})."));
    }

    public async Task SendDraftForReviewAsync(CommunityPublicationEntity draft, CancellationToken ct = default)
    {
        draft.ReviewSubject = BuildReviewSubject(draft);
        var reviewers = GetReviewerList();
        if (!mailService.IsConfigured || reviewers.Count == 0)
        {
            logger.LogWarning("Community draft {DraftId} could not be sent for review because mail/reviewers are not configured", draft.Id);
            return;
        }

        var html = BuildReviewEmailHtml(draft);
        await mailService.SendBulkEmailAsync(reviewers, draft.ReviewSubject, html, isHtml: true, ct: ct);
    }

    public string BuildReviewEmailHtml(CommunityPublicationEntity draft)
    {
        var hashtags = ParseStringArray(draft.HashtagsJson);
        var mediaUrls = ExtractMediaUrls(draft.DesignJson);
        var contentTypeLabel = draft.ContentType.Replace("_", " ", StringComparison.OrdinalIgnoreCase);
        var reviewStage = NormalizeReviewStage(draft.ReviewStage);
        var stageLabel = reviewStage == CommunityReviewStage.PreMedia
            ? "AprobaciÃ³n previa a multimedia"
            : "AprobaciÃ³n final";
        var approveLabel = reviewStage == CommunityReviewStage.PreMedia
            ? "Aprobar y generar multimedia"
            : "Aprobar y publicar";
        var approveUrl = BuildReviewActionUrl(_publicBaseUrl, draft.ReviewToken, "approve");
        var rejectUrl = BuildReviewActionUrl(_publicBaseUrl, draft.ReviewToken, "reject");
        var visualPlanHtml = BuildVisualPlanHtml(draft.DesignJson, draft.ContentType);

        var body = new StringBuilder();
        body.AppendLine("<div style=\"background:#f7f4ea;padding:16px 18px;border-left:4px solid #b6892d;margin-bottom:20px;color:#3d3529;font-size:14px;\">");
        body.AppendLine("<p style=\"margin:0 0 10px 0;\"><b>RevisiÃ³n de publicaciÃ³n social</b></p>");
        body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><b>Etapa:</b> {WebUtility.HtmlEncode(stageLabel)}</p>");
        body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><b>Tema:</b> {WebUtility.HtmlEncode(draft.Topic)}</p>");
        body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><b>Enfoque:</b> {WebUtility.HtmlEncode(draft.Angle)}</p>");
        body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><b>Objetivo:</b> {WebUtility.HtmlEncode(draft.Objective)}</p>");
        body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><b>Tipo:</b> {WebUtility.HtmlEncode(contentTypeLabel)}</p>");
        if (draft.ContentType.Equals("video_post", StringComparison.OrdinalIgnoreCase))
            body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><b>DuraciÃ³n:</b> {draft.VideoDurationSeconds} segundos</p>");

        if (reviewStage == CommunityReviewStage.PreMedia)
            body.AppendLine("<p style=\"margin:12px 0 0 0;color:#5b5247;\">Esta es la validaciÃ³n previa al gasto fuerte: todavÃ­a no se generaron imÃ¡genes o videos finales. AcÃ¡ se aprueban el copy y la direcciÃ³n visual detallada.</p>");
        else
            body.AppendLine("<p style=\"margin:12px 0 0 0;color:#5b5247;\">Esta es la aprobaciÃ³n final antes de publicaciÃ³n. Ya incluye la multimedia generada lista para revisar.</p>");

        body.AppendLine("<p style=\"margin:14px 0 8px 0;\"><b>Copy propuesto:</b></p>");
        body.AppendLine($"<div style=\"white-space:pre-wrap;background:#fff;padding:12px;border:1px solid #ddd;border-radius:8px;\">{WebUtility.HtmlEncode(draft.Caption)}</div>");

        if (hashtags.Count > 0)
            body.AppendLine($"<p style=\"margin:12px 0 0 0;\"><b>Hashtags:</b> {WebUtility.HtmlEncode(string.Join(' ', hashtags.Select(tag => $"#{tag}")))}</p>");

        if (!string.IsNullOrWhiteSpace(visualPlanHtml))
        {
            body.AppendLine("<p style=\"margin:14px 0 8px 0;\"><b>Plan visual propuesto:</b></p>");
            body.AppendLine(visualPlanHtml);
        }

        if (reviewStage == CommunityReviewStage.Final && mediaUrls.Count > 0)
        {
            body.AppendLine("<p style=\"margin:14px 0 8px 0;\"><b>Preview media:</b></p>");
            foreach (var mediaUrl in mediaUrls)
            {
                body.AppendLine($"<p style=\"margin:0 0 8px 0;\"><a href=\"{WebUtility.HtmlEncode(mediaUrl)}\">{WebUtility.HtmlEncode(mediaUrl)}</a></p>");
                if (draft.ContentType.Equals("image_post", StringComparison.OrdinalIgnoreCase))
                    body.AppendLine($"<p style=\"margin:0 0 12px 0;\"><img src=\"{WebUtility.HtmlEncode(mediaUrl)}\" style=\"max-width:100%;border-radius:8px;border:1px solid #ddd;\" /></p>");
            }
        }

            body.AppendLine("<p style=\"margin:16px 0 8px 0;\"><b>Acciones rÃ¡pidas:</b></p>");
            body.AppendLine("<div style=\"margin:0 0 14px 0;display:flex;gap:12px;flex-wrap:wrap;\">");
            body.AppendLine($"<a href=\"{WebUtility.HtmlEncode(approveUrl)}\" style=\"display:inline-block;background:#1f7a4d;color:#fff;text-decoration:none;padding:10px 16px;border-radius:999px;font-weight:700;\">{WebUtility.HtmlEncode(approveLabel)}</a>");
            body.AppendLine($"<a href=\"{WebUtility.HtmlEncode(rejectUrl)}\" style=\"display:inline-block;background:#8f2d2d;color:#fff;text-decoration:none;padding:10px 16px;border-radius:999px;font-weight:700;\">Rechazar o pedir cambios</a>");
            body.AppendLine("</div>");
            body.AppendLine("<p style=\"margin:0 0 12px 0;color:#5b5247;\">Estos links evitan depender de que el bot lea una respuesta en el inbox para aprobar o rechazar.</p>");

        body.AppendLine("<p style=\"margin:16px 0 8px 0;\"><b>Acciones por mail:</b></p>");
        body.AppendLine("<ul style=\"padding-left:18px;margin:0;\">");
        body.AppendLine("<li>RespondÃ© con <b>APROBAR</b> para publicar.</li>");
        body.AppendLine("<li>RespondÃ© con <b>RECHAZAR</b> para descartar esta pieza.</li>");
        body.AppendLine("<li>Si querÃ©s cambios, respondÃ© con el feedback y, si podÃ©s, empezÃ¡ el mail con <b>TEXTO:</b>, <b>VIDEO:</b> o <b>TODO:</b>.</li>");
        body.AppendLine("</ul>");
        body.AppendLine("</div>");

        return NurturingContentRenderer.WrapInHtmlEmail(body.ToString());
    }

    public static string NormalizeFeedback(string body)
    {
        var stripped = NurturingWorkflowSupport.StripQuotedReply(body ?? string.Empty);
        return stripped.Trim();
    }

    public static bool IsApprovalRequest(string body)
    {
        var normalized = NormalizeFeedback(body).ToLowerInvariant();
        return !IsRejectRequest(normalized) && ApproveKeywords.Any(normalized.Contains);
    }

    public static bool IsRejectRequest(string body)
    {
        var normalized = NormalizeFeedback(body).ToLowerInvariant();
        return RejectKeywords.Any(normalized.Contains);
    }

    public static string DetectRevisionTarget(string body)
    {
        var normalized = NormalizeFeedback(body).ToLowerInvariant();

        if (normalized.StartsWith("video:") || normalized.StartsWith("imagen:") || normalized.StartsWith("diseÃ±o:"))
            return CommunityRevisionTarget.Designer;

        if (normalized.StartsWith("texto:") || normalized.StartsWith("copy:"))
            return CommunityRevisionTarget.Copywriter;

        if (normalized.StartsWith("todo:") || normalized.StartsWith("tema:") || normalized.StartsWith("estrategia:"))
            return CommunityRevisionTarget.All;

        var mentionsDesign = normalized.Contains("video") || normalized.Contains("reel") || normalized.Contains("duraciÃ³n") || normalized.Contains("duracion") || normalized.Contains("imagen") || normalized.Contains("visual") || normalized.Contains("diseÃ±o") || normalized.Contains("diseno");
        var mentionsCopy = normalized.Contains("texto") || normalized.Contains("copy") || normalized.Contains("caption") || normalized.Contains("gancho") || normalized.Contains("hashtag") || normalized.Contains("titulo") || normalized.Contains("tÃ­tulo");

        if (mentionsDesign && mentionsCopy)
            return CommunityRevisionTarget.All;
        if (mentionsDesign)
            return CommunityRevisionTarget.Designer;
        if (mentionsCopy)
            return CommunityRevisionTarget.Copywriter;

        return CommunityRevisionTarget.All;
    }

    public static string MergeRevisionTargets(IEnumerable<string> targets)
    {
        var distinct = targets
            .Where(target => !string.IsNullOrWhiteSpace(target))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToList();

        return distinct.Count == 1 ? distinct[0] : CommunityRevisionTarget.All;
    }

    internal static string BuildReviewActionUrl(string publicBaseUrl, string reviewToken, string action)
    {
        var safeBaseUrl = string.IsNullOrWhiteSpace(publicBaseUrl)
            ? "https://ia.novitsoftware.com"
            : publicBaseUrl.TrimEnd('/');

        return $"{safeBaseUrl}/api/community/review/{Uri.EscapeDataString(reviewToken)}/{Uri.EscapeDataString(action)}";
    }

    public static string AppendFeedbackHistoryJson(
        string? existingJson,
        IEnumerable<IncomingEmail> emails,
        string action,
        string revisionTarget)
    {
        var history = new List<FeedbackHistoryEntry>();
        if (!string.IsNullOrWhiteSpace(existingJson))
        {
            try
            {
                history = JsonSerializer.Deserialize<List<FeedbackHistoryEntry>>(existingJson) ?? [];
            }
            catch (JsonException)
            {
                history = [];
            }
        }

        history.AddRange(emails.Select(email => new FeedbackHistoryEntry(
            email.From,
            action,
            revisionTarget,
            NormalizeFeedback(email.Body),
            email.Date)));

        return JsonSerializer.Serialize(history);
    }

    private static IEnumerable<ReviewerMemoryFact> ExtractReviewerMemoryFacts(CommunityPublicationEntity publication)
    {
        var historyFacts = ParseFeedbackHistory(publication.ReviewerFeedbackHistoryJson)
            .Where(entry => string.Equals(entry.Action, CommunityPublicationStatus.PendingReview, StringComparison.OrdinalIgnoreCase))
            .Select(entry => new ReviewerMemoryFact(
                NormalizeFeedback(entry.Body),
                NormalizeRevisionTarget(entry.RevisionTarget),
                publication.Topic,
                entry.ReceivedAt))
            .Where(fact => IsUsefulReviewerMemory(fact.Body))
            .ToList();

        if (historyFacts.Count > 0)
            return historyFacts;

        var fallback = NormalizeFeedback(publication.LastReviewerFeedback);
        if (!IsUsefulReviewerMemory(fallback))
            return [];

        return
        [
            new ReviewerMemoryFact(
                fallback,
                NormalizeRevisionTarget(publication.LastRevisionTarget),
                publication.Topic,
                publication.UpdatedAt)
        ];
    }

    private static List<FeedbackHistoryEntry> ParseFeedbackHistory(string? json)
    {
        if (string.IsNullOrWhiteSpace(json))
            return [];

        try
        {
            return JsonSerializer.Deserialize<List<FeedbackHistoryEntry>>(json) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    private static bool IsUsefulReviewerMemory(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
            return false;

        var normalized = NormalizeFeedback(body);
        return !string.IsNullOrWhiteSpace(normalized) &&
               !IsApprovalRequest(normalized) &&
               !IsRejectRequest(normalized);
    }

    private static string NormalizeMemoryKey(string body) =>
        NormalizeFeedback(body).Trim().ToLowerInvariant();

    private static string NormalizeRevisionTarget(string? revisionTarget)
    {
        if (string.Equals(revisionTarget, CommunityRevisionTarget.Copywriter, StringComparison.OrdinalIgnoreCase))
            return CommunityRevisionTarget.Copywriter;

        if (string.Equals(revisionTarget, CommunityRevisionTarget.Designer, StringComparison.OrdinalIgnoreCase))
            return CommunityRevisionTarget.Designer;

        return CommunityRevisionTarget.All;
    }

    private static List<string> ParseStringArray(string json)
    {
        if (string.IsNullOrWhiteSpace(json))
            return [];

        try
        {
            return JsonSerializer.Deserialize<List<string>>(json) ?? [];
        }
        catch (JsonException)
        {
            return [];
        }
    }

    private static List<string> ExtractMediaUrls(string designJson)
    {
        if (string.IsNullOrWhiteSpace(designJson))
            return [];

        var urls = new List<string>();
        try
        {
            using var doc = JsonDocument.Parse(designJson);
            var root = doc.RootElement;

            if (root.TryGetProperty("images", out var images) && images.ValueKind == JsonValueKind.Array)
            {
                foreach (var image in images.EnumerateArray())
                {
                    if (image.TryGetProperty("url", out var imageUrl) && imageUrl.ValueKind == JsonValueKind.String)
                    {
                        var value = imageUrl.GetString();
                        if (!string.IsNullOrWhiteSpace(value))
                            urls.Add(value);
                    }
                }
            }

            if (root.TryGetProperty("video", out var video) && video.ValueKind == JsonValueKind.Object)
            {
                if (video.TryGetProperty("url", out var videoUrl) && videoUrl.ValueKind == JsonValueKind.String)
                {
                    var value = videoUrl.GetString();
                    if (!string.IsNullOrWhiteSpace(value))
                        urls.Add(value);
                }
            }
        }
        catch (JsonException)
        {
            return [];
        }

        return urls;
    }

    private static string BuildVisualPlanHtml(string designJson, string contentType)
    {
        if (string.IsNullOrWhiteSpace(designJson))
            return string.Empty;

        try
        {
            using var doc = JsonDocument.Parse(designJson);
            var root = doc.RootElement;

            if (string.Equals(contentType, "video_post", StringComparison.OrdinalIgnoreCase))
                return BuildVideoPlanHtml(root);

            return BuildImagePlanHtml(root);
        }
        catch (JsonException)
        {
            return string.Empty;
        }
    }

    private static string BuildImagePlanHtml(JsonElement root)
    {
        if (!root.TryGetProperty("images", out var images) || images.ValueKind != JsonValueKind.Array)
            return string.Empty;

        var items = new List<string>();
        var index = 0;
        foreach (var image in images.EnumerateArray())
        {
            index++;
            var slideNumber = image.TryGetProperty("slide_number", out var slide) && slide.TryGetInt32(out var parsedSlide)
                ? parsedSlide
                : index;
            var reviewSummary = GetFirstString(image, "review_summary", "plan_summary", "prompt");
            var visibleText = GetFirstString(image, "visible_text", "headline", "overlay_text");

            if (string.IsNullOrWhiteSpace(reviewSummary) && string.IsNullOrWhiteSpace(visibleText))
                continue;

            var details = new StringBuilder();
            details.Append($"<b>Slide {slideNumber}.</b> {WebUtility.HtmlEncode(reviewSummary)}");
            if (!string.IsNullOrWhiteSpace(visibleText))
                details.Append($"<br /><span style=\"color:#5b5247;\"><b>Texto visible esperado:</b> {WebUtility.HtmlEncode(visibleText)}</span>");

            items.Add($"<li style=\"margin:0 0 10px 0;\">{details}</li>");
        }

        if (items.Count == 0)
            return string.Empty;

        return $"<ol style=\"margin:0;padding-left:18px;\">{string.Join(string.Empty, items)}</ol>";
    }

    private static string BuildVideoPlanHtml(JsonElement root)
    {
        if (!root.TryGetProperty("video", out var video) || video.ValueKind != JsonValueKind.Object)
            return string.Empty;

        var body = new StringBuilder();
        var reviewSummary = GetFirstString(video, "review_summary", "plan_summary", "prompt");
        var avatarScript = GetFirstString(video, "avatar_script", "voiceover_script", "voiceover_summary");

        if (!string.IsNullOrWhiteSpace(reviewSummary))
            body.AppendLine($"<p style=\"margin:0 0 8px 0;\">{WebUtility.HtmlEncode(reviewSummary)}</p>");

        if (!string.IsNullOrWhiteSpace(avatarScript))
            body.AppendLine($"<div style=\"white-space:pre-wrap;background:#fff;padding:12px;border:1px solid #ddd;border-radius:8px;margin:0 0 12px 0;\"><b>LocuciÃ³n / guion:</b><br />{WebUtility.HtmlEncode(avatarScript)}</div>");

        if (video.TryGetProperty("supporting_clips", out var clips) && clips.ValueKind == JsonValueKind.Array)
        {
            var items = new List<string>();
            foreach (var clip in clips.EnumerateArray())
            {
                var summary = GetFirstString(clip, "review_summary", "purpose", "prompt");
                if (string.IsNullOrWhiteSpace(summary))
                    continue;

                var timing = new List<string>();
                if (clip.TryGetProperty("start_second", out var startSecond) && startSecond.ValueKind == JsonValueKind.Number)
                    timing.Add($"entra en {startSecond.GetDouble():0.#}s");
                if (clip.TryGetProperty("duration_seconds", out var durationSeconds) && durationSeconds.ValueKind == JsonValueKind.Number)
                    timing.Add($"duraciÃ³n {durationSeconds.GetDouble():0.#}s");
                var transition = GetFirstString(clip, "transition");
                if (!string.IsNullOrWhiteSpace(transition))
                    timing.Add($"transiciÃ³n {transition}");

                var timingSuffix = timing.Count > 0
                    ? $" <span style=\"color:#5b5247;\">({WebUtility.HtmlEncode(string.Join(", ", timing))})</span>"
                    : string.Empty;

                items.Add($"<li style=\"margin:0 0 10px 0;\">{WebUtility.HtmlEncode(summary)}{timingSuffix}</li>");
            }

            if (items.Count > 0)
            {
                body.AppendLine("<p style=\"margin:0 0 8px 0;\"><b>Clips / escenas de apoyo:</b></p>");
                body.AppendLine($"<ul style=\"margin:0;padding-left:18px;\">{string.Join(string.Empty, items)}</ul>");
            }
        }

        return body.ToString();
    }

    private static string GetFirstString(JsonElement element, params string[] propertyNames)
    {
        foreach (var propertyName in propertyNames)
        {
            if (!element.TryGetProperty(propertyName, out var value) || value.ValueKind != JsonValueKind.String)
                continue;

            var text = value.GetString();
            if (!string.IsNullOrWhiteSpace(text))
                return text.Trim();
        }

        return string.Empty;
    }
}
