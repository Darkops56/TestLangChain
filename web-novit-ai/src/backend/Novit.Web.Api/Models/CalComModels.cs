namespace Novit.Web.Api.Models;

/// <summary>Available slots grouped by date.</summary>
public sealed record CalComSlotsResult(
    bool Success,
    Dictionary<string, List<string>> SlotsByDate,
    string? Error = null);

/// <summary>Result of a booking operation (create, cancel, reschedule).</summary>
public sealed record CalComBookingResult(
    bool Success,
    string? BookingUid = null,
    string? Title = null,
    string? Start = null,
    string? End = null,
    string? MeetingUrl = null,
    string? Status = null,
    string? Error = null);
