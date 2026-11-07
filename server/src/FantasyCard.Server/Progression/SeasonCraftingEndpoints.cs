using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;

namespace FantasyCard.Server.Progression;

public static class SeasonCraftingEndpoints
{
    public static IEndpointRouteBuilder MapSeasonCraftingEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group=endpoints.MapGroup("/api/v1/season-crafting").AddEndpointFilter<ProtobufHttpFilter>().WithTags("SeasonCrafting");
        group.MapGet("/",OverviewAsync).Produces<SeasonCraftingResponse>().ProducesProblem(400).ProducesProblem(401);
        group.MapGet("/reforge-quote",ReforgeQuoteAsync).Produces<ReforgeQuoteResponse>().ProducesProblem(400).ProducesProblem(401);
        group.MapPost("/craft",CraftAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<CraftEquipmentResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        group.MapPost("/recipes/learn",LearnAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<LearnSeasonRecipeResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        group.MapPost("/reforge",ReforgeAsync).RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<ReforgeEquipmentResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(409);
        return endpoints;
    }

    private static async Task<IResult> OverviewAsync(HttpContext context,IdentityService identity,ProgressionRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        try{return Results.Ok(await repository.GetSeasonCraftingAsync(player.UserId,ct));}
        catch(DomainValidationException error){return Problem(context,400,"Cannot read crafting",error.Message);}
    }

    private static async Task<IResult> ReforgeQuoteAsync(string seasonId,Guid recipeId,Guid bodyEquipmentId,HttpContext context,
        IdentityService identity,ProgressionRepository repository,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        try{return Results.Ok(await repository.GetReforgeQuoteAsync(player.UserId,seasonId,recipeId,bodyEquipmentId,ct));}
        catch(DomainValidationException error){return Problem(context,400,"Cannot quote rebuild",error.Message);}
    }

    private static Task<IResult> CraftAsync(GameBody<CraftEquipmentRequest> body,HttpContext context,IdentityService identity,
        ProgressionRepository repository,CancellationToken ct) => MutateAsync(context,identity,
            (player,key)=>repository.CraftSeasonEquipmentAsync(player,key,body.Value,ct),ct);
    private static Task<IResult> LearnAsync(GameBody<LearnSeasonRecipeRequest> body,HttpContext context,IdentityService identity,
        ProgressionRepository repository,CancellationToken ct) => MutateAsync(context,identity,
            (player,key)=>repository.LearnSeasonRecipeAsync(player,key,body.Value,ct),ct);
    private static Task<IResult> ReforgeAsync(GameBody<ReforgeEquipmentRequest> body,HttpContext context,IdentityService identity,
        ProgressionRepository repository,CancellationToken ct) => MutateAsync(context,identity,
            (player,key)=>repository.ReforgeSeasonEquipmentAsync(player,key,body.Value,ct),ct);

    private static async Task<IResult> MutateAsync<T>(HttpContext context,IdentityService identity,Func<Guid,string,Task<T>> action,CancellationToken ct)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        var key=IdempotencyKeys.Read(context);if(key is null)return IdempotencyKeys.InvalidProblem(context);
        try{return Results.Ok(await action(player.UserId,key));}
        catch(IdempotencyConflictException){return Problem(context,409,"Idempotency conflict","The Idempotency-Key was already used with a different request.");}
        catch(DomainValidationException error){return Problem(context,400,"Cannot change crafting assets",error.Message);}
    }

    private static IResult Problem(HttpContext context,int status,string title,string detail) =>
        Results.Problem(statusCode:status,title:title,detail:detail,extensions:new Dictionary<string,object?> { ["traceId"]=context.TraceIdentifier });
}
