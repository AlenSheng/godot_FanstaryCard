using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Bootstrap;

public static class BootstrapEndpoints
{
    public static IServiceCollection AddBootstrapModule(this IServiceCollection services)
    {
        services.AddSingleton<BootstrapRepository>();
        return services;
    }

    public static IEndpointRouteBuilder MapBootstrapEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/v1/bootstrap", GetAsync).AddEndpointFilter<ProtobufHttpFilter>()
            .WithTags("Bootstrap")
            .Produces<BootstrapResponse>()
            .ProducesProblem(400)
            .ProducesProblem(401);
        return endpoints;
    }

    private static async Task<IResult> GetAsync(
        HttpContext context,
        IdentityService identityService,
        BootstrapRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (context.Request.Query.TryGetValue("settlementMatchId", out var selector))
        {
            if (selector.Count != 1 || !Guid.TryParse(selector[0], out var matchId) || matchId == Guid.Empty)
                return Results.Problem(statusCode: 400, title: "Invalid settlement match selector",
                    detail: "settlementMatchId must be one nonempty match UUID.");
            return Results.Ok(await repository.GetSettlementAsync(player.UserId, matchId, cancellationToken));
        }
        return Results.Ok(await repository.GetAsync(player, cancellationToken));
    }
}
