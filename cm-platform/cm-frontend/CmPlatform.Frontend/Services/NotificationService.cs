using System.Text.Json;
using Microsoft.AspNetCore.SignalR.Client;

namespace CmPlatform.Frontend.Services;

public sealed class NotificationService : IAsyncDisposable
{
    private HubConnection? _connection;

    public event Action<JsonElement>? OnPublicationStatusChanged;

    public async Task ConnectAsync(string hubUrl, string token)
    {
        _connection = new HubConnectionBuilder()
            .WithUrl(hubUrl, options =>
            {
                options.AccessTokenProvider = () => Task.FromResult(token)!;
            })
            .WithAutomaticReconnect()
            .Build();

        _connection.On<JsonElement>("PublicationStatusChanged", data =>
        {
            OnPublicationStatusChanged?.Invoke(data);
        });

        await _connection.StartAsync();
    }

    public async Task JoinClientGroup(Guid clientId)
    {
        if (_connection is not null)
            await _connection.InvokeAsync("JoinGroup", $"client-{clientId}");
    }

    public async ValueTask DisposeAsync()
    {
        if (_connection is not null)
            await _connection.DisposeAsync();
    }
}
