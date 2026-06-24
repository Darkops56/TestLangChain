using Microsoft.AspNetCore.Mvc;
using Microsoft.EntityFrameworkCore;
using CmPlatform.Api.Data;

namespace CmPlatform.Api.Controllers;

[ApiController]
[Route("api/health")]
public sealed class HealthController(NovitDbContext db, ILogger<HealthController> logger) : ControllerBase
{
    [HttpGet]
    public async Task<IActionResult> GetHealth()
    {
        var dbStatus = "unknown";

        try
        {
            dbStatus = await db.Database.CanConnectAsync() ? "ok" : "error";
        }
        catch (Exception ex)
        {
            logger.LogWarning(ex, "Health check: database connection failed");
            dbStatus = "error";
        }

        return Ok(new
        {
            status = "ok",
            services = new
            {
                database = dbStatus,
            }
        });
    }
}
