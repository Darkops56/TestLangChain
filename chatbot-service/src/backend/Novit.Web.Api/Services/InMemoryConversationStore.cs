using System.Collections.Concurrent;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public sealed class InMemoryConversationStore : IConversationStore
{
    private sealed class ConversationState
    {
        public required string Id { get; init; }
        public required string Locale { get; init; }
        public DateTimeOffset CreatedAt { get; init; } = DateTimeOffset.UtcNow;
        public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
        public int UserMessageCount { get; set; }
        public bool IsRateLimited { get; set; }
        public DateTimeOffset? RateLimitedAt { get; set; }
        public List<MessageDto> Messages { get; } = [];
    }

    private sealed class IpRateState
    {
        public int MessageCount { get; set; }
        public DateTimeOffset WindowStart { get; set; } = DateTimeOffset.UtcNow;
    }

    private readonly ConcurrentDictionary<string, ConversationState> _conversations = new();
    private readonly ConcurrentDictionary<string, IpRateState> _ipRates = new();

    private static readonly int MaxMessagesPerIpPerDay = ChatLimits.MaxRequestsPerIpPerDay;

    public ConversationCreateResponse Create(string locale)
    {
        var normalizedLocale = locale is "en" or "en-US" ? "en-US" : "es-AR";
        var state = new ConversationState
        {
            Id = Guid.NewGuid().ToString("N"),
            Locale = normalizedLocale
        };

        _conversations[state.Id] = state;
        return new ConversationCreateResponse(state.Id, state.Locale);
    }

    public ConversationDto? Get(string conversationId)
    {
        if (!_conversations.TryGetValue(conversationId, out var state))
        {
            return null;
        }

        return ToDto(state);
    }

    public bool Delete(string conversationId)
    {
        return _conversations.TryRemove(conversationId, out _);
    }

    public MessageDto AddMessage(string conversationId, string role, string content, string? ttsUrl = null, bool isVoice = false)
    {
        if (!_conversations.TryGetValue(conversationId, out var state))
        {
            throw new KeyNotFoundException($"Conversation '{conversationId}' not found.");
        }

        var message = new MessageDto(Guid.NewGuid().ToString("N"), role, content, DateTimeOffset.UtcNow, ttsUrl, isVoice);
        lock (state.Messages)
        {
            state.Messages.Add(message);
            if (role == "user")
            {
                state.UserMessageCount++;
                if (!state.IsRateLimited && state.UserMessageCount >= ChatLimits.MaxMessagesPerConversation)
                {
                    state.IsRateLimited = true;
                    state.RateLimitedAt = DateTimeOffset.UtcNow;
                }
            }

            state.UpdatedAt = DateTimeOffset.UtcNow;
        }

        return message;
    }

    private static ConversationDto ToDto(ConversationState state)
    {
        // Reset per-conversation rate limit after 24h
        if (state.IsRateLimited && state.RateLimitedAt.HasValue &&
            DateTimeOffset.UtcNow - state.RateLimitedAt.Value > TimeSpan.FromHours(24))
        {
            state.IsRateLimited = false;
            state.UserMessageCount = 0;
            state.RateLimitedAt = null;
        }

        return new ConversationDto(
            state.Id,
            state.Messages.ToArray(),
            new ConversationMeta(state.Locale, state.UserMessageCount, state.IsRateLimited, state.CreatedAt, state.UpdatedAt));
    }

    public bool IsIpRateLimited(string ipAddress)
    {
        if (!_ipRates.TryGetValue(ipAddress, out var state))
            return false;

        // Reset window if older than 24h
        if (DateTimeOffset.UtcNow - state.WindowStart > TimeSpan.FromHours(24))
        {
            state.MessageCount = 0;
            state.WindowStart = DateTimeOffset.UtcNow;
            return false;
        }

        return state.MessageCount >= MaxMessagesPerIpPerDay;
    }

    public void IncrementIpCounter(string ipAddress)
    {
        var state = _ipRates.GetOrAdd(ipAddress, _ => new IpRateState());

        // Reset window if older than 24h
        if (DateTimeOffset.UtcNow - state.WindowStart > TimeSpan.FromHours(24))
        {
            state.MessageCount = 0;
            state.WindowStart = DateTimeOffset.UtcNow;
        }

        state.MessageCount++;
    }
}
