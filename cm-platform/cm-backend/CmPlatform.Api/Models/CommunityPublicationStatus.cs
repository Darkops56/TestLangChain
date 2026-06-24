namespace CmPlatform.Api.Models;

public static class CommunityPublicationStatus
{
    public const string Denied = "denied";
    public const string PendingReview = "pending_review";
    public const string RevisionQueued = "revision_queued";
    public const string MediaGenerationQueued = "media_generation_queued";
    public const string Approved = "approved";
    public const string Rejected = "rejected";
    public const string Published = "published";
}

public static class CommunityReviewStage
{
    public const string PreMedia = "pre_media";
    public const string Final = "final";
}

public static class CommunityRevisionTarget
{
    public const string All = "all";
    public const string Copywriter = "copywriter";
    public const string Designer = "designer";
}
