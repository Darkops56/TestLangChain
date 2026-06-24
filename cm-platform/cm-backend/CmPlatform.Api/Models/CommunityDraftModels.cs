using System.Text.Json.Serialization;

namespace CmPlatform.Api.Models;

public sealed record CommunityDraftPayload(
    [property: JsonPropertyName("content_type")] string ContentType,
    [property: JsonPropertyName("topic")] string Topic,
    [property: JsonPropertyName("angle")] string Angle,
    [property: JsonPropertyName("objective")] string Objective,
    [property: JsonPropertyName("caption")] string Caption,
    [property: JsonPropertyName("hashtags")] IReadOnlyList<string> Hashtags,
    [property: JsonPropertyName("alt_text")] string AltText,
    [property: JsonPropertyName("strategy_json")] string StrategyJson,
    [property: JsonPropertyName("copy_json")] string CopyJson,
    [property: JsonPropertyName("design_json")] string DesignJson,
    [property: JsonPropertyName("evaluation_json")] string EvaluationJson,
    [property: JsonPropertyName("media_urls")] IReadOnlyList<string> MediaUrls,
    [property: JsonPropertyName("media_blob_names")] IReadOnlyList<string> MediaBlobNames,
    [property: JsonPropertyName("video_duration_seconds")] int VideoDurationSeconds,
    [property: JsonPropertyName("draft_status")] string DraftStatus = CommunityPublicationStatus.PendingReview,
    [property: JsonPropertyName("review_stage")] string ReviewStage = CommunityReviewStage.Final,
    [property: JsonPropertyName("failure_reason")] string? FailureReason = null,
    [property: JsonPropertyName("retry_count")] int RetryCount = 0);

public sealed record IncomingEmail(
    string MessageId,
    string From,
    string Subject,
    string Body,
    DateTimeOffset Date,
    string? InReplyTo);

public sealed record AgentPlatformPublishResult(
    [property: JsonPropertyName("platform")] string Platform,
    [property: JsonPropertyName("success")] bool Success,
    [property: JsonPropertyName("post_id")] string? PostId,
    [property: JsonPropertyName("error")] string? Error,
    [property: JsonPropertyName("permalink")] string? Permalink);

public sealed record AgentCommunityPublishResult(
    [property: JsonPropertyName("results")] IReadOnlyList<AgentPlatformPublishResult> Results,
    [property: JsonPropertyName("published_at")] DateTimeOffset? PublishedAt,
    [property: JsonPropertyName("all_success")] bool AllSuccess)
{
    public bool InstagramSuccess => Results.Any(result =>
        result.Success && result.Platform.Equals("instagram", StringComparison.OrdinalIgnoreCase));
}
