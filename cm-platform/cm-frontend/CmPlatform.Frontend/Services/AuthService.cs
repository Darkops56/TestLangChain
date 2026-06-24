using Microsoft.JSInterop;
using System.Net.Http.Headers;

namespace CmPlatform.Frontend.Services;

public sealed class AuthService
{
    private const string TokenKey = "cm_auth_token";
    private readonly IJSRuntime _js;

    public AuthService(IJSRuntime js)
    {
        _js = js;
    }

    public string? Token { get; private set; }
    public bool IsLoggedIn => !string.IsNullOrEmpty(Token);

    public async Task InitAsync()
    {
        try
        {
            Token = await _js.InvokeAsync<string?>("localStorage.getItem", TokenKey);
        }
        catch
        {
            Token = null;
        }
    }

    public async Task SetTokenAsync(string token)
    {
        Token = token;
        try
        {
            await _js.InvokeVoidAsync("localStorage.setItem", TokenKey, token);
        }
        catch { }
    }

    public async Task LogoutAsync()
    {
        Token = null;
        try
        {
            await _js.InvokeVoidAsync("localStorage.removeItem", TokenKey);
        }
        catch { }
    }
}
