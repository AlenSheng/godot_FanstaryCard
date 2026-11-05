using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;

namespace FantasyCard.Server.Progression;

public static class SeasonJourneyRewardEndpoints
{
    public static IEndpointRouteBuilder MapJourneyRewardEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var journey=endpoints.MapGroup("/api/v1/season-journey/rewards").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Journey rewards");
        journey.MapGet("",Rewards).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<JourneyRewardsResponse>().ProducesProblem(401).ProducesProblem(409);
        journey.MapPost("/{rewardId:guid}/claim",Claim).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<JourneyClaimResponse>().ProducesProblem(401).ProducesProblem(409);
        var cosmetics=endpoints.MapGroup("/api/v1/cosmetics").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Cosmetics");
        cosmetics.MapGet("",Cosmetics).RequireRateLimiting(RequestLimitOptions.ReadPolicy).Produces<CosmeticsResponse>().ProducesProblem(401);
        cosmetics.MapPut("/selection",Select).RequireRateLimiting(RequestLimitOptions.WritePolicy).Produces<CosmeticSelectionResponse>().ProducesProblem(401).ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> Rewards(HttpContext context,IdentityService identity,SeasonJourneyRepository repository,CancellationToken ct,string? seasonId=null)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        if(seasonId is null)return Rejected(context,"Choose the original season before reading rewards.");
        try{return Results.Ok(await repository.GetRewardsAsync(player.UserId,seasonId,ct));}
        catch(DomainValidationException error){return Rejected(context,error.Message);}
    }

    private static async Task<IResult> Claim(Guid rewardId,GameBody<JourneyClaimRequest> request,HttpContext context,
        IdentityService identity,SeasonJourneyRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try{return Results.Ok(await repository.ClaimRewardAsync(player.UserId,rewardId,key,request,ct));}
        catch(IdempotencyConflictException){return Rejected(context,"This Idempotency-Key belongs to a different journey claim.");}
        catch(DomainValidationException error){return Rejected(context,error.Message);}
    }

    private static async Task<IResult> Cosmetics(HttpContext context,IdentityService identity,SeasonJourneyRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        return Results.Ok(await repository.GetCosmeticsAsync(player.UserId,ct));
    }

    private static async Task<IResult> Select(GameBody<CosmeticSelectionRequest> request,HttpContext context,IdentityService identity,
        SeasonJourneyRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try{return Results.Ok(await repository.SelectCosmeticAsync(player.UserId,key,request,ct));}
        catch(IdempotencyConflictException){return Rejected(context,"This Idempotency-Key belongs to a different cosmetic selection.");}
        catch(DomainValidationException error){return Rejected(context,error.Message);}
    }

    private static IResult Rejected(HttpContext context,string detail)=>Results.Problem(statusCode:409,title:"Journey reward action rejected",detail:detail,
        extensions:new Dictionary<string,object?>{["traceId"]=context.TraceIdentifier});
}
