using System.Threading.RateLimiting;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Options;
using Npgsql;
using System.Net;
using System.Text.RegularExpressions;

namespace FantasyCard.Server.Common;

public sealed class RequestLimitOptions
{
    public const string SectionName = "RequestLimits";
    public const string AuthPolicy = "auth";
    public const string AdminPolicy = "admin";
    public const string ReadPolicy = "market-read";
    public const string WritePolicy = "economy-write";

    public int WindowSeconds { get; init; } = 60;
    public int AuthPermitLimit { get; init; } = 10;
    public int AdminPermitLimit { get; init; } = 60;
    public int MarketReadPermitLimit { get; init; } = 120;
    public int EconomyWritePermitLimit { get; init; } = 30;
    public int RealtimeCommandsPerSecond { get; init; } = 30;
    // Explicitly opt in only for a disposable, loopback-bound load-test server.
    public bool OwnedTestBypass { get; init; }
    public string OwnedTestSession { get; init; } = "";
    public long RestMaximumBodyBytes { get; init; } = 65_536;
    public int JsonMaximumDepth { get; init; } = 16;
}

public static class RequestLimitExtensions
{
    public static void ValidateOwnedTestBypass(IConfiguration configuration, IHostEnvironment environment)
    {
        var limits = configuration.GetSection(RequestLimitOptions.SectionName).Get<RequestLimitOptions>();
        if (limits?.OwnedTestBypass != true) return;
        var addresses = (configuration["urls"] ?? "").Split(';', StringSplitOptions.RemoveEmptyEntries);
        var database = new NpgsqlConnectionStringBuilder(configuration.GetConnectionString("Postgres") ?? "");
        var loopbackDatabase = database.Host == "localhost" ||
            (IPAddress.TryParse(database.Host, out var address) && IPAddress.IsLoopback(address));
        if (!environment.IsDevelopment() || addresses.Length == 0 ||
            addresses.Any(value => !Uri.TryCreate(value, UriKind.Absolute, out var uri) || !uri.IsLoopback) ||
            !loopbackDatabase || !Regex.IsMatch(database.Database ?? "", @"\Apr13_tencent_live_[0-9a-f]{16}\z") ||
            !Regex.IsMatch(limits.OwnedTestSession, @"\Apr13-tencent-[0-9]{8}\z"))
            throw new InvalidOperationException("Unlimited test admission requires Development, loopback bindings and an owned disposable Tencent test database/session.");
    }

    public static IServiceCollection AddFantasyCardRequestLimits(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        services.AddOptions<RequestLimitOptions>()
            .Bind(configuration.GetSection(RequestLimitOptions.SectionName))
            .Validate(options => options.WindowSeconds is >= 1 and <= 3600,
                "Request limit window must be 1-3600 seconds.")
            .Validate(options =>
                    options.AuthPermitLimit is >= 1 and <= 10_000 &&
                    options.AdminPermitLimit is >= 1 and <= 10_000 &&
                    options.MarketReadPermitLimit is >= 1 and <= 10_000 &&
                    options.EconomyWritePermitLimit is >= 1 and <= 10_000 &&
                    options.RealtimeCommandsPerSecond is >= 1 and <= 1_000 &&
                    options.RestMaximumBodyBytes is >= 1_024 and <= 1_048_576 &&
                    options.JsonMaximumDepth is >= 4 and <= 64,
                "Request permit limits are outside the supported range.")
            .ValidateOnStart();

        var limits = configuration.GetSection(RequestLimitOptions.SectionName)
            .Get<RequestLimitOptions>() ?? new RequestLimitOptions();
        services.AddRateLimiter(options =>
        {
            options.RejectionStatusCode = StatusCodes.Status429TooManyRequests;
            options.OnRejected = async (context, cancellationToken) =>
            {
                var retryAfter = context.Lease.TryGetMetadata(MetadataName.RetryAfter, out var retry)
                    ? Math.Max(1, (int)Math.Ceiling(retry.TotalSeconds))
                    : limits.WindowSeconds;
                context.HttpContext.Response.Headers.RetryAfter =
                    retryAfter.ToString(System.Globalization.CultureInfo.InvariantCulture);
                context.HttpContext.Response.ContentType = "application/problem+json";
                await context.HttpContext.Response.WriteAsJsonAsync(new
                {
                    type = "about:blank",
                    title = "Too many requests",
                    status = StatusCodes.Status429TooManyRequests,
                    traceId = context.HttpContext.TraceIdentifier
                }, cancellationToken);
            };
            options.AddPolicy(RequestLimitOptions.AuthPolicy, context =>
                Partition(context, limits.AuthPermitLimit, limits));
            options.AddPolicy(RequestLimitOptions.AdminPolicy, context =>
                Partition(context, limits.AdminPermitLimit, limits));
            options.AddPolicy(RequestLimitOptions.ReadPolicy, context =>
                Partition(context, limits.MarketReadPermitLimit, limits));
            options.AddPolicy(RequestLimitOptions.WritePolicy, context =>
                Partition(context, limits.EconomyWritePermitLimit, limits));
        });
        return services;
    }

    private static RateLimitPartition<string> Partition(
        HttpContext context,
        int permitLimit,
        RequestLimitOptions limits) =>
        limits.OwnedTestBypass
        ? RateLimitPartition.GetNoLimiter("owned-test")
        : RateLimitPartition.GetFixedWindowLimiter(
            context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = permitLimit,
                Window = TimeSpan.FromSeconds(limits.WindowSeconds),
                QueueLimit = 0,
                AutoReplenishment = true
            });
}

public sealed class RealtimeCommandRateLimiter(int permitLimit, bool ownedTestBypass = false)
{
    private readonly int _permitLimit = permitLimit > 0
        ? permitLimit
        : throw new ArgumentOutOfRangeException(nameof(permitLimit));
    private readonly Queue<DateTimeOffset> _accepted = [];

    public bool TryAcquire(DateTimeOffset now)
    {
        if (ownedTestBypass) return true;
        while (_accepted.TryPeek(out var acceptedAt) && now - acceptedAt >= TimeSpan.FromSeconds(1))
            _accepted.Dequeue();
        if (_accepted.Count >= _permitLimit) return false;
        _accepted.Enqueue(now);
        return true;
    }
}
