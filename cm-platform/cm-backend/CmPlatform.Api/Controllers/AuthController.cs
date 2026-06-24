using Microsoft.AspNetCore.Authorization;
using System.IdentityModel.Tokens.Jwt;
using System.Security.Claims;
using System.Text;
using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using CmPlatform.Api.Data;
using CmPlatform.Api.Data.Entities;

namespace CmPlatform.Api.Controllers;

[ApiController]
[Route("api/auth")]
public sealed class AuthController(NovitDbContext db, IConfiguration configuration) : ControllerBase
{
    [HttpGet("me")]
    [Authorize]
    public async Task<IActionResult> GetCurrentUser()
    {
        var userIdClaim = User.FindFirst(ClaimTypes.NameIdentifier)?.Value;
        if (userIdClaim is null || !Guid.TryParse(userIdClaim, out var userId))
            return Unauthorized();

        var client = await db.Clients
            .Include(c => c.SocialAccounts)
            .FirstOrDefaultAsync(c => c.Id == userId);

        if (client is null)
            return NotFound();

        return Ok(new
        {
            client.Id,
            client.Name,
            client.Email,
            client.Phone,
            client.Company,
            client.SubscriptionStatus,
            client.CreatedAt,
        });
    }

    [HttpPost("login")]
    public async Task<IActionResult> Login([FromBody] LoginRequest request)
    {
        var client = await db.Clients.FirstOrDefaultAsync(c => c.Email == request.Email);
        if (client is null)
            return Unauthorized(new { error = "Invalid email" });

        var token = GenerateToken(client);
        return Ok(new
        {
            token,
            client = new
            {
                client.Id,
                client.Name,
                client.Email,
                client.SubscriptionStatus,
            }
        });
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

    public sealed record LoginRequest(string Email);
}
