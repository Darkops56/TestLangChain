using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

[ApiController]
[Route("api/voice")]
public sealed class VoiceController(ISpeechService speechService, IOptions<AzureAIOptions> options, IHttpClientFactory httpClientFactory, IConversationStore store) : ControllerBase
{
    private bool IsClientIpRateLimited(out string clientIp)
    {
        clientIp = HttpContext.Connection.RemoteIpAddress?.ToString() ?? "unknown";
        return store.IsIpRateLimited(clientIp);
    }

    [HttpPost("transcribe")]
    public async Task<ActionResult<VoiceTranscribeResponse>> Transcribe([FromForm] IFormFile? audio, [FromForm] string? locale, CancellationToken ct)
    {
        if (IsClientIpRateLimited(out var clientIp))
            return StatusCode(StatusCodes.Status429TooManyRequests, new { error = "Rate limit reached. Try again later." });

        if (audio is null || audio.Length == 0)
        {
            return BadRequest(new { error = "Audio file is required." });
        }

        using var stream = audio.OpenReadStream();
        var (text, confidence, durationMs) = await speechService.TranscribeAsync(stream, locale ?? "es-AR", audio.ContentType ?? "audio/wav", ct);

        store.IncrementIpCounter(clientIp);

        return Ok(new VoiceTranscribeResponse(text, confidence, durationMs));
    }

    [HttpPost("synthesize")]
    public async Task Synthesize([FromBody] VoiceSynthesizeRequest request, CancellationToken ct)
    {
        if (IsClientIpRateLimited(out var clientIp))
        {
            Response.StatusCode = StatusCodes.Status429TooManyRequests;
            await Response.WriteAsJsonAsync(new { error = "Rate limit reached. Try again later." }, ct);
            return;
        }

        if (string.IsNullOrWhiteSpace(request.Text))
        {
            Response.StatusCode = StatusCodes.Status400BadRequest;
            await Response.WriteAsJsonAsync(new { error = "Text is required." }, ct);
            return;
        }

        if (!speechService.IsConfigured)
        {
            Response.StatusCode = StatusCodes.Status501NotImplemented;
            await Response.WriteAsJsonAsync(new { error = "TTS synthesis is not configured in this environment." }, ct);
            return;
        }

        try
        {
            Response.ContentType = "audio/mpeg";
            // Stream TTS audio directly from Azure to the client without buffering the full response,
            // reducing time-to-first-byte and memory usage.
            await speechService.SynthesizeStreamAsync(request.Text, request.Locale ?? "es-AR", Response.Body, ct);
            store.IncrementIpCounter(clientIp);
        }
        catch (HttpRequestException ex)
        {
            if (!Response.HasStarted)
            {
                Response.StatusCode = StatusCodes.Status502BadGateway;
                await Response.WriteAsJsonAsync(new
                {
                    error = "Speech synthesis failed.",
                    detail = ex.StatusCode is not null ? $"Upstream returned {(int)ex.StatusCode}" : ex.Message
                }, ct);
            }
        }
    }

    /// <summary>Returns a short-lived speech token for browser-side WebSocket STT.</summary>
    [HttpGet("token")]
    public async Task<IActionResult> GetSpeechToken(CancellationToken ct)
    {
        var opts = options.Value;
        if (!opts.IsSpeechConfigured || string.IsNullOrWhiteSpace(opts.AzureAISpeechUrl) || string.IsNullOrWhiteSpace(opts.STTUrl))
        {
            return StatusCode(StatusCodes.Status501NotImplemented, new { error = "Speech not configured." });
        }

        // Request auth token from Azure Speech issueToken endpoint
        var issueTokenUrl = $"{opts.AzureAISpeechUrl.TrimEnd('/')}/sts/v1.0/issueToken";
        using var http = httpClientFactory.CreateClient();
        using var request = new HttpRequestMessage(HttpMethod.Post, issueTokenUrl);
        request.Headers.Add("Ocp-Apim-Subscription-Key", opts.AzureAISpeechKey);
        request.Content = new StringContent("");

        var response = await http.SendAsync(request, ct);
        response.EnsureSuccessStatusCode();
        var token = await response.Content.ReadAsStringAsync(ct);

        // Extract region from STTUrl (e.g., https://eastus.stt.speech.microsoft.com → eastus)
        var sttUri = new Uri(opts.STTUrl);
        var region = sttUri.Host.Split('.')[0];

        return Ok(new { token, region });
    }
}
