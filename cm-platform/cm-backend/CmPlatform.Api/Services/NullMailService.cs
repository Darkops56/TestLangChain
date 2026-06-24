using CmPlatform.Api.Models;

namespace CmPlatform.Api.Services;

public sealed class NullMailService : INurturingMailService
{
    public bool IsConfigured => false;

    public Task SendBulkEmailAsync(
        IReadOnlyList<string> recipients,
        string subject,
        string body,
        bool isHtml = false,
        CancellationToken ct = default) => Task.CompletedTask;

    public Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default)
        => Task.FromResult<IReadOnlyList<IncomingEmail>>([]);

    public Task MarkAsReadAsync(IReadOnlyList<string> messageIds, CancellationToken ct = default) => Task.CompletedTask;
}
