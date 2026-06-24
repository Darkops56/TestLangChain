using Microsoft.AspNetCore.Mvc;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

[ApiController]
[Route("api/chat")]
public sealed class ChatController(IConversationStore store, IChatAIService aiService) : ControllerBase
{
    [HttpPost("conversations")]
    public ActionResult<ConversationCreateResponse> CreateConversation([FromBody] ConversationCreateRequest? request)
    {
        var created = store.Create(request?.Locale ?? "es-AR");
        return Ok(created);
    }

    [HttpGet("conversations/{id}")]
    public ActionResult<ConversationDto> GetConversation(string id)
    {
        var conversation = store.Get(id);
        if (conversation is null)
        {
            return NotFound();
        }

        return Ok(conversation);
    }

    [HttpDelete("conversations/{id}")]
    public IActionResult DeleteConversation(string id)
    {
        return store.Delete(id) ? NoContent() : NotFound();
    }

    [HttpPost("conversations/{id}/messages")]
    public async Task<ActionResult<UserMessageResponse>> SendMessage(string id, [FromBody] UserMessageRequest request, CancellationToken ct)
    {
        var conversation = store.Get(id);
        if (conversation is null)
        {
            return NotFound();
        }

        if (string.IsNullOrWhiteSpace(request.Text) || request.Text.Length > 1000)
        {
            return BadRequest(new { error = "Message must be between 1 and 1000 characters." });
        }

        // Check per-conversation rate limit
        if (conversation.Metadata.IsRateLimited)
        {
            // Save the message for reporting even though it's rate-limited
            var savedMsg = store.AddMessage(id, "user", request.Text, isVoice: request.IsVoice);
            return StatusCode(StatusCodes.Status429TooManyRequests,
                new { error = "Rate limit reached.", savedMessageId = savedMsg.Id });
        }

        // Check per-IP rate limit (prevent abuse across multiple conversations)
        var clientIp = HttpContext.Connection.RemoteIpAddress?.ToString() ?? "unknown";
        if (store.IsIpRateLimited(clientIp))
        {
            var savedMsg = store.AddMessage(id, "user", request.Text, isVoice: request.IsVoice);
            return StatusCode(StatusCodes.Status429TooManyRequests,
                new { error = "Too many requests from this IP. Try again later.", savedMessageId = savedMsg.Id });
        }

        var userMessage = store.AddMessage(id, "user", request.Text, isVoice: request.IsVoice);
        store.IncrementIpCounter(clientIp);
        var locale = request.Locale ?? conversation.Metadata.Locale;

        var botText = await aiService.GetCompletionAsync(id, request.Text, locale, ct);
        var botMessage = store.AddMessage(id, "bot", botText);
        var updated = store.Get(id)!;

        return Ok(new UserMessageResponse(
            userMessage,
            botMessage,
            Math.Max(0, ChatLimits.MaxMessagesPerConversation - updated.Metadata.MessageCount)));
    }
}
