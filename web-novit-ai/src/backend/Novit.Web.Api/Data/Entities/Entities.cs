using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Novit.Web.Api.Data.Entities;

[Table("conversations")]
public class ConversationEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("ip_address")]
    [MaxLength(45)]
    public string IpAddress { get; set; } = "0.0.0.0";

    [Column("locale")]
    [MaxLength(5)]
    public string Locale { get; set; } = "es";

    [Column("email")]
    [MaxLength(255)]
    public string? Email { get; set; }

    [Column("lead_id")]
    public Guid? LeadId { get; set; }

    [Column("message_count")]
    public int MessageCount { get; set; }

    [Column("is_rate_limited")]
    public bool IsRateLimited { get; set; }

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    [Column("updated_at")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;

    [Column("expires_at")]
    public DateTimeOffset ExpiresAt { get; set; } = DateTimeOffset.UtcNow.AddHours(24);

    public List<MessageEntity> Messages { get; set; } = [];
    public LeadEntity? Lead { get; set; }
}

[Table("messages")]
public class MessageEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("conversation_id")]
    public Guid ConversationId { get; set; }

    [Column("role")]
    [MaxLength(10)]
    public string Role { get; set; } = "user";

    [Column("content")]
    public string Content { get; set; } = "";

    [Column("widgets", TypeName = "jsonb")]
    public string? Widgets { get; set; }

    [Column("audio_url")]
    public string? AudioUrl { get; set; }

    [Column("tts_url")]
    public string? TtsUrl { get; set; }

    [Column("token_count")]
    public int? TokenCount { get; set; }

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    public ConversationEntity Conversation { get; set; } = null!;
}

[Table("leads")]
public class LeadEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("email")]
    [MaxLength(255)]
    public string Email { get; set; } = "";

    [Column("conversation_id")]
    public Guid? ConversationId { get; set; }

    [Column("pipedrive_id")]
    public long? PipedriveId { get; set; }

    [Column("source")]
    [MaxLength(50)]
    public string Source { get; set; } = "auth_gate";

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    public ConversationEntity? Conversation { get; set; }
}

[Table("rate_limits")]
public class RateLimitEntity
{
    [Key]
    [Column("ip_address")]
    [MaxLength(45)]
    public string IpAddress { get; set; } = "";

    [Column("message_count")]
    public int MessageCount { get; set; }

    [Column("window_start")]
    public DateTimeOffset WindowStart { get; set; } = DateTimeOffset.UtcNow;

    [Column("conversation_id")]
    public Guid? ConversationId { get; set; }

    [Column("is_blocked")]
    public bool IsBlocked { get; set; }

    [Column("updated_at")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}
