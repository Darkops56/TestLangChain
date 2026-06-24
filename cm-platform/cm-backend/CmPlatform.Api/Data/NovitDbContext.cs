using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data.Entities;

namespace CmPlatform.Api.Data;

public class NovitDbContext(DbContextOptions<NovitDbContext> options) : DbContext(options)
{
    public DbSet<CommunityPublicationEntity> CommunityPublications => Set<CommunityPublicationEntity>();
    public DbSet<ClientEntity> Clients => Set<ClientEntity>();
    public DbSet<SocialAccountEntity> SocialAccounts => Set<SocialAccountEntity>();
    public DbSet<PublicationEntity> Publications => Set<PublicationEntity>();
    public DbSet<InvoiceEntity> Invoices => Set<InvoiceEntity>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<CommunityPublicationEntity>(e =>
        {
            e.HasIndex(p => p.Status).HasDatabaseName("idx_community_publications_status");
            e.HasIndex(p => p.CreatedAt).HasDatabaseName("idx_community_publications_created_at");
            e.HasIndex(p => p.ReviewToken).IsUnique().HasDatabaseName("idx_community_publications_review_token");
        });

        modelBuilder.Entity<SocialAccountEntity>(e =>
        {
            e.HasOne(s => s.Client)
                .WithMany(c => c.SocialAccounts)
                .HasForeignKey(s => s.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<PublicationEntity>(e =>
        {
            e.HasOne(p => p.Client)
                .WithMany(c => c.Publications)
                .HasForeignKey(p => p.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
        });

        modelBuilder.Entity<InvoiceEntity>(e =>
        {
            e.HasOne(i => i.Client)
                .WithMany(c => c.Invoices)
                .HasForeignKey(i => i.ClientId)
                .OnDelete(DeleteBehavior.Cascade);
        });
    }
}
