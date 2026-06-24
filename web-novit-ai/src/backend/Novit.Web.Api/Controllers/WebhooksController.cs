using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

/// <summary>
/// Public webhook endpoints for Meta (Instagram/Facebook) and other platforms.
/// Receives incoming messages and forwards them to the Python agent for processing.
/// 
/// Meta webhook flow:
///   1. Meta sends POST /api/webhooks/meta with message payload
///   2. This controller validates the signature (HMAC-SHA256)
///   3. Forwards the message to the Python agent via <see cref="IAgentClient"/>
///   4. Returns 200 immediately (Meta requires fast response)
/// </summary>
[ApiController]
[Route("api/webhooks")]
public sealed class WebhooksController(
    IAgentClient agentClient,
    IConfiguration config,
    ILogger<WebhooksController> logger) : ControllerBase
{
    /// <summary>
    /// Meta webhook verification (GET). Used during webhook setup to verify ownership.
    /// Meta sends hub.mode=subscribe, hub.verify_token, hub.challenge.
    /// </summary>
    [HttpGet("meta")]
    public IActionResult VerifyWebhook(
        [FromQuery(Name = "hub.mode")] string? mode,
        [FromQuery(Name = "hub.verify_token")] string? verifyToken,
        [FromQuery(Name = "hub.challenge")] string? challenge)
    {
        var expectedToken = config["WEBHOOK_VERIFY_TOKEN"] ?? config["Meta:WebhookVerifyToken"];

        if (string.IsNullOrWhiteSpace(expectedToken))
        {
            logger.LogWarning("Meta webhook verify token not configured");
            return StatusCode(500, "Webhook verify token not configured");
        }

        if (mode == "subscribe" && verifyToken == expectedToken)
        {
            logger.LogInformation("Meta webhook verification successful");
            return Ok(challenge);
        }

        logger.LogWarning("Meta webhook verification failed: mode={Mode}, token mismatch", mode);
        return Forbid();
    }

    /// <summary>
    /// Meta webhook callback (POST). Receives Instagram/Facebook message events.
    /// Validates HMAC-SHA256 signature and forwards messages to the Python agent.
    /// </summary>
    [HttpPost("meta")]
    public async Task<IActionResult> ReceiveWebhook(CancellationToken ct)
    {
        // Read raw body for signature verification
        string body;
        using (var reader = new StreamReader(Request.Body, Encoding.UTF8))
            body = await reader.ReadToEndAsync(ct);

        // Validate signature if app secret is configured
        var appSecret = config["META_APP_SECRET"] ?? config["Meta:AppSecret"];
        if (!string.IsNullOrWhiteSpace(appSecret))
        {
            var signatureHeader = Request.Headers["X-Hub-Signature-256"].FirstOrDefault();
            if (!ValidateSignature(body, signatureHeader, appSecret))
            {
                logger.LogWarning("Invalid Meta webhook signature");
                return Unauthorized("Invalid signature");
            }
        }

        // Parse the webhook payload
        try
        {
            using var doc = JsonDocument.Parse(body);
            var root = doc.RootElement;

            // Meta sends: { "object": "instagram"|"page", "entry": [...] }
            var objectType = root.TryGetProperty("object", out var obj) ? obj.GetString() : null;
            var platform = NormalizePlatform(objectType);

            if (root.TryGetProperty("entry", out var entries))
            {
                foreach (var entry in entries.EnumerateArray())
                {
                    // Instagram messaging
                    if (entry.TryGetProperty("messaging", out var messagingArray))
                    {
                        foreach (var messaging in messagingArray.EnumerateArray())
                        {
                            await ProcessMessagingEventAsync(messaging, platform, ct);
                        }
                    }

                    if (entry.TryGetProperty("changes", out var changesArray))
                    {
                        foreach (var change in changesArray.EnumerateArray())
                        {
                            await ProcessChangeEventAsync(change, platform, ct);
                        }
                    }
                }
            }
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to parse Meta webhook payload");
            // Still return 200 to prevent Meta from retrying
        }

        // Always return 200 quickly — Meta requires response within 20 seconds
        return Ok("EVENT_RECEIVED");
    }

    /// <summary>
    /// Process a single messaging event and forward to the Python agent.
    /// </summary>
    private async Task ProcessMessagingEventAsync(JsonElement messaging, string platform, CancellationToken ct)
    {
        try
        {
            // Extract sender
            var senderId = messaging.TryGetProperty("sender", out var sender)
                && sender.TryGetProperty("id", out var sid)
                    ? sid.GetString()
                    : null;

            if (string.IsNullOrEmpty(senderId))
                return;

            // Extract message text
            if (!messaging.TryGetProperty("message", out var message))
                return;

            var text = message.TryGetProperty("text", out var t) ? t.GetString() : null;
            if (string.IsNullOrWhiteSpace(text))
                return;

            var messageId = message.TryGetProperty("mid", out var mid) ? mid.GetString() : null;

            logger.LogInformation("Forwarding Meta message from {SenderId} to agent: {TextPreview}",
                senderId, text.Length > 50 ? text[..50] + "…" : text);

            // Fire-and-forget: forward to Python agent
            _ = Task.Run(async () =>
            {
                try
                {
                    var result = await agentClient.ForwardWebhookMessageAsync(
                        senderId, text, platform, messageId, CancellationToken.None);

                    if (result is not null)
                        logger.LogInformation("Agent replied to {SenderId}: {Reply}",
                            senderId, result.Reply?.Length > 50 ? result.Reply[..50] + "…" : result.Reply);
                }
                catch (Exception ex)
                {
                    logger.LogError(ex, "Failed to forward message to agent for sender {SenderId}", senderId);
                }
            }, ct);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to process messaging event");
        }
    }

    private async Task ProcessChangeEventAsync(JsonElement change, string platform, CancellationToken ct)
    {
        try
        {
            var field = change.TryGetProperty("field", out var fieldProp) ? fieldProp.GetString() : null;
            logger.LogInformation("Meta change event: {Field} on {Platform}", field, platform);

            if (!change.TryGetProperty("value", out var value))
                return;

            var isInstagramComment = string.Equals(field, "comments", StringComparison.OrdinalIgnoreCase);
            var isInstagramMessage = string.Equals(field, "messages", StringComparison.OrdinalIgnoreCase);
            var isFacebookComment =
                string.Equals(field, "feed", StringComparison.OrdinalIgnoreCase)
                && value.TryGetProperty("item", out var itemProp)
                && string.Equals(itemProp.GetString(), "comment", StringComparison.OrdinalIgnoreCase);

            if (isInstagramMessage)
            {
                var messageSenderId = TryGetNestedString(value, "from", "id")
                    ?? TryGetNestedString(value, "sender", "id");
                if (string.IsNullOrWhiteSpace(messageSenderId) || IsOwnActor(platform, messageSenderId))
                    return;

                var messageSenderName = TryGetNestedString(value, "from", "username")
                    ?? TryGetNestedString(value, "from", "name")
                    ?? TryGetNestedString(value, "sender", "username")
                    ?? TryGetNestedString(value, "sender", "name");
                var messageId = value.TryGetProperty("id", out var directIdProp)
                    ? directIdProp.GetString()
                    : TryGetNestedString(value, "message", "mid");
                var messageText = value.TryGetProperty("text", out var directTextProp)
                    ? directTextProp.GetString()
                    : TryGetNestedString(value, "message", "text");

                if (string.IsNullOrWhiteSpace(messageText))
                    return;

                logger.LogInformation("Forwarding Meta message from {SenderId} to agent: {TextPreview}",
                    messageSenderId, messageText.Length > 50 ? messageText[..50] + "…" : messageText);

                _ = Task.Run(async () =>
                {
                    try
                    {
                        var result = await agentClient.ForwardWebhookMessageAsync(
                            messageSenderId,
                            messageText,
                            platform,
                            messageId,
                            CancellationToken.None,
                            senderName: messageSenderName);

                        if (result is not null)
                            logger.LogInformation("Agent replied to {SenderId}: {Reply}",
                                messageSenderId, result.Reply?.Length > 50 ? result.Reply[..50] + "…" : result.Reply);
                    }
                    catch (Exception ex)
                    {
                        logger.LogError(ex, "Failed to forward message change to agent for sender {SenderId}", messageSenderId);
                    }
                }, ct);

                return;
            }

            if (!isInstagramComment && !isFacebookComment)
                return;

            var verb = value.TryGetProperty("verb", out var verbProp) ? verbProp.GetString() : null;
            if (!string.IsNullOrWhiteSpace(verb) && !string.Equals(verb, "add", StringComparison.OrdinalIgnoreCase))
                return;

            var senderId = TryGetNestedString(value, "from", "id");
            if (string.IsNullOrWhiteSpace(senderId) || IsOwnActor(platform, senderId))
                return;

            var senderName = TryGetNestedString(value, "from", "username")
                ?? TryGetNestedString(value, "from", "name");
            var commentId = value.TryGetProperty("id", out var commentIdProp) ? commentIdProp.GetString() : null;
            var postContextId = TryGetNestedString(value, "media", "id")
                ?? TryGetNestedString(value, "post", "id")
                ?? (value.TryGetProperty("post_id", out var postIdProp) ? postIdProp.GetString() : null);
            var postContextText = TryGetNestedString(value, "media", "caption")
                ?? TryGetNestedString(value, "post", "message");
            var text = value.TryGetProperty("text", out var textProp)
                ? textProp.GetString()
                : (value.TryGetProperty("message", out var messageProp) ? messageProp.GetString() : null);

            if (string.IsNullOrWhiteSpace(commentId) || string.IsNullOrWhiteSpace(text))
                return;

            logger.LogInformation("Forwarding Meta comment {CommentId} from {SenderId} to agent: {TextPreview}",
                commentId, senderId, text.Length > 50 ? text[..50] + "…" : text);

            _ = Task.Run(async () =>
            {
                try
                {
                    var result = await agentClient.ForwardWebhookMessageAsync(
                        senderId,
                        text,
                        platform,
                        commentId,
                        CancellationToken.None,
                        senderName: senderName,
                        replyTargetId: commentId,
                        replyTargetType: "comment",
                        postContextId: postContextId,
                        postContextText: postContextText);

                    if (result is not null)
                        logger.LogInformation("Agent replied to comment {CommentId}: {Reply}",
                            commentId, result.Reply?.Length > 50 ? result.Reply[..50] + "…" : result.Reply);
                }
                catch (Exception ex)
                {
                    logger.LogError(ex, "Failed to forward comment to agent for sender {SenderId}", senderId);
                }
            }, ct);
        }
        catch (Exception ex)
        {
            logger.LogError(ex, "Failed to process Meta change event");
        }
    }

    private static string NormalizePlatform(string? objectType) =>
        string.Equals(objectType, "page", StringComparison.OrdinalIgnoreCase) ? "facebook" : "instagram";

    private bool IsOwnActor(string platform, string senderId)
    {
        var configuredId = string.Equals(platform, "facebook", StringComparison.OrdinalIgnoreCase)
            ? config["META_FACEBOOK_PAGE_ID"] ?? config["Meta:FacebookPageId"]
            : config["META_INSTAGRAM_ACCOUNT_ID"] ?? config["Meta:InstagramAccountId"];

        return !string.IsNullOrWhiteSpace(configuredId)
            && string.Equals(configuredId, senderId, StringComparison.OrdinalIgnoreCase);
    }

    private static string? TryGetNestedString(JsonElement root, string propertyName, string nestedPropertyName)
    {
        if (!root.TryGetProperty(propertyName, out var nested))
            return null;

        if (!nested.TryGetProperty(nestedPropertyName, out var value))
            return null;

        return value.GetString();
    }

    /// <summary>
    /// Validate Meta webhook signature using HMAC-SHA256.
    /// </summary>
    private static bool ValidateSignature(string payload, string? signatureHeader, string appSecret)
    {
        if (string.IsNullOrWhiteSpace(signatureHeader))
            return false;

        // Header format: "sha256=HEXDIGEST"
        if (!signatureHeader.StartsWith("sha256="))
            return false;

        var expectedHash = signatureHeader["sha256=".Length..];

        using var hmac = new HMACSHA256(Encoding.UTF8.GetBytes(appSecret));
        var hash = hmac.ComputeHash(Encoding.UTF8.GetBytes(payload));
        var computed = Convert.ToHexStringLower(hash);

        return CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(computed),
            Encoding.UTF8.GetBytes(expectedHash));
    }
}
