using System.Text.RegularExpressions;

namespace CmPlatform.Api.Services;

public static partial class NurturingWorkflowSupport
{
    [GeneratedRegex(@"^.* wrote:.*$\n?", RegexOptions.Multiline)]
    private static partial Regex QuotedReplyPattern();

    public static string StripQuotedReply(string body)
    {
        if (string.IsNullOrWhiteSpace(body))
            return body;

        var lines = body.Split('\n');
        var result = new List<string>();
        foreach (var line in lines)
        {
            if (line.TrimStart().StartsWith('>'))
                continue;
            result.Add(line);
        }

        var joined = string.Join("\n", result);
        joined = QuotedReplyPattern().Replace(joined, "");
        return joined.Trim();
    }
}
