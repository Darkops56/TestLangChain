using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.EntityFrameworkCore;
using Novit.Web.Api.Data;
using Novit.Web.Api.Hubs;
using Novit.Web.Api.Models;
using Novit.Web.Api.Services;

var builder = WebApplication.CreateBuilder(args);

// Bind options from environment variables
builder.Services.Configure<AzureAIOptions>(opts =>
{
    opts.AIFoundryDeployment = builder.Configuration["AIFoundryDeployment"];
    opts.AIFoundryKey = builder.Configuration["AIFoundryKey"];
    opts.AzureAISpeechKey = builder.Configuration["AzureAISpeechKey"];
    opts.AzureAISpeechUrl = builder.Configuration["AzureAISpeechUrl"];
    opts.STTUrl = builder.Configuration["STTUrl"];
    opts.TTSUrl = builder.Configuration["TTSUrl"];
});

builder.Services.Configure<PipedriveOptions>(opts =>
{
    opts.PipedriveKey = builder.Configuration["PipedriveKey"];
    opts.PipedriveBaseUrl = builder.Configuration["PipedriveBaseUrl"];
});

builder.Services.Configure<CalComOptions>(opts =>
{
    opts.BaseUrl = builder.Configuration["CalCom:BaseUrl"];
    opts.ApiKey = builder.Configuration["CalCom:ApiKey"];
    if (int.TryParse(builder.Configuration["CalCom:EventTypeIdDemo"], out var demoId))
        opts.EventTypeIdDemo = demoId;
    if (int.TryParse(builder.Configuration["CalCom:EventTypeIdDiscovery"], out var discoveryId))
        opts.EventTypeIdDiscovery = discoveryId;
    if (int.TryParse(builder.Configuration["CalCom:DefaultDurationMinutes"], out var duration))
        opts.DefaultDurationMinutes = duration;

    // Derive CalCom DB connection string from the main one (same Postgres, different database)
    var mainConn = builder.Configuration.GetConnectionString("DefaultConnection");
    if (!string.IsNullOrWhiteSpace(mainConn))
    {
        var connBuilder = new Npgsql.NpgsqlConnectionStringBuilder(mainConn) { Database = "calcom" };
        opts.DatabaseConnectionString = connBuilder.ConnectionString;
    }
});

builder.Services.Configure<NurturingOptions>(opts =>
{
    if (bool.TryParse(builder.Configuration["Nurturing:Enabled"], out var nurturingEnabled))
        opts.Enabled = nurturingEnabled;
    if (bool.TryParse(builder.Configuration["Nurturing:AutoReplyEnabled"], out var autoReplyEnabled))
        opts.AutoReplyEnabled = autoReplyEnabled;
    opts.ImapHost = builder.Configuration["Nurturing:ImapHost"];
    if (int.TryParse(builder.Configuration["Nurturing:ImapPort"], out var imapPort))
        opts.ImapPort = imapPort;
    opts.SmtpHost = builder.Configuration["Nurturing:SmtpHost"];
    if (int.TryParse(builder.Configuration["Nurturing:SmtpPort"], out var smtpPort))
        opts.SmtpPort = smtpPort;
    opts.LoginEmail = builder.Configuration["Nurturing:LoginEmail"];
    opts.EmailPassword = builder.Configuration["Nurturing:EmailPassword"];
    opts.SenderEmail = builder.Configuration["Nurturing:SenderEmail"];
    opts.SenderName = builder.Configuration["Nurturing:SenderName"] ?? "Nicolás Piccardo";
    opts.RecipientOverride = builder.Configuration["Nurturing:RecipientOverride"];
    opts.ReviewerEmails = builder.Configuration["Nurturing:ReviewerEmails"] ?? "rodrigo.vazquez@novit.com.ar,leav@novitsoftware.com";
    opts.NewsletterAIDeployment = builder.Configuration["Nurturing:NewsletterAIDeployment"];
    opts.NewsletterAIModel = builder.Configuration["Nurturing:NewsletterAIModel"];
    opts.NewsletterAIKey = builder.Configuration["Nurturing:NewsletterAIKey"];
    opts.SerperWebSearchApiKey = builder.Configuration["Nurturing:SerperWebSearchApiKey"];
});

builder.Services.Configure<GoogleOptions>(opts =>
{
    opts.ClientId = builder.Configuration["Google:ClientId"];
    opts.ClientSecret = builder.Configuration["Google:ClientSecret"];
    opts.RefreshToken = builder.Configuration["Google:RefreshToken"];
});

builder.Services.AddControllers();
builder.Services.AddSignalR();
builder.Services.Configure<ForwardedHeadersOptions>(options =>
{
    options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto;
    options.KnownNetworks.Clear();
    options.KnownProxies.Clear();
});

// Database: use PostgreSQL if ConnectionStrings__DefaultConnection is set, otherwise in-memory
var connectionString = builder.Configuration.GetConnectionString("DefaultConnection");
if (!string.IsNullOrWhiteSpace(connectionString))
{
    builder.Services.AddDbContext<NovitDbContext>(options =>
        options.UseNpgsql(connectionString));
    builder.Services.AddSingleton<IConversationStore, PostgresConversationStore>();
}
else
{
    builder.Services.AddDbContext<NovitDbContext>(options =>
        options.UseInMemoryDatabase("novit-dev"));
    builder.Services.AddSingleton<IConversationStore, InMemoryConversationStore>();
}

builder.Services.AddHttpClient<IChatAIService, AzureAIChatService>();
builder.Services.AddHttpClient<ISpeechService, AzureSpeechService>();
builder.Services.AddHttpClient<IPipedriveService, PipedriveService>();
builder.Services.AddHttpClient<ICalComService, CalComService>();
builder.Services.AddTransient<ChatToolHandler>();
builder.Services.AddSingleton<INurturingMailService, NurturingMailService>();
builder.Services.AddScoped<CommunityReviewService>();
builder.Services.AddScoped<CommunityPublicationPublisher>();
builder.Services.AddHostedService<CommunityApprovalBackgroundService>();
builder.Services.AddHttpClient<IAgentClient, AgentClient>();
builder.Services.AddOpenApi();

var app = builder.Build();

// Auto-migrate database if PostgreSQL is configured
if (!string.IsNullOrWhiteSpace(connectionString))
{
    using var scope = app.Services.CreateScope();
    var db = scope.ServiceProvider.GetRequiredService<NovitDbContext>();
    db.Database.Migrate();
}

if (app.Environment.IsDevelopment())
{
    app.MapOpenApi();
}

app.UseForwardedHeaders();
app.UseDefaultFiles();
app.UseStaticFiles();
app.UseHttpsRedirection();
app.UseAuthorization();

app.MapControllers();
app.MapHub<ChatHub>("/hubs/chat");

app.Run();

public partial class Program;
