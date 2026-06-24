using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace CmPlatform.Api.Data.Entities;

[Table("social_accounts")]
public class SocialAccountEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("client_id")]
    public Guid ClientId { get; set; }

    [Column("platform")]
    [MaxLength(50)]
    public string Platform { get; set; } = "";

    [Column("username")]
    [MaxLength(200)]
    public string Username { get; set; } = "";

    [Column("access_token")]
    public string? AccessToken { get; set; }

    [Column("refresh_token")]
    public string? RefreshToken { get; set; }

    [Column("token_expires_at")]
    public DateTimeOffset? TokenExpiresAt { get; set; }

    [Column("is_active")]
    public bool IsActive { get; set; } = true;

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    public ClientEntity Client { get; set; } = null!;
}
