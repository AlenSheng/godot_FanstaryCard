using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text.Json;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Identity;

namespace FantasyCard.Server.Admin;

public sealed class ClientSettingsHub
{
    private sealed record Subscriber(WebSocket Socket, SemaphoreSlim SendLock);
    private readonly ConcurrentDictionary<Guid, Subscriber> _subscribers = new();
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    public async Task SubscribeAsync(WebSocket socket, object initial, CancellationToken cancellationToken)
    {
        var id = Guid.NewGuid();
        var subscriber = new Subscriber(socket, new SemaphoreSlim(1, 1));
        if (_subscribers.Count >= 2000)
        {
            await socket.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Subscriber limit reached", cancellationToken);
            return;
        }
        _subscribers[id] = subscriber;
        try
        {
            await SendAsync(subscriber, initial, cancellationToken);
            var buffer = new byte[128];
            while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                var message = await socket.ReceiveAsync(buffer, cancellationToken);
                if (message.MessageType == WebSocketMessageType.Close) break;
                if (message.Count > 0)
                    await socket.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Read-only channel", cancellationToken);
            }
        }
        catch (WebSocketException) { }
        catch (OperationCanceledException) { }
        finally
        {
            _subscribers.TryRemove(id, out _);
            subscriber.SendLock.Dispose();
            if (socket.State == WebSocketState.Open)
                await socket.CloseAsync(WebSocketCloseStatus.NormalClosure, "Closed", CancellationToken.None);
        }
    }

    public async Task PublishAsync(object update, CancellationToken cancellationToken)
    {
        foreach (var (id, subscriber) in _subscribers)
        {
            try { await SendAsync(subscriber, update, cancellationToken); }
            catch (WebSocketException) { _subscribers.TryRemove(id, out _); }
            catch (ObjectDisposedException) { _subscribers.TryRemove(id, out _); }
        }
    }

    private static async Task SendAsync(Subscriber subscriber, object payload, CancellationToken cancellationToken)
    {
        var bytes = JsonSerializer.SerializeToUtf8Bytes(payload, Json);
        await subscriber.SendLock.WaitAsync(cancellationToken);
        try
        {
            if (subscriber.Socket.State == WebSocketState.Open)
                await subscriber.Socket.SendAsync(bytes, WebSocketMessageType.Text, true, cancellationToken);
        }
        finally { subscriber.SendLock.Release(); }
    }
}

public static class ClientSettingsEndpoints
{
    public static IEndpointRouteBuilder MapClientSettingsEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/v1/client-info", GetInfoAsync);
        endpoints.MapGet("/ws/v1/client-info", SubscribeAsync);
        return endpoints;
    }

    public static object PublicInfo(ClientSettings settings, IHostEnvironment environment, IConfiguration configuration) =>
        new
        {
            configVersion = BootstrapRepository.CurrentConfigVersion,
            capabilities = Capabilities(settings, environment, configuration),
            announcement = new
            {
                title = settings.AnnouncementTitle,
                body = settings.AnnouncementBody,
                version = settings.Version
            }
        };

    private static string[] Capabilities(ClientSettings settings, IHostEnvironment environment, IConfiguration configuration)
    {
        var result = new List<string>();
        if (LocalAuthPolicy.IsEnabled(environment.EnvironmentName,
            configuration.GetValue<bool>("Identity:EnableLocalAuth"),
            configuration.GetValue<bool>("Identity:AllowManagedLocalAuth") && settings.LocalLoginEnabled))
            result.Add("identity.local");
        if (configuration.GetValue<bool>("Identity:Steam:Enabled"))
            result.Add("identity.steam");
        return [.. result];
    }

    private static async Task<IResult> GetInfoAsync(ClientSettingsRepository repository,
        IHostEnvironment environment, IConfiguration configuration, CancellationToken cancellationToken) =>
        Results.Ok(PublicInfo(await repository.GetAsync(cancellationToken), environment, configuration));

    private static async Task SubscribeAsync(HttpContext context, ClientSettingsRepository repository,
        ClientSettingsHub hub, IHostEnvironment environment, IConfiguration configuration,
        CancellationToken cancellationToken)
    {
        if (!context.WebSockets.IsWebSocketRequest)
        {
            context.Response.StatusCode = StatusCodes.Status426UpgradeRequired;
            return;
        }
        using var socket = await context.WebSockets.AcceptWebSocketAsync();
        var settings = await repository.GetAsync(cancellationToken);
        await hub.SubscribeAsync(socket, PublicInfo(settings, environment, configuration), cancellationToken);
    }
}
