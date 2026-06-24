using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Novit.Web.Api.Data;
using Novit.Web.Api.Data.Entities;
using Novit.Web.Api.Filters;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

/// <summary>
/// Internal API endpoints called by the Python agent service over the Docker network.
/// These expose .NET-owned capabilities (Pipedrive, Email, Database) that the agent needs.
/// Protected by the <c>X-Internal-Key</c> header via <see cref="RequireInternalKeyAttribute"/>.
/// 
/// NOTE: These endpoints are NOT exposed through Caddy — they are only reachable
/// from within the Docker network (http://backend:5000/api/internal/*).
/// </summary>
[ApiController]
[Route("api/internal")]
[RequireInternalKey]
public sealed class InternalController(
    INurturingMailService mailService,
    IPipedriveService pipedrive,
    NovitDbContext db,
    CommunityReviewService communityReviewService,
    IChatAIService chatAIService,
    IConversationStore conversationStore,
    ILogger<InternalController> logger) : ControllerBase
{
    private sealed record PublishedImageSlide(int SlideNumber, string Url, string Prompt);
    public sealed record DmReplyRequest(string Platform, string SenderId, string? SenderName, string Text, string? Locale = null);

    [HttpPost("chat/dm-reply")]
    public async Task<IActionResult> GenerateDmReply([FromBody] DmReplyRequest req, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(req.SenderId) || string.IsNullOrWhiteSpace(req.Text))
            return BadRequest(new { error = "sender_id and text are required." });

        var locale = NormalizeLocale(req.Locale);
        var conversationGuid = DeriveDeterministicConversationId($"dm:{req.Platform}:{req.SenderId}");
        var conversationId = conversationGuid.ToString("N");

        var conversation = await db.Conversations.FindAsync([conversationGuid], ct);
        if (conversation is null)
        {
            conversation = new ConversationEntity
            {
                Id = conversationGuid,
                Locale = locale,
                IpAddress = $"internal:{req.Platform}:{req.SenderId}",
            };

            db.Conversations.Add(conversation);
            await db.SaveChangesAsync(ct);
        }
        else if (!string.Equals(conversation.Locale, locale, StringComparison.OrdinalIgnoreCase))
        {
            conversation.Locale = locale;
            conversation.UpdatedAt = DateTimeOffset.UtcNow;
            await db.SaveChangesAsync(ct);
        }

        conversationStore.AddMessage(conversationId, "user", req.Text);
        var reply = await chatAIService.GetCompletionAsync(conversationId, req.Text, locale, ct);
        conversationStore.AddMessage(conversationId, "bot", reply);

        return Ok(new { reply, conversation_id = conversationId });
    }

    // ══════════════════════════════════════════════════════════
    //  NURTURING: Recipients
    // ══════════════════════════════════════════════════════════

    /// <summary>Get Pipedrive contacts in the nurturing stage.</summary>
    [HttpGet("nurturing/recipients")]
    public async Task<IActionResult> GetNurturingRecipients(CancellationToken ct)
    {
        if (!pipedrive.IsConfigured)
            return BadRequest(new { error = "Pipedrive is not configured." });

        try
        {
            var contacts = await pipedrive.GetNurturingDealContactsAsync(ct);
            var unique = contacts
                .Where(c => !string.IsNullOrWhiteSpace(c.ContactEmail))
                .GroupBy(c => c.ContactEmail, StringComparer.OrdinalIgnoreCase)
                .Select(g => g.First())
                .ToList();

            return Ok(new
            {
                recipients = unique.Select(c => new
                {
                    deal_id = c.DealId,
                    deal_title = c.DealTitle,
                    contact_name = c.ContactName,
                    first_name = NurturingWorkflowSupport.ExtractFirstName(c.ContactName) ?? string.Empty,
                    email = c.ContactEmail,
                    org_name = c.OrganizationName ?? string.Empty
                })
            });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to fetch nurturing recipients for agent");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    private static string NormalizeLocale(string? locale) =>
        locale is not null && locale.StartsWith("en", StringComparison.OrdinalIgnoreCase)
            ? "en-US"
            : "es-AR";

    private static Guid DeriveDeterministicConversationId(string seed)
    {
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(seed));
        return new Guid(hash[..16]);
    }

    // ══════════════════════════════════════════════════════════
    //  EMAIL: Send / Reply / Unanswered
    // ══════════════════════════════════════════════════════════

    public sealed record SendEmailRequest(string To, string Subject, string HtmlBody, string? FirstName = null, string? InReplyTo = null);
    public sealed record BulkEmailRequest(IReadOnlyList<string> Recipients, string Subject, string HtmlBody);
    public sealed record SendReplyRequest(string To, string Subject, string Body, string? InReplyTo = null, string? MessageId = null);

    /// <summary>Send a single email via SMTP.</summary>
    [HttpPost("email/send")]
    public async Task<IActionResult> SendEmail([FromBody] SendEmailRequest req, CancellationToken ct)
    {
        if (!mailService.IsConfigured)
            return BadRequest(new { error = "Mail service not configured." });

        try
        {
            await mailService.SendEmailAsync(req.To, req.Subject, req.HtmlBody, isHtml: true, ct: ct);
            return Ok(new { status = "sent" });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to send email to {To}", req.To);
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Send bulk email to multiple recipients.</summary>
    [HttpPost("email/bulk")]
    public async Task<IActionResult> SendBulkEmail([FromBody] BulkEmailRequest req, CancellationToken ct)
    {
        if (!mailService.IsConfigured)
            return BadRequest(new { error = "Mail service not configured." });

        try
        {
            await mailService.SendBulkEmailAsync(req.Recipients, req.Subject, req.HtmlBody, isHtml: true, ct: ct);
            return Ok(new { status = "sent", count = req.Recipients.Count });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to send bulk email");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Send a reply to an existing email thread.</summary>
    [HttpPost("email/reply")]
    public async Task<IActionResult> SendReply([FromBody] SendReplyRequest req, CancellationToken ct)
    {
        if (!mailService.IsConfigured)
            return BadRequest(new { error = "Mail service not configured." });

        try
        {
            await mailService.SendReplyAsync(req.To, req.Subject, req.Body, req.InReplyTo ?? "", ct: ct);
            return Ok(new { status = "sent" });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to send reply to {To}", req.To);
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Get unanswered email replies from the last N days.</summary>
    [HttpGet("email/unanswered")]
    public async Task<IActionResult> GetUnansweredReplies([FromQuery] int days = 30, CancellationToken ct = default)
    {
        if (!mailService.IsConfigured)
            return BadRequest(new { error = "Mail service not configured." });

        try
        {
            var replies = await mailService.GetUnansweredRepliesAsync(days, ct);
            return Ok(new
            {
                replies = replies.Select(r => new
                {
                    message_id = r.MessageId,
                    from_email = r.From,
                    subject = r.Subject,
                    body = r.Body,
                    date = r.Date,
                    in_reply_to = r.InReplyTo,
                    sender_name = r.From.Contains('@')
                        ? r.From.Split('@')[0].Replace('.', ' ').Replace('_', ' ')
                        : r.From
                })
            });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to fetch unanswered replies");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    // ══════════════════════════════════════════════════════════
    //  NEWSLETTER: DB operations
    // ══════════════════════════════════════════════════════════

    [HttpGet("community/reviewer-memory")]
    public async Task<IActionResult> GetCommunityReviewerMemory(CancellationToken ct)
    {
        var memory = await communityReviewService.BuildReviewerMemoryAsync(ct);
        return Ok(new { memory });
    }

    [HttpGet("community/publication-history")]
    public async Task<IActionResult> GetCommunityPublicationHistory([FromQuery] int limit = 8, CancellationToken ct = default)
    {
        limit = Math.Clamp(limit, 1, 10);

        var publications = await db.CommunityPublications
            .AsNoTracking()
            .OrderByDescending(p => p.PublishedAt ?? p.CreatedAt)
            .Take(limit)
            .Select(p => new
            {
                p.ContentType,
                p.Status,
                p.Topic,
                p.Angle,
                Timestamp = p.PublishedAt ?? p.CreatedAt,
            })
            .ToListAsync(ct);

        var history = publications
            .Select(p => $"{p.Timestamp:yyyy-MM-dd} | {p.ContentType} | {p.Status} | {p.Topic} | {p.Angle}")
            .ToList();

        return Ok(new { publications = history });
    }

    [HttpGet("community/published-image-references")]
    public async Task<IActionResult> GetRecentPublishedImageReferences([FromQuery] int limit = 2, CancellationToken ct = default)
    {
        limit = Math.Clamp(limit, 1, 4);

        var publishedPosts = await db.CommunityPublications
            .AsNoTracking()
            .Where(p => p.Status == CommunityPublicationStatus.Published && p.ContentType == "image_post")
            .OrderByDescending(p => p.PublishedAt ?? p.CreatedAt)
            .Take(Math.Max(limit * 3, 6))
            .ToListAsync(ct);

        var references = publishedPosts
            .Select(p => new
            {
                topic = p.Topic,
                angle = p.Angle,
                caption = p.Caption,
                published_at = p.PublishedAt ?? p.CreatedAt,
                style_notes = ExtractStyleNotes(p.DesignJson),
                slides = ExtractPublishedImageSlides(p.DesignJson)
                    .Select(slide => new
                    {
                        slide_number = slide.SlideNumber,
                        url = slide.Url,
                        prompt = slide.Prompt,
                    })
                    .ToList(),
            })
            .Where(reference => reference.slides.Count > 0)
            .Take(limit)
            .ToList();

        return Ok(new { references });
    }

    [HttpPost("community/drafts")]
    public async Task<IActionResult> SaveCommunityDraft([FromBody] CommunityDraftPayload req, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(req.ContentType) ||
            string.IsNullOrWhiteSpace(req.Topic) ||
            string.IsNullOrWhiteSpace(req.StrategyJson) ||
            string.IsNullOrWhiteSpace(req.CopyJson) ||
            string.IsNullOrWhiteSpace(req.DesignJson))
        {
            return BadRequest(new { error = "Missing required draft fields." });
        }

        var isSupportedContentType =
            string.Equals(req.ContentType, "image_post", StringComparison.OrdinalIgnoreCase) ||
            string.Equals(req.ContentType, "video_post", StringComparison.OrdinalIgnoreCase);

        if (!isSupportedContentType)
        {
            return BadRequest(new { error = "Only 'image_post' and 'video_post' community drafts are enabled right now." });
        }

        try
        {
            var draftStatus = string.Equals(req.DraftStatus, CommunityPublicationStatus.Denied, StringComparison.OrdinalIgnoreCase)
                ? CommunityPublicationStatus.Denied
                : CommunityPublicationStatus.PendingReview;
            var isDenied = draftStatus == CommunityPublicationStatus.Denied;
            var reviewStage = string.Equals(req.ReviewStage, CommunityReviewStage.PreMedia, StringComparison.OrdinalIgnoreCase)
                ? CommunityReviewStage.PreMedia
                : CommunityReviewStage.Final;

            var draft = new CommunityPublicationEntity
            {
                ContentType = req.ContentType,
                ReviewStage = reviewStage,
                Topic = req.Topic,
                Angle = req.Angle,
                Objective = req.Objective,
                Caption = req.Caption,
                AltText = req.AltText,
                HashtagsJson = System.Text.Json.JsonSerializer.Serialize(req.Hashtags),
                StrategyJson = req.StrategyJson,
                CopyJson = req.CopyJson,
                DesignJson = req.DesignJson,
                EvaluationJson = req.EvaluationJson,
                VideoDurationSeconds = req.VideoDurationSeconds,
                Status = draftStatus,
                Version = 1,
                LastError = req.FailureReason ?? string.Empty,
                RejectedAt = isDenied ? DateTimeOffset.UtcNow : null,
                UpdatedAt = DateTimeOffset.UtcNow,
            };

            db.CommunityPublications.Add(draft);
            await db.SaveChangesAsync(ct);

            if (isDenied)
            {
                return Ok(new
                {
                    status = CommunityPublicationStatus.Denied,
                    draft_id = draft.Id,
                    failure_reason = req.FailureReason,
                    retry_count = req.RetryCount,
                });
            }

            await communityReviewService.SendDraftForReviewAsync(draft, ct);
            await db.SaveChangesAsync(ct);

            return Ok(new
            {
                status = "queued",
                draft_id = draft.Id,
                review_token = draft.ReviewToken,
                review_subject = draft.ReviewSubject,
            });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to save community draft for review");
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Get the current newsletter for a given month.</summary>
    [HttpGet("nurturing/newsletter/{monthKey}")]
    public async Task<IActionResult> GetNewsletter(string monthKey, CancellationToken ct)
    {
        var newsletter = await db.NurturingEmails
            .FirstOrDefaultAsync(e => e.MonthKey == monthKey, ct);

        if (newsletter is null)
            return NotFound(new { error = $"No newsletter found for {monthKey}." });

        return Ok(new
        {
            month_key = newsletter.MonthKey,
            subject = newsletter.Subject,
            body = newsletter.Body,
            report_title = newsletter.ReportTitle,
            executive_summary = newsletter.ExecutiveSummary,
            artifact_json = newsletter.ArtifactJson,
            version = newsletter.Version,
            is_sent = newsletter.IsSent,
            is_on_hold = newsletter.IsOnHold,
            scheduled_send_date = newsletter.ScheduledSendDate,
            sent_at = newsletter.SentAt,
            created_at = newsletter.CreatedAt
        });
    }

    public sealed record SaveNewsletterRequest(
        string MonthKey, string Subject, string Body,
        DateTimeOffset? ScheduledSendDate = null,
        int Version = 1,
        string? ReportTitle = null,
        string? ExecutiveSummary = null,
        string? ArtifactJson = null);

    private static string ExtractStyleNotes(string designJson)
    {
        if (string.IsNullOrWhiteSpace(designJson))
            return string.Empty;

        try
        {
            using var doc = JsonDocument.Parse(designJson);
            var root = doc.RootElement;
            if (root.TryGetProperty("style_notes", out var styleNotes) && styleNotes.ValueKind == JsonValueKind.String)
                return styleNotes.GetString() ?? string.Empty;
        }
        catch (JsonException)
        {
            return string.Empty;
        }

        return string.Empty;
    }

    private static List<PublishedImageSlide> ExtractPublishedImageSlides(string designJson)
    {
        if (string.IsNullOrWhiteSpace(designJson))
            return [];

        var slides = new List<PublishedImageSlide>();
        try
        {
            using var doc = JsonDocument.Parse(designJson);
            var root = doc.RootElement;

            if (!root.TryGetProperty("images", out var images) || images.ValueKind != JsonValueKind.Array)
                return [];

            var slideNumber = 1;
            foreach (var image in images.EnumerateArray())
            {
                var url = image.TryGetProperty("url", out var imageUrl) && imageUrl.ValueKind == JsonValueKind.String
                    ? imageUrl.GetString() ?? string.Empty
                    : string.Empty;
                if (string.IsNullOrWhiteSpace(url))
                {
                    slideNumber++;
                    continue;
                }

                var prompt = image.TryGetProperty("prompt", out var imagePrompt) && imagePrompt.ValueKind == JsonValueKind.String
                    ? imagePrompt.GetString() ?? string.Empty
                    : string.Empty;

                slides.Add(new PublishedImageSlide(slideNumber, url, prompt));
                slideNumber++;
            }
        }
        catch (JsonException)
        {
            return [];
        }

        return slides;
    }

    /// <summary>Save or update a newsletter in the database.</summary>
    [HttpPost("nurturing/newsletter")]
    public async Task<IActionResult> SaveNewsletter([FromBody] SaveNewsletterRequest req, CancellationToken ct)
    {
        try
        {
            var existing = await db.NurturingEmails
                .FirstOrDefaultAsync(e => e.MonthKey == req.MonthKey, ct);

            if (existing is not null)
            {
                existing.Subject = req.Subject;
                existing.Body = req.Body;
                existing.ReportTitle = req.ReportTitle;
                existing.ExecutiveSummary = req.ExecutiveSummary;
                existing.ArtifactJson = req.ArtifactJson;
                existing.Version = req.Version > 0 ? req.Version : existing.Version + 1;
                if (req.ScheduledSendDate.HasValue)
                    existing.ScheduledSendDate = req.ScheduledSendDate.Value;
            }
            else
            {
                db.NurturingEmails.Add(new NurturingEmailEntity
                {
                    MonthKey = req.MonthKey,
                    Subject = req.Subject,
                    Body = req.Body,
                    ReportTitle = req.ReportTitle,
                    ExecutiveSummary = req.ExecutiveSummary,
                    ArtifactJson = req.ArtifactJson,
                    ScheduledSendDate = req.ScheduledSendDate ?? DateTimeOffset.UtcNow,
                    Version = req.Version,
                    IsSent = false
                });
            }

            await db.SaveChangesAsync(ct);
            return Ok(new { status = "saved", month_key = req.MonthKey });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to save newsletter for {MonthKey}", req.MonthKey);
            return StatusCode(500, new { error = ex.Message });
        }
    }

    /// <summary>Mark a newsletter as sent.</summary>
    [HttpPost("nurturing/newsletter/{monthKey}/mark-sent")]
    public async Task<IActionResult> MarkNewsletterSent(string monthKey, CancellationToken ct)
    {
        var newsletter = await db.NurturingEmails
            .FirstOrDefaultAsync(e => e.MonthKey == monthKey, ct);

        if (newsletter is null)
            return NotFound(new { error = $"No newsletter found for {monthKey}." });

        if (!newsletter.IsSent)
        {
            newsletter.IsSent = true;
            newsletter.SentAt = DateTimeOffset.UtcNow;
            await db.SaveChangesAsync(ct);
        }

        return Ok(new { status = "marked_sent", month_key = monthKey, already_sent = newsletter.IsSent && newsletter.SentAt.HasValue });
    }

    /// <summary>Get conclusions from the last N newsletters for contextual awareness.</summary>
    [HttpGet("nurturing/conclusions/last")]
    public async Task<IActionResult> GetLastConclusions([FromQuery] int count = 3, CancellationToken ct = default)
    {
        var newsletters = await db.NurturingEmails
            .Where(e => e.ArtifactJson != null)
            .OrderByDescending(e => e.CreatedAt)
            .Take(count)
            .Select(e => new {
                e.MonthKey,
                e.ReportTitle,
                e.ArtifactJson
            })
            .ToListAsync(ct);

        var result = newsletters.Select(n =>
        {
            string? conclusions = null;
            if (!string.IsNullOrWhiteSpace(n.ArtifactJson))
            {
                try
                {
                    using var doc = System.Text.Json.JsonDocument.Parse(n.ArtifactJson);
                    if (doc.RootElement.TryGetProperty("conclusions", out var c))
                        conclusions = c.GetString();
                }
                catch { }
            }

            return new
            {
                month_key = n.MonthKey,
                report_title = n.ReportTitle,
                conclusions = conclusions ?? ""
            };
        });

        return Ok(result);
    }

    // ══════════════════════════════════════════════════════════
    //  PIPEDRIVE: Deal notes & stage management
    // ══════════════════════════════════════════════════════════

    /// <summary>Get all notes for a Pipedrive deal.</summary>
    [HttpGet("pipedrive/deals/{dealId:int}/notes")]
    public async Task<IActionResult> GetDealNotes(int dealId, CancellationToken ct)
    {
        if (!pipedrive.IsConfigured)
            return BadRequest(new { error = "Pipedrive not configured." });

        try
        {
            var notes = await pipedrive.GetDealNotesAsync(dealId, ct);
            return Ok(new { deal_id = dealId, notes });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to fetch notes for deal {DealId}", dealId);
            return StatusCode(500, new { error = ex.Message });
        }
    }

    public sealed record AddNoteRequest(string Content);

    /// <summary>Add a note to a Pipedrive deal.</summary>
    [HttpPost("pipedrive/deals/{dealId:int}/notes")]
    public async Task<IActionResult> AddDealNote(int dealId, [FromBody] AddNoteRequest req, CancellationToken ct)
    {
        if (!pipedrive.IsConfigured)
            return BadRequest(new { error = "Pipedrive not configured." });

        try
        {
            await pipedrive.AddNoteToDealAsync(dealId, req.Content, ct);
            return Ok(new { status = "added", deal_id = dealId });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to add note to deal {DealId}", dealId);
            return StatusCode(500, new { error = ex.Message });
        }
    }

    public sealed record MoveDealRequest(string StageName);

    /// <summary>Move a Pipedrive deal to a different pipeline stage.</summary>
    [HttpPost("pipedrive/deals/{dealId:int}/move")]
    public async Task<IActionResult> MoveDeal(int dealId, [FromBody] MoveDealRequest req, CancellationToken ct)
    {
        if (!pipedrive.IsConfigured)
            return BadRequest(new { error = "Pipedrive not configured." });

        try
        {
            var success = await pipedrive.MoveDealToStageAsync(dealId, req.StageName, ct);
            return success
                ? Ok(new { status = "moved", deal_id = dealId, stage = req.StageName })
                : BadRequest(new { error = $"Failed to move deal {dealId} to stage '{req.StageName}'." });
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to move deal {DealId} to stage {Stage}", dealId, req.StageName);
            return StatusCode(500, new { error = ex.Message });
        }
    }
}
