using FantasyCard.Domain.Players;

namespace FantasyCard.Server.Identity;

public static class HttpContextAuthenticationExtensions
{
    public static Task<PlayerProfile?> AuthenticatePlayerAsync(
        this HttpContext context,
        IdentityService identityService,
        CancellationToken cancellationToken,
        string? explicitToken = null)
    {
        var token = explicitToken;
        if (token is null)
        {
            var authorization = context.Request.Headers.Authorization.FirstOrDefault();
            const string bearerPrefix = "Bearer ";
            token = authorization?.StartsWith(bearerPrefix, StringComparison.OrdinalIgnoreCase) == true
                ? authorization[bearerPrefix.Length..].Trim()
                : null;
        }

        return token is null
            ? Task.FromResult<PlayerProfile?>(null)
            : identityService.AuthenticateAsync(token, cancellationToken);
    }

    public static IResult UnauthorizedProblem(this HttpContext context)
    {
        context.Response.Headers.WWWAuthenticate = "Bearer";
        return Results.Problem(
            statusCode: StatusCodes.Status401Unauthorized,
            title: "Authentication required",
            detail: "Supply a valid bearer access token.",
            extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
    }
}
