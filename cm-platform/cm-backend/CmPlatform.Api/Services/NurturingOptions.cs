using System.Text.Json.Serialization;

namespace CmPlatform.Api.Services;

public sealed record ReviewerEntry(
    [property: JsonPropertyName("email")] string Email,
    [property: JsonPropertyName("name")] string Name);

public sealed class NurturingOptions
{
    public List<ReviewerEntry> Reviewers { get; set; } = [];

    public IReadOnlyList<string> GetReviewerList() =>
        Reviewers.Select(r => r.Email).ToList();
}
