using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Matchmaking;

public static class PreparationEndpoints
{
    public static IServiceCollection AddPreparationModule(this IServiceCollection services)
    {
        services.AddSingleton<PreparationRepository>();
        return services;
    }

    public static IEndpointRouteBuilder MapPreparationEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/preparations").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Preparation");
        group.MapGet("/", GetActiveAsync)
            .Produces<PreparationResponse>()
            .ProducesProblem(401)
            .ProducesProblem(404);
        group.MapPost("/", CreateAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<PreparationResponse>(201)
            .Produces<PreparationResponse>(200)
            .ProducesProblem(400)
            .ProducesProblem(401)
            .ProducesProblem(409);
        group.MapDelete("/{preparationId:guid}", CancelAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces(204)
            .ProducesProblem(401)
            .ProducesProblem(404)
            .ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> GetActiveAsync(
        HttpContext context,
        IdentityService identityService,
        PreparationRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null)
        {
            return context.UnauthorizedProblem();
        }

        var preparation = await repository.GetActiveAsync(player.UserId, cancellationToken);
        return preparation is null
            ? Problem(context, 404, "Preparation not found", "The player has no active preparation.")
            : Results.Ok(preparation);
    }

    private static async Task<IResult> CreateAsync(
        GameBody<CreatePreparationRequest> request,
        HttpContext context,
        IdentityService identityService,
        PreparationRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null)
        {
            return context.UnauthorizedProblem();
        }

        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);

        try
        {
            var result = await repository.CreateAsync(player.UserId, requestId, request, cancellationToken);
            return result.Status switch
            {
                CreatePreparationStatus.Created => Results.Created(
                    $"/api/v1/preparations/{result.Preparation!.PreparationId:D}",
                    result.Preparation),
                CreatePreparationStatus.Replayed => Results.Ok(result.Preparation),
                CreatePreparationStatus.DeckVersionConflict => Problem(
                    context,
                    409,
                    "Deck changed",
                    result.Detail!),
                CreatePreparationStatus.RequestConflict => Problem(
                    context,
                    409,
                    "Idempotency conflict",
                    result.Detail!),
                CreatePreparationStatus.ActivePreparationExists => Problem(
                    context,
                    409,
                    "Active preparation exists",
                    result.Detail!),
                _ => Problem(context, 409, "Asset unavailable", result.Detail!)
            };
        }
        catch (DomainValidationException exception)
        {
            return Problem(context, 400, "Invalid preparation", exception.Message);
        }
    }

    private static async Task<IResult> CancelAsync(
        Guid preparationId,
        HttpContext context,
        IdentityService identityService,
        PreparationRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null)
        {
            return context.UnauthorizedProblem();
        }

        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var result = await repository.CancelAsync(player.UserId, preparationId, requestId, cancellationToken);
            return result switch
            {
                CancelPreparationStatus.Cancelled => Results.NoContent(),
                CancelPreparationStatus.NotFound => Problem(
                    context,
                    404,
                    "Preparation not found",
                    "The preparation does not exist for this player."),
                _ => Problem(
                    context,
                    409,
                    "Preparation cannot be cancelled",
                    "Only an Active preparation can be cancelled through this endpoint.")
            };
        }
        catch (IdempotencyConflictException)
        {
            return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used for another preparation.");
        }
    }

    private static IResult Problem(HttpContext context, int status, string title, string detail) =>
        Results.Problem(
            statusCode: status,
            title: title,
            detail: detail,
            extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
