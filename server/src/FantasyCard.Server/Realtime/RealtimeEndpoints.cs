using System.Net.WebSockets;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Realtime;

public static class RealtimeEndpoints
{
    private const int MaximumMessageBytes = 16 * 1024;

    public static IServiceCollection AddRealtimeModule(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        services.AddOptions<RealtimeOptions>()
            .Bind(configuration.GetSection(RealtimeOptions.SectionName))
            .Validate(options => options.EventStreamIdleRetentionMinutes is >= 5 and <= 1440,
                "Realtime event stream retention must be 5-1440 minutes.")
            .Validate(options => options.CleanupIntervalMinutes is >= 1 and <= 60,
                "Realtime cleanup interval must be 1-60 minutes.")
            .ValidateOnStart();
        services.AddSingleton<ConnectionRegistry>();
        services.AddSingleton<RealtimeEventStore>();
        services.AddSingleton<RealtimeCommandRouter>();
        services.AddHostedService<RealtimeMaintenanceWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapRealtimeEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/ws/v1/session", HandleSessionAsync).WithTags("Realtime");
        return endpoints;
    }

    private static async Task HandleSessionAsync(
        HttpContext context,
        IdentityService identityService,
        ConnectionRegistry registry,
        RealtimeEventStore eventStore,
        RealtimeCommandRouter router,
        RoomRegistry roomRegistry,
        IRoomReadyService roomReadyService,
        ServerMetrics metrics,
        SettlementEventPublisher settlementEvents,
        TimeProvider timeProvider,
        IOptions<RequestLimitOptions> requestLimits,
        CancellationToken cancellationToken)
    {
        if (!context.WebSockets.IsWebSocketRequest)
        {
            context.Response.StatusCode = StatusCodes.Status426UpgradeRequired;
            return;
        }

        var accessToken = context.Request.Query["access_token"].FirstOrDefault();
        var player = await context.AuthenticatePlayerAsync(identityService, cancellationToken, accessToken);
        if (player is null)
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return;
        }

        var socket = await context.WebSockets.AcceptWebSocketAsync();
        metrics.RealtimeConnectionOpened();
        await using var connection = new RealtimeConnection(socket);
        var replaced = registry.Register(player.UserId, connection);
        var commandLimiter = new RealtimeCommandRateLimiter(
            requestLimits.Value.RealtimeCommandsPerSecond);
        DateTimeOffset? lastRateLimitNotice = null;
        await roomRegistry.MarkPlayerConnectedAsync(player.UserId);
        if (replaced is not null)
        {
            var replacedEvent = eventStore.Create(
                player.UserId,
                "session.replaced",
                context.TraceIdentifier,
                new SessionReplacedEventPayload("newer_connection"));
            await replaced.SendAsync(replacedEvent, CancellationToken.None);
            await replaced.CloseAsync(
                WebSocketCloseStatus.PolicyViolation,
                "Replaced by a newer connection",
                CancellationToken.None);
        }

        try
        {
            await connection.SendAsync(
                eventStore.Create(
                    player.UserId,
                    "session.connected",
                    context.TraceIdentifier,
                    new SessionConnectedEventPayload(player.UserId)),
                cancellationToken);
            await settlementEvents.PublishReadyAsync(player.UserId, cancellationToken);

            if (roomRegistry.TryGetForPlayer(player.UserId, out var roomActor, out var matchId) && roomActor is not null)
            {
                var roomState = await roomActor.ExecuteAsync(
                    new GetRoomClientStateCommand(player.UserId),
                    cancellationToken);
                await connection.SendAsync(
                    eventStore.Create(
                        player.UserId,
                        "room.snapshot",
                        context.TraceIdentifier,
                        RoomSnapshotProjection.Build(roomState, player.UserId, matchId, timeProvider.GetUtcNow()),
                        roomRevision: roomState.Snapshot.Revision),
                    cancellationToken);
            }
            else if (await roomReadyService.GetAsync(player.UserId, cancellationToken) is { } ready)
            {
                await connection.SendAsync(
                    eventStore.Create(player.UserId, "room.ready_required", context.TraceIdentifier,
                        new RoomReadyRequiredEventPayload(ready.MatchId, ready.RoomId,
                            ready.ReadyDeadline.ToUnixTimeMilliseconds(), ready.ReadyPlayers, ready.RequiredPlayers)),
                    cancellationToken);
            }

            while (socket.State == WebSocketState.Open && !cancellationToken.IsCancellationRequested)
            {
                var received = await ReceiveAsync(socket, cancellationToken);
                metrics.RealtimeMessageReceived();
                if (received.Payload is { } payload)
                    metrics.ObserveRealtimeMessageBytes(payload.Length);
                if (received.Status == ReceiveStatus.Closed)
                {
                    await connection.CloseAsync(
                        WebSocketCloseStatus.NormalClosure,
                        "Client closed",
                        CancellationToken.None);
                    return;
                }

                if (received.Status == ReceiveStatus.InvalidType)
                {
                    await connection.CloseAsync(
                        WebSocketCloseStatus.InvalidMessageType,
                        "Only protobuf binary messages are supported",
                        CancellationToken.None);
                    return;
                }

                if (received.Status == ReceiveStatus.TooLarge)
                {
                    await connection.CloseAsync(
                        WebSocketCloseStatus.MessageTooBig,
                        "Message exceeds 16 KiB",
                        CancellationToken.None);
                    return;
                }

                ClientCommand? command;
                try
                {
                    command = RealtimeProtobufCodec.DecodeClient(received.Payload!);
                }
                catch (Exception exception) when (exception is InvalidDataException or OverflowException)
                {
                    await connection.SendAsync(
                        eventStore.Create(
                            player.UserId,
                            "error.invalid_message",
                            context.TraceIdentifier,
                            null),
                        cancellationToken);
                    continue;
                }

                if (command is null)
                {
                    await connection.SendAsync(
                        eventStore.Create(
                            player.UserId,
                            "error.invalid_message",
                            context.TraceIdentifier,
                            null),
                        cancellationToken);
                    continue;
                }

                var receivedAt = timeProvider.GetUtcNow();
                if (!commandLimiter.TryAcquire(receivedAt))
                {
                    metrics.RealtimeCommandRateLimited();
                    if (lastRateLimitNotice is null ||
                        receivedAt - lastRateLimitNotice >= TimeSpan.FromSeconds(1))
                    {
                        lastRateLimitNotice = receivedAt;
                        await connection.SendAsync(
                            eventStore.Create(
                                player.UserId,
                                "error.rate_limited",
                                context.TraceIdentifier,
                                null),
                            cancellationToken);
                    }
                    continue;
                }

                foreach (var response in await router.RouteAsync(
                    player,
                    command,
                    context.TraceIdentifier,
                    cancellationToken))
                {
                    await connection.SendAsync(response, cancellationToken);
                }
            }
        }
        catch (WebSocketException) when (socket.State != WebSocketState.Open)
        {
            // The peer disconnected without a closing handshake.
        }
        finally
        {
            metrics.RealtimeConnectionClosed();
            if (registry.Unregister(player.UserId, connection))
                await roomRegistry.MarkPlayerDisconnectedAsync(player.UserId);
        }
    }

    private static async Task<ReceiveResult> ReceiveAsync(
        WebSocket socket,
        CancellationToken cancellationToken)
    {
        var buffer = new byte[MaximumMessageBytes];
        var count = 0;
        while (true)
        {
            var result = await socket.ReceiveAsync(buffer.AsMemory(count), cancellationToken);
            if (result.MessageType == WebSocketMessageType.Close)
            {
                return new ReceiveResult(ReceiveStatus.Closed, null);
            }

            if (result.MessageType != WebSocketMessageType.Binary)
            {
                return new ReceiveResult(ReceiveStatus.InvalidType, null);
            }

            count += result.Count;
            if (count == MaximumMessageBytes && !result.EndOfMessage)
            {
                return new ReceiveResult(ReceiveStatus.TooLarge, null);
            }

            if (result.EndOfMessage)
            {
                return new ReceiveResult(ReceiveStatus.Complete, buffer.AsMemory(0, count).ToArray());
            }
        }
    }

    private enum ReceiveStatus
    {
        Complete,
        Closed,
        InvalidType,
        TooLarge
    }

    private sealed record ReceiveResult(ReceiveStatus Status, byte[]? Payload);
}
