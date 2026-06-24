using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using System.Text.Json;
using CmPlatform.Api.Controllers;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Models;
using CmPlatform.Api.Services;

namespace CmPlatform.Api.Tests;

public class CommunityControllerTests
{
    [Fact]
    public async Task TriggerPublishOnDemand_QueuesDraftForReview_WithEditorialOverrides()
    {
        await using var db = CreateDbContext();
        var agentClient = new CapturingAgentClient
        {
            DraftKickResult = new AgentCommunityDraftKickResult(
                JobId: "job-123",
                Status: "started",
                ContentType: "image_post",
                Topic: "Nueva regulaciÃ³n para importadores",
                Angle: "QuÃ© cambia operativamente para una pyme",
                Objective: "Aprovechar noticia sectorial para abrir conversaciÃ³n comercial")
        };
        var controller = CreateController(db, agentClient);

        var result = await controller.TriggerPublishOnDemand(
            new CommunityController.CommunityPublishOnDemandRequest(
                ContentType: "image_post",
                Topic: "Nueva regulaciÃ³n para importadores",
                Angle: "QuÃ© cambia operativamente para una pyme",
                Objective: "Aprovechar noticia sectorial para abrir conversaciÃ³n comercial"),
            CancellationToken.None);

        var accepted = Assert.IsType<AcceptedResult>(result);
        Assert.Equal("image_post", agentClient.ContentType);
        Assert.Equal("Nueva regulaciÃ³n para importadores", agentClient.Topic);
        Assert.Equal("QuÃ© cambia operativamente para una pyme", agentClient.Angle);
        Assert.Equal("Aprovechar noticia sectorial para abrir conversaciÃ³n comercial", agentClient.Objective);
        Assert.NotNull(accepted.Value);

        Assert.Empty(await db.CommunityPublications.ToListAsync());
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(accepted.Value));
        Assert.Equal("job-123", json.RootElement.GetProperty("job_id").GetString());
        Assert.Equal("/api/community/trigger-publish/status/job-123", json.RootElement.GetProperty("status_endpoint").GetString());
    }

    [Fact]
    public async Task TriggerPublishOnDemand_PassesExplicitNumImages_ForImagePosts()
    {
        await using var db = CreateDbContext();
        var agentClient = new CapturingAgentClient
        {
            DraftKickResult = new AgentCommunityDraftKickResult(
                JobId: "job-456",
                Status: "started",
                ContentType: "image_post",
                Topic: "Tema",
                Angle: "Angulo",
                Objective: "Objetivo")
        };
        var controller = CreateController(db, agentClient);

        var result = await controller.TriggerPublishOnDemand(
            new CommunityController.CommunityPublishOnDemandRequest(
                ContentType: "image_post",
                Topic: "Tema",
                NumImages: 6),
            CancellationToken.None);

        Assert.IsType<AcceptedResult>(result);
        Assert.Equal("image_post", agentClient.ContentType);
        Assert.Equal(6, agentClient.NumImages);
    }

    [Fact]
    public async Task TriggerPublishOnDemand_AllowsVideoPosts_AndIgnoresNumImages()
    {
        await using var db = CreateDbContext();
        var agentClient = new CapturingAgentClient
        {
            DraftKickResult = new AgentCommunityDraftKickResult(
                JobId: "job-789",
                Status: "started",
                ContentType: "video_post",
                Topic: "Tema video",
                Angle: "Angulo video",
                Objective: "Objetivo video")
        };
        var controller = CreateController(db, agentClient);

        var result = await controller.TriggerPublishOnDemand(
            new CommunityController.CommunityPublishOnDemandRequest(
                ContentType: "video_post",
                Topic: "Tema video",
                NumImages: 4),
            CancellationToken.None);

        Assert.IsType<AcceptedResult>(result);
        Assert.Equal("video_post", agentClient.ContentType);
        Assert.Null(agentClient.NumImages);
    }

    [Fact]
    public async Task TriggerPublishOnDemand_RequiresAtLeastOneOverride()
    {
        await using var db = CreateDbContext();
        var controller = CreateController(db, new CapturingAgentClient());

        var result = await controller.TriggerPublishOnDemand(
            new CommunityController.CommunityPublishOnDemandRequest(ContentType: "image_post"),
            CancellationToken.None);

        Assert.IsType<BadRequestObjectResult>(result);
    }

    [Fact]
    public async Task GetTriggerPublishStatus_ReturnsDraftMetadata_WhenJobCompleted()
    {
        await using var db = CreateDbContext();
        var draft = new CommunityPublicationEntity
        {
            ContentType = "image_post",
            Status = CommunityPublicationStatus.PendingReview,
            Topic = "Tema revisado",
            Angle = "Angulo revisado",
            Objective = "Objetivo revisado",
            ReviewSubject = "[REVISIÃ“N] Tema revisado",
            ReviewToken = "rvw123",
        };
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var agentClient = new CapturingAgentClient
        {
            DraftJobStatusResult = new AgentCommunityDraftJobStatusResult(
                Found: true,
                JobId: "job-123",
                State: "completed",
                Step: "saved",
                ContentType: "image_post",
                Topic: draft.Topic,
                Angle: draft.Angle,
                Objective: draft.Objective,
                DraftId: draft.Id.ToString(),
                DraftStatus: CommunityPublicationStatus.PendingReview,
                ReviewSubject: draft.ReviewSubject,
                ReviewToken: draft.ReviewToken,
                FailureReason: null,
                Error: null,
                StartedAt: DateTimeOffset.UtcNow.AddMinutes(-2).ToString("O"),
                UpdatedAt: DateTimeOffset.UtcNow.AddMinutes(-1).ToString("O"),
                CompletedAt: DateTimeOffset.UtcNow.ToString("O"))
        };
        var controller = CreateController(db, agentClient);

        var result = await controller.GetTriggerPublishStatus("job-123", CancellationToken.None);

        var ok = Assert.IsType<OkObjectResult>(result);
        using var json = JsonDocument.Parse(JsonSerializer.Serialize(ok.Value));
        Assert.Equal("completed", json.RootElement.GetProperty("job").GetProperty("state").GetString());
        Assert.Equal(draft.Id.ToString(), json.RootElement.GetProperty("job").GetProperty("draft_id").GetString());
        Assert.Equal(CommunityPublicationStatus.PendingReview, json.RootElement.GetProperty("draft").GetProperty("status").GetString());
    }

    [Fact]
    public async Task ForcePublishDraft_PublishesPendingReviewDraft()
    {
        await using var db = CreateDbContext();
        var draft = new CommunityPublicationEntity
        {
            ContentType = "image_post",
            Status = CommunityPublicationStatus.PendingReview,
            Topic = "Tema revisado",
            Angle = "Angulo revisado",
            Objective = "Objetivo revisado",
            Caption = "Caption revisado",
            AltText = "Alt revisado",
            StrategyJson = "{\"step\":\"strategy\"}",
            CopyJson = "{\"step\":\"copy\"}",
            DesignJson = "{\"step\":\"design\"}",
            EvaluationJson = "{\"step\":\"evaluation\"}",
            HashtagsJson = "[\"novit\"]",
        };
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var agentClient = new CapturingAgentClient
        {
            PublishDraftResult = new AgentCommunityPublishResult(
                Results:
                [
                    new AgentPlatformPublishResult("instagram", true, "ig-123", null, "https://instagram.com/p/ig-123")
                ],
                PublishedAt: DateTimeOffset.UtcNow,
                AllSuccess: true)
        };
        var controller = CreateController(db, agentClient);

        var result = await controller.ForcePublishDraft(draft.Id, CancellationToken.None);

        Assert.IsType<OkObjectResult>(result);
        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.Published, saved.Status);
        Assert.NotNull(saved.ApprovedAt);
        Assert.NotNull(saved.PublishedAt);
    }

    [Fact]
    public async Task ForcePublishDraft_RejectsDeniedDraft()
    {
        await using var db = CreateDbContext();
        var draft = new CommunityPublicationEntity
        {
            ContentType = "image_post",
            Status = CommunityPublicationStatus.Denied,
            Topic = "Tema denegado",
            LastError = "No aprobado",
        };
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var controller = CreateController(db, new CapturingAgentClient());

        var result = await controller.ForcePublishDraft(draft.Id, CancellationToken.None);

        Assert.IsType<ConflictObjectResult>(result);
    }

    [Fact]
    public async Task ForcePublishDraft_RejectsPreMediaDraft()
    {
        await using var db = CreateDbContext();
        var draft = new CommunityPublicationEntity
        {
            ContentType = "image_post",
            Status = CommunityPublicationStatus.PendingReview,
            ReviewStage = CommunityReviewStage.PreMedia,
            Topic = "Tema pre-media",
            StrategyJson = "{\"step\":\"strategy\"}",
            CopyJson = "{\"step\":\"copy\"}",
            DesignJson = "{\"step\":\"design\"}",
            EvaluationJson = "{\"step\":\"evaluation\"}",
        };
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var controller = CreateController(db, new CapturingAgentClient());

        var result = await controller.ForcePublishDraft(draft.Id, CancellationToken.None);

        Assert.IsType<ConflictObjectResult>(result);
    }

    private static CommunityController CreateController(NovitDbContext db, IAgentClient agentClient)
    {
        var reviewService = new CommunityReviewService(
            new FakeMailService(),
            Options.Create(new NurturingOptions()),
            new ConfigurationBuilder()
                .AddInMemoryCollection(new Dictionary<string, string?>
                {
                    ["PublicBaseUrl"] = "https://ia.novitsoftware.com"
                })
                .Build(),
            db,
            NullLogger<CommunityReviewService>.Instance);

        var publisher = new CommunityPublicationPublisher(agentClient, NullLogger<CommunityPublicationPublisher>.Instance);

        return new CommunityController(
            db,
            publisher,
            agentClient,
            NullLogger<CommunityController>.Instance);
    }

    private static NovitDbContext CreateDbContext()
    {
        var options = new DbContextOptionsBuilder<NovitDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString("N"))
            .Options;

        return new NovitDbContext(options);
    }

    private static CommunityDraftPayload CreateDraftPayload() => new(
        ContentType: "image_post",
        Topic: "Tema revisado",
        Angle: "Angulo revisado",
        Objective: "Objetivo revisado",
        Caption: "Caption revisado",
        Hashtags: ["novit"],
        AltText: "Alt revisado",
        StrategyJson: "{\"step\":\"strategy\"}",
        CopyJson: "{\"step\":\"copy\"}",
        DesignJson: "{\"step\":\"design\"}",
        EvaluationJson: "{\"step\":\"evaluation\"}",
        MediaUrls: ["https://example.com/slide-1.png"],
        MediaBlobNames: ["slide-1.png"],
        VideoDurationSeconds: 12);

    private sealed class FakeMailService : INurturingMailService
    {
        public bool IsConfigured => false;

        public Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default) =>
            Task.FromResult<IReadOnlyList<IncomingEmail>>([]);

        public Task SendBulkEmailAsync(IReadOnlyList<string> recipients, string subject, string body, bool isHtml = false, CancellationToken ct = default) => Task.CompletedTask;

        public Task MarkAsReadAsync(IReadOnlyList<string> messageIds, CancellationToken ct = default) => Task.CompletedTask;
    }

    private sealed class CapturingAgentClient : IAgentClient
    {
        public bool IsConfigured => true;
        public AgentCommunityPublishResult? PublishDraftResult { get; init; }
        public AgentCommunityDraftKickResult? DraftKickResult { get; init; }
        public AgentCommunityDraftJobStatusResult? DraftJobStatusResult { get; init; }
        public string? ContentType { get; private set; }
        public string? Topic { get; private set; }
        public string? Angle { get; private set; }
        public string? Objective { get; private set; }
        public int? NumImages { get; private set; }

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

        public Task<AgentCommunityDraftKickResult?> KickCommunityDraftAsync(string contentType, string? topic = null, string? angle = null, string? objective = null, int? numImages = null, CancellationToken ct = default)
        {
            ContentType = contentType;
            Topic = topic;
            Angle = angle;
            Objective = objective;
            NumImages = numImages;
            return Task.FromResult(DraftKickResult);
        }

        public Task<AgentCommunityDraftJobStatusResult?> GetCommunityDraftJobStatusAsync(string jobId, CancellationToken ct = default) =>
            Task.FromResult(DraftJobStatusResult);

        public Task<CommunityDraftPayload?> GenerateCommunityDraftAsync(string contentType, string reviewerMemory = "", IReadOnlyList<string>? publicationHistory = null, string? topic = null, string? angle = null, string? objective = null, int? numImages = null, CancellationToken ct = default)
        {
            ContentType = contentType;
            Topic = topic;
            Angle = angle;
            Objective = objective;
            NumImages = numImages;
            return Task.FromResult<CommunityDraftPayload?>(null);
        }

        public Task<bool> DeleteCommunityDraftMediaAsync(string designJson, CancellationToken ct = default) =>
            Task.FromResult(true);

        public Task<CommunityDraftPayload?> MaterializeCommunityDraftMediaAsync(string strategyJson, string copyJson, string designJson, CancellationToken ct = default) =>
            Task.FromResult<CommunityDraftPayload?>(null);

        public Task<CommunityDraftPayload?> ReviseCommunityDraftAsync(string strategyJson, string copyJson, string designJson, string reviewerFeedback, string revisionTarget, string reviewerMemory, CancellationToken ct = default) =>
            Task.FromResult<CommunityDraftPayload?>(null);

        public Task<AgentCommunityPublishResult?> PublishCommunityDraftAsync(string strategyJson, string copyJson, string designJson, CancellationToken ct = default) =>
            Task.FromResult(PublishDraftResult);

        public Task<string?> PublishCommunityNowAsync(string contentType, string? topic = null, string? angle = null, string? objective = null, CancellationToken ct = default)
        {
            ContentType = contentType;
            Topic = topic;
            Angle = angle;
            Objective = objective;
            return Task.FromResult<string?>(null);
        }

        public Task<string?> WrapEmailAsync(string htmlBody, string? firstName = null, string? personalClosing = null, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<AgentStatusResult?> GetStatusAsync(CancellationToken ct = default) =>
            Task.FromResult<AgentStatusResult?>(null);
    }
}
