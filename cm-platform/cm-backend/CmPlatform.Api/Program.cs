using System.Text;
using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Tokens;
using CmPlatform.Api.Data;
using CmPlatform.Api.Hubs;
using CmPlatform.Api.Services;

var builder = WebApplication.CreateBuilder(args);

builder.Services.AddControllers();
builder.Services.AddSignalR();
builder.Services.AddOpenApi();

var jwtSecret = builder.Configuration["JWT:Secret"] ?? "default-dev-secret-change-in-production";
var jwtIssuer = builder.Configuration["JWT:Issuer"] ?? "cm-platform";
var jwtAudience = builder.Configuration["JWT:Audience"] ?? "cm-frontend";

builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ValidateIssuerSigningKey = true,
            ValidIssuer = jwtIssuer,
            ValidAudience = jwtAudience,
            IssuerSigningKey = new SymmetricSecurityKey(Encoding.UTF8.GetBytes(jwtSecret))
        };
    });
builder.Services.AddAuthorization();

var connectionString = builder.Configuration.GetConnectionString("DefaultConnection");
if (!string.IsNullOrWhiteSpace(connectionString))
{
    builder.Services.AddDbContext<NovitDbContext>(options =>
        options.UseNpgsql(connectionString));
}
else
{
    builder.Services.AddDbContext<NovitDbContext>(options =>
        options.UseInMemoryDatabase("cm-dev"));
}

var agentBaseUrl = builder.Configuration["AgentBaseUrl"];
if (!string.IsNullOrWhiteSpace(agentBaseUrl) && !builder.Configuration.GetValue<bool>("UseMockAgent"))
{
    builder.Services.AddHttpClient<IAgentClient, AgentClient>();
}
else
{
    builder.Services.AddSingleton<IAgentClient, MockAgentClient>();
}
builder.Services.AddScoped<CommunityReviewService>();
builder.Services.AddScoped<CommunityPublicationPublisher>();
builder.Services.AddHostedService<CommunityApprovalBackgroundService>();
builder.Services.AddSingleton<INurturingMailService, NullMailService>();
builder.Services.Configure<NurturingOptions>(builder.Configuration.GetSection("Nurturing"));

var app = builder.Build();

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

app.UseAuthentication();
app.UseAuthorization();
app.MapControllers();
app.MapHub<NotificationHub>("/hubs/notifications");

app.Run();

public partial class Program;
