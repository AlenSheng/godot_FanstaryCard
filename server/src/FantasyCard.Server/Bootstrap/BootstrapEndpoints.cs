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
        return player is null
            ? context.UnauthorizedProblem()
            : Results.Ok(await repository.GetAsync(player, cancellationToken));
    }
}
