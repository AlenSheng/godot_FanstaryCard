using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Players;

public static class PlayerEndpoints
{
    public static IServiceCollection AddPlayersModule(this IServiceCollection services)
    {
        services.AddSingleton<PlayerRepository>();
        return services;
    }

    public static IEndpointRouteBuilder MapPlayerEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/players").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Players");
        group.MapGet("/me", GetMeAsync).Produces<PlayerProfileResponse>().ProducesProblem(401);
        group.MapPut("/me", UpdateMeAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<PlayerProfileResponse>()
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> GetMeAsync(
        HttpContext context,
        IdentityService identityService,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        return player is null ? context.UnauthorizedProblem() : Results.Ok(player.ToResponse());
    }

    private static async Task<IResult> UpdateMeAsync(
        GameBody<UpdatePlayerProfileRequest> request,
        HttpContext context,
        IdentityService identityService,
        PlayerRepository playerRepository,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null)
        {
            return context.UnauthorizedProblem();
        }

        if (request.Value.DisplayName is null && request.Value.SelectedClass is null)
        {
            return Results.Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "No profile changes supplied",
                detail: "Supply displayName, selectedClass, or both.",
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }

        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);

        try
        {
            var result = await playerRepository.UpdateAsync(
                player.UserId, request, requestId, timeProvider.GetUtcNow(), cancellationToken);
            return result.Status switch
            {
                UpdatePlayerResult.Updated => Results.Ok(result.Profile),
                UpdatePlayerResult.VersionConflict => Conflict(context),
                _ => Results.NotFound()
            };
        }
        catch (DomainValidationException exception)
        {
            return Results.Problem(
                statusCode: StatusCodes.Status400BadRequest,
                title: "Invalid player profile",
                detail: exception.Message,
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
        catch (IdempotencyConflictException)
        {
            return Results.Problem(
                statusCode: StatusCodes.Status409Conflict,
                title: "Idempotency conflict",
                detail: "The Idempotency-Key was already used with a different request.",
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
        catch (PlayerNameConflictException exception)
        {
            return Results.Problem(
                statusCode: StatusCodes.Status409Conflict,
                title: "Player name conflict",
                detail: exception.Message,
                extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
        }
    }

    private static IResult Conflict(HttpContext context) => Results.Problem(
        statusCode: StatusCodes.Status409Conflict,
        title: "Player profile changed",
        detail: "Reload the profile and retry with its latest version.",
        extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
