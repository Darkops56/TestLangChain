namespace Novit.Web.Api.Models;

public sealed class PipedriveOptions
{
    public string? PipedriveKey { get; set; }
    public string? PipedriveBaseUrl { get; set; }

    public bool IsConfigured => !string.IsNullOrWhiteSpace(PipedriveKey) && !string.IsNullOrWhiteSpace(PipedriveBaseUrl);
}
