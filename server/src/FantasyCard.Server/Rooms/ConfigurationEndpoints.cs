using FantasyCard.Contracts.Configuration;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;

namespace FantasyCard.Server.Rooms;

public static class ConfigurationEndpoints
{
    public static IEndpointRouteBuilder MapConfigurationEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGroup("/api/v1/config").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Configuration")
            .MapGet("/{configVersion}", GetAsync)
            .RequireRateLimiting(RequestLimitOptions.ReadPolicy)
            .Produces<PublishedConfigurationResponse>()
            .ProducesProblem(401).ProducesProblem(404);
        return endpoints;
    }

    private static async Task<IResult> GetAsync(string configVersion, HttpContext context, IdentityService identity,
        PublishedConfigCatalogs configurations, CancellationToken ct)
    {
        if (await context.AuthenticatePlayerAsync(identity,ct) is null) return context.UnauthorizedProblem();
        try
        {
            var catalog = configurations.Resolve(configVersion);
            return Results.Ok(new PublishedConfigurationResponse(catalog.Version,catalog.ContentHash,catalog.ExportPublishedBytes()));
        }
        catch (IOException)
        {
            return Results.Problem(statusCode:404,title:"Published configuration unavailable");
        }
    }
}
