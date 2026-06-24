using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace CmPlatform.Api.Data.Entities;

[Table("publications")]
public class PublicationEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("client_id")]
    public Guid ClientId { get; set; }

    [Column("platform")]
    [MaxLength(50)]
    public string Platform { get; set; } = "";

    [Column("content_type")]
    [MaxLength(50)]
    public string ContentType { get; set; } = "";

    [Column("content")]
    public string Content { get; set; } = "";

    [Column("media_urls_json")]
    public string MediaUrlsJson { get; set; } = "[]";

    [Column("status")]
    [MaxLength(50)]
    public string Status { get; set; } = "draft";

    [Column("scheduled_at")]
    public DateTimeOffset? ScheduledAt { get; set; }

    [Column("published_at")]
    public DateTimeOffset? PublishedAt { get; set; }

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    [Column("updated_at")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;

    public ClientEntity Client { get; set; } = null!;
}
