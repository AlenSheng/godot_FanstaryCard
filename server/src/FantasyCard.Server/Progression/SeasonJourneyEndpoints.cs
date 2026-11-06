using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;

namespace FantasyCard.Server.Progression;

public static class SeasonJourneyEndpoints
{
    public static IEndpointRouteBuilder MapSeasonJourneyEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGroup("/api/v1/season-journey").AddEndpointFilter<ProtobufHttpFilter>().WithTags("SeasonJourney")
            .MapGet("",Get).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<SeasonJourneyResponse>().ProducesProblem(401).ProducesProblem(409);
        endpoints.MapJourneyRewardEndpoints();
        return endpoints;
    }
    private static async Task<IResult> Get(HttpContext context,IdentityService identity,SeasonJourneyRepository repository,
        CancellationToken ct,string? seasonId=null,int limit=50,int offset=0)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        try{return Results.Ok(await repository.GetAsync(player.UserId,ct,seasonId,limit,offset));}
        catch(DomainValidationException e){return Results.Problem(statusCode:409,title:"Journey unavailable",detail:e.Message,
            extensions:new Dictionary<string,object?>{["traceId"]=context.TraceIdentifier});}
    }
}
