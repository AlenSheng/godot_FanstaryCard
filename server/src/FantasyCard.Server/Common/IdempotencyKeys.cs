namespace FantasyCard.Server.Common;

public static class IdempotencyKeys
{
    public const string HeaderName = "Idempotency-Key";
    public const int MinimumLength = 8;
    public const int MaximumLength = 80;

    public static string? Read(HttpContext context)
    {
        ArgumentNullException.ThrowIfNull(context);
        var value = context.Request.Headers[HeaderName].FirstOrDefault()?.Trim();
        return value is null or { Length: < MinimumLength or > MaximumLength } || value.Any(char.IsControl)
            ? null
            : value;
    }

    public static IResult InvalidProblem(HttpContext context) => Results.Problem(
        statusCode: StatusCodes.Status400BadRequest,
        title: "Invalid Idempotency-Key",
        detail: $"Supply an {MinimumLength}-{MaximumLength} character Idempotency-Key and reuse it when retrying the same request.",
        extensions: new Dictionary<string, object?> { ["traceId"] = context.TraceIdentifier });
}
