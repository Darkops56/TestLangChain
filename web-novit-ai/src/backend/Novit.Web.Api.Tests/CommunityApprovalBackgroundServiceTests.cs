using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using Novit.Web.Api.Data;
using Novit.Web.Api.Data.Entities;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Tests;

public class CommunityApprovalBackgroundServiceTests
{
    [Fact]
    public async Task ExpireStalePendingReviewDraftsAsync_RejectsAndRequestsMediaCleanup()
    {
        await using var db = CreateDbContext();
        var staleDraft = new CommunityPublicationEntity
        {
            Status = CommunityPublicationStatus.PendingReview,
            DesignJson = "{\"images\":[{\"url\":\"https://example.com/slide-1.png\",\"blob_name\":\"social/slide-1.png\"}]}",
            UpdatedAt = DateTimeOffset.UtcNow.AddDays(-20),
        };
        db.CommunityPublications.Add(staleDraft);
        await db.SaveChangesAsync();

        var agentClient = new CleanupCapturingAgentClient();

        await CommunityApprovalBackgroundService.ExpireStalePendingReviewDraftsAsync(db, agentClient, ttlDays: 14, CancellationToken.None);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.Rejected, saved.Status);
        Assert.NotNull(saved.RejectedAt);
        Assert.Contains("expired without reviewer response", saved.LastError, StringComparison.OrdinalIgnoreCase);
        Assert.Single(agentClient.CleanupRequests);
        Assert.Equal(staleDraft.DesignJson, agentClient.CleanupRequests[0]);
    }

    [Fact]
    public async Task ExpireStalePendingReviewDraftsAsync_IgnoresFreshDrafts()
    {
        await using var db = CreateDbContext();
        db.CommunityPublications.Add(new CommunityPublicationEntity
        {
            Status = CommunityPublicationStatus.PendingReview,
            DesignJson = "{\"images\":[]}",
            UpdatedAt = DateTimeOffset.UtcNow.AddDays(-2),
        });
        await db.SaveChangesAsync();

        var agentClient = new CleanupCapturingAgentClient();

        await CommunityApprovalBackgroundService.ExpireStalePendingReviewDraftsAsync(db, agentClient, ttlDays: 14, CancellationToken.None);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.PendingReview, saved.Status);
        Assert.Empty(agentClient.CleanupRequests);
    }

    [Fact]
    public async Task ProcessQueuedMediaGenerationAsync_PromotesDraftToFinalReview()
    {
        await using var db = CreateDbContext();
        var draft = new CommunityPublicationEntity
        {
            Status = CommunityPublicationStatus.MediaGenerationQueued,
            ReviewStage = CommunityReviewStage.PreMedia,
            ContentType = "image_post",
            Topic = "Tema base",
            Angle = "Angulo base",
            Objective = "Objetivo base",
            Caption = "Caption base",
            AltText = "Alt base",
            StrategyJson = "{\"step\":\"strategy\"}",
            CopyJson = "{\"step\":\"copy\"}",
            DesignJson = "{\"images\":[{\"prompt\":\"slide 1\"}]}",
            EvaluationJson = "{\"step\":\"evaluation\"}",
            HashtagsJson = "[\"novit\"]",
            ReviewSubject = "[REVISIÓN CM review12345 v1] Tema base",
            ReviewToken = "review12345",
            Version = 1,
        };
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var agentClient = new CleanupCapturingAgentClient
        {
            MaterializedDraft = new CommunityDraftPayload(
                ContentType: "image_post",
                Topic: "Tema final",
                Angle: "Angulo final",
                Objective: "Objetivo final",
                Caption: "Caption final",
                Hashtags: ["novit"],
                AltText: "Alt final",
                StrategyJson: "{\"step\":\"strategy\"}",
                CopyJson: "{\"step\":\"copy\"}",
                DesignJson: "{\"images\":[{\"prompt\":\"slide 1\",\"url\":\"https://example.com/slide-1.png\"}]}",
                EvaluationJson: "{\"step\":\"evaluation\"}",
                MediaUrls: ["https://example.com/slide-1.png"],
                MediaBlobNames: ["slide-1.png"],
                VideoDurationSeconds: 12,
                DraftStatus: CommunityPublicationStatus.PendingReview,
                ReviewStage: CommunityReviewStage.Final)
        };
        var reviewService = CreateReviewService(db);

        await CommunityApprovalBackgroundService.ProcessQueuedMediaGenerationAsync(db, reviewService, agentClient, CancellationToken.None);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.PendingReview, saved.Status);
        Assert.Equal(CommunityReviewStage.Final, saved.ReviewStage);
        Assert.Equal("Tema final", saved.Topic);
        Assert.Equal(2, saved.Version);
    }

    private static NovitDbContext CreateDbContext()
    {
        var options = new DbContextOptionsBuilder<NovitDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString("N"))
            .Options;

        return new NovitDbContext(options);
    }

    private static CommunityReviewService CreateReviewService(NovitDbContext db) =>
        new(
            new FakeMailService(),
            Options.Create(new NurturingOptions { ReviewerEmails = string.Empty }),
            new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["PublicBaseUrl"] = "https://ia.novitsoftware.com"
                })
                .Build(),
            db,
            NullLogger<CommunityReviewService>.Instance);

    private sealed class FakeMailService : INurturingMailService
    {
        public bool IsConfigured => false;

        public Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default) =>
            Task.FromResult<IReadOnlyList<IncomingEmail>>([]);

        public Task SendEmailAsync(string to, string subject, string body, bool isHtml = false, CancellationToken ct = default) => Task.CompletedTask;

        public Task SendBulkEmailAsync(IEnumerable<string> recipients, string subject, string body, bool isHtml = false, CancellationToken ct = default) => Task.CompletedTask;

        public Task SendReplyAsync(string to, string subject, string body, string inReplyToMessageId, bool isHtml = false, CancellationToken ct = default) => Task.CompletedTask;

        public Task MarkAsReadAsync(IEnumerable<string> messageIds, CancellationToken ct = default) => Task.CompletedTask;
    }

    private sealed class CleanupCapturingAgentClient : IAgentClient
    {
        public bool IsConfigured => true;
        public List<string> CleanupRequests { get; } = [];
        public CommunityDraftPayload? MaterializedDraft { get; init; }

        public Task<AgentReplyResult?> ForwardWebhookMessageAsync(string senderId, string text, string platform, string? messageId, CancellationToken ct = default, string? senderName = null, string? replyTargetId = null, string? replyTargetType = null, string? postContextId = null, string? postContextText = null) =>
            Task.FromResult<AgentReplyResult?>(null);

        public Task<AgentNewsletterResult?> GenerateNewsletterAsync(CancellationToken ct = default) =>
            Task.FromResult<AgentNewsletterResult?>(null);

        public Task<AgentNewsletterResult?> ReviseNewsletterAsync(string currentSubject, string currentBody, string reviewerFeedback, CancellationToken ct = default) =>
            Task.FromResult<AgentNewsletterResult?>(null);

        public Task<string?> GenerateReplyAsync(string originalSubject, string originalBody, string senderName, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<string?> GenerateClosingAsync(string newsletterSubject, string? newsletterBody, string? firstName, string? orgName, IReadOnlyList<string> dealNotes, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<AgentCommunityDraftKickResult?> KickCommunityDraftAsync(string contentType, string? topic = null, string? angle = null, string? objective = null, int? numImages = null, CancellationToken ct = default) =>
            Task.FromResult<AgentCommunityDraftKickResult?>(null);

        public Task<AgentCommunityDraftJobStatusResult?> GetCommunityDraftJobStatusAsync(string jobId, CancellationToken ct = default) =>
            Task.FromResult<AgentCommunityDraftJobStatusResult?>(null);

        public Task<CommunityDraftPayload?> ReviseCommunityDraftAsync(string strategyJson, string copyJson, string designJson, string reviewerFeedback, string revisionTarget, string reviewerMemory, CancellationToken ct = default) =>
            Task.FromResult<CommunityDraftPayload?>(null);

        public Task<CommunityDraftPayload?> GenerateCommunityDraftAsync(string contentType, string reviewerMemory = "", IReadOnlyList<string>? publicationHistory = null, string? topic = null, string? angle = null, string? objective = null, int? numImages = null, CancellationToken ct = default) =>
            Task.FromResult<CommunityDraftPayload?>(null);

        public Task<bool> DeleteCommunityDraftMediaAsync(string designJson, CancellationToken ct = default)
        {
            CleanupRequests.Add(designJson);
            return Task.FromResult(true);
        }

        public Task<CommunityDraftPayload?> MaterializeCommunityDraftMediaAsync(string strategyJson, string copyJson, string designJson, CancellationToken ct = default) =>
            Task.FromResult(MaterializedDraft);

        public Task<AgentCommunityPublishResult?> PublishCommunityDraftAsync(string strategyJson, string copyJson, string designJson, CancellationToken ct = default) =>
            Task.FromResult<AgentCommunityPublishResult?>(null);

        public Task<string?> PublishCommunityNowAsync(string contentType, string? topic = null, string? angle = null, string? objective = null, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<string?> WrapEmailAsync(string htmlBody, string? firstName = null, string? personalClosing = null, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<AgentStatusResult?> GetStatusAsync(CancellationToken ct = default) =>
            Task.FromResult<AgentStatusResult?>(null);
    }
}