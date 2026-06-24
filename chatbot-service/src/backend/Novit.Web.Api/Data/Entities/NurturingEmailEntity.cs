using System.ComponentModel.DataAnnotations;
using System.ComponentModel.DataAnnotations.Schema;

namespace Novit.Web.Api.Data.Entities;

/// <summary>Tracks nurturing newsletter cycles and their reply state.</summary>
[Table("nurturing_emails")]
public class NurturingEmailEntity
{
    [Key]
    [Column("id")]
    public Guid Id { get; set; } = Guid.NewGuid();

    /// <summary>Cycle key for this newsletter slot (e.g. "2026-03-c1").</summary>
    [Column("month_key")]
    [MaxLength(10)]
    public string MonthKey { get; set; } = "";

    /// <summary>The generated newsletter body (plain text).</summary>
    [Column("body")]
    public string Body { get; set; } = "";

    /// <summary>Optional long-form report title for the AI Radar artifact.</summary>
    [Column("report_title")]
    [MaxLength(500)]
    public string? ReportTitle { get; set; }

    /// <summary>Optional executive summary stored separately for reuse in previews and exports.</summary>
    [Column("executive_summary")]
    public string? ExecutiveSummary { get; set; }

    /// <summary>Optional JSON payload with report artifact metadata such as Doc/PDF URLs, sources and charts.</summary>
    [Column("artifact_json")]
    public string? ArtifactJson { get; set; }

    /// <summary>Subject line for the email.</summary>
    [Column("subject")]
    [MaxLength(500)]
    public string Subject { get; set; } = "";

    /// <summary>Scheduled send date for the cycle slot.</summary>
    [Column("scheduled_send_date")]
    public DateTimeOffset ScheduledSendDate { get; set; }

    /// <summary>True once the newsletter has been sent.</summary>
    [Column("is_sent")]
    public bool IsSent { get; set; }

    /// <summary>True when a reviewer has requested the newsletter not be sent (standby).
    /// The newsletter stays on hold until a reviewer explicitly resumes it.</summary>
    [Column("is_on_hold")]
    public bool IsOnHold { get; set; }

    /// <summary>Revision version number. Starts at 1, increments with each reviewer revision.</summary>
    [Column("version")]
    public int Version { get; set; } = 1;

    /// <summary>Actual send timestamp (null until sent).</summary>
    [Column("sent_at")]
    public DateTimeOffset? SentAt { get; set; }

    [Column("created_at")]
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
}
