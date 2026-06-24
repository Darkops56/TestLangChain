namespace Novit.Web.Api.Models;

public sealed class CalComOptions
{
    /// <summary>Base URL of the Cal.com instance (e.g. https://api.cal.com or self-hosted URL).</summary>
    public string? BaseUrl { get; set; }

    /// <summary>API key prefixed with cal_ for authenticating against Cal.com v2 API.</summary>
    public string? ApiKey { get; set; }

    /// <summary>Event type ID used for "demo" meetings (product demo with a partner).</summary>
    public int? EventTypeIdDemo { get; set; }

    /// <summary>Event type ID used for "discovery" meetings (initial discovery call).</summary>
    public int? EventTypeIdDiscovery { get; set; }

    /// <summary>Default meeting duration in minutes. Falls back to 30.</summary>
    public int DefaultDurationMinutes { get; set; } = 30;

    /// <summary>
    /// Npgsql connection string pointing to the Cal.com database.
    /// Used to clean up stale idempotency keys from cancelled bookings
    /// (workaround for Cal.com not clearing them on cancellation).
    /// </summary>
    public string? DatabaseConnectionString { get; set; }

    public bool IsConfigured =>
        !string.IsNullOrWhiteSpace(BaseUrl) &&
        !string.IsNullOrWhiteSpace(ApiKey) &&
        (EventTypeIdDemo.HasValue || EventTypeIdDiscovery.HasValue);
}
