using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Options;
using Npgsql;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

/// <summary>
/// Cal.com integration using the self-hosted web app endpoints:
/// - Slots: tRPC public procedure at /api/trpc/slots/getSchedule
/// - Bookings: web handler at /api/book/event (v1-style payload)
/// - Cancel/Reschedule: not available via public API in self-hosted;
///   the bot offers email coordination as fallback.
/// </summary>
public sealed class CalComService : ICalComService
{
    private readonly CalComOptions _options;
    private readonly HttpClient _http;
    private readonly ILogger<CalComService> _logger;

    /// <summary>Default meeting duration in minutes (used to compute end time for bookings).</summary>
    private const int DefaultDurationMinutes = 30;

    public CalComService(IOptions<CalComOptions> options, HttpClient http, ILogger<CalComService> logger)
    {
        _options = options.Value;
        _http = http;
        _logger = logger;

        if (_options.IsConfigured)
            _logger.LogInformation("Cal.com configured: BaseUrl={BaseUrl}, EventTypeIdDemo={Demo}, EventTypeIdDiscovery={Discovery}",
                _options.BaseUrl, _options.EventTypeIdDemo, _options.EventTypeIdDiscovery);
        else
            _logger.LogWarning("Cal.com is NOT configured. BaseUrl={BaseUrl}, ApiKey={HasKey}, Demo={Demo}, Discovery={Discovery}",
                _options.BaseUrl ?? "(null)",
                !string.IsNullOrWhiteSpace(_options.ApiKey),
                _options.EventTypeIdDemo,
                _options.EventTypeIdDiscovery);
    }

    public bool IsConfigured => _options.IsConfigured;

    // ── Slots (tRPC public procedure) ───────────────────────────────

    public async Task<CalComSlotsResult> GetAvailableSlotsAsync(
        string dateFrom, string dateTo, string meetingType, string timezone,
        CancellationToken ct = default)
    {
        if (!IsConfigured)
            return new CalComSlotsResult(false, [], "Cal.com is not configured.");

        var eventTypeId = ResolveEventTypeId(meetingType);
        if (eventTypeId is null)
            return new CalComSlotsResult(false, [], $"Unknown meeting type: {meetingType}");

        try
        {
            // Convert YYYY-MM-DD dates to ISO 8601 UTC timestamps for the tRPC input
            var startTime = ParseDateToUtcIso(dateFrom, timezone, startOfDay: true);
            var endTime = ParseDateToUtcIso(dateTo, timezone, startOfDay: false);

            var input = JsonSerializer.Serialize(new
            {
                json = new
                {
                    eventTypeId = eventTypeId.Value,
                    startTime,
                    endTime,
                    timeZone = timezone,
                    isTeamEvent = false
                }
            });

            var url = $"{BaseUrl}/api/trpc/slots/getSchedule?input={Uri.EscapeDataString(input)}";

            _logger.LogDebug("Cal.com slots request: {Url}", url);

            using var request = new HttpRequestMessage(HttpMethod.Get, url);
            var response = await _http.SendAsync(request, ct);
            var body = await response.Content.ReadAsStringAsync(ct);

            if (!response.IsSuccessStatusCode)
            {
                _logger.LogWarning("Cal.com slots tRPC returned {Status}: {Body}", response.StatusCode, body);
                return new CalComSlotsResult(false, [], $"Cal.com returned {response.StatusCode}.");
            }

            // tRPC response: {"result":{"data":{"json":{"slots":{"2025-07-14":[{time:"..."},...], ...}}}}}
            using var doc = JsonDocument.Parse(body);
            var slotsElement = doc.RootElement
                .GetProperty("result")
                .GetProperty("data")
                .GetProperty("json")
                .GetProperty("slots");

            var slotsByDate = new Dictionary<string, List<string>>();

            foreach (var dateProp in slotsElement.EnumerateObject())
            {
                var slots = new List<string>();
                foreach (var slot in dateProp.Value.EnumerateArray())
                {
                    // Slots can be either strings or objects with a "time" property
                    if (slot.ValueKind == JsonValueKind.String)
                    {
                        slots.Add(slot.GetString()!);
                    }
                    else if (slot.TryGetProperty("time", out var timeProp))
                    {
                        slots.Add(timeProp.GetString()!);
                    }
                }
                if (slots.Count > 0)
                    slotsByDate[dateProp.Name] = slots;
            }

            _logger.LogInformation("Cal.com returned {Count} days with slots for {Type}",
                slotsByDate.Count, meetingType);

            return new CalComSlotsResult(true, slotsByDate);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error fetching Cal.com slots");
            return new CalComSlotsResult(false, [], "Could not reach Cal.com scheduling service.");
        }
    }

    // ── Create booking (/api/book/event) ────────────────────────────

    public async Task<CalComBookingResult> CreateBookingAsync(
        string startTimeUtc, string meetingType,
        string attendeeName, string attendeeEmail, string attendeeTimezone,
        string? notes = null, CancellationToken ct = default)
    {
        if (!IsConfigured)
            return new CalComBookingResult(false, Error: "Cal.com is not configured.");

        var eventTypeId = ResolveEventTypeId(meetingType);
        if (eventTypeId is null)
            return new CalComBookingResult(false, Error: $"Unknown meeting type: {meetingType}");

        // Allow one automatic retry after cleaning stale idempotency keys
        const int maxAttempts = 2;

        for (int attempt = 1; attempt <= maxAttempts; attempt++)
        {
            try
            {
                var result = await SendBookingRequestAsync(
                    eventTypeId.Value, startTimeUtc, attendeeName, attendeeEmail,
                    attendeeTimezone, notes, ct);

                if (result.Success)
                    return result;

                // Check if the error is caused by a duplicate idempotencyKey on a cancelled booking
                if (attempt < maxAttempts && IsIdempotencyKeyConflict(result.Error))
                {
                    _logger.LogWarning(
                        "Cal.com booking failed due to idempotencyKey conflict. " +
                        "Cleaning stale keys from cancelled bookings and retrying (attempt {Attempt}/{Max})...",
                        attempt, maxAttempts);

                    var cleaned = await ClearCancelledIdempotencyKeysAsync(ct);
                    _logger.LogInformation("Cleared idempotencyKey from {Count} cancelled booking(s)", cleaned);
                    continue; // retry
                }

                return result;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error creating Cal.com booking (attempt {Attempt})", attempt);
                if (attempt >= maxAttempts)
                    return new CalComBookingResult(false, Error: "Could not reach Cal.com scheduling service.");
            }
        }

        return new CalComBookingResult(false, Error: "Could not create booking after retries.");
    }

    /// <summary>
    /// Sends the actual HTTP request to Cal.com /api/book/event.
    /// Extracted to allow retry logic in <see cref="CreateBookingAsync"/>.
    /// </summary>
    private async Task<CalComBookingResult> SendBookingRequestAsync(
        int eventTypeId, string startTimeUtc,
        string attendeeName, string attendeeEmail, string attendeeTimezone,
        string? notes, CancellationToken ct)
    {
        // Compute end time (start + duration)
        var startDt = DateTime.Parse(startTimeUtc, null, System.Globalization.DateTimeStyles.RoundtripKind);
        var endDt = startDt.AddMinutes(DefaultDurationMinutes);

        var language = attendeeTimezone.StartsWith("America/Argentina", StringComparison.OrdinalIgnoreCase) ? "es" : "en";

        // Location must be explicitly specified; without it Cal.com falls back to Daily.co.
        // Event types are configured with Google Meet (integrations:google:meet).
        const string meetingLocation = "integrations:google:meet";

        var payload = new Dictionary<string, object>
        {
            ["eventTypeId"] = eventTypeId,
            ["start"] = startDt.ToString("o"),
            ["end"] = endDt.ToString("o"),
            ["timeZone"] = attendeeTimezone,
            ["language"] = language,
            ["location"] = meetingLocation,
            ["metadata"] = new Dictionary<string, object>(),
            ["responses"] = new Dictionary<string, object>
            {
                ["name"] = attendeeName,
                ["email"] = attendeeEmail,
                ["location"] = new Dictionary<string, string>
                {
                    ["optionValue"] = "",
                    ["value"] = meetingLocation
                }
            }
        };

        if (!string.IsNullOrWhiteSpace(notes))
        {
            ((Dictionary<string, object>)payload["responses"])["notes"] = notes;
            // Also set as top-level description so it appears in the calendar event body
            payload["description"] = notes;
        }

        var url = $"{BaseUrl}/api/book/event";

        _logger.LogDebug("Cal.com booking request: {Url} payload: {Payload}",
            url, JsonSerializer.Serialize(payload));

        using var request = new HttpRequestMessage(HttpMethod.Post, url);
        request.Content = new StringContent(
            JsonSerializer.Serialize(payload),
            Encoding.UTF8, "application/json");

        var response = await _http.SendAsync(request, ct);
        var body = await response.Content.ReadAsStringAsync(ct);

        if (!response.IsSuccessStatusCode)
        {
            _logger.LogWarning("Cal.com create booking returned {Status}: {Body}", response.StatusCode, body);
            return new CalComBookingResult(false, Error: ExtractErrorMessage(body) ?? $"Cal.com returned {response.StatusCode}.");
        }

        _logger.LogInformation("Cal.com booking created successfully");
        return ParseBookingResponse(body);
    }

    /// <summary>
    /// Checks whether the Cal.com error message indicates a duplicate idempotencyKey
    /// constraint violation (Prisma P2002 on cancelled bookings).
    /// </summary>
    private static bool IsIdempotencyKeyConflict(string? error)
    {
        if (string.IsNullOrEmpty(error)) return false;
        // Cal.com wraps the Prisma error — the user-facing message is generic
        return error.Contains("error occurred while querying the database", StringComparison.OrdinalIgnoreCase)
            || error.Contains("idempotencyKey", StringComparison.OrdinalIgnoreCase)
            || error.Contains("P2002", StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Connects to the Cal.com database and sets idempotencyKey = NULL for all
    /// cancelled bookings. This works around a Cal.com bug where cancelled bookings
    /// retain their deterministic idempotency key, blocking new bookings at the
    /// same event type + time slot.
    /// Returns the number of rows cleaned.
    /// </summary>
    private async Task<int> ClearCancelledIdempotencyKeysAsync(CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(_options.DatabaseConnectionString))
        {
            _logger.LogWarning("Cannot clean CalCom idempotency keys: no database connection string configured");
            return 0;
        }

        try
        {
            await using var conn = new NpgsqlConnection(_options.DatabaseConnectionString);
            await conn.OpenAsync(ct);

            await using var cmd = new NpgsqlCommand(
                """UPDATE "Booking" SET "idempotencyKey" = NULL WHERE "status" = 'cancelled' AND "idempotencyKey" IS NOT NULL""",
                conn);

            return await cmd.ExecuteNonQueryAsync(ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to clean cancelled booking idempotency keys from CalCom database");
            return 0;
        }
    }

    // ── Cancel / Reschedule (not available in self-hosted web-only container) ──

    public Task<CalComBookingResult> CancelBookingAsync(
        string bookingUid, string? reason = null,
        CancellationToken ct = default)
    {
        _logger.LogWarning("Cancel booking requested for {Uid} but this operation is not available via the self-hosted web API", bookingUid);
        return Task.FromResult(new CalComBookingResult(false,
            Error: "Cancellation is not available through the automated system. " +
                   "Please coordinate directly via email at info@novitsoftware.com or WhatsApp at +54 11 3176 9406."));
    }

    public Task<CalComBookingResult> RescheduleBookingAsync(
        string bookingUid, string newStartTimeUtc, string? reason = null,
        CancellationToken ct = default)
    {
        _logger.LogWarning("Reschedule booking requested for {Uid} but this operation is not available via the self-hosted web API", bookingUid);
        return Task.FromResult(new CalComBookingResult(false,
            Error: "Rescheduling is not available through the automated system. " +
                   "Please coordinate directly via email at info@novitsoftware.com or WhatsApp at +54 11 3176 9406."));
    }

    public async Task<CalComBookingResult> UpdateBookingNotesAsync(
        string bookingUid, string notes,
        CancellationToken ct = default)
    {
        if (string.IsNullOrWhiteSpace(_options.DatabaseConnectionString))
        {
            _logger.LogWarning("Cannot update booking notes: no database connection string configured");
            return new CalComBookingResult(false,
                Error: "Booking notes update is not available (no database connection configured).");
        }

        try
        {
            await using var conn = new NpgsqlConnection(_options.DatabaseConnectionString);
            await conn.OpenAsync(ct);

            // Update the description field on the Booking row identified by uid
            await using var cmd = new NpgsqlCommand(
                """UPDATE "Booking" SET "description" = @notes WHERE "uid" = @uid""",
                conn);
            cmd.Parameters.AddWithValue("notes", notes);
            cmd.Parameters.AddWithValue("uid", bookingUid);

            var rows = await cmd.ExecuteNonQueryAsync(ct);

            if (rows == 0)
            {
                _logger.LogWarning("No booking found with UID {Uid} to update notes", bookingUid);
                return new CalComBookingResult(false, Error: "Booking not found.");
            }

            _logger.LogInformation("Updated notes for booking {Uid}", bookingUid);
            return new CalComBookingResult(true, BookingUid: bookingUid, Status: "NOTES_UPDATED");
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to update booking notes for {Uid}", bookingUid);
            return new CalComBookingResult(false,
                Error: "Could not update booking notes.");
        }
    }

    // ── Helpers ──────────────────────────────────────────────────────

    private string BaseUrl => _options.BaseUrl!.TrimEnd('/');

    private int? ResolveEventTypeId(string meetingType)
    {
        return meetingType.ToLowerInvariant() switch
        {
            "demo" => _options.EventTypeIdDemo,
            "discovery" => _options.EventTypeIdDiscovery,
            _ => _options.EventTypeIdDiscovery // default to discovery
        };
    }

    /// <summary>
    /// Converts a YYYY-MM-DD date string to an ISO 8601 UTC timestamp.
    /// For startOfDay=true, uses 00:00 local time; for false, uses 23:59:59 local time.
    /// </summary>
    private static string ParseDateToUtcIso(string dateStr, string timezone, bool startOfDay)
    {
        if (DateTime.TryParse(dateStr, out var dt))
        {
            // If it's already a full ISO timestamp, return as-is
            if (dateStr.Contains('T'))
                return dt.ToUniversalTime().ToString("o");

            // It's a YYYY-MM-DD date — add time component
            try
            {
                var tz = TimeZoneInfo.FindSystemTimeZoneById(timezone);
                var local = startOfDay
                    ? new DateTime(dt.Year, dt.Month, dt.Day, 0, 0, 0)
                    : new DateTime(dt.Year, dt.Month, dt.Day, 23, 59, 59);
                var utc = TimeZoneInfo.ConvertTimeToUtc(local, tz);
                return utc.ToString("o");
            }
            catch (TimeZoneNotFoundException)
            {
                // Fallback: treat as UTC
                return startOfDay
                    ? $"{dateStr}T00:00:00.000Z"
                    : $"{dateStr}T23:59:59.000Z";
            }
        }

        // Fallback: return as-is with time appended
        return startOfDay
            ? $"{dateStr}T00:00:00.000Z"
            : $"{dateStr}T23:59:59.000Z";
    }

    /// <summary>
    /// Parses the /api/book/event response.
    /// Response is a flat booking object (not wrapped in data/status like v2).
    /// </summary>
    private static CalComBookingResult ParseBookingResponse(string body)
    {
        try
        {
            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;

            // The /api/book/event response is a flat object with booking fields
            // Try both root-level (web handler) and nested "data" (v2-style) formats
            var data = root.TryGetProperty("data", out var dataProp) ? dataProp : root;

            return new CalComBookingResult(
                Success: true,
                BookingUid: data.TryGetProperty("uid", out var uid) ? uid.GetString() : null,
                Title: data.TryGetProperty("title", out var title) ? title.GetString() : null,
                Start: data.TryGetProperty("startTime", out var startTime) ? startTime.GetString()
                     : data.TryGetProperty("start", out var start) ? start.GetString() : null,
                End: data.TryGetProperty("endTime", out var endTime) ? endTime.GetString()
                   : data.TryGetProperty("end", out var end) ? end.GetString() : null,
                MeetingUrl: ExtractMeetingUrl(data),
                Status: data.TryGetProperty("status", out var status) ? status.GetString() : null);
        }
        catch (JsonException)
        {
            return new CalComBookingResult(true,
                BookingUid: null,
                Status: "ACCEPTED");
        }
    }

    /// <summary>
    /// Extracts the meeting URL from various possible locations in the response.
    /// </summary>
    private static string? ExtractMeetingUrl(JsonElement data)
    {
        // Direct meetingUrl field
        if (data.TryGetProperty("meetingUrl", out var meetUrl) && meetUrl.ValueKind == JsonValueKind.String)
            return meetUrl.GetString();

        // From metadata.videoCallUrl
        if (data.TryGetProperty("metadata", out var meta) && meta.ValueKind == JsonValueKind.Object)
        {
            if (meta.TryGetProperty("videoCallUrl", out var vcUrl) && vcUrl.ValueKind == JsonValueKind.String)
                return vcUrl.GetString();
        }

        // From references array (booking references contain the meet link)
        if (data.TryGetProperty("references", out var refs) && refs.ValueKind == JsonValueKind.Array)
        {
            foreach (var r in refs.EnumerateArray())
            {
                if (r.TryGetProperty("meetingUrl", out var refUrl) && refUrl.ValueKind == JsonValueKind.String)
                    return refUrl.GetString();
            }
        }

        return null;
    }

    private static string? ExtractErrorMessage(string body)
    {
        try
        {
            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;

            // Try "message" (Cal.com web handler format)
            if (root.TryGetProperty("message", out var msg) && msg.ValueKind == JsonValueKind.String)
                return msg.GetString();

            // Try "error" (various formats)
            if (root.TryGetProperty("error", out var err))
            {
                if (err.ValueKind == JsonValueKind.String)
                    return err.GetString();
                if (err.TryGetProperty("message", out var errMsg))
                    return errMsg.GetString();
            }
        }
        catch { /* ignore parse errors */ }
        return null;
    }
}
