using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;
using CmPlatform.Api.Controllers;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Models;
using CmPlatform.Api.Services;

namespace CmPlatform.Api.Tests;

public class CommunityReviewControllerTests
{
    [Fact]
    public async Task RejectWithFeedback_QueuesRevision_WhenFeedbackIsPresent()
    {
        await using var db = CreateDbContext();
        var draft = CreateDraft();
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var agentClient = new FakeAgentClient
        {
            RevisedDraft = CreateRevisedDraftPayload()
        };

        var controller = CreateController(db, agentClient);

        var result = await controller.RejectWithFeedback(draft.ReviewToken, "Mover el grafico lejos del logo", "reject", CancellationToken.None);

        Assert.IsType<ContentResult>(result);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.RevisionQueued, saved.Status);
        Assert.Equal("Tema original", saved.Topic);
        Assert.Equal("Mover el grafico lejos del logo", saved.LastReviewerFeedback);
        Assert.Null(saved.RejectedAt);
        Assert.Equal(1, saved.Version);
        Assert.Equal(0, agentClient.ReviseCallCount);
    }

    [Fact]
    public async Task RejectWithFeedback_QueuesRevision_WhenFeedbackIsPresentAndAgentFails()
    {
        await using var db = CreateDbContext();
        var draft = CreateDraft();
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var controller = CreateController(db, new FakeAgentClient());

        var result = await controller.RejectWithFeedback(draft.ReviewToken, "Mover el grafico lejos del logo", "reject", CancellationToken.None);

        Assert.IsType<ContentResult>(result);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.RevisionQueued, saved.Status);
        Assert.Equal("Mover el grafico lejos del logo", saved.LastReviewerFeedback);
        Assert.Null(saved.RejectedAt);
    }

    [Fact]
    public async Task Approve_QueuesMediaGeneration_WhenDraftIsPreMediaReview()
    {
        await using var db = CreateDbContext();
        var draft = CreateDraft();
        draft.ReviewStage = CommunityReviewStage.PreMedia;
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var controller = CreateController(db, new FakeAgentClient());

        var result = await controller.Approve(draft.ReviewToken, CancellationToken.None);

        var content = Assert.IsType<ContentResult>(result);
        Assert.Contains("Plan aprobado", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.MediaGenerationQueued, saved.Status);
        Assert.Equal(CommunityReviewStage.PreMedia, saved.ReviewStage);
        Assert.Null(saved.ApprovedAt);
        Assert.Null(saved.RejectedAt);
    }

    [Fact]
    public async Task RejectWithFeedback_ShowsGenerationInProgress_WhenMediaGenerationAlreadyQueued()
    {
        await using var db = CreateDbContext();
        var draft = CreateDraft();
        draft.Status = CommunityPublicationStatus.MediaGenerationQueued;
        draft.ReviewStage = CommunityReviewStage.PreMedia;
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var controller = CreateController(db, new FakeAgentClient());

        var result = await controller.RejectWithFeedback(draft.ReviewToken, "Cambiar la apertura", "reject", CancellationToken.None);

        Assert.IsType<ContentResult>(result);

        var saved = await db.CommunityPublications.SingleAsync();
        Assert.Equal(CommunityPublicationStatus.MediaGenerationQueued, saved.Status);
        Assert.Equal(CommunityReviewStage.PreMedia, saved.ReviewStage);
    }

    [Fact]
    public async Task Approve_ShowsDeniedMessage_WhenDraftWasDenied()
    {
        await using var db = CreateDbContext();
        var draft = CreateDraft();
        draft.Status = CommunityPublicationStatus.Denied;
        db.CommunityPublications.Add(draft);
        await db.SaveChangesAsync();

        var controller = CreateController(db, new FakeAgentClient());

        var result = await controller.Approve(draft.ReviewToken, CancellationToken.None);

        var content = Assert.IsType<ContentResult>(result);
        Assert.Contains("denegada", content.Content ?? string.Empty, StringComparison.OrdinalIgnoreCase);
    }

    private static CommunityReviewController CreateController(NovitDbContext db, IAgentClient agentClient)
    {
        var publisher = new CommunityPublicationPublisher(agentClient, NullLogger<CommunityPublicationPublisher>.Instance);
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

        return new CommunityReviewController(
            db,
            publisher,
            agentClient,
            reviewService,
            NullLogger<CommunityReviewController>.Instance);
    }

    private static NovitDbContext CreateDbContext()
    {
        var options = new DbContextOptionsBuilder<NovitDbContext>()
            .UseInMemoryDatabase(Guid.NewGuid().ToString("N"))
            .Options;

        return new NovitDbContext(options);
    }

    private static CommunityPublicationEntity CreateDraft() => new()
    {
        ReviewToken = "review12345",
        Status = CommunityPublicationStatus.PendingReview,
        ReviewSubject = "[REVISIÃ“N CM review12345 v1] Tema",
        Topic = "Tema original",
        Angle = "Angulo original",
        Objective = "Objetivo original",
        ContentType = "image_post",
        Caption = "Caption original",
        AltText = "Alt text original",
        StrategyJson = "{}",
        CopyJson = "{}",
        DesignJson = "{}",
        EvaluationJson = "{}",
        HashtagsJson = "[]",
        ReviewerFeedbackHistoryJson = "[]",
        LastRevisionTarget = CommunityRevisionTarget.All,
        ReviewStage = CommunityReviewStage.Final,
        Version = 1,
    };

    private static CommunityDraftPayload CreateRevisedDraftPayload() => new(
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
        MediaUrls: [],
        MediaBlobNames: [],
        VideoDurationSeconds: 12);

    private sealed class FakeMailService : INurturingMailService
    {
        public bool IsConfigured => false;

        public Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default) =>
            Task.FromResult<IReadOnlyList<IncomingEmail>>([]);

        public Task SendBulkEmailAsync(IReadOnlyList<string> recipients, string subject, string body, bool isHtml = false, CancellationToken ct = default) => Task.CompletedTask;

        public Task MarkAsReadAsync(IReadOnlyList<string> messageIds, CancellationToken ct = default) => Task.CompletedTask;
    }

    private sealed class FakeAgentClient : IAgentClient
    {
        public bool IsConfigured => true;

        public CommunityDraftPayload? RevisedDraft { get; init; }
        public int ReviseCallCount { get; private set; }

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

        public Task<CommunityDraftPayload?> ReviseCommunityDraftAsync(string strategyJson, string copyJson, string designJson, string reviewerFeedback, string revisionTarget, string reviewerMemory, CancellationToken ct = default)
        {
            ReviseCallCount++;
            return Task.FromResult(RevisedDraft);
        }

        public Task<CommunityDraftPayload?> GenerateCommunityDraftAsync(string contentType, string reviewerMemory = "", IReadOnlyList<string>? publicationHistory = null, string? topic = null, string? angle = null, string? objective = null, int? numImages = null, CancellationToken ct = default) =>
            Task.FromResult<CommunityDraftPayload?>(null);

        public Task<bool> DeleteCommunityDraftMediaAsync(string designJson, CancellationToken ct = default) =>
            Task.FromResult(true);

        public Task<CommunityDraftPayload?> MaterializeCommunityDraftMediaAsync(string strategyJson, string copyJson, string designJson, CancellationToken ct = default) =>
            Task.FromResult<CommunityDraftPayload?>(null);

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
