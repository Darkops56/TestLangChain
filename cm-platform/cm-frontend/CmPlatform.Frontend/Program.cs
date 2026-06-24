using Microsoft.AspNetCore.Components.Web;
using Microsoft.AspNetCore.Components.WebAssembly.Hosting;
using MudBlazor.Services;
using CmPlatform.Frontend;
using CmPlatform.Frontend.Services;

var builder = WebAssemblyHostBuilder.CreateDefault(args);
builder.RootComponents.Add<App>("#app");
builder.RootComponents.Add<HeadOutlet>("head::after");

builder.Services.AddMudServices();
builder.Services.AddSingleton<AuthService>();
builder.Services.AddScoped<ApiClient>();
builder.Services.AddSingleton<NotificationService>();

await builder.Build().RunAsync();
