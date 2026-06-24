namespace Novit.Web.Api.Models;

public sealed class NurturingOptions
{
    /// <summary>Master kill switch. Set to false (or env var Nurturing__Enabled=false) to disable
    /// the background service entirely without removing any other configuration.</summary>
    public bool Enabled { get; set; } = true;

    /// <summary>Controls automatic AI replies to lead responses. Set to false
    /// (or env var Nurturing__AutoReplyEnabled=false) to disable auto-replies
    /// while keeping newsletter generation, review, and sending fully operational.
    /// When false, replies must be handled manually.</summary>
    public bool AutoReplyEnabled { get; set; } = false;

    /// <summary>IMAP host for reading replies (e.g. imap.gmail.com).</summary>
    public string? ImapHost { get; set; }

    /// <summary>IMAP port (default 993 for SSL).</summary>
    public int ImapPort { get; set; } = 993;

    /// <summary>SMTP host for sending emails (e.g. smtp.gmail.com).</summary>
    public string? SmtpHost { get; set; }

    /// <summary>SMTP port (default 587 for STARTTLS).</summary>
    public int SmtpPort { get; set; } = 587;

    /// <summary>Login email used for IMAP/SMTP authentication (e.g. nicolasp@novitsoftware.com).
    /// This is the real Google Workspace account that owns the mailbox.</summary>
    public string? LoginEmail { get; set; }

    /// <summary>Password / app-specific password for <see cref="LoginEmail"/>.</summary>
    public string? EmailPassword { get; set; }

    /// <summary>Sender email shown in the From header (e.g. nicolasp@novitsoftware.com).
    /// Can be an alias of <see cref="LoginEmail"/>. If not set, <see cref="LoginEmail"/> is used.</summary>
    public string? SenderEmail { get; set; }

    /// <summary>Display name used in the From header (e.g. "Nicolás Piccardo").</summary>
    public string SenderName { get; set; } = "Nicolás Piccardo";

    /// <summary>Comma-separated list of recipient emails for newsletter sends.
    /// In production this comes from Pipedrive contacts; this override is for testing.</summary>
    public string? RecipientOverride { get; set; }

    /// <summary>Comma-separated reviewer emails who validate the newsletter before it is sent.
    /// The generated newsletter is sent to these addresses on Monday for review.</summary>
    public string ReviewerEmails { get; set; } = "rodrigo.vazquez@novit.com.ar,leav@novitsoftware.com";

    /// <summary>Azure AI Foundry endpoint for the complex model used for newsletter generation and revision.
    /// This is a separate, more capable model than the one used for lead replies.</summary>
    public string? NewsletterAIDeployment { get; set; }

    /// <summary>Deployment/model name required by the Responses API (for example: gpt-5.4).</summary>
    public string? NewsletterAIModel { get; set; }

    /// <summary>API key for the complex newsletter AI model.</summary>
    public string? NewsletterAIKey { get; set; }

    /// <summary>Serper.dev API key for real-time web search during newsletter generation.</summary>
    public string? SerperWebSearchApiKey { get; set; }

    /// <summary>True when the Serper.dev web search API is configured.</summary>
    public bool IsWebSearchConfigured => !string.IsNullOrWhiteSpace(SerperWebSearchApiKey);

    /// <summary>The effective email address used for authentication (IMAP/SMTP login).</summary>
    public string? EffectiveLoginEmail => LoginEmail;

    /// <summary>The effective sender address shown in outgoing From headers.
    /// Falls back to <see cref="LoginEmail"/> when <see cref="SenderEmail"/> is not set.</summary>
    public string? EffectiveFromAddress =>
        !string.IsNullOrWhiteSpace(SenderEmail) ? SenderEmail : LoginEmail;

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(ImapHost) &&
        !string.IsNullOrWhiteSpace(SmtpHost) &&
        !string.IsNullOrWhiteSpace(LoginEmail) &&
        !string.IsNullOrWhiteSpace(EmailPassword);

    /// <summary>True when the complex newsletter AI model is configured.</summary>
    public bool IsNewsletterAIConfigured =>
        !string.IsNullOrWhiteSpace(NewsletterAIDeployment) &&
        !string.IsNullOrWhiteSpace(NewsletterAIKey) &&
        (!UsesResponsesApi || !string.IsNullOrWhiteSpace(NewsletterAIModel));

    private bool UsesResponsesApi =>
        NewsletterAIDeployment?.Contains("/openai/responses", StringComparison.OrdinalIgnoreCase) == true ||
        NewsletterAIDeployment?.Contains("/openai/v1/responses", StringComparison.OrdinalIgnoreCase) == true;

    /// <summary>Parsed list of reviewer email addresses.</summary>
    public List<string> GetReviewerList() =>
        ReviewerEmails
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .ToList();
}
