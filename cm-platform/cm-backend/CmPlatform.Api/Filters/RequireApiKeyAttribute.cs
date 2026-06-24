using System.Net;
using System.Net.Sockets;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Filters;

namespace CmPlatform.Api.Filters;

/// <summary>
/// Action filter that requires a valid API key in the <c>X-Api-Key</c> header.
/// The expected key is read from the <c>AdminApiKey</c> configuration / environment variable.
/// Returns 401 if missing or invalid.
/// </summary>
[AttributeUsage(AttributeTargets.Class | AttributeTargets.Method)]
public sealed class RequireApiKeyAttribute : Attribute, IAsyncActionFilter
{
    private const string HeaderName = "X-Api-Key";

    public async Task OnActionExecutionAsync(ActionExecutingContext context, ActionExecutionDelegate next)
    {
        var configuration = context.HttpContext.RequestServices.GetRequiredService<IConfiguration>();
        var expectedKey = configuration["AdminApiKey"];

        // If no key is configured, reject all requests (fail-closed)
        if (string.IsNullOrWhiteSpace(expectedKey))
        {
            context.Result = new ObjectResult(new { error = "API key not configured on server." })
            {
                StatusCode = StatusCodes.Status500InternalServerError
            };
            return;
        }

        if (!context.HttpContext.Request.Headers.TryGetValue(HeaderName, out var providedKey)
            || !string.Equals(expectedKey, providedKey.ToString(), StringComparison.Ordinal))
        {
            context.Result = new UnauthorizedObjectResult(new { error = "Invalid or missing API key." });
            return;
        }

        var allowedIps = configuration["AdminApiAllowedIps"];
        if (!ApiKeyAccessPolicy.IsRequestIpAllowed(context.HttpContext.Connection.RemoteIpAddress, allowedIps))
        {
            context.Result = new ObjectResult(new { error = "Your IP is not allowed to access this admin API." })
            {
                StatusCode = StatusCodes.Status403Forbidden
            };
            return;
        }

        await next();
    }
}

internal static class ApiKeyAccessPolicy
{
    public static bool IsRequestIpAllowed(IPAddress? remoteIp, string? allowedIps)
    {
        if (remoteIp is null)
            return false;

        var normalizedRemoteIp = Normalize(remoteIp);
        if (IPAddress.IsLoopback(normalizedRemoteIp))
            return true;

        var rules = ParseRules(allowedIps);
        if (rules.Count == 0)
            return false;

        return rules.Any(rule => rule.Matches(normalizedRemoteIp));
    }

    private static List<IpRule> ParseRules(string? allowedIps)
    {
        if (string.IsNullOrWhiteSpace(allowedIps))
            return [];

        var rules = new List<IpRule>();
        var tokens = allowedIps
            .Split([',', ';', '\n', '\r', '\t', ' '], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);

        foreach (var token in tokens)
        {
            if (TryParseRule(token, out var rule))
                rules.Add(rule);
        }

        return rules;
    }

    private static bool TryParseRule(string token, out IpRule rule)
    {
        rule = default;

        var separatorIndex = token.IndexOf('/');
        if (separatorIndex >= 0)
        {
            var addressPart = token[..separatorIndex];
            var prefixPart = token[(separatorIndex + 1)..];
            if (!IPAddress.TryParse(addressPart, out var networkAddress) ||
                !int.TryParse(prefixPart, out var prefixLength))
            {
                return false;
            }

            var normalizedNetwork = Normalize(networkAddress);
            var maxPrefixLength = normalizedNetwork.GetAddressBytes().Length * 8;
            if (prefixLength < 0 || prefixLength > maxPrefixLength)
                return false;

            rule = new IpRule(normalizedNetwork, prefixLength, true);
            return true;
        }

        if (!IPAddress.TryParse(token, out var address))
            return false;

        var normalizedAddress = Normalize(address);
        rule = new IpRule(normalizedAddress, normalizedAddress.GetAddressBytes().Length * 8, false);
        return true;
    }

    private static IPAddress Normalize(IPAddress address) =>
        address.IsIPv4MappedToIPv6 ? address.MapToIPv4() : address;

    private readonly record struct IpRule(IPAddress Address, int PrefixLength, bool IsCidr)
    {
        public bool Matches(IPAddress remoteIp)
        {
            if (remoteIp.AddressFamily != Address.AddressFamily)
                return false;

            if (!IsCidr)
                return remoteIp.Equals(Address);

            var networkBytes = Address.GetAddressBytes();
            var remoteBytes = remoteIp.GetAddressBytes();
            var fullBytes = PrefixLength / 8;
            var remainingBits = PrefixLength % 8;

            for (var index = 0; index < fullBytes; index++)
            {
                if (networkBytes[index] != remoteBytes[index])
                    return false;
            }

            if (remainingBits == 0)
                return true;

            var mask = (byte)(0xFF << (8 - remainingBits));
            return (networkBytes[fullBytes] & mask) == (remoteBytes[fullBytes] & mask);
        }
    }
}
