namespace Novit.Web.Api.Services;

public interface ISpeechService
{
    bool IsConfigured { get; }
    Task<(string text, double confidence, int durationMs)> TranscribeAsync(Stream audio, string locale, string contentType = "audio/wav", CancellationToken ct = default);
    Task<byte[]> SynthesizeAsync(string text, string locale, CancellationToken ct = default);
    /// <summary>Synthesize speech and stream the audio directly to the destination stream (avoids buffering the full response).</summary>
    Task SynthesizeStreamAsync(string text, string locale, Stream destination, CancellationToken ct = default);
}
