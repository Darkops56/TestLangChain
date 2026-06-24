namespace Novit.Web.Api.Services;

/// <summary>Represents a Pipedrive deal with its associated contact info.</summary>
public sealed record PipedriveDealContact(int DealId, string DealTitle, string ContactEmail, string? ContactName, string? OrganizationName);

public interface IPipedriveService
{
    bool IsConfigured { get; }
    Task<string?> CreateLeadAsync(string name, string email, string message, CancellationToken ct = default);
    Task<string?> FindOrCreatePersonAsync(string email, CancellationToken ct = default);

    /// <summary>
    /// Creates a full Pipedrive deal from a booking: Person + Organization + Deal + Note.
    /// Returns the deal ID, or null on failure.
    /// </summary>
    Task<string?> CreateDealFromBookingAsync(
        string attendeeName, string attendeeEmail, string? company,
        string meetingType, string bookingUid, string? meetingUrl,
        string? conversationSummary, CancellationToken ct = default);

    /// <summary>
    /// Gets all deals in the "Nurturing Automático" pipeline stage together with their
    /// primary contact email addresses.
    /// </summary>
    Task<List<PipedriveDealContact>> GetNurturingDealContactsAsync(CancellationToken ct = default);

    /// <summary>
    /// Fetches a specific deal by ID directly from Pipedrive (any stage, any status)
    /// and returns the associated contact. Used for ?dealId=N testing.
    /// </summary>
    Task<PipedriveDealContact?> GetDealContactAsync(int dealId, CancellationToken ct = default);

    /// <summary>
    /// Adds a note to a Pipedrive deal (e.g. when a nurturing lead replies).
    /// </summary>
    Task AddNoteToDealAsync(int dealId, string noteContent, CancellationToken ct = default);

    /// <summary>
    /// Gets all notes attached to a Pipedrive deal, most recent first.
    /// Returns plain-text versions of the notes (HTML tags stripped).
    /// </summary>
    Task<List<string>> GetDealNotesAsync(int dealId, CancellationToken ct = default);

    /// <summary>
    /// Gets personalization context for a deal, combining notes and recent associated emails.
    /// Entries are returned as dated plain-text snippets for AI prompting.
    /// </summary>
    Task<List<string>> GetDealPersonalizationContextAsync(int dealId, CancellationToken ct = default);

    /// <summary>
    /// Moves a deal to the specified pipeline stage by stage name.
    /// Returns true on success.
    /// </summary>
    Task<bool> MoveDealToStageAsync(int dealId, string stageName, CancellationToken ct = default);

    /// <summary>
    /// Creates a deal directly in the specified pipeline stage (e.g. "R1 agendada").
    /// Returns the deal ID, or null on failure.
    /// </summary>
    Task<string?> CreateDealInStageAsync(
        string dealTitle, string attendeeName, string attendeeEmail, string? company,
        string stageName, string? note, CancellationToken ct = default);
}
