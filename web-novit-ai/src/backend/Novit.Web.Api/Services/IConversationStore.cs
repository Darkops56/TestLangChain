using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public interface IConversationStore
{
    ConversationCreateResponse Create(string locale);
    ConversationDto? Get(string conversationId);
    bool Delete(string conversationId);
    MessageDto AddMessage(string conversationId, string role, string content, string? ttsUrl = null, bool isVoice = false);

    /// <summary>Check if an IP address has exceeded the global rate limit (120 requests per 24h, covering chat + TTS + STT).</summary>
    bool IsIpRateLimited(string ipAddress);

    /// <summary>Increment the message counter for an IP address.</summary>
    void IncrementIpCounter(string ipAddress);
}
