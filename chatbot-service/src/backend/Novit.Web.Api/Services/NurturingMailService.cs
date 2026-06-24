using System.Net;
using System.Net.Mail;
using System.Text.RegularExpressions;
using MailKit;
using MailKit.Net.Imap;
using MailKit.Search;
using Microsoft.Extensions.Options;
using MimeKit;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

/// <summary>
/// IMAP/SMTP mail service for the nurturing flow.
/// Supports separate login credentials and sender (alias) address — e.g. authenticate as
/// nicolasp@novitsoftware.com and send emails as Nicolás Piccardo &lt;nicolasp@novitsoftware.com&gt;.
/// Works with Gmail / Google Workspace, Zoho, or any standard IMAP+SMTP provider.
/// </summary>
public sealed class NurturingMailService : INurturingMailService
{
    private readonly NurturingOptions _options;
    private readonly ILogger<NurturingMailService> _logger;

    public NurturingMailService(IOptions<NurturingOptions> options, ILogger<NurturingMailService> logger)
    {
        _options = options.Value;
        _logger = logger;
    }

    public bool IsConfigured => _options.IsConfigured;

    public async Task<IReadOnlyList<IncomingEmail>> GetUnansweredRepliesAsync(int days = 30, CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            _logger.LogWarning("Nurturing mail not configured — skipping unanswered reply check");
            return [];
        }

        var results = new List<IncomingEmail>();

        try
        {
            using var client = new ImapClient();
            await client.ConnectAsync(_options.ImapHost, _options.ImapPort, MailKit.Security.SecureSocketOptions.SslOnConnect, ct);
            await client.AuthenticateAsync(_options.EffectiveLoginEmail, _options.EmailPassword, ct);

            var inbox = client.Inbox;
            await inbox.OpenAsync(FolderAccess.ReadOnly, ct);

            var since = DateTimeOffset.UtcNow.AddDays(-days);

            // Exclude messages sent from *both* the login account and the sender alias
            var loginEmail = _options.EffectiveLoginEmail!;
            var senderEmail = _options.EffectiveFromAddress!;

            var query = SearchQuery.DeliveredAfter(since.DateTime)
                .And(SearchQuery.Not(SearchQuery.FromContains(loginEmail)));

            // If the sender alias is different from the login, also exclude it
            if (!string.Equals(loginEmail, senderEmail, StringComparison.OrdinalIgnoreCase))
            {
                query = query.And(SearchQuery.Not(SearchQuery.FromContains(senderEmail)));
            }

            var uids = await inbox.SearchAsync(query, ct);

            // ── Build set of Message-IDs that WE sent (from Sent folder) ──
            // This is used to (a) detect already-answered threads and (b) verify
            // that incoming emails are genuine replies to messages we originated.
            var sentMessageIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            var answeredMessageIds = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            var sentFolder = (await client.GetFoldersAsync(client.PersonalNamespaces[0], cancellationToken: ct))
                .FirstOrDefault(f => f.Attributes.HasFlag(FolderAttributes.Sent))
                ?? (await client.GetFoldersAsync(client.PersonalNamespaces[0], cancellationToken: ct))
                    .FirstOrDefault(f => f.Name.Contains("Sent", StringComparison.OrdinalIgnoreCase));

            if (sentFolder is not null)
            {
                await sentFolder.OpenAsync(FolderAccess.ReadOnly, ct);
                var sentUids = await sentFolder.SearchAsync(SearchQuery.DeliveredAfter(since.DateTime), ct);
                foreach (var uid in sentUids)
                {
                    var sentMsg = await sentFolder.GetMessageAsync(uid, ct);

                    // Track every message we sent so we can verify In-Reply-To
                    if (!string.IsNullOrEmpty(sentMsg.MessageId))
                        sentMessageIds.Add(sentMsg.MessageId);

                    // Track which threads we already replied to
                    if (!string.IsNullOrEmpty(sentMsg.InReplyTo))
                        answeredMessageIds.Add(sentMsg.InReplyTo);
                }
            }

            _logger.LogInformation("Found {SentCount} sent message IDs and {AnsweredCount} answered thread IDs",
                sentMessageIds.Count, answeredMessageIds.Count);

            // Re-open inbox — opening sentFolder above implicitly closed it
            // (IMAP only allows one folder open per session)
            await inbox.OpenAsync(FolderAccess.ReadOnly, ct);

            foreach (var uid in uids)
            {
                var message = await inbox.GetMessageAsync(uid, ct);
                var messageId = message.MessageId ?? "";

                // Skip if we already replied to this message
                if (answeredMessageIds.Contains(messageId))
                    continue;

                // ── CRITICAL SAFETY CHECK ──
                // Only process emails that are genuine replies to messages WE sent.
                // This prevents auto-replying to spam, vendor newsletters, Google
                // notifications, or any other email that just happens to be in the inbox.
                var inReplyTo = message.InReplyTo;
                var isReplyToOurMessage = !string.IsNullOrEmpty(inReplyTo) && sentMessageIds.Contains(inReplyTo);

                // Also check References header as a fallback (some clients put it there)
                if (!isReplyToOurMessage && message.References is { Count: > 0 })
                {
                    isReplyToOurMessage = message.References.Any(r => sentMessageIds.Contains(r));
                }

                if (!isReplyToOurMessage)
                {
                    _logger.LogDebug("Skipping email from {From} ({Subject}) — not a reply to our sent messages",
                        message.From.Mailboxes.FirstOrDefault()?.Address, message.Subject);
                    continue;
                }

                results.Add(new IncomingEmail(
                    MessageId: messageId,
                    From: message.From.Mailboxes.FirstOrDefault()?.Address ?? "",
                    Subject: message.Subject ?? "",
                    Body: message.TextBody ?? message.HtmlBody ?? "",
                    Date: message.Date,
                    InReplyTo: message.InReplyTo));
            }

            await client.DisconnectAsync(true, ct);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to fetch unanswered replies via IMAP");
        }

        return results;
    }

    public async Task SendEmailAsync(string to, string subject, string body, bool isHtml = false, CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            _logger.LogWarning("Nurturing email not configured — skipping send to {To}", to);
            return;
        }

        using var smtp = CreateSmtpClient();

        var msg = new MailMessage(
            new MailAddress(_options.EffectiveFromAddress!, _options.SenderName),
            new MailAddress(to))
        {
            Subject = subject
        };

        if (isHtml)
            AttachHtmlWithPlainTextAlternative(msg, body);
        else
        {
            msg.Body = body;
            msg.IsBodyHtml = false;
        }

        await smtp.SendMailAsync(msg, ct);
        _logger.LogInformation("Nurturing email sent to {To}: {Subject}", to, subject);

        await LabelLastSentMessageAsync(subject, ct);
    }

    public async Task SendBulkEmailAsync(IEnumerable<string> recipients, string subject, string body, bool isHtml = false, CancellationToken ct = default)
    {
        if (!IsConfigured) return;

        var recipientList = recipients.ToList();
        if (recipientList.Count == 0) return;

        using var smtp = CreateSmtpClient();
        var from = new MailAddress(_options.EffectiveFromAddress!, _options.SenderName);

        var msg = new MailMessage
        {
            From = from,
            Subject = subject
        };

        foreach (var recipient in recipientList)
            msg.To.Add(new MailAddress(recipient));

        if (isHtml)
            AttachHtmlWithPlainTextAlternative(msg, body);
        else
        {
            msg.Body = body;
            msg.IsBodyHtml = false;
        }

        await smtp.SendMailAsync(msg, ct);
        _logger.LogInformation("Nurturing email sent to {Recipients}: {Subject}",
            string.Join(", ", recipientList), subject);

        await LabelLastSentMessageAsync(subject, ct);
    }

    public async Task SendReplyAsync(string to, string subject, string body, string inReplyToMessageId, bool isHtml = false, CancellationToken ct = default)
    {
        if (!IsConfigured) return;

        using var smtp = CreateSmtpClient();

        // Normalize subject: Gmail threads by subject, so preserve the original without adding extra "Re:"
        var replySubject = subject.StartsWith("Re:", StringComparison.OrdinalIgnoreCase) ? subject : $"Re: {subject}";

        var msg = new MailMessage(
            new MailAddress(_options.EffectiveFromAddress!, _options.SenderName),
            new MailAddress(to))
        {
            Subject = replySubject
        };

        if (isHtml)
            AttachHtmlWithPlainTextAlternative(msg, body);
        else
        {
            msg.Body = body;
            msg.IsBodyHtml = false;
        }

        msg.Headers.Add("In-Reply-To", inReplyToMessageId);
        msg.Headers.Add("References", inReplyToMessageId);

        await smtp.SendMailAsync(msg, ct);
        _logger.LogInformation("Nurturing reply sent to {To}: {Subject}", to, replySubject);

        await LabelLastSentMessageAsync(replySubject, ct);
    }

    public async Task MarkAsReadAsync(IEnumerable<string> messageIds, CancellationToken ct = default)
    {
        if (!IsConfigured) return;

        var idsToMark = messageIds.Where(id => !string.IsNullOrWhiteSpace(id)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        if (idsToMark.Count == 0) return;

        try
        {
            using var client = new ImapClient();
            await client.ConnectAsync(_options.ImapHost, _options.ImapPort, MailKit.Security.SecureSocketOptions.SslOnConnect, ct);
            await client.AuthenticateAsync(_options.EffectiveLoginEmail, _options.EmailPassword, ct);

            var nurturingFolder = await GetOrCreateNurturingFolderAsync(client, ct);

            var inbox = client.Inbox;
            await inbox.OpenAsync(FolderAccess.ReadWrite, ct);

            // Search recent messages and match by Message-ID header
            var since = DateTimeOffset.UtcNow.AddDays(-60);
            var uids = await inbox.SearchAsync(SearchQuery.DeliveredAfter(since.DateTime), ct);

            var marked = 0;
            var archived = 0;
            var labeled = 0;
            foreach (var uid in uids)
            {
                if (idsToMark.Count == 0) break;

                var headers = await inbox.GetHeadersAsync(uid, ct);
                var msgId = headers[HeaderId.MessageId];
                if (msgId is not null && idsToMark.Remove(msgId))
                {
                    await inbox.AddFlagsAsync(uid, MessageFlags.Seen, silent: true, ct);
                    marked++;

                    // Prefer moving processed replies out of Inbox entirely so the mailbox
                    // owner no longer sees them once the bot consumed them.
                    if (nurturingFolder is not null)
                    {
                        try
                        {
                            await inbox.MoveToAsync(uid, nurturingFolder, ct);
                            archived++;
                            continue;
                        }
                        catch (Exception ex)
                        {
                            _logger.LogWarning(ex, "Could not archive inbox message into Nurturing; falling back to labeling");
                        }

                        try
                        {
                            await inbox.CopyToAsync(uid, nurturingFolder, ct);
                            labeled++;
                        }
                        catch (Exception ex)
                        {
                            _logger.LogWarning(ex, "Could not label inbox message as Nurturing");
                        }
                    }
                }
            }

            await client.DisconnectAsync(true, ct);
            _logger.LogInformation("Marked {Marked} emails as read, archived {Archived}, labeled {Labeled} as Nurturing", marked, archived, labeled);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to mark emails as read via IMAP");
        }
    }

    // ── IMAP Nurturing label helpers ──────────────────────────────

    private const string NurturingLabelName = "Nurturing";

    /// <summary>
    /// Gets or creates the "Nurturing" IMAP folder/Gmail label.
    /// Returns null if creation fails (non-fatal).
    /// </summary>
    private async Task<IMailFolder?> GetOrCreateNurturingFolderAsync(ImapClient client, CancellationToken ct)
    {
        try
        {
            var personal = client.PersonalNamespaces[0];
            var folders = await client.GetFoldersAsync(personal, cancellationToken: ct);
            var existing = folders.FirstOrDefault(f =>
                f.Name.Equals(NurturingLabelName, StringComparison.OrdinalIgnoreCase));

            if (existing is not null)
                return existing;

            // Create the label — Gmail exposes labels as top-level IMAP folders
            var topLevel = client.GetFolder(personal);
            var created = await topLevel.CreateAsync(NurturingLabelName, isMessageFolder: true, ct);
            _logger.LogInformation("Created Gmail label '{Label}'", NurturingLabelName);
            return created;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "Could not get/create '{Label}' IMAP folder", NurturingLabelName);
            return null;
        }
    }

    /// <summary>
    /// After sending an email via SMTP, finds the most recent message in the Sent folder
    /// matching the subject and copies it to the "Nurturing" label.
    /// Gmail IMAP COPY adds the label without duplicating the message.
    /// </summary>
    private async Task LabelLastSentMessageAsync(string subject, CancellationToken ct)
    {
        try
        {
            using var client = new ImapClient();
            await client.ConnectAsync(_options.ImapHost, _options.ImapPort, MailKit.Security.SecureSocketOptions.SslOnConnect, ct);
            await client.AuthenticateAsync(_options.EffectiveLoginEmail, _options.EmailPassword, ct);

            var nurturingFolder = await GetOrCreateNurturingFolderAsync(client, ct);
            if (nurturingFolder is null)
            {
                await client.DisconnectAsync(true, ct);
                return;
            }

            // Find the Sent folder
            var sentFolder = (await client.GetFoldersAsync(client.PersonalNamespaces[0], cancellationToken: ct))
                .FirstOrDefault(f => f.Attributes.HasFlag(FolderAttributes.Sent))
                ?? (await client.GetFoldersAsync(client.PersonalNamespaces[0], cancellationToken: ct))
                    .FirstOrDefault(f => f.Name.Contains("Sent", StringComparison.OrdinalIgnoreCase));

            if (sentFolder is null)
            {
                _logger.LogWarning("Could not find Sent folder to label message");
                await client.DisconnectAsync(true, ct);
                return;
            }

            await sentFolder.OpenAsync(FolderAccess.ReadOnly, ct);

            // Search for messages sent in the last 5 minutes with matching subject
            var since = DateTimeOffset.UtcNow.AddMinutes(-5);
            var query = SearchQuery.DeliveredAfter(since.DateTime)
                .And(SearchQuery.SubjectContains(subject.Length > 60 ? subject[..60] : subject));
            var uids = await sentFolder.SearchAsync(query, ct);

            if (uids.Count > 0)
            {
                // Copy the most recent match to the Nurturing label
                var lastUid = uids[^1];
                await sentFolder.CopyToAsync(lastUid, nurturingFolder, ct);
                _logger.LogDebug("Labeled sent message as Nurturing: {Subject}", subject);
            }
            else
            {
                _logger.LogDebug("No recent sent message found to label for subject: {Subject}", subject);
            }

            await client.DisconnectAsync(true, ct);
        }
        catch (Exception ex)
        {
            // Non-fatal — labeling failure should never break the send flow
            _logger.LogWarning(ex, "Failed to label sent message as Nurturing");
        }
    }

    // ── Helpers ─────────────────────────────────────────────────────

    /// <summary>
    /// Attaches both a plain-text and HTML version to the email as multipart/alternative.
    /// This improves deliverability (reduces spam score) because mail clients can pick
    /// the format they prefer and spam filters see a legitimate plain-text body.
    /// </summary>
    private static void AttachHtmlWithPlainTextAlternative(MailMessage msg, string htmlBody)
    {
        var plainText = HtmlToPlainText(htmlBody);

        // Set plain text as the body (fallback)
        msg.Body = plainText;
        msg.IsBodyHtml = false;

        // Add HTML as an alternate view — mail clients that support HTML will prefer this
        var htmlView = AlternateView.CreateAlternateViewFromString(htmlBody, System.Text.Encoding.UTF8, "text/html");
        msg.AlternateViews.Add(htmlView);
    }

    /// <summary>
    /// Converts HTML to readable plain text by stripping tags and decoding entities.
    /// Preserves paragraph breaks and link URLs.
    /// </summary>
    private static string HtmlToPlainText(string html)
    {
        if (string.IsNullOrWhiteSpace(html)) return "";

        var text = html;

        // Convert <br>, </p>, </div>, </tr> to newlines
        text = Regex.Replace(text, @"<br\s*/?>", "\n", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"</(?:p|div|tr|li|h[1-6])>", "\n", RegexOptions.IgnoreCase);
        text = Regex.Replace(text, @"<hr[^>]*>", "\n---\n", RegexOptions.IgnoreCase);

        // Extract link URLs: <a href="URL">text</a> → text (URL)
        text = Regex.Replace(text, @"<a\s[^>]*href\s*=\s*[""']([^""']+)[""'][^>]*>(.*?)</a>",
            m =>
            {
                var url = m.Groups[1].Value;
                var linkText = m.Groups[2].Value;
                var cleanLinkText = Regex.Replace(linkText, @"<[^>]+>", "").Trim();
                return string.Equals(cleanLinkText, url, StringComparison.OrdinalIgnoreCase)
                    ? url
                    : $"{cleanLinkText} ({url})";
            },
            RegexOptions.IgnoreCase | RegexOptions.Singleline);

        // Strip all remaining HTML tags
        text = Regex.Replace(text, @"<[^>]+>", "");

        // Decode HTML entities
        text = WebUtility.HtmlDecode(text);

        // Collapse multiple blank lines into at most two
        text = Regex.Replace(text, @"\n{3,}", "\n\n");

        return text.Trim();
    }

    /// <summary>Creates a configured SMTP client for sending emails.</summary>
    private System.Net.Mail.SmtpClient CreateSmtpClient()
    {
        var smtp = new System.Net.Mail.SmtpClient(_options.SmtpHost!, _options.SmtpPort);
        smtp.EnableSsl = true;
        smtp.Credentials = new NetworkCredential(_options.EffectiveLoginEmail, _options.EmailPassword);
        return smtp;
    }
}
