namespace Novit.Web.Api.Models;

public sealed class AzureAIOptions
{
    public string? AIFoundryDeployment { get; set; }
    public string? AIFoundryKey { get; set; }
    public string? AzureAISpeechKey { get; set; }
    public string? AzureAISpeechUrl { get; set; }
    public string? STTUrl { get; set; }
    public string? TTSUrl { get; set; }

    public bool IsFoundryConfigured => !string.IsNullOrWhiteSpace(AIFoundryDeployment) && !string.IsNullOrWhiteSpace(AIFoundryKey);
    public bool IsSpeechConfigured => !string.IsNullOrWhiteSpace(AzureAISpeechKey) && !string.IsNullOrWhiteSpace(STTUrl) && !string.IsNullOrWhiteSpace(TTSUrl);
}
