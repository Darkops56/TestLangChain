using Microsoft.AspNetCore.Mvc;
using System.Net.Mail;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

namespace Novit.Web.Api.Controllers;

[ApiController]
[Route("api/contact")]
public sealed class ContactController(IPipedriveService pipedriveService) : ControllerBase
{
    [HttpPost("form")]
    public async Task<ActionResult<ContactFormResponse>> SubmitForm([FromBody] ContactFormRequest request, CancellationToken ct)
    {
        if (!IsValidEmail(request.Email))
        {
            return BadRequest(new { error = "Valid email is required." });
        }

        var pipedriveId = await pipedriveService.CreateLeadAsync(request.Name, request.Email, request.Message, ct);
        return Ok(new ContactFormResponse(true, pipedriveId ?? $"lead-{Guid.NewGuid():N}"));
    }

    [HttpPost("auth-gate")]
    public async Task<ActionResult<AuthGateResponse>> AuthGate([FromBody] AuthGateRequest request, CancellationToken ct)
    {
        if (!IsValidEmail(request.Email))
        {
            return BadRequest(new { error = "Valid email is required." });
        }

        var personId = await pipedriveService.FindOrCreatePersonAsync(request.Email, ct);
        return Ok(new AuthGateResponse(true, personId ?? $"person-{Guid.NewGuid():N}"));
    }

    private static bool IsValidEmail(string? email)
    {
        if (string.IsNullOrWhiteSpace(email))
        {
            return false;
        }

        try
        {
            _ = new MailAddress(email);
            return true;
        }
        catch
        {
            return false;
        }
    }
}
