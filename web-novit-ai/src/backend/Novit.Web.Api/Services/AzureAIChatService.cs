using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Extensions.Options;
using Novit.Web.Api.Models;

namespace Novit.Web.Api.Services;

public sealed class AzureAIChatService : IChatAIService
{
    private readonly AzureAIOptions _options;
    private readonly IConversationStore _store;
    private readonly HttpClient _http;
    private readonly ChatToolHandler _toolHandler;
    private readonly ILogger<AzureAIChatService> _logger;

    private static string? _systemPromptEs;
    private static string? _systemPromptEn;
    private static readonly object _lockEs = new();
    private static readonly object _lockEn = new();

    /// <summary>Max tool-call round-trips to prevent infinite loops.</summary>
    private const int MaxToolRounds = 5;

    public AzureAIChatService(
        IOptions<AzureAIOptions> options,
        IConversationStore store,
        HttpClient http,
        ChatToolHandler toolHandler,
        ILogger<AzureAIChatService> logger)
    {
        _options = options.Value;
        _store = store;
        _http = http;
        _toolHandler = toolHandler;
        _logger = logger;
    }

    public bool IsConfigured => _options.IsFoundryConfigured;

    public async Task<string> GetCompletionAsync(string conversationId, string userMessage, string locale, CancellationToken ct = default)
    {
        if (!IsConfigured)
            return GetFallbackReply(locale);

        var messages = BuildMessages(conversationId, userMessage, locale);

        // Tool-call loop: resolve all function calls before returning content
        for (var round = 0; round < MaxToolRounds; round++)
        {
            var (content, toolCalls) = await CallCompletionAsync(messages, ct);

            if (toolCalls is null || toolCalls.Count == 0)
                return StripTimestamps(content ?? GetFallbackReply(locale));

            // Append the assistant message containing tool_calls
            // CRITICAL: Azure AI expects tool_calls in a specific format:
            // [{"id":"...","type":"function","function":{"name":"...","arguments":"..."}}]
            messages.Add(new Dictionary<string, object?>
            {
                ["role"] = "assistant",
                ["content"] = content,
                ["tool_calls"] = FormatToolCallsForApi(toolCalls)
            });

            // Execute each tool call and add results
            foreach (var tc in toolCalls)
            {
                var result = await _toolHandler.ExecuteAsync(tc.FunctionName, tc.Arguments, ct);
                messages.Add(new Dictionary<string, object>
                {
                    ["role"] = "tool",
                    ["tool_call_id"] = tc.Id,
                    ["content"] = result
                });
            }
        }

        _logger.LogWarning("Tool-call loop hit max rounds ({Max}) for conversation {Id}", MaxToolRounds, conversationId);
        return GetFallbackReply(locale);
    }

    public async IAsyncEnumerable<string> StreamCompletionAsync(string conversationId, string userMessage, string locale, [EnumeratorCancellation] CancellationToken ct = default)
    {
        if (!IsConfigured)
        {
            foreach (var token in GetFallbackReply(locale).Split(' '))
                yield return token + " ";
            yield break;
        }

        var messages = BuildMessages(conversationId, userMessage, locale);

        // Resolve tool calls in non-streaming mode first
        for (var round = 0; round < MaxToolRounds; round++)
        {
            var (content, toolCalls) = await CallCompletionAsync(messages, ct);

            if (toolCalls is null || toolCalls.Count == 0)
                break; // No more tool calls — proceed to streaming

            messages.Add(new Dictionary<string, object?>
            {
                ["role"] = "assistant",
                ["content"] = content,
                ["tool_calls"] = FormatToolCallsForApi(toolCalls)
            });

            foreach (var tc in toolCalls)
            {
                var result = await _toolHandler.ExecuteAsync(tc.FunctionName, tc.Arguments, ct);
                messages.Add(new Dictionary<string, object>
                {
                    ["role"] = "tool",
                    ["tool_call_id"] = tc.Id,
                    ["content"] = result
                });
            }
        }

        // Now stream the final response (after all tools are resolved)
        var body = BuildRequestBody(messages, stream: true);

        using var request = new HttpRequestMessage(HttpMethod.Post, _options.AIFoundryDeployment);
        request.Headers.Add("api-key", _options.AIFoundryKey);
        request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");

        var response = await _http.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync(ct);
            _logger.LogError("Azure AI streaming completion failed with {Status}: {Body}", response.StatusCode, errorBody);
            response.EnsureSuccessStatusCode();
        }

        using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var reader = new StreamReader(stream);

        while (true)
        {
            var line = await reader.ReadLineAsync(ct);
            if (line is null || ct.IsCancellationRequested)
                break;

            if (string.IsNullOrEmpty(line) || !line.StartsWith("data: "))
                continue;

            var data = line["data: ".Length..];
            if (data == "[DONE]")
                break;

            string? tokenText = null;
            try
            {
                using var doc = JsonDocument.Parse(data);
                var delta = doc.RootElement
                    .GetProperty("choices")[0]
                    .GetProperty("delta");

                if (delta.TryGetProperty("content", out var c))
                    tokenText = c.GetString();
            }
            catch (JsonException) { /* skip malformed chunks */ }

            if (tokenText is not null)
                yield return tokenText;
        }
    }

    // ── Core API call ─────────────────────────────────────────────────

    /// <summary>
    /// Makes a single non-streaming completion call.
    /// Returns the content string and any tool_calls the model requested.
    /// </summary>
    private async Task<(string? Content, List<ToolCallInfo>? ToolCalls)> CallCompletionAsync(
        List<object> messages, CancellationToken ct)
    {
        var body = BuildRequestBody(messages, stream: false);

        using var request = new HttpRequestMessage(HttpMethod.Post, _options.AIFoundryDeployment);
        request.Headers.Add("api-key", _options.AIFoundryKey);
        request.Content = new StringContent(JsonSerializer.Serialize(body), Encoding.UTF8, "application/json");

        var response = await _http.SendAsync(request, ct);

        if (!response.IsSuccessStatusCode)
        {
            var errorBody = await response.Content.ReadAsStringAsync(ct);
            _logger.LogError("Azure AI completion failed with {Status}: {Body}", response.StatusCode, errorBody);
            response.EnsureSuccessStatusCode(); // throw with status info
        }

        using var doc = await JsonDocument.ParseAsync(await response.Content.ReadAsStreamAsync(ct), cancellationToken: ct);
        var message = doc.RootElement.GetProperty("choices")[0].GetProperty("message");

        // Extract content (may be null when model calls tools)
        string? content = null;
        if (message.TryGetProperty("content", out var contentProp) && contentProp.ValueKind == JsonValueKind.String)
            content = contentProp.GetString();

        // Extract tool_calls if present
        List<ToolCallInfo>? toolCalls = null;
        if (message.TryGetProperty("tool_calls", out var toolCallsArr) && toolCallsArr.ValueKind == JsonValueKind.Array)
        {
            toolCalls = [];
            foreach (var tc in toolCallsArr.EnumerateArray())
            {
                var fn = tc.GetProperty("function");
                toolCalls.Add(new ToolCallInfo(
                    Id: tc.GetProperty("id").GetString()!,
                    FunctionName: fn.GetProperty("name").GetString()!,
                    Arguments: fn.GetProperty("arguments").GetString()!));
            }
        }

        return (content, toolCalls);
    }

    /// <summary>
    /// Builds the JSON request body, conditionally including tools and streaming flag.
    /// </summary>
    private Dictionary<string, object> BuildRequestBody(List<object> messages, bool stream)
    {
        var body = new Dictionary<string, object>
        {
            ["messages"] = messages,
            ["max_completion_tokens"] = 800,
            ["temperature"] = 0.7
        };

        if (stream)
            body["stream"] = true;

        // Only include tools if Cal.com is configured
        if (_toolHandler.HasTools)
            body["tools"] = ChatToolDefinitions.GetAll();

        return body;
    }

    private List<object> BuildMessages(string conversationId, string userMessage, string locale)
    {
        var systemPrompt = locale.StartsWith("en", StringComparison.OrdinalIgnoreCase)
            ? LoadPrompt("en")
            : LoadPrompt("es");

        // Inject current date/time so the model knows "today" and can handle
        // relative references like "next week", "tomorrow", etc.
        var buenosAires = TimeZoneInfo.FindSystemTimeZoneById("America/Buenos_Aires");
        var now = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, buenosAires);
        var dateContext = locale.StartsWith("en", StringComparison.OrdinalIgnoreCase)
            ? $"[Current date and time: {now:dddd, MMMM d, yyyy} at {now:HH:mm} (Argentina time, UTC-3). Use this as reference for any scheduling or date-related conversation.]\n\n"
            : $"[Fecha y hora actual: {now.ToString("dddd d 'de' MMMM 'de' yyyy", new System.Globalization.CultureInfo("es-AR"))} a las {now:HH:mm} (hora de Argentina, UTC-3). Usá esto como referencia para cualquier conversación sobre agendamiento o fechas.]\n\n";

        var messages = new List<object> { new { role = "system", content = dateContext + systemPrompt } };

        var conversation = _store.Get(conversationId);
        if (conversation is not null)
        {
            foreach (var msg in conversation.Messages)
            {
                var role = msg.Role == "bot" ? "assistant" : "user";
                var msgTime = TimeZoneInfo.ConvertTimeFromUtc(msg.CreatedAt.UtcDateTime, buenosAires);
                messages.Add(new { role, content = $"[{msgTime:yyyy-MM-dd HH:mm}] {msg.Content}" });
            }
        }

        // If the current user message was already persisted (included in conversation above),
        // don't duplicate it. Only append when there's no conversation yet (first message).
        if (conversation is null || conversation.Messages.Count == 0 ||
            conversation.Messages[^1].Content != userMessage || conversation.Messages[^1].Role != "user")
        {
            var msgTime = TimeZoneInfo.ConvertTimeFromUtc(DateTime.UtcNow, buenosAires);
            messages.Add(new { role = "user", content = $"[{msgTime:yyyy-MM-dd HH:mm}] {userMessage}" });
        }

        return messages;
    }

    /// <summary>
    /// Strip [YYYY-MM-DD HH:mm] (and optional :ss) timestamps the AI may accidentally echo.
    /// Applied as a safety net before storing/returning bot replies.
    /// </summary>
    private static readonly Regex TimestampRegex = new(@"\[\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}(?::\d{2})?\]\s*", RegexOptions.Compiled);
    internal static string StripTimestamps(string text) => TimestampRegex.Replace(text, "").Trim();

    private static string GetFallbackReply(string locale)
    {
        return locale.StartsWith("en", StringComparison.OrdinalIgnoreCase)
            ? "Great to meet you! Tell me more about your project and I will guide you."
            : "¡Un gusto conocerte! Contame más sobre tu proyecto y te guío con opciones de Novit.";
    }

    /// <summary>
    /// Converts internal ToolCallInfo records to the JSON format Azure AI expects:
    /// [{"id":"...","type":"function","function":{"name":"...","arguments":"..."}}]
    /// </summary>
    private static List<object> FormatToolCallsForApi(List<ToolCallInfo> toolCalls) =>
        toolCalls.Select(tc => (object)new Dictionary<string, object>
        {
            ["id"] = tc.Id,
            ["type"] = "function",
            ["function"] = new Dictionary<string, object>
            {
                ["name"] = tc.FunctionName,
                ["arguments"] = tc.Arguments
            }
        }).ToList();

    /// <summary>
    /// Loads system prompt from a .md file in the Prompts folder.
    /// Files are cached after first read for performance.
    /// To update prompts at runtime, restart the container.
    /// </summary>
    private string LoadPrompt(string lang)
    {
        ref string? cached = ref (lang == "en" ? ref _systemPromptEn : ref _systemPromptEs);
        var lockObj = lang == "en" ? _lockEn : _lockEs;

        if (cached is not null)
            return cached;

        lock (lockObj)
        {
            if (cached is not null)
                return cached;

            var fileName = $"system-prompt-{lang}.md";
            var basePath = AppContext.BaseDirectory;
            var filePath = Path.Combine(basePath, "Prompts", fileName);

            if (!File.Exists(filePath))
            {
                _logger.LogWarning("Prompt file not found: {Path}. Using fallback.", filePath);
                cached = lang == "en"
                    ? "You are the virtual sales representative of Novit Software. Your name is Novit AI. Be professional, friendly, and concise."
                    : "Sos la representante comercial virtual de Novit Software. Tu nombre es Novit AI. Sé profesional, cercana y concisa. Usá voseo argentino.";
                return cached;
            }

            cached = File.ReadAllText(filePath);
            _logger.LogInformation("Loaded prompt from {Path} ({Length} chars)", filePath, cached.Length);
            return cached;
        }
    }
}

/// <summary>Represents a single tool call from the AI model response.</summary>
internal sealed record ToolCallInfo(string Id, string FunctionName, string Arguments);
