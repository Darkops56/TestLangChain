using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;

namespace CmPlatform.Api.Controllers;

[ApiController]
[Route("api/billing")]
[Authorize]
public sealed class BillingController(NovitDbContext db) : ControllerBase
{
    [HttpGet("invoices")]
    public async Task<IActionResult> GetInvoices([FromQuery] Guid? clientId, [FromQuery] string? status)
    {
        var query = db.Invoices.AsQueryable();

        if (clientId.HasValue)
            query = query.Where(i => i.ClientId == clientId.Value);

        if (!string.IsNullOrWhiteSpace(status))
            query = query.Where(i => i.Status == status);

        var invoices = await query
            .Include(i => i.Client)
            .OrderByDescending(i => i.CreatedAt)
            .ToListAsync();

        return Ok(invoices.Select(MapInvoice));
    }

    [HttpGet("invoices/{id:guid}")]
    public async Task<IActionResult> GetInvoiceById(Guid id)
    {
        var invoice = await db.Invoices
            .Include(i => i.Client)
            .FirstOrDefaultAsync(i => i.Id == id);

        if (invoice is null)
            return NotFound();

        return Ok(MapInvoice(invoice));
    }

    [HttpPost("invoices")]
    public async Task<IActionResult> CreateInvoice([FromBody] CreateInvoiceRequest request)
    {
        var client = await db.Clients.FindAsync(request.ClientId);
        if (client is null)
            return BadRequest(new { error = "Client not found" });

        var invoice = new InvoiceEntity
        {
            ClientId = request.ClientId,
            Amount = request.Amount,
            Currency = request.Currency ?? "USD",
            Description = request.Description,
            DueAt = request.DueAt,
            Status = "pending",
        };

        db.Invoices.Add(invoice);
        await db.SaveChangesAsync();

        return CreatedAtAction(nameof(GetInvoiceById), new { id = invoice.Id }, MapInvoice(invoice));
    }

    [HttpPost("invoices/{id:guid}/pay")]
    public async Task<IActionResult> MarkAsPaid(Guid id)
    {
        var invoice = await db.Invoices.FindAsync(id);
        if (invoice is null)
            return NotFound();

        invoice.Status = "paid";
        invoice.PaidAt = DateTimeOffset.UtcNow;
        invoice.UpdatedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync();

        return Ok(MapInvoice(invoice));
    }

    private static object MapInvoice(InvoiceEntity i) => new
    {
        i.Id,
        i.ClientId,
        ClientName = i.Client?.Name,
        i.Amount,
        i.Currency,
        i.Status,
        i.Description,
        i.DueAt,
        i.PaidAt,
        i.CreatedAt,
    };

    public sealed record CreateInvoiceRequest(
        Guid ClientId,
        decimal Amount,
        string? Currency,
        string? Description,
        DateTimeOffset DueAt);
}
