namespace Novit.Web.Api.Models;

public sealed record ConversationCreateRequest(string? Locale);

public sealed record ConversationCreateResponse(string ConversationId, string Locale);

public sealed record MessageDto(string Id, string Role, string Content, DateTimeOffset CreatedAt, string? TtsUrl = null, bool IsVoice = false);

public sealed record ConversationMeta(string Locale, int MessageCount, bool IsRateLimited, DateTimeOffset CreatedAt, DateTimeOffset UpdatedAt);

public sealed record ConversationDto(string ConversationId, IReadOnlyList<MessageDto> Messages, ConversationMeta Metadata);

public sealed record UserMessageRequest(string Text, string? Locale, bool IsVoice = false);

public sealed record UserMessageResponse(MessageDto UserMessage, MessageDto BotMessage, int RemainingMessages);

public sealed record ContactFormRequest(string Name, string Email, string Message, string Locale);

public sealed record ContactFormResponse(bool Success, string? PipedriveId = null);

public sealed record AuthGateRequest(string Email, string ConversationId);

public sealed record AuthGateResponse(bool Success, string? PipedrivePersonId = null);

public sealed record VoiceTranscribeResponse(string Text, double Confidence, int DurationMs);

public sealed record VoiceSynthesizeRequest(string Text, string Locale, string MessageId);

public sealed record HealthResponse(string Status, object Services);
