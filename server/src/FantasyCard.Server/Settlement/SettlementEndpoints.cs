using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Settlement;

public static class SettlementEndpoints
{
    public static IEndpointRouteBuilder MapSettlementEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var settlements = endpoints.MapGroup("/api/v1/settlements").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Settlement");
        settlements.MapGet("/{settlementId:guid}", GetAsync).Produces<SettlementResponse>().ProducesProblem(401).ProducesProblem(404);
        settlements.MapPost("/{settlementId:guid}/acknowledge", AcknowledgeAsync)
            .Produces<SettlementAcknowledgementResponse>()
            .ProducesProblem(401)
            .ProducesProblem(404)
            .ProducesProblem(409);
        endpoints.MapGet("/api/v1/matches/{matchId:guid}/settlement", GetForMatchAsync).AddEndpointFilter<ProtobufHttpFilter>()
            .WithTags("Settlement").Produces<SettlementResponse>().ProducesProblem(401).ProducesProblem(404);
        return endpoints;
    }

    private static async Task<IResult> AcknowledgeAsync(Guid settlementId, HttpContext context, IdentityService identity, SettlementRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try { return Results.Ok(await repository.AcknowledgeAsync(player.UserId, settlementId, requestId, ct)); }
        catch (IdempotencyConflictException) { return Results.Problem(statusCode: 409, title: "Idempotency conflict", detail: "The Idempotency-Key was already used for another settlement."); }
        catch (SettlementNotFoundException) { return Results.Problem(statusCode: 404, title: "Settlement not found"); }
        catch (SettlementNotReadyException) { return Results.Problem(statusCode: 409, title: "Settlement is not ready"); }
    }

    private static async Task<IResult> GetAsync(Guid settlementId, HttpContext context, IdentityService identity, SettlementRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        try { return Results.Ok(await repository.GetAsync(player.UserId, settlementId, ct)); }
        catch (InvalidOperationException ex) { return Results.Problem(statusCode: 404, title: "Settlement not found", detail: ex.Message); }
    }

    private static async Task<IResult> GetForMatchAsync(Guid matchId, HttpContext context, IdentityService identity, SettlementRepository repository, CancellationToken ct)
    {
        var player = await context.AuthenticatePlayerAsync(identity, ct); if (player is null) return context.UnauthorizedProblem();
        try { return Results.Ok(await repository.GetForMatchAsync(player.UserId, matchId, ct)); }
        catch (InvalidOperationException ex) { return Results.Problem(statusCode: 404, title: "Settlement not found", detail: ex.Message); }
    }
}
