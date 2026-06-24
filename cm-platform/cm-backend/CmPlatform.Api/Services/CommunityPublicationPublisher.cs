using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Models;

namespace CmPlatform.Api.Services;

public sealed class CommunityPublicationPublisher(
    IAgentClient agentClient,
    ILogger<CommunityPublicationPublisher> logger)
{
    private static readonly HashSet<string> SupportedContentTypes = new(StringComparer.OrdinalIgnoreCase)
    {
        "image_post",
        "video_post",
    };

    public async Task<AgentCommunityPublishResult?> PublishApprovedDraftAsync(
        CommunityPublicationEntity draft,
        CancellationToken ct = default)
    {
        if (!SupportedContentTypes.Contains(draft.ContentType))
        {
            draft.Status = CommunityPublicationStatus.Approved;
            draft.LastError = $"Publishing is disabled for community content type '{draft.ContentType}'. Supported values: {string.Join(", ", SupportedContentTypes)}.";
            draft.UpdatedAt = DateTimeOffset.UtcNow;
            logger.LogWarning("Skipping publish for draft {DraftId} because content type {ContentType} is disabled", draft.Id, draft.ContentType);
            return null;
        }

        var publishResult = await agentClient.PublishCommunityDraftAsync(
            draft.StrategyJson,
            draft.CopyJson,
            draft.DesignJson,
            ct);

        if (publishResult is null)
        {
            draft.Status = CommunityPublicationStatus.Approved;
            draft.LastError = "The Python agent failed to publish the approved draft.";
            draft.UpdatedAt = DateTimeOffset.UtcNow;
            logger.LogWarning("Publishing approved draft {DraftId} failed because the Python agent did not return a publish result", draft.Id);
            return null;
        }

        draft.LastError = BuildLastError(publishResult);
        if (publishResult.InstagramSuccess)
        {
            draft.Status = CommunityPublicationStatus.Published;
            draft.PublishedAt = publishResult.PublishedAt ?? DateTimeOffset.UtcNow;
            logger.LogInformation("Approved draft {DraftId} published successfully to Instagram", draft.Id);
        }
        else
        {
            draft.Status = CommunityPublicationStatus.Approved;
            logger.LogWarning("Approved draft {DraftId} could not be published to Instagram: {LastError}", draft.Id, draft.LastError);
        }

        draft.UpdatedAt = DateTimeOffset.UtcNow;
        return publishResult;
    }

    internal static string BuildLastError(AgentCommunityPublishResult publishResult)
    {
        return publishResult.InstagramSuccess
            ? string.Join(" | ", publishResult.Results.Where(result => !result.Success).Select(result => result.Error).Where(error => !string.IsNullOrWhiteSpace(error)))
            : string.Join(" | ", publishResult.Results.Select(result => result.Error).Where(error => !string.IsNullOrWhiteSpace(error)));
    }
}
