using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Matchmaking;

public static class MatchmakingEndpoints
{
    public static IServiceCollection AddMatchmakingModule(this IServiceCollection services)
    {
        services.AddSingleton<MatchmakingRepository>();
        services.AddSingleton<RoomReadyCoordinator>();
        services.AddSingleton<IRoomReadyService>(provider => provider.GetRequiredService<RoomReadyCoordinator>());
        services.AddHostedService(provider => provider.GetRequiredService<RoomReadyCoordinator>());
        services.AddHostedService<MatchmakerWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapMatchmakingEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/matches").WithTags("Matchmaking");
        group.MapPost("/enqueue", EnqueueAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<MatchTicketResponse>(202).ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        group.MapGet("/tickets/{ticketId:guid}", GetTicketAsync).Produces<MatchTicketResponse>().ProducesProblem(401).ProducesProblem(404);
        group.MapDelete("/tickets/{ticketId:guid}", CancelAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces(204).ProducesProblem(401).ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> GetTicketAsync(Guid ticketId, HttpContext context, IdentityService identity, MatchmakingRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        try { return Results.Ok(await repository.GetTicketAsync(player.UserId, ticketId, ct)); }
        catch (InvalidOperationException ex) { return Problem(context, 404, "Match ticket not found", ex.Message); }
    }

    private static async Task<IResult> EnqueueAsync(EnqueueMatchRequest request, HttpContext context, IdentityService identity, MatchmakingRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { return Results.Accepted("/api/v1/matches", await repository.EnqueueAsync(player.UserId, requestId, request, ct)); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used for another preparation."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Matchmaking rejected", ex.Message); }
    }

    private static async Task<IResult> CancelAsync(Guid ticketId, HttpContext context, IdentityService identity, MatchmakingRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { await repository.CancelAsync(player.UserId, ticketId, requestId, ct); return Results.NoContent(); }
        catch (IdempotencyConflictException) { return Problem(context, 409, "Idempotency conflict", "The Idempotency-Key was already used for another ticket."); }
        catch (InvalidOperationException ex) { return Problem(context, 409, "Cancellation rejected", ex.Message); }
    }

    private static IResult Problem(HttpContext context, int status, string title, string detail) => Results.Problem(statusCode: status, title: title, detail: detail, extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
