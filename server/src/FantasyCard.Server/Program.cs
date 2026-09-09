using System.Text.Json.Serialization;
using FantasyCard.Server.Common;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
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
var requestLimitDefaults = builder.Configuration
    .GetSection(RequestLimitOptions.SectionName)
    .Get<RequestLimitOptions>() ?? new RequestLimitOptions();
builder.WebHost.ConfigureKestrel(options =>
    options.Limits.MaxRequestBodySize = requestLimitDefaults.RestMaximumBodyBytes);

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
var capabilities = new List<string>
{
    "players.profile",
    "bootstrap",
    "cards.read",
    "decks.read_write",
    "inventory.read",
    "loadouts.read",
    "loadouts.write",
    "equipment.enhance",
    "shop.gold_only",
    "shop.daily_cards",
    "market.gold_only",
    "economy.reconciliation_monitor",
    "security.layered_rate_limits",
    "observability.otlp_metrics",
    "identity.expired_session_cleanup",
    "matchmaking.chaos_realm",
    "matchmaking.ready_15s_bot_fill",
    "preparations.create_read_cancel",
    "realtime.ping_resume",
    "rooms.actor",
    "rooms.snapshot_persistence",
    "rooms.recovery",
    "rooms.persistence_readiness",
    "rooms.player_projection",
    "bots.room_runtime",
    "battle.play_cards",
    "battle.pve_pvp_snapshots",
    "relic.read_take",
    "action.extract_readbar",
    "action.spring_readbar",
    "action.potion_instant",
    "reward.choice",
    "choice.refresh",
    "choice.pick",
    "settlement.idempotent_holds"
};
if (LocalAuthPolicy.IsEnabled(
    app.Environment.EnvironmentName,
    app.Configuration.GetValue<bool>("Identity:EnableLocalAuth")))
{
    capabilities.Insert(0, "identity.local");
}
if (app.Configuration.GetValue<bool>("Identity:Steam:Enabled"))
{
    capabilities.Insert(0, "identity.steam");
}

app.UseExceptionHandler();
app.UseMiddleware<RequestTraceMiddleware>();
app.UseRateLimiter();
app.UseWebSockets(new WebSocketOptions
{
    KeepAliveInterval = TimeSpan.FromSeconds(30)
});

app.MapGet("/", () => Results.Ok(new
{
    service = "FantasyCard.Server",
    version = typeof(Program).Assembly
        .GetCustomAttributes(typeof(System.Reflection.AssemblyInformationalVersionAttribute), false)
        .OfType<System.Reflection.AssemblyInformationalVersionAttribute>()
        .SingleOrDefault()?.InformationalVersion ?? "unknown",
    configVersion = BootstrapRepository.CurrentConfigVersion,
    milestone = "S0/S1 complete; S2-S9 vertical slices available; room recovery, player snapshots, bot runtime, rate limits, and economy reconciliation",
    capabilities
}));
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
app.MapRealtimeEndpoints();

app.Run();

public partial class Program;
