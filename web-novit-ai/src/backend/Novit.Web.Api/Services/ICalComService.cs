using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public interface ICalComService
{
    bool IsConfigured { get; }

    /// <summary>Get available time slots for a given date range and meeting type.</summary>
    Task<CalComSlotsResult> GetAvailableSlotsAsync(
        string dateFrom, string dateTo, string meetingType, string timezone,
        CancellationToken ct = default);

    /// <summary>Create a new booking.</summary>
    Task<CalComBookingResult> CreateBookingAsync(
        string startTimeUtc, string meetingType,
        string attendeeName, string attendeeEmail, string attendeeTimezone,
        string? notes = null, CancellationToken ct = default);

    /// <summary>Cancel an existing booking by UID.</summary>
    Task<CalComBookingResult> CancelBookingAsync(
        string bookingUid, string? reason = null,
        CancellationToken ct = default);

    /// <summary>Reschedule an existing booking to a new time.</summary>
    Task<CalComBookingResult> RescheduleBookingAsync(
        string bookingUid, string newStartTimeUtc, string? reason = null,
        CancellationToken ct = default);

    /// <summary>Update the notes/description of an existing booking.</summary>
    Task<CalComBookingResult> UpdateBookingNotesAsync(
        string bookingUid, string notes,
        CancellationToken ct = default);
}
