using CmPlatform.Api.Models;

namespace CmPlatform.Api.Services;

public interface INurturingMailService
{
    bool IsConfigured { get; }

    Task SendBulkEmailAsync(
        IReadOnlyList<string> recipients,
        string subject,
        string body,
        bool isHtml = false,
        CancellationToken ct = default);

    Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default);

    Task MarkAsReadAsync(IReadOnlyList<string> messageIds, CancellationToken ct = default);
}
