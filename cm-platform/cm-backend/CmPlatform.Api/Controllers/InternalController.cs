using System.Text.Json;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Filters;
using CmPlatform.Api.Models;
using CmPlatform.Api.Services;

namespace CmPlatform.Api.Controllers;

[ApiController]
[Route("api/internal")]
[RequireInternalKey]
public sealed class InternalController(
    NovitDbContext db,
    CommunityReviewService communityReviewService) : ControllerBase
{
    [HttpGet("community/reviewer-memory")]
    public async Task<IActionResult> GetReviewerMemory()
    {
        var memory = await communityReviewService.BuildReviewerMemoryAsync();
        return Ok(new { memory });
    }

    [HttpGet("community/publication-history")]
    public async Task<IActionResult> GetPublicationHistory([FromQuery] int limit = 5)
    {
        var publications = await db.CommunityPublications
            .Where(p => p.Status == CommunityPublicationStatus.Published)
            .OrderByDescending(p => p.PublishedAt)
            .Take(limit)
            .Select(p => $"[{p.Platform}] {p.Topic} ({p.CreatedAt:yyyy-MM-dd})")
            .ToListAsync();

        return Ok(new { publications });
    }

    [HttpGet("community/published-image-references")]
    public async Task<IActionResult> GetPublishedImageReferences([FromQuery] int limit = 2)
    {
        var references = await db.CommunityPublications
            .Where(p => p.Status == CommunityPublicationStatus.Published && p.ContentType == "image")
            .OrderByDescending(p => p.PublishedAt)
            .Take(limit)
            .Select(p => new
            {
                p.Id,
                p.Topic,
                p.Angle,
                p.Caption,
                p.CreatedAt
            })
            .ToListAsync();

        return Ok(new { references });
    }

    [HttpPost("community/drafts")]
    public async Task<IActionResult> CreateDraft([FromBody] JsonElement draft)
    {
        var entity = new CommunityPublicationEntity
        {
            ContentType = draft.TryGetProperty("content_type", out var ct) ? ct.GetString() ?? "" : "",
            Topic = draft.TryGetProperty("topic", out var t) ? t.GetString() ?? "" : "",
            Angle = draft.TryGetProperty("angle", out var a) ? a.GetString() ?? "" : "",
            Objective = draft.TryGetProperty("objective", out var o) ? o.GetString() ?? "" : "",
            Caption = draft.TryGetProperty("caption", out var cap) ? cap.GetString() ?? "" : "",
            Platform = draft.TryGetProperty("platform", out var p) ? p.GetString() ?? "instagram" : "instagram",
            Status = CommunityPublicationStatus.PendingReview,
            StrategyJson = draft.TryGetProperty("strategy_json", out var sj) ? sj.GetRawText() : "{}",
            CopyJson = draft.TryGetProperty("copy_json", out var cj) ? cj.GetRawText() : "{}",
            DesignJson = draft.TryGetProperty("design_json", out var dj) ? dj.GetRawText() : "{}",
        };

        db.CommunityPublications.Add(entity);
        await db.SaveChangesAsync();

        return Ok(new { id = entity.Id, status = entity.Status, review_token = entity.ReviewToken });
    }

    [HttpPost("publications")]
    public async Task<IActionResult> CreatePublication([FromBody] CreateInternalPublicationRequest request)
    {
        var client = await db.Clients.FindAsync(request.ClientId);
        if (client is null)
            return BadRequest(new { error = "Client not found" });

        var pub = new PublicationEntity
        {
            ClientId = request.ClientId,
            Platform = request.Platform,
            ContentType = request.ContentType,
            Content = request.Content,
            MediaUrlsJson = request.MediaUrlsJson ?? "[]",
            Status = request.Status ?? "draft",
            ScheduledAt = request.ScheduledAt,
            PublishedAt = request.PublishedAt,
        };

        db.Publications.Add(pub);
        await db.SaveChangesAsync();

        return Ok(new { pub.Id, pub.Status, pub.CreatedAt });
    }

    [HttpPut("publications/{id:guid}/status")]
    public async Task<IActionResult> UpdatePublicationStatus(Guid id, [FromBody] UpdateInternalStatusRequest request)
    {
        var pub = await db.Publications.FindAsync(id);
        if (pub is null)
            return NotFound();

        pub.Status = request.Status;
        if (request.Status == "published")
            pub.PublishedAt = DateTimeOffset.UtcNow;
        pub.UpdatedAt = DateTimeOffset.UtcNow;

        await db.SaveChangesAsync();
        return Ok(new { pub.Id, pub.Status });
    }

    public sealed record CreateInternalPublicationRequest(
        Guid ClientId,
        string Platform,
        string ContentType,
        string Content,
        string? MediaUrlsJson,
        string? Status,
        DateTimeOffset? ScheduledAt,
        DateTimeOffset? PublishedAt);

    public sealed record UpdateInternalStatusRequest(string Status);
}
