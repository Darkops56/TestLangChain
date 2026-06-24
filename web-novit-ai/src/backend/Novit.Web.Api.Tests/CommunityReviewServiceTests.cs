using System.Net;
using Novit.Web.Api.Filters;
using Novit.Web.Api.Data.Entities;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Tests;

public class CommunityReviewServiceTests
{
    [Theory]
    [InlineData("APROBAR", true)]
    [InlineData("Se puede publicar", true)]
    [InlineData("Ok, pero cambien el video", false)]
    [InlineData("TEXTO: hacerlo mas directo", false)]
    [InlineData("RECHAZAR", false)]
    public void IsApprovalRequest_ReturnsExpected(string body, bool expected)
    {
        Assert.Equal(expected, CommunityReviewService.IsApprovalRequest(body));
    }

    [Theory]
    [InlineData("VIDEO: cambiar el ritmo del reel", CommunityRevisionTarget.Designer)]
    [InlineData("IMAGEN: menos texto en placa", CommunityRevisionTarget.Designer)]
    [InlineData("TEXTO: caption mas filoso", CommunityRevisionTarget.Copywriter)]
    [InlineData("COPY: acortar el primer parrafo", CommunityRevisionTarget.Copywriter)]
    [InlineData("TODO: rehacer el enfoque", CommunityRevisionTarget.All)]
    [InlineData("Cambiar el video y tambien el caption", CommunityRevisionTarget.All)]
    public void DetectRevisionTarget_ReturnsExpected(string body, string expected)
    {
        Assert.Equal(expected, CommunityReviewService.DetectRevisionTarget(body));
    }

    [Fact]
    public void NormalizeFeedback_StripsQuotedReply()
    {
        var body = "VIDEO: hacerlo mas corto\n\nOn Mon, Apr 1, 2026 at 10:00 AM someone wrote:\n> quoted";

        var normalized = CommunityReviewService.NormalizeFeedback(body);

        Assert.Equal("VIDEO: hacerlo mas corto", normalized);
    }

    [Fact]
    public void AppendFeedbackHistoryJson_AppendsEntries()
    {
        var email = new IncomingEmail(
            MessageId: "m1",
            From: "reviewer@example.com",
            Subject: "[REVISIÓN CM abc123] Test",
            Body: "TEXTO: hacerlo mas concreto",
            Date: DateTimeOffset.Parse("2026-04-26T12:00:00Z"),
            InReplyTo: null);

        var json = CommunityReviewService.AppendFeedbackHistoryJson(
            existingJson: "[]",
            emails: [email],
            action: CommunityPublicationStatus.PendingReview,
            revisionTarget: CommunityRevisionTarget.Copywriter);

        Assert.Contains("reviewer@example.com", json);
        Assert.Contains("copywriter", json);
        Assert.Contains("hacerlo mas concreto", json);
    }

    [Fact]
    public void BuildReviewerMemory_KeepsOlderDistinctRulesBeyondRecentDrafts()
    {
        var publications = new List<CommunityPublicationEntity>
        {
            CreatePublication("Branding", "IMAGEN: no usar rojo", CommunityRevisionTarget.Designer, DateTimeOffset.Parse("2026-04-01T10:00:00Z")),
            CreatePublication("Tema 2", "TEXTO: hacerlo mas directo", CommunityRevisionTarget.Copywriter, DateTimeOffset.Parse("2026-04-02T10:00:00Z")),
            CreatePublication("Tema 3", "COPY: abrir con una pregunta", CommunityRevisionTarget.Copywriter, DateTimeOffset.Parse("2026-04-03T10:00:00Z")),
            CreatePublication("Tema 4", "VIDEO: bajar la duracion", CommunityRevisionTarget.Designer, DateTimeOffset.Parse("2026-04-04T10:00:00Z")),
            CreatePublication("Tema 5", "TODO: profundizar mas el insight", CommunityRevisionTarget.All, DateTimeOffset.Parse("2026-04-05T10:00:00Z")),
            CreatePublication("Tema 6", "TEXTO: menos hashtags", CommunityRevisionTarget.Copywriter, DateTimeOffset.Parse("2026-04-06T10:00:00Z")),
        };

        var memory = CommunityReviewService.BuildReviewerMemory(publications, maxEntries: 20);

        Assert.Contains("no usar rojo", memory, StringComparison.OrdinalIgnoreCase);
        Assert.Contains("Branding", memory, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildReviewerMemory_DeduplicatesRulesAndIgnoresApprovalEntries()
    {
        var publications = new List<CommunityPublicationEntity>
        {
            CreatePublication("Branding 1", "IMAGEN: no usar rojo", CommunityRevisionTarget.Designer, DateTimeOffset.Parse("2026-04-01T10:00:00Z")),
            CreatePublication("Branding 2", "IMAGEN: no usar rojo", CommunityRevisionTarget.Designer, DateTimeOffset.Parse("2026-04-07T10:00:00Z")),
            new()
            {
                Topic = "Aprobada",
                LastReviewerFeedback = "APROBAR",
                LastRevisionTarget = CommunityRevisionTarget.All,
                ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                    existingJson: "[]",
                    emails:
                    [
                        new IncomingEmail(
                            MessageId: "approve-1",
                            From: "reviewer@example.com",
                            Subject: "[REVISIÓN CM ok]",
                            Body: "APROBAR",
                            Date: DateTimeOffset.Parse("2026-04-08T10:00:00Z"),
                            InReplyTo: null)
                    ],
                    action: CommunityPublicationStatus.Approved,
                    revisionTarget: CommunityRevisionTarget.All),
                UpdatedAt = DateTimeOffset.Parse("2026-04-08T10:00:00Z"),
            }
        };

        var memory = CommunityReviewService.BuildReviewerMemory(publications, maxEntries: 20);

        Assert.Contains("visto 2 veces", memory, StringComparison.OrdinalIgnoreCase);
        Assert.DoesNotContain("APROBAR", memory, StringComparison.OrdinalIgnoreCase);
    }

    [Fact]
    public void BuildReviewActionUrl_ReturnsExpectedPath()
    {
        var url = CommunityReviewService.BuildReviewActionUrl(
            "https://ia.novitsoftware.com/",
            "abc123",
            "approve");

        Assert.Equal("https://ia.novitsoftware.com/api/community/review/abc123/approve", url);
    }

    private static CommunityPublicationEntity CreatePublication(string topic, string feedback, string revisionTarget, DateTimeOffset updatedAt) =>
        new()
        {
            Topic = topic,
            LastReviewerFeedback = feedback,
            LastRevisionTarget = revisionTarget,
            ReviewerFeedbackHistoryJson = CommunityReviewService.AppendFeedbackHistoryJson(
                existingJson: "[]",
                emails:
                [
                    new IncomingEmail(
                        MessageId: Guid.NewGuid().ToString("N"),
                        From: "reviewer@example.com",
                        Subject: $"[REVISIÓN CM {topic}]",
                        Body: feedback,
                        Date: updatedAt,
                        InReplyTo: null)
                ],
                action: CommunityPublicationStatus.PendingReview,
                revisionTarget: revisionTarget),
            UpdatedAt = updatedAt,
        };
}

public class ApiKeyAccessPolicyTests
{
    [Fact]
    public void IsRequestIpAllowed_Allows_Loopback_WhenNoAllowlistConfigured()
    {
        var allowed = ApiKeyAccessPolicy.IsRequestIpAllowed(IPAddress.Loopback, null);

        Assert.True(allowed);
    }

    [Fact]
    public void IsRequestIpAllowed_Rejects_PublicIp_WhenNoAllowlistConfigured()
    {
        var allowed = ApiKeyAccessPolicy.IsRequestIpAllowed(IPAddress.Parse("181.92.127.116"), null);

        Assert.False(allowed);
    }

    [Fact]
    public void IsRequestIpAllowed_Matches_ExactIp()
    {
        var allowed = ApiKeyAccessPolicy.IsRequestIpAllowed(
            IPAddress.Parse("181.92.127.116"),
            "181.92.127.116, 10.0.0.5");

        Assert.True(allowed);
    }

    [Fact]
    public void IsRequestIpAllowed_Matches_Cidr()
    {
        var allowed = ApiKeyAccessPolicy.IsRequestIpAllowed(
            IPAddress.Parse("181.92.127.116"),
            "181.92.127.0/24");

        Assert.True(allowed);
    }

    [Fact]
    public void IsRequestIpAllowed_Rejects_IpOutsideAllowlist()
    {
        var allowed = ApiKeyAccessPolicy.IsRequestIpAllowed(
            IPAddress.Parse("181.92.127.116"),
            "10.0.0.0/8, 192.168.1.50");

        Assert.False(allowed);
    }

    [Fact]
    public void IsRequestIpAllowed_Allows_Loopback_EvenWhenAllowlistConfigured()
    {
        var allowed = ApiKeyAccessPolicy.IsRequestIpAllowed(
            IPAddress.Loopback,
            "181.92.127.116/32");

        Assert.True(allowed);
    }
}