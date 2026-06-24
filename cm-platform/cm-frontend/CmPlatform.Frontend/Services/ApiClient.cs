using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace CmPlatform.Frontend.Services;

public sealed class ApiClient
{
    private readonly HttpClient _http;
    private readonly AuthService _auth;

    public ApiClient(AuthService auth)
    {
        _http = new HttpClient { BaseAddress = new Uri("http://localhost:5000") };
        _auth = auth;
    }

    private void ApplyAuth()
    {
        _http.DefaultRequestHeaders.Authorization =
            _auth.IsLoggedIn ? new AuthenticationHeaderValue("Bearer", _auth.Token) : null;
    }

    public Task<HttpResponseMessage> GetAsync(string url)
    {
        ApplyAuth();
        return _http.GetAsync(url);
    }

    public Task<T?> GetFromJsonAsync<T>(string url, JsonSerializerOptions? options = null)
    {
        ApplyAuth();
        return _http.GetFromJsonAsync<T>(url, options);
    }

    public Task<HttpResponseMessage> PostAsJsonAsync<T>(string url, T value)
    {
        ApplyAuth();
        return _http.PostAsJsonAsync(url, value);
    }

    public Task<HttpResponseMessage> PostAsync(string url, HttpContent? content)
    {
        ApplyAuth();
        return _http.PostAsync(url, content);
    }

    public Task<HttpResponseMessage> DeleteAsync(string url)
    {
        ApplyAuth();
        return _http.DeleteAsync(url);
    }

    public Task<HttpResponseMessage> PutAsJsonAsync<T>(string url, T value)
    {
        ApplyAuth();
        return _http.PutAsJsonAsync(url, value);
    }

    public string? GetToken() => _auth.IsLoggedIn ? _auth.Token : null;
}
