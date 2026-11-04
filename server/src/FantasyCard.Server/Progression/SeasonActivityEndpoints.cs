using FantasyCard.Contracts.Progression;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;

namespace FantasyCard.Server.Progression;

public static class SeasonActivityEndpoints
{
    public static IEndpointRouteBuilder MapSeasonActivityEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group=endpoints.MapGroup("/api/v1/season-activities").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Season activities");
        group.MapGet("/",Get).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<SeasonActivitiesResponse>().ProducesProblem(401);
        group.MapPost("/{eventId}/exchanges",Exchange).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<ActivityExchangeResponse>().ProducesProblem(401).ProducesProblem(409);
        group.MapPost("/rewards/{rewardId:guid}/claim",Claim).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<ActivityClaimResponse>().ProducesProblem(401).ProducesProblem(409);
        return endpoints;
    }
    private static async Task<IResult> Get(HttpContext context,IdentityService identity,SeasonActivityRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var page=GamePage.Read(context);
        try{return Results.Ok(await repository.GetAsync(player.UserId,ct,context.Request.Query["seasonId"].FirstOrDefault(),Math.Min(page.Limit,100),page.Offset));}
        catch(FantasyCard.Domain.Players.DomainValidationException e){return Rejected(context,e.Message);}
    }
    private static async Task<IResult> Exchange(string eventId,GameBody<ActivityExchangeRequest> request,HttpContext context,IdentityService identity,SeasonActivityRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try{return Results.Ok(await repository.ExchangeAsync(player.UserId,eventId,key,request,ct));}
        catch(IdempotencyConflictException){return Rejected(context,"This Idempotency-Key belongs to a different activity action.");}
        catch(FantasyCard.Domain.Players.DomainValidationException e){return Rejected(context,e.Message);}
    }
    private static async Task<IResult> Claim(Guid rewardId,HttpContext context,IdentityService identity,SeasonActivityRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try{return Results.Ok(await repository.ClaimAsync(player.UserId,rewardId,key,ct));}
        catch(IdempotencyConflictException){return Rejected(context,"This Idempotency-Key belongs to a different activity action.");}
        catch(FantasyCard.Domain.Players.DomainValidationException e){return Rejected(context,e.Message);}
    }
    private static IResult Rejected(HttpContext context,string detail)=>Results.Problem(statusCode:409,title:"Activity action rejected",detail:detail,
        extensions:new Dictionary<string,object?>{["traceId"]=context.TraceIdentifier});
}
