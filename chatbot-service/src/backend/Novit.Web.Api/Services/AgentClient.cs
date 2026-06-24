using System.Net;
using System.Text.Json;
using System.Text.Json.Serialization;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

/// <summary>
/// Client for the internal Python agent service (http://agent:8000).
/// Used to delegate AI-intensive operations (newsletter generation, revision,
/// reply generation, personal closings) to the Python agent when NURTURING_V2_ENABLED.
/// Also used to forward incoming Meta webhook messages.
/// </summary>
public interface IAgentClient
{
    /// <summary>Whether the agent service is configured (base URL is set).</summary>
    bool IsConfigured { get; }

    /// <summary>Forward an incoming Meta/Instagram message to the Python agent for processing.</summary>
    Task<AgentReplyResult?> ForwardWebhookMessageAsync(
        string senderId,
        string text,
        string platform,
        string? messageId,
        CancellationToken ct = default,
        string? senderName = null,
        string? replyTargetId = null,
        string? replyTargetType = null,
        string? postContextId = null,
        string? postContextText = null);

    /// <summary>Generate a newsletter with AI and web search tools.</summary>
    Task<AgentNewsletterResult?> GenerateNewsletterAsync(CancellationToken ct = default);

    /// <summary>Revise a newsletter based on reviewer feedback.</summary>
    Task<AgentNewsletterResult?> ReviseNewsletterAsync(string currentSubject, string currentBody, string reviewerFeedback, CancellationToken ct = default);

    /// <summary>Generate a reply to a lead's newsletter response.</summary>
    Task<string?> GenerateReplyAsync(string originalSubject, string originalBody, string senderName, CancellationToken ct = default);

    /// <summary>Generate a personalized closing for a newsletter recipient.</summary>
    Task<string?> GenerateClosingAsync(string newsletterSubject, string? newsletterBody, string? firstName, string? orgName, IReadOnlyList<string> dealNotes, CancellationToken ct = default);

    /// <summary>Wrap HTML body in the full email template with signature.</summary>
    Task<string?> WrapEmailAsync(string htmlBody, string? firstName = null, string? personalClosing = null, CancellationToken ct = default);

    /// <summary>Get the current status of the Python agent.</summary>
    Task<AgentStatusResult?> GetStatusAsync(CancellationToken ct = default);
}

public sealed record AgentReplyResult(string? Reply);
public sealed record AgentNewsletterResult(
    string Subject,
    string Body,
    string? ReportTitle = null,
    string? ExecutiveSummary = null,
    string? ArtifactJson = null);
public sealed record AgentStatusResult(string State, string? LastRun, bool SchedulerActive, bool NurturingV2Enabled);

public sealed class AgentClient : IAgentClient
{
    private readonly HttpClient _http;
    private readonly IConfiguration _config;
    private readonly ILogger<AgentClient> _logger;

    private static readonly JsonSerializerOptions JsonOpts = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public AgentClient(HttpClient http, IConfiguration config, ILogger<AgentClient> logger)
    {
        _http = http;
        _config = config;

        // Base URL defaults to http://agent:8000 (Docker internal network)
        var baseUrl = config["AgentBaseUrl"] ?? "http://agent:8000";
        _http.BaseAddress = new Uri(baseUrl.TrimEnd('/') + "/");
        var agentTimeoutSeconds = config.GetValue<int?>("AgentRequestTimeoutSeconds") ?? 1800;
        if (agentTimeoutSeconds <= 0)
            agentTimeoutSeconds = 1800;

        _http.Timeout = TimeSpan.FromSeconds(agentTimeoutSeconds);

        // Set internal API key header
        var internalKey = config["INTERNAL_API_KEY"];
        if (!string.IsNullOrWhiteSpace(internalKey))
            _http.DefaultRequestHeaders.Add("X-Internal-Key", internalKey);

        _logger = logger;
    }

    public bool IsConfigured => _http.BaseAddress is not null;

    public async Task<AgentReplyResult?> ForwardWebhookMessageAsync(
        string senderId,
        string text,
        string platform,
        string? messageId,
        CancellationToken ct = default,
        string? senderName = null,
        string? replyTargetId = null,
        string? replyTargetType = null,
        string? postContextId = null,
        string? postContextText = null)
    {
        try
        {
            var response = await _http.PostAsJsonAsync("internal/webhook/message", new
            {
                sender_id = senderId,
                sender_name = senderName,
                text,
                platform,
                message_id = messageId,
                reply_target_id = replyTargetId,
                reply_target_type = replyTargetType,
                post_context_id = postContextId,
                post_context_text = postContextText
            }, JsonOpts, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("Agent webhook forward failed: {Status}", response.StatusCode);
                return null;
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            string? reply = null;
            if (doc.RootElement.TryGetProperty("reply", out var r))
            {
                if (r.ValueKind == JsonValueKind.String)
                    reply = r.GetString();
                else if (r.ValueKind == JsonValueKind.Object && r.TryGetProperty("text", out var replyText))
                    reply = replyText.GetString();
            }

            return new AgentReplyResult(reply);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to forward webhook message to agent");
            return null;
        }
    }

    public async Task<AgentNewsletterResult?> GenerateNewsletterAsync(CancellationToken ct = default)
    {
        try
        {
            _logger.LogInformation("Requesting newsletter generation from Python agent…");
            var response = await _http.PostAsync("internal/nurturing/generate-sync", null, ct);

            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(ct);
                _logger.LogWarning("Agent newsletter generation failed: {Status} — {Body}", response.StatusCode, body);
                return null;
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var subject = doc.RootElement.GetProperty("subject").GetString() ?? "";
            var htmlBody = doc.RootElement.GetProperty("body").GetString() ?? "";

            _logger.LogInformation("Newsletter generated by Python agent: {Subject}", subject);
            var reportTitle = doc.RootElement.TryGetProperty("report_title", out var reportTitleElement)
                ? reportTitleElement.GetString()
                : null;
            var executiveSummary = doc.RootElement.TryGetProperty("executive_summary", out var executiveSummaryElement)
                ? executiveSummaryElement.GetString()
                : null;
            var artifactJson = doc.RootElement.TryGetProperty("artifact_json", out var artifactJsonElement)
                ? artifactJsonElement.GetString()
                : null;

            return new AgentNewsletterResult(subject, htmlBody, reportTitle, executiveSummary, artifactJson);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to generate newsletter via agent");
            return null;
        }
    }

    public async Task<AgentNewsletterResult?> ReviseNewsletterAsync(
        string currentSubject, string currentBody, string reviewerFeedback, CancellationToken ct = default)
    {
        try
        {
            _logger.LogInformation("Requesting newsletter revision from Python agent…");
            var response = await _http.PostAsJsonAsync("internal/nurturing/revise", new
            {
                current_subject = currentSubject,
                current_body = currentBody,
                reviewer_feedback = reviewerFeedback
            }, JsonOpts, ct);

            if (!response.IsSuccessStatusCode)
            {
                var body = await response.Content.ReadAsStringAsync(ct);
                _logger.LogWarning("Agent newsletter revision failed: {Status} — {Body}", response.StatusCode, body);
                return null;
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var subject = doc.RootElement.GetProperty("subject").GetString() ?? "";
            var htmlBody = doc.RootElement.GetProperty("body").GetString() ?? "";

            var reportTitle = doc.RootElement.TryGetProperty("report_title", out var reportTitleElement)
                ? reportTitleElement.GetString()
                : null;
            var executiveSummary = doc.RootElement.TryGetProperty("executive_summary", out var executiveSummaryElement)
                ? executiveSummaryElement.GetString()
                : null;
            var artifactJson = doc.RootElement.TryGetProperty("artifact_json", out var artifactJsonElement)
                ? artifactJsonElement.GetString()
                : null;

            return new AgentNewsletterResult(subject, htmlBody, reportTitle, executiveSummary, artifactJson);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to revise newsletter via agent");
            return null;
        }
    }

    public async Task<string?> GenerateReplyAsync(
        string originalSubject, string originalBody, string senderName, CancellationToken ct = default)
    {
        try
        {
            var response = await _http.PostAsJsonAsync("internal/nurturing/reply", new
            {
                original_subject = originalSubject,
                original_body = originalBody,
                sender_name = senderName
            }, JsonOpts, ct);

            if (!response.IsSuccessStatusCode) return null;

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            return doc.RootElement.TryGetProperty("reply", out var r) ? r.GetString() : null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to generate reply via agent");
            return null;
        }
    }

    public async Task<string?> GenerateClosingAsync(
        string newsletterSubject, string? newsletterBody, string? firstName,
        string? orgName, IReadOnlyList<string> dealNotes, CancellationToken ct = default)
    {
        try
        {
            var response = await _http.PostAsJsonAsync("internal/nurturing/closing", new
            {
                newsletter_subject = newsletterSubject,
                newsletter_body = newsletterBody,
                first_name = firstName,
                org_name = orgName,
                deal_notes = dealNotes
            }, JsonOpts, ct);

            if (!response.IsSuccessStatusCode) return null;

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            return doc.RootElement.TryGetProperty("closing", out var c) ? c.GetString() : null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to generate closing via agent");
            return null;
        }
    }

    public async Task<string?> WrapEmailAsync(
        string htmlBody, string? firstName = null, string? personalClosing = null, CancellationToken ct = default)
    {
        try
        {
            var response = await _http.PostAsJsonAsync("internal/nurturing/wrap-email", new
            {
                html_body = htmlBody,
                first_name = firstName,
                personal_closing = personalClosing
            }, JsonOpts, ct);

            if (!response.IsSuccessStatusCode) return null;

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            return doc.RootElement.TryGetProperty("html", out var h) ? h.GetString() : null;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to wrap email via agent");
            return null;
        }
    }

    public async Task<AgentStatusResult?> GetStatusAsync(CancellationToken ct = default)
    {
        try
        {
            var response = await _http.GetAsync("internal/nurturing/status", ct);
            if (!response.IsSuccessStatusCode) return null;

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            return new AgentStatusResult(
                State: doc.RootElement.GetProperty("state").GetString() ?? "unknown",
                LastRun: doc.RootElement.TryGetProperty("last_run", out var lr) ? lr.GetString() : null,
                SchedulerActive: doc.RootElement.TryGetProperty("scheduler_active", out var sa) && sa.GetBoolean(),
                NurturingV2Enabled: doc.RootElement.TryGetProperty("nurturing_v2_enabled", out var nv) && nv.GetBoolean()
            );
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to get agent status");
            return null;
        }
    }
}
