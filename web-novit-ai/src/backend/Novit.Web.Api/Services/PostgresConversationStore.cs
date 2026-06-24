using Microsoft.EntityFrameworkCore;
using Novit.Web.Api.Data;
using Novit.Web.Api.Data.Entities;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public sealed class PostgresConversationStore(IServiceScopeFactory scopeFactory) : IConversationStore
{
    private const string VoiceMessageMarker = "voice";
    public ConversationCreateResponse Create(string locale)
    {
        using var scope = scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();

        var normalizedLocale = locale is "en" or "en-US" ? "en-US" : "es-AR";
        var entity = new ConversationEntity
        {
            Locale = normalizedLocale
        };

        db.Conversations.Add(entity);
        db.SaveChanges();

        return new ConversationCreateResponse(entity.Id.ToString("N"), entity.Locale);
    }

    public ConversationDto? Get(string conversationId)
    {
        if (!Guid.TryParse(conversationId, out var id))
            return null;

        using var scope = scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();

        var entity = db.Conversations
            .Include(c => c.Messages.OrderBy(m => m.CreatedAt))
            .FirstOrDefault(c => c.Id == id);

        if (entity is null)
            return null;

        // Reset per-conversation rate limit after 24h (ExpiresAt stores when the limit expires)
        if (entity.IsRateLimited && DateTimeOffset.UtcNow >= entity.ExpiresAt)
        {
            entity.IsRateLimited = false;
            entity.MessageCount = 0;
            db.SaveChanges();
        }

        return ToDto(entity);
    }

    public bool Delete(string conversationId)
    {
        if (!Guid.TryParse(conversationId, out var id))
            return false;

        using var scope = scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();

        var entity = db.Conversations.Find(id);
        if (entity is null)
            return false;

        db.Conversations.Remove(entity);
        db.SaveChanges();
        return true;
    }

    public MessageDto AddMessage(string conversationId, string role, string content, string? ttsUrl = null, bool isVoice = false)
    {
        if (!Guid.TryParse(conversationId, out var id))
            throw new KeyNotFoundException($"Conversation '{conversationId}' not found.");

        using var scope = scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();

        var conversation = db.Conversations.Find(id)
            ?? throw new KeyNotFoundException($"Conversation '{conversationId}' not found.");

        var message = new MessageEntity
        {
            ConversationId = id,
            Role = role,
            Content = content,
            TtsUrl = ttsUrl,
            AudioUrl = isVoice ? VoiceMessageMarker : null
        };

        db.Messages.Add(message);

        if (role == "user")
        {
            conversation.MessageCount++;
            if (!conversation.IsRateLimited && conversation.MessageCount >= ChatLimits.MaxMessagesPerConversation)
            {
                conversation.IsRateLimited = true;
                conversation.ExpiresAt = DateTimeOffset.UtcNow.AddHours(24);
            }
        }

        conversation.UpdatedAt = DateTimeOffset.UtcNow;
        db.SaveChanges();

        return new MessageDto(message.Id.ToString("N"), message.Role, message.Content, message.CreatedAt, message.TtsUrl, message.AudioUrl == VoiceMessageMarker);
    }

    private static ConversationDto ToDto(ConversationEntity entity)
    {
        var messages = entity.Messages
            .Select(m => new MessageDto(m.Id.ToString("N"), m.Role, m.Content, m.CreatedAt, m.TtsUrl, m.AudioUrl == VoiceMessageMarker))
            .ToArray();

        return new ConversationDto(
            entity.Id.ToString("N"),
            messages,
            new ConversationMeta(entity.Locale, entity.MessageCount, entity.IsRateLimited, entity.CreatedAt, entity.UpdatedAt));
    }

    // IP rate limiting uses the rate_limits table in the database
    public bool IsIpRateLimited(string ipAddress)
    {
        using var scope = scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();

        var rateLimit = db.RateLimits.Find(ipAddress);
        if (rateLimit is null) return false;

        // Reset if window is older than 24h
        if (DateTimeOffset.UtcNow - rateLimit.WindowStart > TimeSpan.FromHours(24))
        {
            rateLimit.MessageCount = 0;
            rateLimit.WindowStart = DateTimeOffset.UtcNow;
            db.SaveChanges();
            return false;
        }

        return rateLimit.MessageCount >= ChatLimits.MaxRequestsPerIpPerDay;
    }

    public void IncrementIpCounter(string ipAddress)
    {
        using var scope = scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();

        var rateLimit = db.RateLimits.Find(ipAddress);
        if (rateLimit is null)
        {
            rateLimit = new Data.Entities.RateLimitEntity
            {
                IpAddress = ipAddress,
                MessageCount = 0,
                WindowStart = DateTimeOffset.UtcNow
            };
            db.RateLimits.Add(rateLimit);
        }

        // Reset if window is older than 24h
        if (DateTimeOffset.UtcNow - rateLimit.WindowStart > TimeSpan.FromHours(24))
        {
            rateLimit.MessageCount = 0;
            rateLimit.WindowStart = DateTimeOffset.UtcNow;
        }

        rateLimit.MessageCount++;
        rateLimit.UpdatedAt = DateTimeOffset.UtcNow;
        db.SaveChanges();
    }
}
