using System.Text.Json;
using FantasyCard.Contracts.Identity;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;
using FantasyCard.Server.Common;
using FantasyCard.Server.Admin;
using FantasyCard.Server.Bootstrap;

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
            .Validate(options => options.AccountDeletionCoolingPeriodDays is >= 1 and <= 30,
                "Account deletion cooling period must be 1-30 days.")
            .Validate(options => options.RealtimeTicketLifetimeSeconds is >= 15 and <= 300,
                "Realtime ticket lifetime must be 15-300 seconds.")
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
        services.AddOptions<GoogleAuthOptions>()
            .Bind(configuration.GetSection(GoogleAuthOptions.SectionName))
            .Validate(options => !options.Enabled || options.GetAudiences().Count > 0,
                "Enabled Google auth requires at least one configured OAuth audience.")
            .Validate(options => options.GetAudiences().All(value => value.Length <= 256),
                "Google OAuth audience exceeds supported length.")
            .ValidateOnStart();
        services.AddSingleton<IdentityRepository>();
        services.AddSingleton<IdentityService>();
        services.AddSingleton<AccountDeletionRepository>();
        services.AddSingleton<SteamTicketVerifier>();
        services.AddHttpClient<GoogleIdTokenVerifier>(client => client.Timeout = TimeSpan.FromSeconds(10));
        services.AddSingleton<PlayerProvisioningService>();
        services.AddHostedService<IdentityMaintenanceWorker>();
        services.AddHostedService<AccountDeletionWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapIdentityEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/auth").WithTags("Identity");

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
        group.MapPost("/google", SignInGoogleAsync)
            .RequireRateLimiting(RequestLimitOptions.AuthPolicy)
            .Produces<LocalSignInResponse>()
            .ProducesProblem(StatusCodes.Status400BadRequest)
            .ProducesProblem(StatusCodes.Status401Unauthorized)
            .ProducesProblem(StatusCodes.Status409Conflict)
            .ProducesProblem(StatusCodes.Status503ServiceUnavailable);
        group.MapPost("/ws-ticket", IssueRealtimeTicketAsync)
            .RequireRateLimiting(RequestLimitOptions.AuthPolicy)
            .ProducesProblem(StatusCodes.Status401Unauthorized);

        return endpoints;
    }

    private static async Task<IResult> IssueRealtimeTicketAsync(
        HttpContext context,
        IdentityService identityService,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var ticket = await identityService.CreateRealtimeTicketAsync(player.UserId, cancellationToken);
        return Results.Ok(new { ticket.Ticket, ticket.ExpiresAt });
    }

    private static async Task<IResult> SignInLocalAsync(
        LocalSignInRequest request,
        IdentityService identityService,
        IOptions<IdentityOptions> options,
        IHostEnvironment environment,
        IConfiguration configuration,
        ClientSettingsRepository settingsRepository,
        BootstrapRepository bootstrapRepository,
        HttpContext context,
        CancellationToken cancellationToken)
    {
        var managed = configuration.GetValue<bool>("Identity:AllowManagedLocalAuth") &&
            (await settingsRepository.GetAsync(cancellationToken)).LocalLoginEnabled;
        if (!LocalAuthPolicy.IsEnabled(environment.EnvironmentName, options.Value.EnableLocalAuth, managed))
        {
            return Results.NotFound();
        }
        if (!ConfigVersionMatches(request.ConfigVersion))
            return ConfigVersionMismatch(context);

        try
        {
            var result = await identityService.SignInLocalAsync(
                request.DeviceId,
                request.DisplayName,
                cancellationToken);
            return Results.Ok(await FullSignInResponseAsync(result, request.IncludeBootstrap, bootstrapRepository,
                settingsRepository, environment, configuration, cancellationToken));
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
        SteamSignInRequest request,
        SteamTicketVerifier verifier,
        IdentityService identityService,
        IOptions<SteamAuthOptions> options,
        ServerMetrics metrics,
        BootstrapRepository bootstrapRepository,
        ClientSettingsRepository settingsRepository,
        IHostEnvironment environment,
        IConfiguration configuration,
        HttpContext context,
        CancellationToken cancellationToken)
    {
        if (!options.Value.Enabled) return Results.NotFound();
        if (!ConfigVersionMatches(request.ConfigVersion))
            return ConfigVersionMismatch(context);
        try
        {
            var steamId = await verifier.VerifyAsync(request.Ticket, cancellationToken);
            if (steamId is null)
            {
                metrics.IdentitySignInFailed("steam", "invalid_ticket");
                return context.UnauthorizedProblem();
            }
            var result = await identityService.SignInExternalAsync(
                "steam", steamId, request.DisplayName, cancellationToken);
            return Results.Ok(await FullSignInResponseAsync(result, request.IncludeBootstrap, bootstrapRepository,
                settingsRepository, environment, configuration, cancellationToken));
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

    private static async Task<IResult> SignInGoogleAsync(
        GoogleSignInRequest request,
        GoogleIdTokenVerifier verifier,
        IdentityService identityService,
        IOptions<GoogleAuthOptions> options,
        ServerMetrics metrics,
        BootstrapRepository bootstrapRepository,
        ClientSettingsRepository settingsRepository,
        IHostEnvironment environment,
        IConfiguration configuration,
        HttpContext context,
        CancellationToken cancellationToken)
    {
        if (!options.Value.Enabled) return Results.NotFound();
        if (!ConfigVersionMatches(request.ConfigVersion))
            return ConfigVersionMismatch(context);
        try
        {
            var identity = await verifier.VerifyAsync(request.IdToken, cancellationToken);
            if (identity is null)
            {
                metrics.IdentitySignInFailed("google", "invalid_id_token");
                return context.UnauthorizedProblem();
            }
            var result = await identityService.SignInExternalAsync(
                "google", identity.Subject, request.DisplayName, cancellationToken);
            return Results.Ok(await FullSignInResponseAsync(result, request.IncludeBootstrap, bootstrapRepository,
                settingsRepository, environment, configuration, cancellationToken));
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
            metrics.IdentitySignInFailed("google", "provider_unavailable");
            return Results.Problem(
                statusCode: StatusCodes.Status503ServiceUnavailable,
                title: "Google authentication unavailable",
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
    }

    private static bool ConfigVersionMatches(string? version) =>
        string.IsNullOrEmpty(version) || string.Equals(version, BootstrapRepository.CurrentConfigVersion, StringComparison.Ordinal);

    private static IResult ConfigVersionMismatch(HttpContext context) => Results.Problem(
        statusCode: StatusCodes.Status409Conflict,
        title: "Client configuration is outdated",
        detail: "Update the client before signing in.",
        extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });

    private static async Task<LocalSignInResponse> FullSignInResponseAsync(
        SignInResult result,
        bool includeBootstrap,
        BootstrapRepository bootstrapRepository,
        ClientSettingsRepository settingsRepository,
        IHostEnvironment environment,
        IConfiguration configuration,
        CancellationToken cancellationToken)
    {
        var response = new LocalSignInResponse(result.AccessToken, result.ExpiresAt, result.Player.ToResponse());
        if (!includeBootstrap) return response;
        var bootstrapTask = bootstrapRepository.GetAsync(result.Player, cancellationToken);
        var settingsTask = settingsRepository.GetAsync(cancellationToken);
        await Task.WhenAll(bootstrapTask, settingsTask);
        return response with
        {
            Bootstrap = await bootstrapTask,
            ClientInfo = ClientSettingsEndpoints.PublicInfo(await settingsTask, environment, configuration)
        };
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
        !string.Equals(environmentName, Environments.Production, StringComparison.OrdinalIgnoreCase) &&
        (managed || configured && string.Equals(environmentName, Environments.Development, StringComparison.OrdinalIgnoreCase));
}
