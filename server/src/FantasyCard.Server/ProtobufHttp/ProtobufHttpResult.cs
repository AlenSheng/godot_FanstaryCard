using System.Globalization;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Http.V1;
using Google.Protobuf;
using Microsoft.AspNetCore.Mvc;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.ProtobufHttp;

public sealed class ProtobufHttpOptions
{
    public bool AllowLegacyJson { get; set; }
}

public static class ProtobufHttpExtensions
{
    public static IServiceCollection AddProtobufHttp(this IServiceCollection services, IConfiguration configuration)
    {
        services.Configure<ProtobufHttpOptions>(configuration.GetSection("ProtobufHttp"));
        return services;
    }
}

public sealed class ProtobufHttpFilter : IEndpointFilter
{
    public async ValueTask<object?> InvokeAsync(EndpointFilterInvocationContext context, EndpointFilterDelegate next)
    {
        var result = await next(context);
        GamePage.SetHeaders(context.HttpContext, (result as IValueHttpResult)?.Value);
        if (context.HttpContext.Items[ProtobufHttpMiddleware.BinaryKey] is not true) return result;
        return result is IResult httpResult ? new ProtobufHttpResult(httpResult) : result;
    }
}

public sealed class ProtobufHttpResult(IResult inner) : IResult
{
    public async Task ExecuteAsync(HttpContext httpContext)
    {
        var status = (inner as IStatusCodeHttpResult)?.StatusCode ?? 200;
        if (status == 204)
        {
            httpContext.Response.StatusCode = status;
            httpContext.Response.ContentType = null;
            httpContext.Response.ContentLength = null;
            return;
        }
        if (status >= 400)
        {
            var problem = (inner as IValueHttpResult)?.Value as ProblemDetails;
            await WriteErrorAsync(httpContext, status, problem?.Title, problem?.Detail);
            return;
        }
        var contract = HttpProtocolRegistry.Find(httpContext.Request.Method, httpContext.Request.Path.Value!)!;
        var bytes = HttpDtoMapper.EncodeResponse(contract, (inner as IValueHttpResult)?.Value);
        httpContext.Response.StatusCode = status;
        if (inner.GetType().GetProperty("Location")?.GetValue(inner) is string location)
            httpContext.Response.Headers.Location = location;
        await WriteBytesAsync(httpContext, bytes);
    }

    internal static async Task WriteBytesAsync(HttpContext context, byte[] bytes)
    {
        context.Response.Headers.CacheControl = "no-store";
        context.Response.Headers.Vary = "Accept";
        context.Response.ContentType = HttpProtocolRegistry.MediaType;
        context.Response.ContentLength = bytes.Length;
        context.Response.Headers["X-Content-Type-Options"] = "nosniff";
        await context.Response.Body.WriteAsync(bytes, context.RequestAborted);
    }

    internal static Task WriteErrorAsync(HttpContext context, int status, string? title = null, string? detail = null)
    {
        context.Response.StatusCode = status;
        var error = new HttpError
        {
            Type = "about:blank", Title = title ?? Microsoft.AspNetCore.WebUtilities.ReasonPhrases.GetReasonPhrase(status),
            Status = status, Detail = detail ?? "", TraceId = context.TraceIdentifier,
            Code = "http_" + status.ToString(CultureInfo.InvariantCulture)
        };
        if (int.TryParse(context.Response.Headers.RetryAfter, CultureInfo.InvariantCulture, out var seconds))
            error.RetryAfterSeconds = seconds;
        return WriteBytesAsync(context, error.ToByteArray());
    }
}
