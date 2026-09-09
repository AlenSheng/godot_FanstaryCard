using System.Diagnostics;
using System.Text.RegularExpressions;

namespace FantasyCard.Server.Common;

public sealed partial class RequestTraceMiddleware(RequestDelegate next)
{
    private const string TraceHeader = "X-Trace-Id";

    public async Task InvokeAsync(HttpContext context)
    {
        var suppliedTraceId = context.Request.Headers[TraceHeader].FirstOrDefault();
        context.TraceIdentifier = IsValidTraceId(suppliedTraceId)
            ? suppliedTraceId!
            : Activity.Current?.TraceId.ToString() ?? Guid.NewGuid().ToString("N");

        context.Response.OnStarting(() =>
        {
            context.Response.Headers[TraceHeader] = context.TraceIdentifier;
            return Task.CompletedTask;
        });

        await next(context);
    }

    private static bool IsValidTraceId(string? value) =>
        value is not null && value.Length <= 64 && TraceIdPattern().IsMatch(value);

    [GeneratedRegex("^[A-Za-z0-9._-]+$", RegexOptions.CultureInvariant)]
    private static partial Regex TraceIdPattern();
}
