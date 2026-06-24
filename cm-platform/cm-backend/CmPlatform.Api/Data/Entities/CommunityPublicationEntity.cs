using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;
using CmPlatform.Api.Models;

namespace CmPlatform.Api.Data.Entities;

[Table("community_publications")]
public class CommunityPublicationEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    [Column("review_token")]
    [MaxLength(16)]
    public string ReviewToken { get; set; } = Guid.NewGuid().ToString("N")[..10];

    [Column("platform")]
    [MaxLength(50)]
    public string Platform { get; set; } = "instagram";

    [Column("content_type")]
    [MaxLength(50)]
    public string ContentType { get; set; } = "";

    [Column("status")]
    [MaxLength(50)]
    public string Status { get; set; } = CommunityPublicationStatus.PendingReview;

    [Column("review_stage")]
    [MaxLength(50)]
    public string ReviewStage { get; set; } = CommunityReviewStage.Final;

    [Column("topic")]
    [MaxLength(500)]
    public string Topic { get; set; } = "";

    [Column("angle")]
    [MaxLength(1000)]
    public string Angle { get; set; } = "";

    [Column("objective")]
    [MaxLength(1000)]
    public string Objective { get; set; } = "";

    [Column("caption")]
    public string Caption { get; set; } = "";

    [Column("alt_text")]
    public string AltText { get; set; } = "";

    [Column("hashtags_json")]
    public string HashtagsJson { get; set; } = "[]";

    [Column("strategy_json")]
    public string StrategyJson { get; set; } = "{}";

    [Column("copy_json")]
    public string CopyJson { get; set; } = "{}";

    [Column("design_json")]
    public string DesignJson { get; set; } = "{}";

    [Column("evaluation_json")]
    public string EvaluationJson { get; set; } = "{}";

    [Column("video_duration_seconds")]
    public int VideoDurationSeconds { get; set; } = 12;

    [Column("version")]
    public int Version { get; set; } = 1;

    [Column("review_subject")]
    [MaxLength(500)]
    public string ReviewSubject { get; set; } = "";

    [Column("last_reviewer_feedback")]
    public string LastReviewerFeedback { get; set; } = "";

    [Column("reviewer_feedback_history_json")]
    public string ReviewerFeedbackHistoryJson { get; set; } = "[]";

    [Column("last_revision_target")]
    [MaxLength(50)]
    public string LastRevisionTarget { get; set; } = CommunityRevisionTarget.All;

    [Column("last_error")]
    public string LastError { get; set; } = "";

    [Column("approved_at")]
    public DateTimeOffset? ApprovedAt { get; set; }

    [Column("rejected_at")]
    public DateTimeOffset? RejectedAt { get; set; }

    [Column("published_at")]
    public DateTimeOffset? PublishedAt { get; set; }

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;

    [Column("updated_at")]
    public DateTimeOffset UpdatedAt { get; set; } = DateTimeOffset.UtcNow;
}
