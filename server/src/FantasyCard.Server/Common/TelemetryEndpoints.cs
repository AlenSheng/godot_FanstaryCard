namespace FantasyCard.Server.Common;

public sealed record ClientTelemetryRequest(
    string? Kind,
    string? AppVersion,
    string? Platform,
    string? Code);

public static partial class TelemetryEndpoints
{
    private static readonly HashSet<string> AllowedKinds = ["startup", "anr", "crash", "network"];

    public static IEndpointRouteBuilder MapTelemetryEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/v1/telemetry/events", ReceiveAsync)
            .RequireRateLimiting(RequestLimitOptions.AuthPolicy)
            .Produces(StatusCodes.Status202Accepted)
            .ProducesProblem(StatusCodes.Status400BadRequest);
        return endpoints;
    }

    private static IResult ReceiveAsync(ClientTelemetryRequest request, ILogger<Program> logger)
    {
        var kind = request.Kind?.Trim().ToLowerInvariant();
        var appVersion = Normalize(request.AppVersion, 32);
        var platform = Normalize(request.Platform, 32);
        var code = Normalize(request.Code, 80);
        if (kind is null || !AllowedKinds.Contains(kind) || appVersion is null || platform is null)
            return Results.Problem(statusCode: StatusCodes.Status400BadRequest, title: "Invalid telemetry event");

        Received(logger, kind, appVersion, platform, code ?? "");
        return Results.Accepted();
    }

    private static string? Normalize(string? value, int maximumLength)
    {
        var normalized = value?.Trim();
        return string.IsNullOrWhiteSpace(normalized) || normalized.Length > maximumLength || normalized.Any(char.IsControl)
            ? null
            : normalized;
    }

    [LoggerMessage(EventId = 4501, Level = LogLevel.Information, Message = "Client telemetry received: kind={Kind}, appVersion={AppVersion}, platform={Platform}, code={Code}")]
    private static partial void Received(ILogger logger, string kind, string appVersion, string platform, string code);
}
