using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.SignalR;
using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;
using CmPlatform.Api.Hubs;

namespace CmPlatform.Api.Controllers;

[ApiController]
[Route("api/publications")]
[Authorize]
public sealed class PublicationsController(NovitDbContext db, IHubContext<NotificationHub> hub) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetAll([FromQuery] Guid? clientId, [FromQuery] string? status)
    {
        var query = db.Publications.AsQueryable();

        if (clientId.HasValue)
            query = query.Where(p => p.ClientId == clientId.Value);

        if (!string.IsNullOrWhiteSpace(status))
            query = query.Where(p => p.Status == status);

        var publications = await query
            .Include(p => p.Client)
            .OrderByDescending(p => p.CreatedAt)
            .ToListAsync();

        return Ok(publications.Select(MapPublication));
    }

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetById(Guid id)
    {
        var pub = await db.Publications
            .Include(p => p.Client)
            .FirstOrDefaultAsync(p => p.Id == id);

        if (pub is null)
            return NotFound();

        return Ok(MapPublication(pub));
    }

    [HttpPost]
    public async Task<IActionResult> Create([FromBody] CreatePublicationRequest request)
    {
        var client = await db.Clients.FindAsync(request.ClientId);
        if (client is null)
            return BadRequest(new { error = "Client not found" });

        var publication = new PublicationEntity
        {
            ClientId = request.ClientId,
            Platform = request.Platform,
            ContentType = request.ContentType,
            Content = request.Content,
            MediaUrlsJson = request.MediaUrlsJson ?? "[]",
            Status = "draft",
            ScheduledAt = request.ScheduledAt,
        };

        db.Publications.Add(publication);
        await db.SaveChangesAsync();

        return CreatedAtAction(nameof(GetById), new { id = publication.Id }, MapPublication(publication));
    }

    [HttpPut("{id:guid}/status")]
    public async Task<IActionResult> UpdateStatus(Guid id, [FromBody] UpdateStatusRequest request)
    {
        var pub = await db.Publications.FindAsync(id);
        if (pub is null)
            return NotFound();

        pub.Status = request.Status;
        if (request.Status == "published")
            pub.PublishedAt = DateTimeOffset.UtcNow;

        if (request.ScheduledAt.HasValue)
            pub.ScheduledAt = request.ScheduledAt;

        pub.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync();

        await hub.Clients.Group($"client-{pub.ClientId}").SendAsync("PublicationStatusChanged", new
        {
            pub.Id,
            pub.ClientId,
            pub.Status,
            pub.Platform,
            pub.ContentType,
        });

        return Ok(MapPublication(pub));
    }

    [HttpDelete("{id:guid}")]
    public async Task<IActionResult> Delete(Guid id)
    {
        var pub = await db.Publications.FindAsync(id);
        if (pub is null)
            return NotFound();

        db.Publications.Remove(pub);
        await db.SaveChangesAsync();
        return NoContent();
    }

    private static object MapPublication(PublicationEntity p) => new
    {
        p.Id,
        p.ClientId,
        ClientName = p.Client?.Name,
        p.Platform,
        p.ContentType,
        p.Content,
        p.Status,
        p.ScheduledAt,
        p.PublishedAt,
        p.CreatedAt,
        p.UpdatedAt,
    };

    public sealed record CreatePublicationRequest(
        Guid ClientId,
        string Platform,
        string ContentType,
        string Content,
        string? MediaUrlsJson,
        DateTimeOffset? ScheduledAt);

    public sealed record UpdateStatusRequest(string Status, DateTimeOffset? ScheduledAt = null);
}
