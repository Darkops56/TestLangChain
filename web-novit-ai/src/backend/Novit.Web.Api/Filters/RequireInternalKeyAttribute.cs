using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;

namespace Novit.Web.Api.Filters;

/// <summary>
/// Action filter that requires a valid internal API key in the <c>X-Internal-Key</c> header.
/// Used to protect endpoints that are only called by the Python agent service (internal Docker network).
/// The expected key is read from the <c>INTERNAL_API_KEY</c> configuration / environment variable.
/// Returns 401 if the key is missing or invalid. If no key is configured, all requests are allowed (dev mode).
/// </summary>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
public sealed class RequireInternalKeyAttribute : Attribute, IAsyncActionFilter
{
    private const string HeaderName = "X-Internal-Key";

    public async Task OnActionExecutionAsync(ActionExecutingContext context, ActionExecutionDelegate next)
    {
        var configuration = context.HttpContext.RequestServices.GetRequiredService<IConfiguration>();
        var expectedKey = configuration["INTERNAL_API_KEY"];

        // If no key is configured, allow all requests (dev mode / backward compat)
        if (string.IsNullOrWhiteSpace(expectedKey))
        {
            await next();
            return;
        }

        if (!context.HttpContext.Request.Headers.TryGetValue(HeaderName, out var providedKey)
            || !string.Equals(expectedKey, providedKey.ToString(), StringComparison.Ordinal))
        {
            context.Result = new UnauthorizedObjectResult(new { error = "Invalid or missing internal API key." });
            return;
        }

        await next();
    }
}
