using System.Text.Json.Serialization;
using FantasyCard.Server.Common;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using OpenTelemetry.Resources;
using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;

var builder = WebApplication.CreateBuilder(args);
// Console logging works in containers and on Windows without Event Log permissions.
builder.Logging.ClearProviders();
builder.Logging.AddConsole();
var requestLimitDefaults = builder.Configuration
    .GetSection(RequestLimitOptions.SectionName)
    .Get<RequestLimitOptions>() ?? new RequestLimitOptions();
builder.WebHost.ConfigureKestrel(options =>
{
    options.AddServerHeader = false;
    options.Limits.MaxRequestBodySize = requestLimitDefaults.RestMaximumBodyBytes;
});

builder.Services.ConfigureHttpJsonOptions(options =>
{
    options.SerializerOptions.Converters.Add(new JsonStringEnumConverter());
    options.SerializerOptions.MaxDepth = requestLimitDefaults.JsonMaximumDepth;
});
builder.Services.AddProblemDetails(options =>
{
    options.CustomizeProblemDetails = context =>
        context.ProblemDetails.Extensions["traceId"] = context.HttpContext.TraceIdentifier;
});
builder.Services.AddSingleton<ServerMetrics>();
builder.Services.AddFantasyCardRequestLimits(builder.Configuration);

builder.Services.AddFantasyCardPersistence(builder.Configuration);
builder.Services.AddIdentityModule(builder.Configuration);
builder.Services.AddPlayersModule();
builder.Services.AddProgressionModule();
builder.Services.AddBootstrapModule();
builder.Services.AddPreparationModule();
builder.Services.AddEconomyModule();
builder.Services.AddMatchmakingModule();
builder.Services.AddMailModule();
builder.Services.AddAdminModule();
builder.Services.AddRoomsModule();
builder.Services.AddSettlementModule();
builder.Services.AddRealtimeModule(builder.Configuration);
builder.Services.AddHealthChecks().AddCheck<PostgresHealthCheck>("postgres", tags: ["ready"]);

var telemetryEndpoint = Uri.TryCreate(
    builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"], UriKind.Absolute, out var configuredTelemetryEndpoint)
    ? configuredTelemetryEndpoint
    : null;
builder.Services
    .AddOpenTelemetry()
    .ConfigureResource(resource => resource.AddService("FantasyCard.Server"))
    .WithTracing(trace =>
    {
        trace.AddAspNetCoreInstrumentation(options =>
            {
                options.EnrichWithHttpRequest = (activity, request) =>
                {
                    if (!request.Path.StartsWithSegments("/ws/v1/session")) return;
                    activity.SetTag("url.query", null);
                    activity.SetTag("url.full", $"{request.Scheme}://{request.Host}{request.Path}");
                    activity.SetTag("http.url", $"{request.Scheme}://{request.Host}{request.Path}");
                };
            })
            .AddSource("FantasyCard.Server")
            .AddSource("Npgsql");

        if (telemetryEndpoint is not null)
        {
            trace.AddOtlpExporter(options => options.Endpoint = telemetryEndpoint);
        }
    })
    .WithMetrics(metrics =>
    {
        metrics.AddMeter(ServerMetrics.MeterName)
            .AddMeter("Npgsql")
            .AddAspNetCoreInstrumentation();
        if (telemetryEndpoint is not null)
            metrics.AddOtlpExporter(options => options.Endpoint = telemetryEndpoint);
    });

var app = builder.Build();
if (app.Environment.IsProduction())
{
    if (app.Configuration.GetValue<bool>("Identity:EnableLocalAuth"))
        throw new InvalidOperationException("Local authentication must be disabled in Production.");
    if ((app.Configuration["Admin:ApiKey"]?.Length ?? 0) < 32)
        throw new InvalidOperationException("Admin:ApiKey must contain at least 32 characters in Production.");
}

app.Use(async (context, next) =>
{
    context.Response.Headers.CacheControl = "no-store";
    context.Response.Headers["X-Content-Type-Options"] = "nosniff";
    context.Response.Headers["X-Frame-Options"] = "DENY";
    context.Response.Headers["Referrer-Policy"] = "no-referrer";
    context.Response.Headers["Permissions-Policy"] =
        "camera=(), microphone=(), geolocation=(), payment=(), usb=()";
    await next(context);
});
app.UseExceptionHandler();
app.UseMiddleware<RequestTraceMiddleware>();
app.UseRateLimiter();
app.UseWebSockets(new WebSocketOptions
{
    KeepAliveInterval = TimeSpan.FromSeconds(30)
});

app.MapGet("/", () => Results.NotFound());
app.MapHealthChecks("/health/live", new() { Predicate = _ => false });
app.MapHealthChecks("/health/ready", new() { Predicate = check => check.Tags.Contains("ready") });
app.MapIdentityEndpoints();
app.MapPlayerEndpoints();
app.MapProgressionEndpoints();
app.MapBootstrapEndpoints();
app.MapPreparationEndpoints();
app.MapEconomyEndpoints();
app.MapMatchmakingEndpoints();
app.MapSettlementEndpoints();
app.MapMailEndpoints();
app.MapAdminEndpoints();
app.MapRealtimeEndpoints();

app.Run();

public partial class Program;
