using Microsoft.AspNetCore.SignalR;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Hubs;

public sealed class ChatHub(IConversationStore store, IChatAIService aiService) : Hub
{
    public async Task SendMessage(string conversationId, string text, string locale)
    {
        if (string.IsNullOrWhiteSpace(text) || text.Length > 1000)
        {
            await Clients.Caller.SendAsync("OnError", "invalid_message", "Message must be between 1 and 1000 characters.");
            return;
        }

        var conversation = store.Get(conversationId);
        if (conversation is null)
        {
            await Clients.Caller.SendAsync("OnError", "conversation_not_found", "Conversation does not exist.");
            return;
        }

        if (conversation.Metadata.IsRateLimited)
        {
            await Clients.Caller.SendAsync("OnRateLimitReached", "whatsapp_or_calendly");
            return;
        }

        store.AddMessage(conversationId, "user", text);

        await Clients.Caller.SendAsync("OnBotTyping", true);

        var fullReply = new System.Text.StringBuilder();
        await foreach (var token in aiService.StreamCompletionAsync(conversationId, text, locale, Context.ConnectionAborted))
        {
            fullReply.Append(token);
            await Clients.Caller.SendAsync("OnTokenReceived", token);
        }

        var reply = AzureAIChatService.StripTimestamps(fullReply.ToString());
        var message = store.AddMessage(conversationId, "bot", reply, $"/api/voice/synthesize?messageId={Guid.NewGuid():N}");
        await Clients.Caller.SendAsync("OnMessageComplete", message);
        await Clients.Caller.SendAsync("OnBotTyping", false);

        var updated = store.Get(conversationId);
        await Clients.Caller.SendAsync("OnRateLimitWarning", Math.Max(0, ChatLimits.MaxMessagesPerConversation - (updated?.Metadata.MessageCount ?? 0)));
        if (updated?.Metadata.IsRateLimited == true)
        {
            await Clients.Caller.SendAsync("OnRateLimitReached", "whatsapp_or_calendly");
        }
    }

    public Task StartTyping(string conversationId) => Clients.Caller.SendAsync("OnBotTyping", true);

    public Task StopTyping(string conversationId) => Clients.Caller.SendAsync("OnBotTyping", false);

    public Task RequestTTS(string conversationId, string messageId)
        => Clients.Caller.SendAsync("OnTTSReady", messageId, $"/api/voice/synthesize?messageId={messageId}");
}
