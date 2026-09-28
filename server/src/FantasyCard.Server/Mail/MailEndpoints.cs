using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Contracts.Mail;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Mail;

public static class MailEndpoints
{
    public static IServiceCollection AddMailModule(this IServiceCollection services)
    {
        services.AddSingleton<MailRepository>();
        return services;
    }

    public static IEndpointRouteBuilder MapMailEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var mail = endpoints.MapGroup("/api/v1/mail").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Mail");
        mail.MapGet("/", GetAsync).Produces<MailListResponse>().ProducesProblem(401);
        mail.MapPost("/{mailId:guid}/read", MarkReadAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces(204).ProducesProblem(401).ProducesProblem(404);
        mail.MapPost("/read-all", MarkAllReadAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces(204).ProducesProblem(401);
        mail.MapPost("/{mailId:guid}/claim", ClaimAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<MailClaimResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(404);
        mail.MapPost("/claim-all", ClaimAllAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<MailClaimAllResponse>().ProducesProblem(400).ProducesProblem(401);
        mail.MapDelete("/{mailId:guid}", DeleteAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<MailDeleteResponse>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(404);
        mail.MapDelete("/read", DeleteReadAsync)
            .RequireRateLimiting(RequestLimitOptions.WritePolicy)
            .Produces<MailDeleteResponse>().ProducesProblem(400).ProducesProblem(401);
        return endpoints;
    }

    private static async Task<IResult> GetAsync(HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        return player is null ? context.UnauthorizedProblem() : Results.Ok(await repository.GetAsync(player.UserId, cancellationToken, GamePage.Read(context).Limit, GamePage.Read(context).Offset));
    }

    private static async Task<IResult> MarkReadAsync(Guid mailId, HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (IdempotencyKeys.Read(context) is null) return IdempotencyKeys.InvalidProblem(context);
        return await repository.MarkReadAsync(player.UserId, mailId, cancellationToken) ? Results.NoContent() : Results.NotFound();
    }

    private static async Task<IResult> MarkAllReadAsync(HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (IdempotencyKeys.Read(context) is null) return IdempotencyKeys.InvalidProblem(context);
        await repository.MarkAllReadAsync(player.UserId, cancellationToken);
        return Results.NoContent();
    }

    private static async Task<IResult> ClaimAsync(Guid mailId, HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            var result = await repository.ClaimAsync(player.UserId, mailId, requestId, cancellationToken);
            return result is null ? Results.NotFound() : Results.Ok(result);
        }
        catch (InvalidOperationException exception)
        {
            return Results.Problem(statusCode: 400, title: "Invalid mail attachment", detail: exception.Message);
        }
        catch (IdempotencyConflictException)
        {
            return Results.Problem(
                statusCode: 409,
                title: "Idempotency conflict",
                detail: "The Idempotency-Key was already used with a different mail claim.");
        }
    }

    private static async Task<IResult> ClaimAllAsync(HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var requestId = IdempotencyKeys.Read(context);
        if (requestId is null) return IdempotencyKeys.InvalidProblem(context);
        try
        {
            return Results.Ok(await repository.ClaimAllAsync(player.UserId, requestId, cancellationToken));
        }
        catch (InvalidOperationException exception)
        {
            return Results.Problem(statusCode: 400, title: "Invalid mail attachment", detail: exception.Message);
        }
        catch (IdempotencyConflictException)
        {
            return Results.Problem(statusCode: 409, title: "Idempotency conflict", detail: "The Idempotency-Key was already used with a different mail claim.");
        }
    }

    private static async Task<IResult> DeleteAsync(Guid mailId, HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (IdempotencyKeys.Read(context) is null) return IdempotencyKeys.InvalidProblem(context);
        return await repository.DeleteAsync(player.UserId, mailId, cancellationToken)
            ? Results.Ok(new MailDeleteResponse(1))
            : Results.NotFound();
    }

    private static async Task<IResult> DeleteReadAsync(HttpContext context, IdentityService identity, MailRepository repository, CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identity, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        if (IdempotencyKeys.Read(context) is null) return IdempotencyKeys.InvalidProblem(context);
        var deleted = await repository.DeleteReadAsync(player.UserId, cancellationToken);
        return Results.Ok(new MailDeleteResponse(deleted));
    }
}
