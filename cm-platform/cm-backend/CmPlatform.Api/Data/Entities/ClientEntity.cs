using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace CmPlatform.Api.Data.Entities;

[Table("clients")]
public class ClientEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("name")]
    [MaxLength(200)]
    public string Name { get; set; } = "";

    [Column("email")]
    [MaxLength(255)]
    public string Email { get; set; } = "";

    [Column("phone")]
    [MaxLength(50)]
    public string? Phone { get; set; }

    [Column("company")]
    [MaxLength(200)]
    public string? Company { get; set; }

    [Column("notes")]
    public string? Notes { get; set; }

    [Column("subscription_status")]
    [MaxLength(50)]
    public string SubscriptionStatus { get; set; } = "active";

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    [Column("updated_at")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;

    public List<SocialAccountEntity> SocialAccounts { get; set; } = [];
    public List<PublicationEntity> Publications { get; set; } = [];
    public List<InvoiceEntity> Invoices { get; set; } = [];
}
