using FantasyCard.Server.ProtobufHttp;
using FantasyCard.Server.Common;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Identity;

public static class AccountDeletionEndpoints
{
    public sealed record EmptyAccountDeletionRequest;

    public static IEndpointRouteBuilder MapAccountDeletionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        var group = endpoints.MapGroup("/api/v1/account-deletion").AddEndpointFilter<ProtobufHttpFilter>().WithTags("Account deletion");
        group.MapPost("", RequestAsync).RequireRateLimiting(RequestLimitOptions.AuthPolicy);
        group.MapGet("", GetAsync);
        group.MapDelete("", CancelAsync).RequireRateLimiting(RequestLimitOptions.AuthPolicy);
        return endpoints;
    }

    private static async Task<IResult> RequestAsync(
        GameBody<EmptyAccountDeletionRequest> request,
        HttpContext context,
        IdentityService identityService,
        AccountDeletionRepository repository,
        IOptions<IdentityOptions> options,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var status = await repository.RequestAsync(
            player.UserId, timeProvider.GetUtcNow(), options.Value.AccountDeletionCoolingPeriodDays, cancellationToken);
        return Results.Ok(status);
    }

    private static async Task<IResult> GetAsync(
        HttpContext context,
        IdentityService identityService,
        AccountDeletionRepository repository,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        var status = await repository.GetAsync(player.UserId, cancellationToken);
        return status is null ? Results.NotFound() : Results.Ok(status);
    }

    private static async Task<IResult> CancelAsync(
        HttpContext context,
        IdentityService identityService,
        AccountDeletionRepository repository,
        TimeProvider timeProvider,
        CancellationToken cancellationToken)
    {
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        return await repository.CancelAsync(player.UserId, timeProvider.GetUtcNow(), cancellationToken)
            ? Results.NoContent()
            : Results.NotFound();
    }
}
