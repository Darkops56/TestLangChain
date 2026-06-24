using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Novit.Web.Api.Controllers;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Tests;

public class WebhooksControllerTests
{
    [Fact]
    public async Task ReceiveWebhook_ForwardsInstagramCommentChangesToAgent()
    {
        var agentClient = new CapturingAgentClient();
        var controller = CreateController(agentClient);

        const string payload = """
        {
          "object": "instagram",
          "entry": [
            {
              "changes": [
                {
                  "field": "comments",
                  "value": {
                    "id": "17890000000000001",
                    "text": "Che, esto tambien sirve para pymes?",
                    "verb": "add",
                    "from": {
                      "id": "88997766",
                      "username": "rodri_cliente"
                    }
                  }
                }
              ]
            }
          ]
        }
        """;

        SetRequestBody(controller, payload);

        var result = await controller.ReceiveWebhook(CancellationToken.None);

        Assert.IsType<OkObjectResult>(result);

        var forwarded = await agentClient.Forwarded.Task.WaitAsync(TimeSpan.FromSeconds(2));
        Assert.Equal("88997766", forwarded.SenderId);
        Assert.Equal("rodri_cliente", forwarded.SenderName);
        Assert.Equal("Che, esto tambien sirve para pymes?", forwarded.Text);
        Assert.Equal("instagram", forwarded.Platform);
        Assert.Equal("17890000000000001", forwarded.MessageId);
        Assert.Equal("17890000000000001", forwarded.ReplyTargetId);
        Assert.Equal("comment", forwarded.ReplyTargetType);
    }

        [Fact]
        public async Task ReceiveWebhook_ForwardsInstagramMessageChangesToAgent()
        {
                var agentClient = new CapturingAgentClient();
                var controller = CreateController(agentClient);

                const string payload = """
                {
                    "object": "instagram",
                    "entry": [
                        {
                            "changes": [
                                {
                                    "field": "messages",
                                    "value": {
                                        "id": "mid.ig_dm_123",
                                        "text": "Hola, quiero saber mas sobre agentes",
                                        "from": {
                                            "id": "55443322",
                                            "username": "lead_dm"
                                        }
                                    }
                                }
                            ]
                        }
                    ]
                }
                """;

                SetRequestBody(controller, payload);

                var result = await controller.ReceiveWebhook(CancellationToken.None);

                Assert.IsType<OkObjectResult>(result);

                var forwarded = await agentClient.Forwarded.Task.WaitAsync(TimeSpan.FromSeconds(2));
                Assert.Equal("55443322", forwarded.SenderId);
                Assert.Equal("lead_dm", forwarded.SenderName);
                Assert.Equal("Hola, quiero saber mas sobre agentes", forwarded.Text);
                Assert.Equal("instagram", forwarded.Platform);
                Assert.Equal("mid.ig_dm_123", forwarded.MessageId);
                Assert.Null(forwarded.ReplyTargetId);
                Assert.Null(forwarded.ReplyTargetType);
        }

    private static WebhooksController CreateController(IAgentClient agentClient)
    {
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(new Dictionary<string, string?>())
            .Build();

        return new WebhooksController(
            agentClient,
            config,
            NullLogger<WebhooksController>.Instance);
    }

    private static void SetRequestBody(ControllerBase controller, string payload)
    {
        controller.ControllerContext = new ControllerContext
        {
            HttpContext = new DefaultHttpContext()
        };

        controller.Request.Body = new MemoryStream(Encoding.UTF8.GetBytes(payload));
        controller.Request.ContentLength = Encoding.UTF8.GetByteCount(payload);
    }

    private sealed record ForwardedWebhookCall(
        string SenderId,
        string SenderName,
        string Text,
        string Platform,
        string? MessageId,
        string? ReplyTargetId,
        string? ReplyTargetType,
        string? PostContextId,
        string? PostContextText);

    private sealed class CapturingAgentClient : IAgentClient
    {
        public bool IsConfigured => true;

        public TaskCompletionSource<ForwardedWebhookCall> Forwarded { get; } =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task<AgentReplyResult?> ForwardWebhookMessageAsync(
            string senderId,
            string text,
            string platform,
            string? messageId,
            CancellationToken ct = default,
            string? senderName = null,
            string? replyTargetId = null,
            string? replyTargetType = null,
            string? postContextId = null,
            string? postContextText = null)
        {
            Forwarded.TrySetResult(new ForwardedWebhookCall(
                senderId,
                senderName ?? string.Empty,
                text,
                platform,
                messageId,
                replyTargetId,
                replyTargetType,
                postContextId,
                postContextText));

            return Task.FromResult<AgentReplyResult?>(new AgentReplyResult("ok"));
        }

        public Task<AgentNewsletterResult?> GenerateNewsletterAsync(CancellationToken ct = default) =>
            Task.FromResult<AgentNewsletterResult?>(null);

        public Task<AgentNewsletterResult?> ReviseNewsletterAsync(string currentSubject, string currentBody, string reviewerFeedback, CancellationToken ct = default) =>
            Task.FromResult<AgentNewsletterResult?>(null);

        public Task<string?> GenerateReplyAsync(string originalSubject, string originalBody, string senderName, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<string?> GenerateClosingAsync(string newsletterSubject, string? newsletterBody, string? firstName, string? orgName, IReadOnlyList<string> dealNotes, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<string?> WrapEmailAsync(string htmlBody, string? firstName = null, string? personalClosing = null, CancellationToken ct = default) =>
            Task.FromResult<string?>(null);

        public Task<AgentStatusResult?> GetStatusAsync(CancellationToken ct = default) =>
            Task.FromResult<AgentStatusResult?>(null);
    }
}