using System.Net;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public sealed class PipedriveService : IPipedriveService
{
    private readonly PipedriveOptions _options;
    private readonly GoogleOptions _googleOptions;
    private readonly HttpClient _http;
    private readonly ILogger<PipedriveService> _logger;

    /// <summary>Cached pipeline stage IDs keyed by stage name. Thread-safe for concurrent access.</summary>
    private volatile Dictionary<string, int>? _stageCache;

    /// <summary>Cached Google OAuth2 access token with expiration.</summary>
    private string? _googleAccessToken;
    private DateTime _googleTokenExpiry = DateTime.MinValue;

    public PipedriveService(IOptions<PipedriveOptions> options, IOptions<GoogleOptions> googleOptions, HttpClient http, ILogger<PipedriveService> logger)
    {
        _options = options.Value;
        _googleOptions = googleOptions.Value;
        _http = http;
        _logger = logger;
    }

    public bool IsConfigured => _options.IsConfigured;

    public async Task<string?> CreateLeadAsync(string name, string email, string message, CancellationToken ct = default)
    {
        if (!IsConfigured) return null;

        // Create person first
        var personId = await FindOrCreatePersonAsync(email, ct);
        if (personId is null) return null;

        // Create deal
        var dealBody = new
        {
            title = $"Web Lead — {name}",
            person_id = int.Parse(personId),
            status = "open"
        };

        var url = $"{_options.PipedriveBaseUrl}/api/v1/deals?api_token={_options.PipedriveKey}";
        var response = await _http.PostAsync(url,
            new StringContent(JsonSerializer.Serialize(dealBody), Encoding.UTF8, "application/json"), ct);

        if (!response.IsSuccessStatusCode) return null;

        using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        return doc.RootElement.GetProperty("data").GetProperty("id").ToString();
    }

    public async Task<string?> FindOrCreatePersonAsync(string email, CancellationToken ct = default)
    {
        if (!IsConfigured) return null;

        // Search for existing person
        var searchUrl = $"{_options.PipedriveBaseUrl}/api/v1/persons/search?term={Uri.EscapeDataString(email)}&fields=email&api_token={_options.PipedriveKey}";
        var searchResponse = await _http.GetAsync(searchUrl, ct);

        if (searchResponse.IsSuccessStatusCode)
        {
            using var searchDoc = await JsonDocument.ParseAsync(await searchResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var items = searchDoc.RootElement.GetProperty("data").GetProperty("items");
            if (items.GetArrayLength() > 0)
            {
                return items[0].GetProperty("item").GetProperty("id").ToString();
            }
        }

        // Create new person
        var personBody = new
        {
            name = email.Split('@')[0],
            email = new[] { new { value = email, primary = true } }
        };

        var createUrl = $"{_options.PipedriveBaseUrl}/api/v1/persons?api_token={_options.PipedriveKey}";
        var createResponse = await _http.PostAsync(createUrl,
            new StringContent(JsonSerializer.Serialize(personBody), Encoding.UTF8, "application/json"), ct);

        if (!createResponse.IsSuccessStatusCode) return null;

        using var createDoc = await JsonDocument.ParseAsync(await createResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        return createDoc.RootElement.GetProperty("data").GetProperty("id").ToString();
    }

    // ── Create deal from booking ────────────────────────────────────

    public async Task<string?> CreateDealFromBookingAsync(
        string attendeeName, string attendeeEmail, string? company,
        string meetingType, string bookingUid, string? meetingUrl,
        string? conversationSummary, CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            _logger.LogWarning("Pipedrive is not configured; skipping deal creation");
            return null;
        }

        try
        {
            // 1. Find or create person (with proper name)
            var personId = await FindOrCreatePersonWithNameAsync(attendeeName, attendeeEmail, ct);

            // 2. Find or create organization (if company is known)
            int? orgId = null;
            if (!string.IsNullOrWhiteSpace(company))
            {
                orgId = await FindOrCreateOrganizationAsync(company, ct);
                // Link person to org if we got both
                if (personId is not null && orgId is not null)
                    await LinkPersonToOrganizationAsync(int.Parse(personId), orgId.Value, ct);
            }

            // 3. Create deal in the "R1 agendada" stage if available, otherwise default
            var dealTitle = $"Novit AI — {attendeeName}" +
                            (string.IsNullOrWhiteSpace(company) ? "" : $" ({company})");

            var dealPayload = new Dictionary<string, object>
            {
                ["title"] = dealTitle,
                ["status"] = "open"
            };
            if (personId is not null) dealPayload["person_id"] = int.Parse(personId);
            if (orgId is not null) dealPayload["org_id"] = orgId.Value;

            // Try to place the deal in the "R1 agendada" stage
            var stageId = await GetStageIdByNameAsync("R1 agendada", ct);
            if (stageId is not null)
            {
                dealPayload["stage_id"] = stageId.Value;
            }

            var dealId = await PostAndGetIdAsync("/api/v1/deals", dealPayload, ct);
            if (dealId is null)
            {
                _logger.LogWarning("Failed to create Pipedrive deal for {Email}", attendeeEmail);
                return null;
            }

            // 4. Add note with conversation summary + booking info
            var noteLines = new List<string>
            {
                $"<b>Reunión agendada vía Novit AI</b>",
                $"<b>Tipo:</b> {meetingType}",
                $"<b>Booking UID:</b> {bookingUid}"
            };
            if (!string.IsNullOrWhiteSpace(meetingUrl))
                noteLines.Add($"<b>Link:</b> <a href=\"{meetingUrl}\">{meetingUrl}</a>");
            if (!string.IsNullOrWhiteSpace(conversationSummary))
            {
                noteLines.Add("");
                noteLines.Add("<b>Resumen de la conversación:</b>");
                noteLines.Add(conversationSummary.Replace("\n", "<br>"));
            }

            var notePayload = new Dictionary<string, object>
            {
                ["deal_id"] = int.Parse(dealId),
                ["content"] = string.Join("<br>", noteLines),
                ["pinned_to_deal_flag"] = 1
            };
            await PostAsync("/api/v1/notes", notePayload, ct);

            _logger.LogInformation("Pipedrive deal {DealId} created for booking {BookingUid} in stage '{Stage}'",
                dealId, bookingUid, stageId is not null ? "R1 agendada" : "default");
            return dealId;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error creating Pipedrive deal for booking {BookingUid}", bookingUid);
            return null;
        }
    }

    // ── Nurturing: get deals in "Nurturing Automático" stage ─────────

    public async Task<List<PipedriveDealContact>> GetNurturingDealContactsAsync(CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            _logger.LogWarning("Pipedrive not configured — cannot fetch nurturing deals");
            return [];
        }

        var stageId = await GetStageIdByNameAsync("Nurturing Automático", ct);
        if (stageId is null)
        {
            _logger.LogWarning("Pipeline stage 'Nurturing Automático' not found in Pipedrive");
            return [];
        }

        var results = new List<PipedriveDealContact>();
        var start = 0;
        const int limit = 100;

        while (true)
        {
            var url = $"{BaseUrl}/api/v1/deals?stage_id={stageId.Value}&status=all_not_deleted&start={start}&limit={limit}&api_token={_options.PipedriveKey}";
            var response = await _http.GetAsync(url, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("Failed to fetch deals from Pipedrive stage {StageId}: {Status}",
                    stageId.Value, response.StatusCode);
                break;
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var data = doc.RootElement.GetProperty("data");

            if (data.ValueKind != JsonValueKind.Array || data.GetArrayLength() == 0)
                break;

            foreach (var deal in data.EnumerateArray())
            {
                var dealId = deal.GetProperty("id").GetInt32();
                var dealTitle = deal.GetProperty("title").GetString() ?? "";

                // Extract organization name from deal's org_id
                string? orgName = null;
                if (deal.TryGetProperty("org_id", out var orgIdProp) &&
                    orgIdProp.ValueKind == JsonValueKind.Object &&
                    orgIdProp.TryGetProperty("name", out var orgNameProp))
                {
                    orgName = orgNameProp.GetString();
                }

                // Extract person email from the deal's person_id
                if (deal.TryGetProperty("person_id", out var personIdProp) &&
                    personIdProp.ValueKind == JsonValueKind.Object)
                {
                    var emails = ExtractPersonEmails(personIdProp);
                    var contactName = personIdProp.TryGetProperty("name", out var nameProp)
                        ? nameProp.GetString() : null;

                    foreach (var email in emails)
                    {
                        results.Add(new PipedriveDealContact(dealId, dealTitle, email, contactName, orgName));
                    }
                }
                else
                {
                    // Person not embedded — fetch it separately
                    var personEmails = await GetPersonEmailsFromDealAsync(deal, ct);
                    foreach (var (email, name) in personEmails)
                    {
                        results.Add(new PipedriveDealContact(dealId, dealTitle, email, name, orgName));
                    }
                }
            }

            // Check pagination
            if (doc.RootElement.TryGetProperty("additional_data", out var additional) &&
                additional.TryGetProperty("pagination", out var pagination) &&
                pagination.TryGetProperty("more_items_in_collection", out var moreItems) &&
                moreItems.GetBoolean())
            {
                start += limit;
            }
            else
            {
                break;
            }
        }

        _logger.LogInformation("Found {Count} nurturing deal contacts in Pipedrive", results.Count);
        return results;
    }

    public async Task<PipedriveDealContact?> GetDealContactAsync(int dealId, CancellationToken ct = default)
    {
        if (!IsConfigured) return null;

        var url = $"{BaseUrl}/api/v1/deals/{dealId}?api_token={_options.PipedriveKey}";
        var response = await _http.GetAsync(url, ct);

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogWarning("Failed to fetch deal {DealId} from Pipedrive: {Status}", dealId, response.StatusCode);
            return null;
        }

        using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        var deal = doc.RootElement.GetProperty("data");

        var dealTitle = deal.GetProperty("title").GetString() ?? "";

        string? orgName = null;
        if (deal.TryGetProperty("org_id", out var orgIdProp) &&
            orgIdProp.ValueKind == JsonValueKind.Object &&
            orgIdProp.TryGetProperty("name", out var orgNameProp))
        {
            orgName = orgNameProp.GetString();
        }

        if (deal.TryGetProperty("person_id", out var personIdProp) &&
            personIdProp.ValueKind == JsonValueKind.Object)
        {
            var emails = ExtractPersonEmails(personIdProp);
            var contactName = personIdProp.TryGetProperty("name", out var nameProp)
                ? nameProp.GetString() : null;

            if (emails.Count > 0)
                return new PipedriveDealContact(dealId, dealTitle, emails[0], contactName, orgName);
        }
        else
        {
            var personEmails = await GetPersonEmailsFromDealAsync(deal, ct);
            if (personEmails.Count > 0)
                return new PipedriveDealContact(dealId, dealTitle, personEmails[0].Email, personEmails[0].Name, orgName);
        }

        _logger.LogWarning("Deal {DealId} has no contact email in Pipedrive", dealId);
        return null;
    }

    public async Task AddNoteToDealAsync(int dealId, string noteContent, CancellationToken ct = default)
    {
        if (!IsConfigured) return;

        var payload = new Dictionary<string, object>
        {
            ["deal_id"] = dealId,
            ["content"] = noteContent
        };
        await PostAsync("/api/v1/notes", payload, ct);
        _logger.LogInformation("Added note to Pipedrive deal {DealId}", dealId);
    }

    public async Task<List<string>> GetDealNotesAsync(int dealId, CancellationToken ct = default)
    {
        if (!IsConfigured) return [];

        try
        {
            var url = $"{BaseUrl}/api/v1/deals/{dealId}/notes?sort=add_time DESC&start=0&limit=10&api_token={_options.PipedriveKey}";
            var response = await _http.GetAsync(url, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("Failed to fetch notes for deal {DealId}: {Status}", dealId, response.StatusCode);
                return [];
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var data = doc.RootElement.GetProperty("data");

            if (data.ValueKind != JsonValueKind.Array)
                return [];

            var notes = new List<string>();
            foreach (var note in data.EnumerateArray())
            {
                var content = note.TryGetProperty("content", out var c) ? c.GetString() : null;
                if (string.IsNullOrWhiteSpace(content)) continue;

                var noteDatePrefix = "[Nota sin fecha]";
                if (note.TryGetProperty("add_time", out var addTimeProp) &&
                    DateTime.TryParse(addTimeProp.GetString(), out var addTime))
                {
                    noteDatePrefix = $"[Nota del {addTime:yyyy-MM-dd}]";
                }

                // Strip HTML tags to get plain text
                var plainText = System.Text.RegularExpressions.Regex.Replace(content, "<[^>]+>", " ");
                plainText = System.Text.RegularExpressions.Regex.Replace(plainText, @"\s+", " ").Trim();

                if (plainText.Length > 0)
                {
                    var trimmed = plainText.Length > 500 ? plainText[..500] + "..." : plainText;
                    notes.Add($"{noteDatePrefix} {trimmed}");
                }

                // Try to fetch Google Doc content if a link is found in the note
                var gdocContent = await TryFetchGoogleDocFromNoteAsync(content, ct);
                if (gdocContent is not null)
                    notes.Add($"{noteDatePrefix} [Minuta/documento adjunto]: {gdocContent}");
            }

            return notes;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error fetching notes for deal {DealId}", dealId);
            return [];
        }
    }

    public async Task<List<string>> GetDealPersonalizationContextAsync(int dealId, CancellationToken ct = default)
    {
        if (!IsConfigured) return [];

        var context = new List<string>();
        context.AddRange(await GetDealNotesAsync(dealId, ct));
        context.AddRange(await GetDealMailContextAsync(dealId, ct));
        return context;
    }

    private async Task<List<string>> GetDealMailContextAsync(int dealId, CancellationToken ct)
    {
        try
        {
            var url = $"{BaseUrl}/api/v1/deals/{dealId}/mailMessages?start=0&limit=5&api_token={_options.PipedriveKey}";
            var response = await _http.GetAsync(url, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogDebug("Failed to fetch mail messages for deal {DealId}: {Status}", dealId, response.StatusCode);
                return [];
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            if (!doc.RootElement.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Array)
                return [];

            var mails = new List<string>();
            foreach (var item in data.EnumerateArray())
            {
                var entry = await BuildMailContextEntryAsync(item, ct);
                if (!string.IsNullOrWhiteSpace(entry))
                    mails.Add(entry);
            }

            return mails;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Error fetching mail messages for deal {DealId}", dealId);
            return [];
        }
    }

    private async Task<string?> BuildMailContextEntryAsync(JsonElement mailMessage, CancellationToken ct)
    {
        var subject = mailMessage.TryGetProperty("subject", out var subjectProp)
            ? subjectProp.GetString()
            : null;

        var bodyPreview = FirstNonEmpty(
            TryGetString(mailMessage, "snippet"),
            TryGetString(mailMessage, "summary"),
            TryGetString(mailMessage, "body_preview"),
            TryGetString(mailMessage, "body"),
            TryGetString(mailMessage, "plain_text_body"));

        if (string.IsNullOrWhiteSpace(bodyPreview) &&
            mailMessage.TryGetProperty("id", out var idProp) &&
            idProp.TryGetInt32(out var mailMessageId))
        {
            bodyPreview = await TryGetMailMessageBodyAsync(mailMessageId, ct);
        }

        bodyPreview = SanitizePlainText(bodyPreview, 500);
        subject = SanitizePlainText(subject, 140);

        if (string.IsNullOrWhiteSpace(subject) && string.IsNullOrWhiteSpace(bodyPreview))
            return null;

        var datePrefix = BuildDatePrefix(mailMessage, "Mail");
        if (string.IsNullOrWhiteSpace(bodyPreview))
            return $"{datePrefix} Asunto: {subject}";

        if (string.IsNullOrWhiteSpace(subject))
            return $"{datePrefix} {bodyPreview}";

        return $"{datePrefix} Asunto: {subject}. {bodyPreview}";
    }

    private async Task<string?> TryGetMailMessageBodyAsync(int mailMessageId, CancellationToken ct)
    {
        try
        {
            var url = $"{BaseUrl}/api/v1/mailbox/mailMessages/{mailMessageId}?include_body=1&api_token={_options.PipedriveKey}";
            var response = await _http.GetAsync(url, ct);
            if (!response.IsSuccessStatusCode)
                return null;

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            if (!doc.RootElement.TryGetProperty("data", out var data) || data.ValueKind != JsonValueKind.Object)
                return null;

            return FirstNonEmpty(
                SanitizePlainText(TryGetString(data, "plain_text_body"), 700),
                SanitizePlainText(TryGetString(data, "body"), 700),
                SanitizePlainText(TryGetString(data, "snippet"), 700));
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Failed to fetch full mail body for mail message {MailMessageId}", mailMessageId);
            return null;
        }
    }

    private static string BuildDatePrefix(JsonElement item, string label)
    {
        foreach (var propertyName in new[] { "message_time", "sent_at", "add_time", "update_time" })
        {
            if (item.TryGetProperty(propertyName, out var dateProp) &&
                DateTime.TryParse(dateProp.GetString(), out var parsed))
            {
                return $"[{label} del {parsed:yyyy-MM-dd}]";
            }
        }

        return $"[{label} sin fecha]";
    }

    private static string? TryGetString(JsonElement item, string propertyName)
    {
        return item.TryGetProperty(propertyName, out var prop) && prop.ValueKind == JsonValueKind.String
            ? prop.GetString()
            : null;
    }

    private static string? FirstNonEmpty(params string?[] values)
    {
        return values.FirstOrDefault(value => !string.IsNullOrWhiteSpace(value));
    }

    private static string? SanitizePlainText(string? text, int maxLength)
    {
        if (string.IsNullOrWhiteSpace(text))
            return null;

        var plainText = System.Text.RegularExpressions.Regex.Replace(text, "<[^>]+>", " ");
        plainText = WebUtility.HtmlDecode(plainText);
        plainText = System.Text.RegularExpressions.Regex.Replace(plainText, @"\s+", " ").Trim();

        if (plainText.Length == 0)
            return null;

        return plainText.Length > maxLength ? plainText[..maxLength] + "..." : plainText;
    }

    /// <summary>
    /// Extracts a Google Docs link from a note and tries to fetch its plain-text content.
    /// Uses Google Drive API with OAuth2 (leav@'s refresh token) if configured.
    /// Returns null if no link found or doc is not accessible.
    /// </summary>
    private async Task<string?> TryFetchGoogleDocFromNoteAsync(string noteHtml, CancellationToken ct)
    {
        try
        {
            // Match Google Docs URLs: docs.google.com/document/d/{docId}
            var match = System.Text.RegularExpressions.Regex.Match(
                noteHtml, @"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)");

            if (!match.Success) return null;

            var docId = match.Groups[1].Value;

            // Use Google Drive API to export as plain text (works for native Docs and uploaded .docx)
            var accessToken = await GetGoogleAccessTokenAsync(ct);
            if (accessToken is null)
            {
                _logger.LogDebug("Google OAuth2 not configured — skipping Google Doc {DocId}", docId);
                return null;
            }

            var exportUrl = $"https://www.googleapis.com/drive/v3/files/{docId}/export?mimeType=text/plain";
            using var request = new HttpRequestMessage(HttpMethod.Get, exportUrl);
            request.Headers.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", accessToken);

            var response = await _http.SendAsync(request, ct);
            if (!response.IsSuccessStatusCode)
            {
                _logger.LogDebug("Google Doc {DocId} not accessible via Drive API (HTTP {Status})", docId, response.StatusCode);
                return null;
            }

            var text = await response.Content.ReadAsStringAsync(ct);
            text = System.Text.RegularExpressions.Regex.Replace(text, @"\s+", " ").Trim();

            if (text.Length < 20) return null; // Too short to be useful

            // Cap at 2000 chars — meeting minutes can be long
            var result = text.Length > 2000 ? text[..2000] + "..." : text;
            _logger.LogInformation("Fetched Google Doc content ({Length} chars) for deal note", result.Length);
            return result;
        }
        catch (Exception ex)
        {
            _logger.LogDebug(ex, "Failed to fetch Google Doc from note");
            return null;
        }
    }

    /// <summary>
    /// Gets a valid Google OAuth2 access token using the refresh token from config.
    /// Caches the token until it expires. Returns null if Google is not configured.
    /// </summary>
    private async Task<string?> GetGoogleAccessTokenAsync(CancellationToken ct)
    {
        if (!_googleOptions.IsConfigured) return null;

        // Return cached token if still valid (with 60s buffer)
        if (_googleAccessToken is not null && DateTime.UtcNow < _googleTokenExpiry.AddSeconds(-60))
            return _googleAccessToken;

        try
        {
            var tokenRequest = new FormUrlEncodedContent(new Dictionary<string, string>
            {
                ["client_id"] = _googleOptions.ClientId!,
                ["client_secret"] = _googleOptions.ClientSecret!,
                ["refresh_token"] = _googleOptions.RefreshToken!,
                ["grant_type"] = "refresh_token"
            });

            var response = await _http.PostAsync("https://oauth2.googleapis.com/token", tokenRequest, ct);
            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("Failed to refresh Google access token: {Status}", response.StatusCode);
                return null;
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            _googleAccessToken = doc.RootElement.GetProperty("access_token").GetString();
            var expiresIn = doc.RootElement.GetProperty("expires_in").GetInt32();
            _googleTokenExpiry = DateTime.UtcNow.AddSeconds(expiresIn);

            _logger.LogInformation("Google OAuth2 access token refreshed, expires in {Seconds}s", expiresIn);
            return _googleAccessToken;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Failed to get Google access token");
            return null;
        }
    }

    public async Task<bool> MoveDealToStageAsync(int dealId, string stageName, CancellationToken ct = default)
    {
        if (!IsConfigured) return false;

        var stageId = await GetStageIdByNameAsync(stageName, ct);
        if (stageId is null)
        {
            _logger.LogWarning("Pipeline stage '{StageName}' not found — cannot move deal {DealId}", stageName, dealId);
            return false;
        }

        var url = $"{BaseUrl}/api/v1/deals/{dealId}?api_token={_options.PipedriveKey}";
        var payload = new Dictionary<string, object> { ["stage_id"] = stageId.Value };
        using var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
        var response = await _http.PutAsync(url, content, ct);

        if (response.IsSuccessStatusCode)
        {
            _logger.LogInformation("Moved deal {DealId} to stage '{StageName}'", dealId, stageName);
            return true;
        }

        _logger.LogWarning("Failed to move deal {DealId} to stage '{StageName}': {Status}",
            dealId, stageName, response.StatusCode);
        return false;
    }

    public async Task<string?> CreateDealInStageAsync(
        string dealTitle, string attendeeName, string attendeeEmail, string? company,
        string stageName, string? note, CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            _logger.LogWarning("Pipedrive not configured — skipping deal creation in stage '{StageName}'", stageName);
            return null;
        }

        try
        {
            var personId = await FindOrCreatePersonWithNameAsync(attendeeName, attendeeEmail, ct);

            int? orgId = null;
            if (!string.IsNullOrWhiteSpace(company))
            {
                orgId = await FindOrCreateOrganizationAsync(company, ct);
                if (personId is not null && orgId is not null)
                    await LinkPersonToOrganizationAsync(int.Parse(personId), orgId.Value, ct);
            }

            var dealPayload = new Dictionary<string, object>
            {
                ["title"] = dealTitle,
                ["status"] = "open"
            };
            if (personId is not null) dealPayload["person_id"] = int.Parse(personId);
            if (orgId is not null) dealPayload["org_id"] = orgId.Value;

            var stageId = await GetStageIdByNameAsync(stageName, ct);
            if (stageId is not null)
                dealPayload["stage_id"] = stageId.Value;

            var dealId = await PostAndGetIdAsync("/api/v1/deals", dealPayload, ct);
            if (dealId is null) return null;

            if (!string.IsNullOrWhiteSpace(note))
            {
                await AddNoteToDealAsync(int.Parse(dealId), note, ct);
            }

            _logger.LogInformation("Created deal {DealId} in stage '{StageName}' for {Email}",
                dealId, stageName, attendeeEmail);
            return dealId;
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error creating deal in stage '{StageName}' for {Email}", stageName, attendeeEmail);
            return null;
        }
    }

    // ── Pipeline / Stage helpers ──────────────────────────────────────

    /// <summary>
    /// Finds a pipeline stage ID by its name. Caches all stages on first call.
    /// </summary>
    private async Task<int?> GetStageIdByNameAsync(string stageName, CancellationToken ct)
    {
        if (_stageCache is null)
        {
            _stageCache = await LoadAllStagesAsync(ct);
        }

        return _stageCache.TryGetValue(stageName, out var stageId) ? stageId : null;
    }

    /// <summary>
    /// Fetches all pipelines and stages from Pipedrive, returning a name→id map.
    /// </summary>
    private async Task<Dictionary<string, int>> LoadAllStagesAsync(CancellationToken ct)
    {
        var stages = new Dictionary<string, int>(StringComparer.OrdinalIgnoreCase);

        try
        {
            var url = $"{BaseUrl}/api/v1/stages?api_token={_options.PipedriveKey}";
            var response = await _http.GetAsync(url, ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("Failed to load Pipedrive stages: {Status}", response.StatusCode);
                return stages;
            }

            using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var data = doc.RootElement.GetProperty("data");

            if (data.ValueKind == JsonValueKind.Array)
            {
                foreach (var stage in data.EnumerateArray())
                {
                    var name = stage.GetProperty("name").GetString();
                    var id = stage.GetProperty("id").GetInt32();
                    if (!string.IsNullOrEmpty(name))
                    {
                        stages[name] = id;
                    }
                }
            }

            _logger.LogInformation("Loaded {Count} Pipedrive stages", stages.Count);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error loading Pipedrive stages");
        }

        return stages;
    }

    // ── Person email extraction ─────────────────────────────────────

    /// <summary>Extracts email addresses from an embedded person_id object in a deal.</summary>
    private static List<string> ExtractPersonEmails(JsonElement personIdObj)
    {
        var emails = new List<string>();

        if (personIdObj.TryGetProperty("email", out var emailArr) && emailArr.ValueKind == JsonValueKind.Array)
        {
            foreach (var emailObj in emailArr.EnumerateArray())
            {
                var value = emailObj.TryGetProperty("value", out var v) ? v.GetString() : null;
                if (!string.IsNullOrWhiteSpace(value))
                    emails.Add(value);
            }
        }

        return emails;
    }

    /// <summary>Fetches person emails from a deal that doesn't have them embedded.</summary>
    private async Task<List<(string Email, string? Name)>> GetPersonEmailsFromDealAsync(
        JsonElement deal, CancellationToken ct)
    {
        // Try to get person_id as a simple integer
        int? personId = null;
        if (deal.TryGetProperty("person_id", out var pidProp))
        {
            if (pidProp.ValueKind == JsonValueKind.Number)
                personId = pidProp.GetInt32();
            else if (pidProp.ValueKind == JsonValueKind.Object && pidProp.TryGetProperty("value", out var valProp))
                personId = valProp.GetInt32();
        }

        if (personId is null) return [];

        var url = $"{BaseUrl}/api/v1/persons/{personId.Value}?api_token={_options.PipedriveKey}";
        var response = await _http.GetAsync(url, ct);

        if (!response.IsSuccessStatusCode) return [];

        using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        var person = doc.RootElement.GetProperty("data");

        var name = person.TryGetProperty("name", out var nameProp) ? nameProp.GetString() : null;
        var results = new List<(string, string?)>();

        if (person.TryGetProperty("email", out var emailArr) && emailArr.ValueKind == JsonValueKind.Array)
        {
            foreach (var emailObj in emailArr.EnumerateArray())
            {
                var value = emailObj.TryGetProperty("value", out var v) ? v.GetString() : null;
                if (!string.IsNullOrWhiteSpace(value))
                    results.Add((value, name));
            }
        }

        return results;
    }

    // ── Private helpers ─────────────────────────────────────────────

    private async Task<string?> FindOrCreatePersonWithNameAsync(string name, string email, CancellationToken ct)
    {
        // Search existing
        var searchUrl = $"{BaseUrl}/api/v1/persons/search?term={Uri.EscapeDataString(email)}&fields=email&api_token={_options.PipedriveKey}";
        var searchResponse = await _http.GetAsync(searchUrl, ct);

        if (searchResponse.IsSuccessStatusCode)
        {
            using var doc = await JsonDocument.ParseAsync(await searchResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var data = doc.RootElement.GetProperty("data");
            if (data.ValueKind == JsonValueKind.Object && data.TryGetProperty("items", out var items) && items.GetArrayLength() > 0)
                return items[0].GetProperty("item").GetProperty("id").ToString();
        }

        // Create with proper name
        var payload = new Dictionary<string, object>
        {
            ["name"] = name,
            ["email"] = new[] { new { value = email, primary = true, label = "work" } }
        };
        return await PostAndGetIdAsync("/api/v1/persons", payload, ct);
    }

    private async Task<int?> FindOrCreateOrganizationAsync(string companyName, CancellationToken ct)
    {
        // Search existing
        var searchUrl = $"{BaseUrl}/api/v1/organizations/search?term={Uri.EscapeDataString(companyName)}&api_token={_options.PipedriveKey}";
        var searchResponse = await _http.GetAsync(searchUrl, ct);

        if (searchResponse.IsSuccessStatusCode)
        {
            using var doc = await JsonDocument.ParseAsync(await searchResponse.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
            var data = doc.RootElement.GetProperty("data");
            if (data.ValueKind == JsonValueKind.Object && data.TryGetProperty("items", out var items) && items.GetArrayLength() > 0)
            {
                var id = items[0].GetProperty("item").GetProperty("id");
                return id.ValueKind == JsonValueKind.Number ? id.GetInt32() : int.Parse(id.GetString()!);
            }
        }

        // Create
        var payload = new Dictionary<string, object> { ["name"] = companyName };
        var orgIdStr = await PostAndGetIdAsync("/api/v1/organizations", payload, ct);
        return orgIdStr is not null ? int.Parse(orgIdStr) : null;
    }

    private async Task LinkPersonToOrganizationAsync(int personId, int orgId, CancellationToken ct)
    {
        var url = $"{BaseUrl}/api/v1/persons/{personId}?api_token={_options.PipedriveKey}";
        var payload = new Dictionary<string, object> { ["org_id"] = orgId };
        using var content = new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
        await _http.PutAsync(url, content, ct);
    }

    private async Task<string?> PostAndGetIdAsync(string path, object payload, CancellationToken ct)
    {
        var url = $"{BaseUrl}{path}?api_token={_options.PipedriveKey}";
        var response = await _http.PostAsync(url,
            new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json"), ct);

        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            _logger.LogWarning("Pipedrive POST {Path} returned {Status}: {Body}", path, response.StatusCode, body);
            return null;
        }

        using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        return doc.RootElement.GetProperty("data").GetProperty("id").ToString();
    }

    private async Task PostAsync(string path, object payload, CancellationToken ct)
    {
        var url = $"{BaseUrl}{path}?api_token={_options.PipedriveKey}";
        var response = await _http.PostAsync(url,
            new StringContent(JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json"), ct);

        if (!response.IsSuccessStatusCode)
        {
            var body = await response.Content.ReadAsStringAsync(ct);
            _logger.LogWarning("Pipedrive POST {Path} returned {Status}: {Body}", path, response.StatusCode, body);
        }
    }

    private string BaseUrl => _options.PipedriveBaseUrl!.TrimEnd('/');
}
