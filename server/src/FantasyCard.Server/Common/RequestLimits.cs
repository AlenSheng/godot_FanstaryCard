using System.Threading.RateLimiting;
using Microsoft.AspNetCore.RateLimiting;
using Microsoft.Extensions.Options;

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
    public long RestMaximumBodyBytes { get; init; } = 65_536;
    public int JsonMaximumDepth { get; init; } = 16;
}

public static class RequestLimitExtensions
{
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
                FixedWindow(context, limits.AuthPermitLimit, limits.WindowSeconds));
            options.AddPolicy(RequestLimitOptions.AdminPolicy, context =>
                FixedWindow(context, limits.AdminPermitLimit, limits.WindowSeconds));
            options.AddPolicy(RequestLimitOptions.ReadPolicy, context =>
                FixedWindow(context, limits.MarketReadPermitLimit, limits.WindowSeconds));
            options.AddPolicy(RequestLimitOptions.WritePolicy, context =>
                FixedWindow(context, limits.EconomyWritePermitLimit, limits.WindowSeconds));
        });
        return services;
    }

    private static RateLimitPartition<string> FixedWindow(
        HttpContext context,
        int permitLimit,
        int windowSeconds) =>
        RateLimitPartition.GetFixedWindowLimiter(
            context.Connection.RemoteIpAddress?.ToString() ?? "unknown",
            _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = permitLimit,
                Window = TimeSpan.FromSeconds(windowSeconds),
                QueueLimit = 0,
                AutoReplenishment = true
            });
}

public sealed class RealtimeCommandRateLimiter(int permitLimit)
{
    private readonly int _permitLimit = permitLimit > 0
        ? permitLimit
        : throw new ArgumentOutOfRangeException(nameof(permitLimit));
    private readonly Queue<DateTimeOffset> _accepted = [];

    public bool TryAcquire(DateTimeOffset now)
    {
        while (_accepted.TryPeek(out var acceptedAt) && now - acceptedAt >= TimeSpan.FromSeconds(1))
            _accepted.Dequeue();
        if (_accepted.Count >= _permitLimit) return false;
        _accepted.Enqueue(now);
        return true;
    }
}
