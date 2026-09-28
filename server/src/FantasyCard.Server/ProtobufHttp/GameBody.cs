using System.Reflection;
using System.Text.Json;
using FantasyCard.Contracts.Http;
using Google.Protobuf;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.ProtobufHttp;

public sealed record GameBody<T>(T Value) where T : class
{
    public static implicit operator T(GameBody<T> body) => body.Value;

    [System.Diagnostics.CodeAnalysis.SuppressMessage("Design", "CA1000", Justification = "ASP.NET Core requires static BindAsync for custom parameter binding.")]
    public static async ValueTask<GameBody<T>> BindAsync(HttpContext context, ParameterInfo parameter)
    {
        var contract = HttpProtocolRegistry.Find(context.Request.Method, context.Request.Path.Value!)
            ?? throw new InvalidOperationException("Unregistered game endpoint.");
        var mediaType = context.Request.ContentType?.Split(';', 2)[0].Trim();
        try
        {
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(context.RequestAborted);
            timeout.CancelAfter(TimeSpan.FromSeconds(15));
            using var body = new MemoryStream();
            var buffer = new byte[8192];
            int count;
            while ((count = await context.Request.Body.ReadAsync(buffer, timeout.Token)) != 0)
            {
                if (body.Length + count > HttpProtocolRegistry.MaximumBodyBytes)
                    throw new BadHttpRequestException("Request body exceeds the game HTTP limit.", 413);
                await body.WriteAsync(buffer.AsMemory(0, count), timeout.Token);
            }
            if (string.Equals(mediaType, HttpProtocolRegistry.MediaType, StringComparison.OrdinalIgnoreCase))
                return new((T)HttpDtoMapper.DecodeRequest(contract, body.ToArray(), typeof(T)));
            if (string.Equals(mediaType, "application/json", StringComparison.OrdinalIgnoreCase)
                && context.RequestServices.GetRequiredService<IOptions<ProtobufHttpOptions>>().Value.AllowLegacyJson)
            {
                var options = context.RequestServices.GetRequiredService<IOptions<Microsoft.AspNetCore.Http.Json.JsonOptions>>().Value;
                return new(JsonSerializer.Deserialize<T>(body.ToArray(), options.SerializerOptions)
                    ?? throw new JsonException("A request object is required."));
            }
            throw new BadHttpRequestException("Use application/protobuf for game requests.", 415);
        }
        catch (OperationCanceledException) when (!context.RequestAborted.IsCancellationRequested)
        {
            throw new BadHttpRequestException("Request body receive timeout.", 408);
        }
        catch (Exception exception) when (exception is InvalidProtocolBufferException or InvalidDataException
            or JsonException or FormatException or ArgumentException or OverflowException or TargetInvocationException)
        {
            throw new BadHttpRequestException("Invalid game request body.", 400, exception);
        }
    }
}
