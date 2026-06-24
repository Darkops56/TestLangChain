namespace Novit.Web.Api.Services;

/// <summary>Represents an email received from a mailbox.</summary>
public sealed record IncomingEmail(
    string MessageId,
    string From,
    string Subject,
    string Body,
    DateTimeOffset Date,
    string? InReplyTo);

/// <summary>Reads and sends nurturing emails via IMAP/SMTP (provider-agnostic).</summary>
public interface INurturingMailService
{
    bool IsConfigured { get; }

    /// <summary>
    /// Fetches unanswered replies to nurturing emails from the last <paramref name="days"/> days.
    /// A reply is considered unanswered if it was received from an external contact and no
    /// subsequent message from the nurturing account exists in the same thread.
    /// </summary>
    Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default);

    /// <summary>Sends an email (plain text or HTML).</summary>
    Task SendEmailAsync(string to, string subject, string body, bool isHtml = false, CancellationToken ct = default);

    /// <summary>Sends an email to multiple recipients (one per recipient, plain text or HTML).</summary>
    Task SendBulkEmailAsync(IEnumerable<string> recipients, string subject, string body, bool isHtml = false, CancellationToken ct = default);

    /// <summary>Sends a reply to an existing email thread.</summary>
    Task SendReplyAsync(string to, string subject, string body, string inReplyToMessageId, bool isHtml = false, CancellationToken ct = default);

    /// <summary>Marks the given emails as read (sets the IMAP \Seen flag) so they
    /// are not picked up again by <see cref="GetUnansweredRepliesAsync"/>.</summary>
    Task MarkAsReadAsync(IEnumerable<string> messageIds, CancellationToken ct = default);
}
