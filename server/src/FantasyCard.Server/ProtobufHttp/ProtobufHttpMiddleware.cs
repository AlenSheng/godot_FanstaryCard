using System.Text.Json;
using FantasyCard.Contracts.Http;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Options;
using Microsoft.Net.Http.Headers;

namespace FantasyCard.Server.ProtobufHttp;

public sealed class ProtobufHttpMiddleware(RequestDelegate next)
{
    public const string BinaryKey = "FantasyCard.ProtobufHttp.Binary";
    public async Task InvokeAsync(HttpContext context, IOptions<ProtobufHttpOptions> options)
    {
        var contract = HttpProtocolRegistry.Find(context.Request.Method, context.Request.Path.Value!);
        if (contract is null)
        { await next(context); return; }
        var binary = SelectBinary(context, options.Value.AllowLegacyJson);
        context.Items[BinaryKey] = binary != false;
        context.Response.Headers.Vary = "Accept";
        if (binary is null) { await ProtobufHttpResult.WriteErrorAsync(context, 406); return; }
        if (context.Request.ContentLength > HttpProtocolRegistry.MaximumBodyBytes)
        { await ProtobufHttpResult.WriteErrorAsync(context, 413); return; }
        var size = context.Features.Get<IHttpMaxRequestBodySizeFeature>();
        if (size is { IsReadOnly: false }) size.MaxRequestBodySize = HttpProtocolRegistry.MaximumBodyBytes;
        if (!binary.Value) { await next(context); return; }
        var original = context.Response.Body;
        await using var captured = new LimitedBodyStream();
        context.Response.Body = captured;
        try
        {
            try
            {
                if (contract.Request == "Empty" && (context.Request.ContentType is not null || context.Request.ContentLength > 0 || context.Request.Headers.ContainsKey("Transfer-Encoding")))
                    await GameBody<FantasyCard.Contracts.Http.V1.Empty>.BindAsync(context, null!);
                await next(context);
            }
            catch (BadHttpRequestException exception)
            {
                captured.SetLength(0); context.Response.Clear();
                await ProtobufHttpResult.WriteErrorAsync(context, exception.StatusCode, detail: exception.Message);
            }
            catch (InvalidDataException)
            {
                captured.SetLength(0); context.Response.Clear();
                await ProtobufHttpResult.WriteErrorAsync(context, 500, "Response exceeds supported HTTP limits");
            }
            if (context.Response.StatusCode >= 400 && context.Response.ContentType != HttpProtocolRegistry.MediaType)
            {
                string? title = null; string? detail = null;
                try
                {
                    captured.Position = 0;
                    if (captured.Length > 0)
                    {
                        using var document = await JsonDocument.ParseAsync(captured, cancellationToken: context.RequestAborted);
                        if (document.RootElement.TryGetProperty("title", out var t)) title = t.GetString();
                        if (document.RootElement.TryGetProperty("detail", out var d)) detail = d.GetString();
                    }
                }
                catch (JsonException) { }
                captured.SetLength(0);
                await ProtobufHttpResult.WriteErrorAsync(context, context.Response.StatusCode, title, detail);
            }
            context.Response.Body = original;
            captured.Position = 0;
            await captured.CopyToAsync(original, context.RequestAborted);
        }
        finally { context.Response.Body = original; }
    }
    public static bool? SelectBinary(HttpContext context, bool legacy)
    {
        IList<MediaTypeHeaderValue> accept;
        try { accept = context.Request.GetTypedHeaders().Accept; }
        catch (FormatException) { return null; }
        if (accept.Count == 0) return !(legacy && (context.Request.HasJsonContentType() || string.IsNullOrEmpty(context.Request.ContentType)));
        var protobufQuality = Quality(accept, HttpProtocolRegistry.MediaType);
        var jsonQuality = legacy ? Quality(accept, "application/json") : 0;
        if (protobufQuality <= 0 && jsonQuality <= 0) return null;
        return protobufQuality >= jsonQuality;
    }
    private static double Quality(IList<MediaTypeHeaderValue> accept, string type)
    {
        var exact = accept.Where(a => string.Equals(a.MediaType.Value, type, StringComparison.OrdinalIgnoreCase)).ToArray();
        var application = accept.Where(a => string.Equals(a.MediaType.Value, "application/*", StringComparison.OrdinalIgnoreCase)).ToArray();
        var selected = exact.Length > 0 ? exact : application.Length > 0 ? application : accept.Where(a => a.MediaType == "*/*").ToArray();
        return selected.Length == 0 ? 0 : selected.Max(a => a.Quality ?? 1);
    }
    private sealed class LimitedBodyStream : MemoryStream
    {
        private void Check(int count)
        { if (Position + count > HttpProtocolRegistry.MaximumBodyBytes) throw new InvalidDataException("Game response limit exceeded."); }
        public override void Write(byte[] buffer, int offset, int count) { Check(count); base.Write(buffer, offset, count); }
        public override void Write(ReadOnlySpan<byte> buffer) { Check(buffer.Length); base.Write(buffer); }
        public override Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken cancellationToken)
        { Check(count); return base.WriteAsync(buffer, offset, count, cancellationToken); }
        public override ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken cancellationToken = default)
        { Check(buffer.Length); return base.WriteAsync(buffer, cancellationToken); }
    }
}
