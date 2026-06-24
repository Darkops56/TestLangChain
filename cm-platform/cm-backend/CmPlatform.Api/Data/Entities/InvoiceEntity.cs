using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace CmPlatform.Api.Data.Entities;

[Table("invoices")]
public class InvoiceEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("client_id")]
    public Guid ClientId { get; set; }

    [Column("amount")]
    [Range(0, double.MaxValue)]
    public decimal Amount { get; set; }

    [Column("currency")]
    [MaxLength(3)]
    public string Currency { get; set; } = "USD";

    [Column("status")]
    [MaxLength(50)]
    public string Status { get; set; } = "pending";

    [Column("description")]
    public string? Description { get; set; }

    [Column("due_at")]
    public DateTimeOffset DueAt { get; set; }

    [Column("paid_at")]
    public DateTimeOffset? PaidAt { get; set; }

    [Column("stripe_payment_intent_id")]
    public string? StripePaymentIntentId { get; set; }

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    [Column("updated_at")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;

    public ClientEntity Client { get; set; } = null!;
}
