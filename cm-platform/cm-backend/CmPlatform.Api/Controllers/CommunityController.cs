using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Filters;
using CmPlatform.Api.Models;
using CmPlatform.Api.Services;

namespace CmPlatform.Api.Controllers;

/// <summary>
/// Admin endpoints for community content management.
/// Protected by API key (X-Api-Key header).
/// </summary>
[ApiController]
[Route("api/community")]
[RequireApiKey]
public sealed class CommunityController(
    NovitDbContext db,
    CommunityPublicationPublisher publisher,
    IAgentClient agentClient,
    ILogger<CommunityController> logger) : ControllerBase
{
    private const string DefaultContentType = "image_post";
    private static readonly HashSet<string> SupportedContentTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "image_post",
        "video_post",
    };

    public sealed record CommunityPublishOnDemandRequest(
        string? ContentType = null,
        string? Topic = null,
        string? Angle = null,
        string? Objective = null,
        int? NumImages = null);

    /// <summary>
    /// Trigger the full content generation pipeline and leave the result pending review.
    /// No publication happens until the draft is later approved by email or force-published.
    /// </summary>
    /// <param name="contentType">Content type: image_post or video_post (default: image_post)</param>
    [HttpPost("trigger-publish")]
    public async Task<IActionResult> TriggerPublish(
        [FromQuery] string contentType = "image_post",
        CancellationToken ct = default)
    {
        return await StartDraftAsync(
            new CommunityPublishOnDemandRequest(ContentType: contentType),
            requireOverrides: false,
            ct);
    }

    /// <summary>
    /// Trigger an on-demand community draft with explicit editorial inputs.
    /// The generated draft remains pending review until explicitly approved or force-published.
    /// </summary>
    [HttpPost("trigger-publish-on-demand")]
    public async Task<IActionResult> TriggerPublishOnDemand(
        [FromBody] CommunityPublishOnDemandRequest req,
        CancellationToken ct = default)
    {
        return await StartDraftAsync(req, requireOverrides: true, ct);
    }

    [HttpGet("trigger-publish/status/{jobId}")]
    public async Task<IActionResult> GetTriggerPublishStatus(string jobId, CancellationToken ct = default)
    {
        var job = await agentClient.GetCommunityDraftJobStatusAsync(jobId, ct);
        if (job is null)
        {
            return StatusCode(502, new
            {
                error = "The Python agent status endpoint is unavailable.",
                job_id = jobId,
            });
        }

        if (!job.Found)
        {
            return NotFound(new
            {
                error = $"No async community draft job found for id '{jobId}'.",
                job_id = jobId,
            });
        }

        object? draft = null;
        if (Guid.TryParse(job.DraftId, out var draftId))
        {
            var savedDraft = await db.CommunityPublications
                .AsNoTracking()
                .FirstOrDefaultAsync(item => item.Id == draftId, ct);

            if (savedDraft is not null)
            {
                draft = new
                {
                    id = savedDraft.Id,
                    status = savedDraft.Status,
                    review_stage = savedDraft.ReviewStage,
                    topic = savedDraft.Topic,
                    angle = savedDraft.Angle,
                    objective = savedDraft.Objective,
                    review_subject = string.IsNullOrWhiteSpace(savedDraft.ReviewSubject) ? null : savedDraft.ReviewSubject,
                    review_token = string.IsNullOrWhiteSpace(savedDraft.ReviewToken) ? null : savedDraft.ReviewToken,
                    last_error = string.IsNullOrWhiteSpace(savedDraft.LastError) ? null : savedDraft.LastError,
                    approved_at = savedDraft.ApprovedAt,
                    rejected_at = savedDraft.RejectedAt,
                    published_at = savedDraft.PublishedAt,
                    created_at = savedDraft.CreatedAt,
                    updated_at = savedDraft.UpdatedAt,
                };
            }
        }

        return Ok(new
        {
            job = new
            {
                job_id = job.JobId,
                state = job.State,
                step = job.Step,
                content_type = job.ContentType,
                topic = job.Topic,
                angle = job.Angle,
                objective = job.Objective,
                draft_id = job.DraftId,
                draft_status = job.DraftStatus,
                review_subject = job.ReviewSubject,
                review_token = job.ReviewToken,
                failure_reason = job.FailureReason,
                error = job.Error,
                started_at = job.StartedAt,
                updated_at = job.UpdatedAt,
                completed_at = job.CompletedAt,
            },
            draft,
        });
    }

    /// <summary>
    /// Publish a previously generated draft after human review.
    /// This is the API alternative to approving from the review email.
    /// </summary>
    [HttpPost("force-publish/{draftId:guid}")]
    public async Task<IActionResult> ForcePublishDraft(Guid draftId, CancellationToken ct = default)
    {
        var draft = await db.CommunityPublications.FirstOrDefaultAsync(item => item.Id == draftId, ct);
        if (draft is null)
            return NotFound(new { error = $"No community draft found for id '{draftId}'." });

        if (draft.Status == CommunityPublicationStatus.Published)
            return Conflict(new { error = "The draft was already published.", draft_id = draft.Id, status = draft.Status });

        if (draft.Status == CommunityPublicationStatus.Denied)
        {
            return Conflict(new
            {
                error = "Cannot publish a denied generation attempt. Regenerate or revise it first.",
                draft_id = draft.Id,
                status = draft.Status,
            });
        }

        if (draft.Status == CommunityPublicationStatus.Rejected || draft.Status == CommunityPublicationStatus.RevisionQueued)
        {
            return Conflict(new
            {
                error = $"Cannot publish a draft while it is in status '{draft.Status}'.",
                draft_id = draft.Id,
                status = draft.Status,
            });
        }

        if (draft.Status == CommunityPublicationStatus.MediaGenerationQueued)
        {
            return Conflict(new
            {
                error = "Cannot publish a draft while the final media is still being generated.",
                draft_id = draft.Id,
                status = draft.Status,
            });
        }

        if (draft.Status == CommunityPublicationStatus.PendingReview)
        {
            if (CommunityReviewService.NormalizeReviewStage(draft.ReviewStage) == CommunityReviewStage.PreMedia)
            {
                return Conflict(new
                {
                    error = "Cannot publish a pre-media draft before the final media is generated and approved.",
                    draft_id = draft.Id,
                    status = draft.Status,
                    review_stage = draft.ReviewStage,
                });
            }

            draft.Status = CommunityPublicationStatus.Approved;
            draft.ApprovedAt = DateTimeOffset.UtcNow;
            draft.RejectedAt = null;
            draft.UpdatedAt = DateTimeOffset.UtcNow;
        }

        var publishResult = await publisher.PublishApprovedDraftAsync(draft, ct);
        await db.SaveChangesAsync(ct);

        if (publishResult?.InstagramSuccess == true)
        {
            return Ok(new
            {
                status = CommunityPublicationStatus.Published,
                draft_id = draft.Id,
                published_at = draft.PublishedAt,
                instagram_success = true,
                all_success = publishResult.AllSuccess,
            });
        }

        return StatusCode(502, new
        {
            error = string.IsNullOrWhiteSpace(draft.LastError)
                ? "The approved draft could not be published."
                : draft.LastError,
            draft_id = draft.Id,
            status = draft.Status,
            instagram_success = false,
        });
    }

    private async Task<IActionResult> StartDraftAsync(
        CommunityPublishOnDemandRequest req,
        bool requireOverrides,
        CancellationToken ct)
    {
        var normalizedType = (req.ContentType ?? string.Empty).Trim().ToLowerInvariant();
        if (string.IsNullOrWhiteSpace(normalizedType))
            normalizedType = DefaultContentType;

        if (!SupportedContentTypes.Contains(normalizedType))
        {
            return BadRequest(new
            {
                error = $"Unsupported content type '{req.ContentType}'. Supported values: {string.Join(", ", SupportedContentTypes)}."
            });
        }

        var numImages = req.NumImages;
        if (string.Equals(normalizedType, "image_post", StringComparison.Ordinal))
        {
            if (numImages is < 2 or > 6)
            {
                return BadRequest(new
                {
                    error = "When provided, 'numImages' must be between 2 and 6 for image_post drafts."
                });
            }
        }
        else
        {
            numImages = null;
        }

        var topic = NormalizeOverride(req.Topic);
        var angle = NormalizeOverride(req.Angle);
        var objective = NormalizeOverride(req.Objective);

        if (requireOverrides && topic is null && angle is null && objective is null)
        {
            return BadRequest(new
            {
                error = "Provide at least one of 'topic', 'angle', or 'objective' for on-demand publishing."
            });
        }

        logger.LogInformation(
            "Community draft generation triggered for content type {ContentType} (topic={Topic}, angle={Angle}, objective={Objective})",
            normalizedType,
            topic ?? "<auto>",
            angle ?? "<auto>",
            objective ?? "<auto>");

        var job = await agentClient.KickCommunityDraftAsync(
            normalizedType,
            topic: topic,
            angle: angle,
            objective: objective,
            numImages: numImages,
            ct: CancellationToken.None);

        if (job is null || string.IsNullOrWhiteSpace(job.JobId))
            return StatusCode(502, new { error = "The Python agent failed to start the reviewable draft generation job." });

        return Accepted(new
        {
            message = "Draft generation started in background. Poll the status endpoint to see when the draft is persisted and sent for review.",
            status = job.Status,
            job_id = job.JobId,
            status_endpoint = $"/api/community/trigger-publish/status/{job.JobId}",
            content_type = job.ContentType,
            topic = job.Topic,
            angle = job.Angle,
            objective = job.Objective,
            num_images = numImages,
        });
    }

    private static string? NormalizeOverride(string? value)
    {
        var normalized = (value ?? string.Empty).Trim();
        return string.IsNullOrWhiteSpace(normalized) ? null : normalized;
    }
}
