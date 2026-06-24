using System.Text.Json;

namespace Novit.Web.Api.Services;

/// <summary>
/// Executes tool calls requested by the AI model.
/// Dispatches function names to the appropriate service and returns JSON results.
/// </summary>
public sealed class ChatToolHandler
{
    private readonly ICalComService _calCom;
    private readonly IPipedriveService _pipedrive;
    private readonly ILogger<ChatToolHandler> _logger;

    public ChatToolHandler(ICalComService calCom, IPipedriveService pipedrive, ILogger<ChatToolHandler> logger)
    {
        _calCom = calCom;
        _pipedrive = pipedrive;
        _logger = logger;
    }

    /// <summary>
    /// Returns true if any scheduling tools are available (Cal.com is configured).
    /// </summary>
    public bool HasTools => _calCom.IsConfigured;

    /// <summary>
    /// Execute a function call by name with the given JSON arguments.
    /// Returns a JSON string with the result.
    /// </summary>
    public async Task<string> ExecuteAsync(string functionName, string argumentsJson, CancellationToken ct = default)
    {
        _logger.LogInformation("Executing tool: {Function} with args: {Args}", functionName, argumentsJson);

        try
        {
            using var args = JsonDocument.Parse(argumentsJson);
            var root = args.RootElement;

            return functionName switch
            {
                "get_available_slots" => await HandleGetAvailableSlots(root, ct),
                "create_booking" => await HandleCreateBooking(root, ct),
                "cancel_booking" => await HandleCancelBooking(root, ct),
                "reschedule_booking" => await HandleRescheduleBooking(root, ct),
                "update_booking_notes" => await HandleUpdateBookingNotes(root, ct),
                _ => JsonSerializer.Serialize(new { error = $"Unknown function: {functionName}" })
            };
        }
        catch (JsonException ex)
        {
            _logger.LogError(ex, "Failed to parse tool arguments for {Function}", functionName);
            return JsonSerializer.Serialize(new { error = "Invalid arguments format." });
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error executing tool {Function}", functionName);
            return JsonSerializer.Serialize(new { error = "An unexpected error occurred while processing the request." });
        }
    }

    private async Task<string> HandleGetAvailableSlots(JsonElement args, CancellationToken ct)
    {
        var dateFrom = args.GetProperty("date_from").GetString()!;
        var dateTo = args.GetProperty("date_to").GetString()!;
        var meetingType = args.GetProperty("meeting_type").GetString()!;
        var timezone = args.GetProperty("timezone").GetString()!;

        var result = await _calCom.GetAvailableSlotsAsync(dateFrom, dateTo, meetingType, timezone, ct);

        if (!result.Success)
            return JsonSerializer.Serialize(new { success = false, error = result.Error });

        if (result.SlotsByDate.Count == 0)
            return JsonSerializer.Serialize(new
            {
                success = true,
                message = "No available slots found in the requested date range.",
                slots = new Dictionary<string, List<string>>()
            });

        return JsonSerializer.Serialize(new
        {
            success = true,
            timezone,
            slots = result.SlotsByDate
        });
    }

    private async Task<string> HandleCreateBooking(JsonElement args, CancellationToken ct)
    {
        var startTime = args.GetProperty("start_time").GetString()!;
        var meetingType = args.GetProperty("meeting_type").GetString()!;
        var attendeeName = args.GetProperty("attendee_name").GetString()!;
        var attendeeEmail = args.GetProperty("attendee_email").GetString()!;
        var attendeeTimezone = args.GetProperty("attendee_timezone").GetString()!;
        var notes = args.TryGetProperty("notes", out var notesProp) ? notesProp.GetString() : null;
        var company = args.TryGetProperty("company", out var companyProp) ? companyProp.GetString() : null;

        var result = await _calCom.CreateBookingAsync(
            startTime, meetingType, attendeeName, attendeeEmail, attendeeTimezone, notes, ct);

        if (!result.Success)
            return JsonSerializer.Serialize(new { success = false, error = result.Error });

        // Create Pipedrive deal in the background (don't fail the booking if Pipedrive fails)
        _ = Task.Run(async () =>
        {
            try
            {
                await _pipedrive.CreateDealFromBookingAsync(
                    attendeeName, attendeeEmail, company,
                    meetingType, result.BookingUid ?? "unknown", result.MeetingUrl,
                    notes, CancellationToken.None);
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Background Pipedrive deal creation failed for booking {Uid}", result.BookingUid);
            }
        });

        return JsonSerializer.Serialize(new
        {
            success = true,
            booking_uid = result.BookingUid,
            title = result.Title,
            start = result.Start,
            end = result.End,
            meeting_url = result.MeetingUrl,
            status = result.Status
        });
    }

    private async Task<string> HandleCancelBooking(JsonElement args, CancellationToken ct)
    {
        var bookingUid = args.GetProperty("booking_uid").GetString()!;
        var reason = args.TryGetProperty("reason", out var reasonProp) ? reasonProp.GetString() : null;

        var result = await _calCom.CancelBookingAsync(bookingUid, reason, ct);

        if (!result.Success)
            return JsonSerializer.Serialize(new { success = false, error = result.Error });

        return JsonSerializer.Serialize(new
        {
            success = true,
            booking_uid = result.BookingUid,
            status = result.Status,
            message = "Booking cancelled successfully."
        });
    }

    private async Task<string> HandleRescheduleBooking(JsonElement args, CancellationToken ct)
    {
        var bookingUid = args.GetProperty("booking_uid").GetString()!;
        var newStartTime = args.GetProperty("new_start_time").GetString()!;
        var reason = args.TryGetProperty("reason", out var reasonProp) ? reasonProp.GetString() : null;

        var result = await _calCom.RescheduleBookingAsync(bookingUid, newStartTime, reason, ct);

        if (!result.Success)
            return JsonSerializer.Serialize(new { success = false, error = result.Error });

        return JsonSerializer.Serialize(new
        {
            success = true,
            booking_uid = result.BookingUid,
            start = result.Start,
            end = result.End,
            meeting_url = result.MeetingUrl,
            status = result.Status,
            message = "Booking rescheduled successfully."
        });
    }

    private async Task<string> HandleUpdateBookingNotes(JsonElement args, CancellationToken ct)
    {
        var bookingUid = args.GetProperty("booking_uid").GetString()!;
        var notes = args.GetProperty("notes").GetString()!;

        var result = await _calCom.UpdateBookingNotesAsync(bookingUid, notes, ct);

        if (!result.Success)
            return JsonSerializer.Serialize(new { success = false, error = result.Error });

        return JsonSerializer.Serialize(new
        {
            success = true,
            booking_uid = result.BookingUid,
            status = result.Status,
            message = "Booking notes updated successfully."
        });
    }
}
