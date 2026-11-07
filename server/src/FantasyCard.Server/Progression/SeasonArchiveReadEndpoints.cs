using FantasyCard.Contracts.Seasons;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.ProtobufHttp;

namespace FantasyCard.Server.Progression;

public static class SeasonArchiveReadEndpoints
{
    public static IEndpointRouteBuilder MapSeasonArchiveReadEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group=endpoints.MapGroup("/api/v1/season-archives").AddEndpointFilter<ProtobufHttpFilter>().WithTags("SeasonArchive");
        group.MapGet("/",ListAsync).Produces<SeasonArchivesResponse>().ProducesProblem(400).ProducesProblem(401);
        group.MapGet("/{seasonId}/{section}",SectionAsync).Produces<SeasonArchiveSectionResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(404);
        return endpoints;
    }
    private static async Task<IResult> ListAsync(HttpContext context,IdentityService identity,ProgressionRepository repository,
        CancellationToken ct,int limit=20,int offset=0)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        try{return Results.Ok(await repository.GetSeasonArchivesAsync(player.UserId,limit,offset,ct));}
        catch(DomainValidationException error){return Problem(context,error.Message);}
    }
    private static async Task<IResult> SectionAsync(string seasonId,string section,HttpContext context,IdentityService identity,
        ProgressionRepository repository,CancellationToken ct,int limit=20,int offset=0)
    {
        var player=await context.AuthenticatePlayerAsync(identity,ct);if(player is null)return context.UnauthorizedProblem();
        try
        {
            var result=await repository.GetSeasonArchiveSectionAsync(player.UserId,seasonId,section,limit,offset,ct);
            return result is null?Results.NotFound():Results.Ok(result);
        }
        catch(DomainValidationException error){return Problem(context,error.Message);}
    }
    private static IResult Problem(HttpContext context,string detail)=>Results.Problem(statusCode:400,title:"Cannot read season archive",detail:detail,extensions:new Dictionary<string,object?> { ["traceId"]=context.TraceIdentifier });
}
