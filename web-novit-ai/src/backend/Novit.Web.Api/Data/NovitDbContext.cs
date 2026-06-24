using Microsoft.EntityFrameworkCore;
using Novit.Web.Api.Data.Entities;

namespace Novit.Web.Api.Data;

public class NovitDbContext(DbContextOptions<NovitDbContext> options) : DbContext(options)
{
    public DbSet<ConversationEntity> Conversations => Set<ConversationEntity>();
    public DbSet<MessageEntity> Messages => Set<MessageEntity>();
    public DbSet<LeadEntity> Leads => Set<LeadEntity>();
    public DbSet<RateLimitEntity> RateLimits => Set<RateLimitEntity>();
    public DbSet<NurturingEmailEntity> NurturingEmails => Set<NurturingEmailEntity>();
    public DbSet<CommunityPublicationEntity> CommunityPublications => Set<CommunityPublicationEntity>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<ConversationEntity>(e =>
        {
            e.HasMany(c => c.Messages)
             .WithOne(m => m.Conversation)
             .HasForeignKey(m => m.ConversationId)
             .OnDelete(DeleteBehavior.Cascade);

            e.HasOne(c => c.Lead)
             .WithOne(l => l!.Conversation)
             .HasForeignKey<ConversationEntity>(c => c.LeadId);

            e.HasIndex(c => c.IpAddress).HasDatabaseName("idx_conversations_ip");
        });

        modelBuilder.Entity<MessageEntity>(e =>
        {
            e.HasIndex(m => new { m.ConversationId, m.CreatedAt })
             .HasDatabaseName("idx_messages_conversation");
        });

        modelBuilder.Entity<LeadEntity>(e =>
        {
            e.HasIndex(l => l.Email).HasDatabaseName("idx_leads_email");
        });

        modelBuilder.Entity<RateLimitEntity>(e =>
        {
            e.HasIndex(r => r.WindowStart).HasDatabaseName("idx_rate_limits_window");
        });

        modelBuilder.Entity<NurturingEmailEntity>(e =>
        {
            e.HasIndex(n => n.MonthKey).IsUnique().HasDatabaseName("idx_nurturing_month_key");
        });

        modelBuilder.Entity<CommunityPublicationEntity>(e =>
        {
            e.HasIndex(p => p.Status).HasDatabaseName("idx_community_publications_status");
            e.HasIndex(p => p.CreatedAt).HasDatabaseName("idx_community_publications_created_at");
            e.HasIndex(p => p.ReviewToken).IsUnique().HasDatabaseName("idx_community_publications_review_token");
        });
    }
}
