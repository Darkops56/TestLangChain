using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;

namespace CmPlatform.Api.Controllers;

[ApiController]
[Route("api/clients")]
public sealed class ClientsController(
    NovitDbContext db,
    IConfiguration configuration) : ControllerBase
{
    [HttpPost("register")]
    public async Task<IActionResult> Register([FromBody] RegisterRequest request)
    {
        var existing = await db.Clients.AnyAsync(c => c.Email == request.Email);
        if (existing)
            return Conflict(new { error = "A client with this email already exists" });

        var client = new ClientEntity
        {
            Name = request.Name,
            Email = request.Email,
            Phone = request.Phone,
            Company = request.Company,
        };

        db.Clients.Add(client);
        await db.SaveChangesAsync();

        var token = GenerateToken(client);

        return Ok(new { client = MapClient(client), token });
    }

    [HttpGet]
    [Authorize]
    public async Task<IActionResult> GetAll()
    {
        var clients = await db.Clients
            .Include(c => c.SocialAccounts)
            .OrderByDescending(c => c.CreatedAt)
            .ToListAsync();

        return Ok(clients.Select(MapClient));
    }

    [HttpGet("{id:guid}")]
    [Authorize]
    public async Task<IActionResult> GetById(Guid id)
    {
        var client = await db.Clients
            .Include(c => c.SocialAccounts)
            .Include(c => c.Publications)
            .Include(c => c.Invoices)
            .FirstOrDefaultAsync(c => c.Id == id);

        if (client is null)
            return NotFound();

        return Ok(MapClient(client));
    }

    [HttpPut("{id:guid}")]
    [Authorize]
    public async Task<IActionResult> Update(Guid id, [FromBody] UpdateClientRequest request)
    {
        var client = await db.Clients.FindAsync(id);
        if (client is null)
            return NotFound();

        if (request.Name is not null) client.Name = request.Name;
        if (request.Phone is not null) client.Phone = request.Phone;
        if (request.Company is not null) client.Company = request.Company;
        if (request.Notes is not null) client.Notes = request.Notes;
        client.UpdatedAt = DateTimeOffset.UtcNow;

        await db.SaveChangesAsync();
        return Ok(MapClient(client));
    }

    [HttpDelete("{id:guid}")]
    [Authorize]
    public async Task<IActionResult> Delete(Guid id)
    {
        var client = await db.Clients.FindAsync(id);
        if (client is null)
            return NotFound();

        db.Clients.Remove(client);
        await db.SaveChangesAsync();
        return NoContent();
    }

    [HttpGet("{id:guid}/social-accounts")]
    [Authorize]
    public async Task<IActionResult> GetSocialAccounts(Guid id)
    {
        var client = await db.Clients.AnyAsync(c => c.Id == id);
        if (!client)
            return NotFound();

        var accounts = await db.SocialAccounts
            .Where(s => s.ClientId == id)
            .OrderBy(s => s.Platform)
            .ToListAsync();

        return Ok(accounts.Select(s => new
        {
            s.Id,
            s.Platform,
            s.Username,
            s.IsActive,
            s.CreatedAt,
        }));
    }

    [HttpPost("{id:guid}/social-accounts")]
    [Authorize]
    public async Task<IActionResult> AddSocialAccount(Guid id, [FromBody] AddSocialAccountRequest request)
    {
        var client = await db.Clients.AnyAsync(c => c.Id == id);
        if (!client)
            return NotFound();

        var account = new SocialAccountEntity
        {
            ClientId = id,
            Platform = request.Platform,
            Username = request.Username,
            AccessToken = request.AccessToken,
            RefreshToken = request.RefreshToken,
            TokenExpiresAt = request.TokenExpiresAt,
        };

        db.SocialAccounts.Add(account);
        await db.SaveChangesAsync();

        return Ok(new { account.Id, account.Platform, account.Username, account.IsActive });
    }

    [HttpDelete("{clientId:guid}/social-accounts/{accountId:guid}")]
    [Authorize]
    public async Task<IActionResult> DeleteSocialAccount(Guid clientId, Guid accountId)
    {
        var account = await db.SocialAccounts.FirstOrDefaultAsync(s => s.Id == accountId && s.ClientId == clientId);
        if (account is null)
            return NotFound();

        db.SocialAccounts.Remove(account);
        await db.SaveChangesAsync();
        return NoContent();
    }

    private string GenerateToken(ClientEntity client)
    {
        var jwtSecret = configuration["JWT:Secret"] ?? "default-dev-secret-change-in-production";
        var issuer = configuration["JWT:Issuer"] ?? "cm-platform";
        var audience = configuration["JWT:Audience"] ?? "cm-frontend";

        var claims = new[]
        {
            new Claim(ClaimTypes.NameIdentifier, client.Id.ToString()),
            new Claim(ClaimTypes.Email, client.Email),
            new Claim(ClaimTypes.Name, client.Name),
        };

        var key = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSecret));
        var creds = new SigningCredentials(key, SecurityAlgorithms.HmacSha256);

        var token = new JwtSecurityToken(
            issuer: issuer,
            audience: audience,
            claims: claims,
            expires: DateTime.UtcNow.AddDays(30),
            signingCredentials: creds);

        return new JwtSecurityTokenHandler().WriteToken(token);
    }

    private static object MapClient(ClientEntity c) => new
    {
        c.Id,
        c.Name,
        c.Email,
        c.Phone,
        c.Company,
        c.Notes,
        c.SubscriptionStatus,
        c.CreatedAt,
        c.UpdatedAt,
        SocialAccounts = c.SocialAccounts?.Select(s => new
        {
            s.Id,
            s.Platform,
            s.Username,
            s.IsActive,
        }),
    };

    public sealed record RegisterRequest(
        string Name,
        string Email,
        string? Phone,
        string? Company);

    public sealed record UpdateClientRequest(
        string? Name,
        string? Phone,
        string? Company,
        string? Notes);

    public sealed record AddSocialAccountRequest(
        string Platform,
        string Username,
        string? AccessToken,
        string? RefreshToken,
        DateTimeOffset? TokenExpiresAt);
}
