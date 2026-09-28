using FantasyCard.Server.ProtobufHttp;
using System.Text.Json;
using FantasyCard.Contracts.Identity;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using FantasyCard.Server.Common;
using FantasyCard.Server.Admin;

namespace FantasyCard.Server.Identity;

public static class IdentityEndpoints
{
    public static IServiceCollection AddIdentityModule(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        services.AddOptions<IdentityOptions>()
            .Bind(configuration.GetSection(IdentityOptions.SectionName))
            .Validate(options => options.SessionLifetimeDays is >= 1 and <= 365, "Session lifetime must be 1-365 days.")
            .ValidateOnStart();
        services.AddOptions<SteamAuthOptions>()
            .Bind(configuration.GetSection(SteamAuthOptions.SectionName))
            .Validate(options => !options.Enabled ||
                options.AppId > 0 &&
                !string.IsNullOrWhiteSpace(options.PublisherKey) &&
                !string.IsNullOrWhiteSpace(options.Identity),
                "Enabled Steam auth requires AppId, PublisherKey, and Identity.")
            .Validate(options => options.PublisherKey.Length <= 256 && options.Identity.Length <= 128,
                "Steam auth credentials exceed supported lengths.")
            .ValidateOnStart();
        services.AddSingleton<IdentityRepository>();
        services.AddSingleton<IdentityService>();
        services.AddSingleton<SteamTicketVerifier>();
        services.AddSingleton<PlayerProvisioningService>();
        services.AddHostedService<IdentityMaintenanceWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapIdentityEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/auth").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Identity");

        group.MapPost("/local", SignInLocalAsync)
            .RequireRateLimiting(RequestLimitOptions.AuthPolicy)
            .Produces<LocalSignInResponse>()
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status409Conflict);
        group.MapPost("/steam", SignInSteamAsync)
            .RequireRateLimiting(RequestLimitOptions.AuthPolicy)
            .Produces<LocalSignInResponse>()
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status401Unauthorized)
            .ProducesProblem(StatusCodes.Status409Conflict)
            .ProducesProblem(StatusCodes.Status503ServiceUnavailable);

        return endpoints;
    }

    private static async Task<IResult> SignInLocalAsync(
        GameBody<LocalSignInRequest> request,
        IdentityService identityService,
        IOptions<IdentityOptions> options,
        IHostEnvironment environment,
        IConfiguration configuration,
        ClientSettingsRepository settingsRepository,
        HttpContext context,
        CancellationToken cancellationToken)
    {
        var managed = configuration.GetValue<bool>("Identity:AllowManagedLocalAuth") &&
            (await settingsRepository.GetAsync(cancellationToken)).LocalLoginEnabled;
        if (!LocalAuthPolicy.IsEnabled(environment.EnvironmentName, options.Value.EnableLocalAuth, managed))
        {
            return Results.NotFound();
        }

        try
        {
            var result = await identityService.SignInLocalAsync(
                request.Value.DeviceId,
                request.Value.DisplayName,
                cancellationToken);
            return Results.Ok(new LocalSignInResponse(
                result.AccessToken,
                result.ExpiresAt,
                result.Player.ToResponse()));
        }
        catch (DomainValidationException exception)
        {
            return Results.Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "Invalid sign-in request",
                detail: exception.Message,
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
        catch (PlayerNameConflictException exception)
        {
            return NameConflict(context, exception);
        }
        catch (PlayerBannedException)
        {
            return Results.Problem(statusCode: 403, title: "Account banned");
        }
    }

    private static async Task<IResult> SignInSteamAsync(
        GameBody<SteamSignInRequest> request,
        SteamTicketVerifier verifier,
        IdentityService identityService,
        IOptions<SteamAuthOptions> options,
        ServerMetrics metrics,
        HttpContext context,
        CancellationToken cancellationToken)
    {
        if (!options.Value.Enabled) return Results.NotFound();
        try
        {
            var steamId = await verifier.VerifyAsync(request.Value.Ticket, cancellationToken);
            if (steamId is null)
            {
                metrics.IdentitySignInFailed("steam", "invalid_ticket");
                return context.UnauthorizedProblem();
            }
            var result = await identityService.SignInExternalAsync(
                "steam", steamId, request.Value.DisplayName, cancellationToken);
            return Results.Ok(new LocalSignInResponse(
                result.AccessToken, result.ExpiresAt, result.Player.ToResponse()));
        }
        catch (DomainValidationException exception)
        {
            return Results.Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "Invalid sign-in request",
                detail: exception.Message,
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
        catch (PlayerNameConflictException exception)
        {
            return NameConflict(context, exception);
        }
        catch (PlayerBannedException)
        {
            return Results.Problem(statusCode: 403, title: "Account banned");
        }
        catch (Exception exception) when (exception is HttpRequestException or TaskCanceledException or JsonException)
        {
            metrics.IdentitySignInFailed("steam", "provider_unavailable");
            return Results.Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                title: "Steam authentication unavailable",
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
    }

    private static IResult NameConflict(HttpContext context, PlayerNameConflictException exception) => Results.Problem(
        statusCode: StatusCodes.Status409Conflict,
        title: "Player name conflict",
        detail: exception.Message,
        extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}

public static class LocalAuthPolicy
{
    public static bool IsEnabled(string environmentName, bool configured, bool managed = false) =>
        managed || configured && string.Equals(environmentName, Environments.Development, StringComparison.OrdinalIgnoreCase);
}
