using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Models;

namespace CmPlatform.Api.Services;

public sealed class CommunityApprovalBackgroundService(
    IServiceProvider services,
    ILogger<CommunityApprovalBackgroundService> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        logger.LogInformation("Community approval background service started");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var nextRunUtc = NurturingSchedule.GetNextRollingIntervalUtc(intervalMinutes: 5);
                var delay = nextRunUtc - DateTime.UtcNow;
                if (delay > TimeSpan.Zero)
                    await Task.Delay(delay, stoppingToken);

                await using var scope = services.CreateAsyncScope();
                var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();
                var configuration = scope.ServiceProvider.GetRequiredService<IConfiguration>();
                var mailService = scope.ServiceProvider.GetRequiredService<INurturingMailService>();
                var reviewService = scope.ServiceProvider.GetRequiredService<CommunityReviewService>();
                var agentClient = scope.ServiceProvider.GetRequiredService<IAgentClient>();
                var publisher = scope.ServiceProvider.GetRequiredService<CommunityPublicationPublisher>();
                var staleDraftMediaTtlDays = Math.Max(configuration.GetValue<int?>("Community:DraftMediaRetentionDays") ?? 14, 1);

                await ProcessQueuedRevisionsAsync(db, reviewService, agentClient, stoppingToken);
                await ProcessQueuedMediaGenerationAsync(db, reviewService, agentClient, stoppingToken);

                if (mailService.IsConfigured)
                    await ProcessPendingFeedbackAsync(db, mailService, reviewService, agentClient, stoppingToken);

                await ExpireStalePendingReviewDraftsAsync(db, agentClient, staleDraftMediaTtlDays, stoppingToken);

                await PublishApprovedDraftsAsync(db, publisher, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception ex)
            {
                logger.LogError(ex, "Unhandled error in community approval background service");
            }
        }

        logger.LogInformation("Community approval background service stopped");
    }

    private static async Task ProcessQueuedRevisionsAsync(
        NovitDbContext db,
        CommunityReviewService reviewService,
        IAgentClient agentClient,
        CancellationToken ct)
    {
        var queuedDrafts = await db.CommunityPublications
            .Where(draft => draft.Status == CommunityPublicationStatus.RevisionQueued)
            .OrderBy(draft => draft.UpdatedAt)
            .ToListAsync(ct);

        foreach (var draft in queuedDrafts)
        {
            if (string.IsNullOrWhiteSpace(draft.LastReviewerFeedback))
            {
                draft.Status = CommunityPublicationStatus.Rejected;
                draft.RejectedAt = DateTimeOffset.UtcNow;
                draft.LastError = "Queued revision had no reviewer feedback to retry.";
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                await db.SaveChangesAsync(ct);
                continue;
            }

            var reviewerMemory = await reviewService.BuildReviewerMemoryAsync(ct);
            var revised = await agentClient.ReviseCommunityDraftAsync(
                draft.StrategyJson,
                draft.CopyJson,
                draft.DesignJson,
                draft.LastReviewerFeedback,
                draft.LastRevisionTarget,
                reviewerMemory,
                ct);

            if (revised is null)
            {
                draft.LastError = "Automatic retry for queued review feedback failed. Will retry on the next loop.";
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                await db.SaveChangesAsync(ct);
                continue;
            }

            ApplyDraftPayload(draft, revised);
            draft.Version++;
            draft.Status = NormalizeDraftStatus(revised);
            draft.ReviewStage = CommunityReviewService.NormalizeReviewStage(revised.ReviewStage);
            draft.ApprovedAt = null;
            draft.RejectedAt = draft.Status == CommunityPublicationStatus.Denied ? DateTimeOffset.UtcNow : null;
            if (draft.Status == CommunityPublicationStatus.PendingReview)
                draft.ReviewSubject = reviewService.BuildReviewSubject(draft);
            draft.UpdatedAt = DateTimeOffset.UtcNow;
            draft.LastError = revised.FailureReason ?? string.Empty;

            await db.SaveChangesAsync(ct);
            if (draft.Status == CommunityPublicationStatus.PendingReview)
            {
                await reviewService.SendDraftForReviewAsync(draft, ct);
                await db.SaveChangesAsync(ct);
            }
        }
    }

    internal static async Task ProcessQueuedMediaGenerationAsync(
        NovitDbContext db,
        CommunityReviewService reviewService,
        IAgentClient agentClient,
        CancellationToken ct)
    {
        var queuedDrafts = await db.CommunityPublications
            .Where(draft => draft.Status == CommunityPublicationStatus.MediaGenerationQueued)
            .OrderBy(draft => draft.UpdatedAt)
            .ToListAsync(ct);

        foreach (var draft in queuedDrafts)
        {
            var materialized = await agentClient.MaterializeCommunityDraftMediaAsync(
                draft.StrategyJson,
                draft.CopyJson,
                draft.DesignJson,
                ct);

            if (materialized is null)
            {
                draft.LastError = "Media generation for the approved pre-media draft failed. Will retry on the next loop.";
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                await db.SaveChangesAsync(ct);
                continue;
            }

            ApplyDraftPayload(draft, materialized);
            draft.Version++;
            draft.Status = NormalizeDraftStatus(materialized);
            draft.ReviewStage = CommunityReviewService.NormalizeReviewStage(materialized.ReviewStage);
            draft.ApprovedAt = null;
            draft.RejectedAt = draft.Status == CommunityPublicationStatus.Denied ? DateTimeOffset.UtcNow : null;
            if (draft.Status == CommunityPublicationStatus.PendingReview)
                draft.ReviewSubject = reviewService.BuildReviewSubject(draft);
            draft.UpdatedAt = DateTimeOffset.UtcNow;
            draft.LastError = materialized.FailureReason ?? string.Empty;

            await db.SaveChangesAsync(ct);
            if (draft.Status == CommunityPublicationStatus.PendingReview)
            {
                await reviewService.SendDraftForReviewAsync(draft, ct);
                await db.SaveChangesAsync(ct);
            }
        }
    }

    private static async Task ProcessPendingFeedbackAsync(
        NovitDbContext db,
        INurturingMailService mailService,
        CommunityReviewService reviewService,
        IAgentClient agentClient,
        CancellationToken ct)
    {
        var reviewers = reviewService.GetReviewerList();
        if (reviewers.Count == 0)
            return;

        var reviewerSet = new HashSet<string>(reviewers, StringComparer.OrdinalIgnoreCase);
        var unanswered = await mailService.GetUnansweredRepliesAsync(14, ct);
        var pendingDrafts = await db.CommunityPublications
            .Where(draft => draft.Status == CommunityPublicationStatus.PendingReview)
            .OrderBy(draft => draft.CreatedAt)
            .ToListAsync(ct);

        var processedMessageIds = new List<string>();

        foreach (var draft in pendingDrafts)
        {
            var currentThreadKey = reviewService.BuildReviewThreadKey(draft);
            var feedbackEmails = unanswered
                .Where(email => reviewerSet.Contains(email.From) &&
                                email.Subject.Contains(currentThreadKey, StringComparison.OrdinalIgnoreCase))
                .ToList();

            if (feedbackEmails.Count == 0)
                continue;

            var rejectEmails = feedbackEmails.Where(email => CommunityReviewService.IsRejectRequest(email.Body)).ToList();
            var approveEmails = feedbackEmails.Where(email => CommunityReviewService.IsApprovalRequest(email.Body)).ToList();
            var revisionEmails = feedbackEmails.Except(rejectEmails).Except(approveEmails).ToList();

            if (rejectEmails.Count > 0)
            {
                processedMessageIds.AddRange(feedbackEmails.Select(email => email.MessageId));
                draft.Status = CommunityPublicationStatus.Rejected;
                draft.RejectedAt = DateTimeOffset.UtcNow;
                draft.LastReviewerFeedback = string.Join("\n\n---\n\n", rejectEmails.Select(email => CommunityReviewService.NormalizeFeedback(email.Body)));
                draft.LastRevisionTarget = CommunityRevisionTarget.All;
                draft.ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                    draft.ReviewerFeedbackHistoryJson,
                    rejectEmails,
                    CommunityPublicationStatus.Rejected,
                    CommunityRevisionTarget.All);
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                await db.SaveChangesAsync(ct);
                continue;
            }

            if (revisionEmails.Count > 0)
            {
                var combinedFeedback = string.Join("\n\n---\n\n", revisionEmails.Select(email => $"De {email.From}:\n{CommunityReviewService.NormalizeFeedback(email.Body)}"));
                var revisionTarget = CommunityReviewService.MergeRevisionTargets(
                    revisionEmails.Select(email => CommunityReviewService.DetectRevisionTarget(email.Body)));
                var reviewerMemory = await reviewService.BuildReviewerMemoryAsync(ct);
                var revised = await agentClient.ReviseCommunityDraftAsync(
                    draft.StrategyJson,
                    draft.CopyJson,
                    draft.DesignJson,
                    combinedFeedback,
                    revisionTarget,
                    reviewerMemory,
                    ct);

                if (revised is null)
                {
                    draft.LastError = "The Python agent failed to revise the draft from reviewer feedback.";
                    draft.UpdatedAt = DateTimeOffset.UtcNow;
                    await db.SaveChangesAsync(ct);
                    continue;
                }

                processedMessageIds.AddRange(feedbackEmails.Select(email => email.MessageId));
                ApplyDraftPayload(draft, revised);
                draft.Version++;
                draft.Status = NormalizeDraftStatus(revised);
                draft.ReviewStage = CommunityReviewService.NormalizeReviewStage(revised.ReviewStage);
                draft.LastReviewerFeedback = combinedFeedback;
                draft.LastRevisionTarget = revisionTarget;
                draft.ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                    draft.ReviewerFeedbackHistoryJson,
                    revisionEmails,
                    CommunityPublicationStatus.PendingReview,
                    revisionTarget);
                draft.ApprovedAt = null;
                draft.RejectedAt = draft.Status == CommunityPublicationStatus.Denied ? DateTimeOffset.UtcNow : null;
                if (draft.Status == CommunityPublicationStatus.PendingReview)
                    draft.ReviewSubject = reviewService.BuildReviewSubject(draft);
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                draft.LastError = revised.FailureReason ?? string.Empty;

                await db.SaveChangesAsync(ct);
                if (draft.Status == CommunityPublicationStatus.PendingReview)
                {
                    await reviewService.SendDraftForReviewAsync(draft, ct);
                    await db.SaveChangesAsync(ct);
                }
                continue;
            }

            if (approveEmails.Count > 0)
            {
                processedMessageIds.AddRange(feedbackEmails.Select(email => email.MessageId));
                if (CommunityReviewService.NormalizeReviewStage(draft.ReviewStage) == CommunityReviewStage.PreMedia)
                {
                    draft.Status = CommunityPublicationStatus.MediaGenerationQueued;
                    draft.ApprovedAt = null;
                    draft.LastError = string.Empty;
                    draft.ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                        draft.ReviewerFeedbackHistoryJson,
                        approveEmails,
                        "approved_pre_media",
                        draft.LastRevisionTarget);
                }
                else
                {
                    draft.Status = CommunityPublicationStatus.Approved;
                    draft.ApprovedAt = DateTimeOffset.UtcNow;
                    draft.ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                        draft.ReviewerFeedbackHistoryJson,
                        approveEmails,
                        CommunityPublicationStatus.Approved,
                        draft.LastRevisionTarget);
                }

                draft.RejectedAt = null;
                draft.UpdatedAt = DateTimeOffset.UtcNow;
                await db.SaveChangesAsync(ct);
            }
        }

        if (processedMessageIds.Count > 0)
            await mailService.MarkAsReadAsync(processedMessageIds, ct);
    }

    private static async Task PublishApprovedDraftsAsync(
        NovitDbContext db,
        CommunityPublicationPublisher publisher,
        CancellationToken ct)
    {
        var approvedDrafts = await db.CommunityPublications
            .Where(draft => draft.Status == CommunityPublicationStatus.Approved && draft.PublishedAt == null)
            .OrderBy(draft => draft.CreatedAt)
            .ToListAsync(ct);

        foreach (var draft in approvedDrafts)
        {
            await publisher.PublishApprovedDraftAsync(draft, ct);
            await db.SaveChangesAsync(ct);
        }
    }

    internal static async Task ExpireStalePendingReviewDraftsAsync(
        NovitDbContext db,
        IAgentClient agentClient,
        int ttlDays,
        CancellationToken ct)
    {
        var cutoff = DateTimeOffset.UtcNow.AddDays(-Math.Max(ttlDays, 1));
        var staleDrafts = await db.CommunityPublications
            .Where(draft =>
                draft.PublishedAt == null &&
                draft.UpdatedAt < cutoff &&
                (draft.Status == CommunityPublicationStatus.PendingReview ||
                 draft.Status == CommunityPublicationStatus.RevisionQueued ||
                 draft.Status == CommunityPublicationStatus.MediaGenerationQueued))
            .OrderBy(draft => draft.UpdatedAt)
            .ToListAsync(ct);

        foreach (var draft in staleDrafts)
        {
            await agentClient.DeleteCommunityDraftMediaAsync(draft.DesignJson, ct);

            draft.Status = CommunityPublicationStatus.Rejected;
            draft.RejectedAt ??= DateTimeOffset.UtcNow;
            draft.LastReviewerFeedback = string.IsNullOrWhiteSpace(draft.LastReviewerFeedback)
                ? "Auto-rejected after exceeding the review window without reviewer response."
                : draft.LastReviewerFeedback;
            draft.LastError = $"Draft expired without reviewer response after {ttlDays} days. Remote media cleanup was requested.";
            draft.UpdatedAt = DateTimeOffset.UtcNow;
        }

        if (staleDrafts.Count > 0)
            await db.SaveChangesAsync(ct);
    }

    private static void ApplyDraftPayload(CommunityPublicationEntity draft, CommunityDraftPayload payload)
    {
        draft.Topic = payload.Topic;
        draft.Angle = payload.Angle;
        draft.Objective = payload.Objective;
        draft.ContentType = payload.ContentType;
        draft.Caption = payload.Caption;
        draft.AltText = payload.AltText;
        draft.HashtagsJson = JsonSerializer.Serialize(payload.Hashtags);
        draft.StrategyJson = payload.StrategyJson;
        draft.CopyJson = payload.CopyJson;
        draft.DesignJson = payload.DesignJson;
        draft.EvaluationJson = payload.EvaluationJson;
        draft.VideoDurationSeconds = payload.VideoDurationSeconds;
    }

    private static string NormalizeDraftStatus(CommunityDraftPayload payload) =>
        string.Equals(payload.DraftStatus, CommunityPublicationStatus.Denied, StringComparison.OrdinalIgnoreCase)
            ? CommunityPublicationStatus.Denied
            : CommunityPublicationStatus.PendingReview;
}
