namespace Novit.Web.Api.Services;

public interface IChatAIService
{
    bool IsConfigured { get; }
    Task<string> GetCompletionAsync(string conversationId, string userMessage, string locale, CancellationToken ct = default);
    IAsyncEnumerable<string> StreamCompletionAsync(string conversationId, string userMessage, string locale, CancellationToken ct = default);
}
