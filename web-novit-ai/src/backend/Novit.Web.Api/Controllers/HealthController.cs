using Microsoft.AspNetCore.Mvc;
using Novit.Web.Api.Data;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

[ApiController]
[Route("api/health")]
public sealed class HealthController(
    IChatAIService aiService,
    ISpeechService speechService,
    IPipedriveService pipedriveService,
    IServiceProvider serviceProvider) : ControllerBase
{
    [HttpGet]
    public ActionResult<HealthResponse> GetHealth()
    {
        var dbStatus = "not_configured";
        var dbContext = serviceProvider.GetService<NovitDbContext>();
        if (dbContext is not null)
        {
            try
            {
                dbStatus = dbContext.Database.CanConnect() ? "ok" : "error";
            }
            catch
            {
                dbStatus = "error";
            }
        }

        return Ok(new HealthResponse("ok", new
        {
            db = dbStatus,
            foundry = aiService.IsConfigured ? "ok" : "not_configured",
            speech = speechService.IsConfigured ? "ok" : "not_configured",
            pipedrive = pipedriveService.IsConfigured ? "ok" : "not_configured"
        }));
    }
}
