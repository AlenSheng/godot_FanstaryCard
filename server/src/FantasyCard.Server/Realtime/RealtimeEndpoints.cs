using System.Net.WebSockets;
using FantasyCard.Server.ProtobufHttp;
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
        services.AddSingleton<RealtimeTicketStore>();
        services.AddSingleton<RealtimeEventStore>();
        services.AddSingleton<RealtimeCommandRouter>();
        services.AddHostedService<RealtimeMaintenanceWorker>();
        return services;
    }

    public static IEndpointRouteBuilder MapRealtimeEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/ws/v1/session", HandleSessionAsync).WithTags("Realtime");
        endpoints.MapPost("/api/v1/realtime/ticket", IssueTicketAsync)
            .AddEndpointFilter<ProtobufHttpFilter>()
            .RequireRateLimiting(RequestLimitOptions.WritePolicy).WithTags("Realtime");
        return endpoints;
    }

    internal static async Task<IResult> IssueTicketAsync(
        HttpContext context, GameBody<EmptyTicketRequest> body, IdentityService identityService, RealtimeTicketStore tickets,
        CancellationToken cancellationToken)
    {
        var token = BearerToken(context);
        var player = token is null ? null : await identityService.AuthenticateAsync(token, cancellationToken);
        if (player is null) return context.UnauthorizedProblem();
        context.Response.Headers.CacheControl = "no-store";
        var issued = tickets.Issue(player.UserId, SessionToken.Hash(token!));
        if (issued is null)
        {
            context.Response.Headers.RetryAfter = "30";
            return Results.Problem(statusCode: 429, title: "Realtime ticket capacity reached");
        }
        return Results.Ok(issued);
    }

    public sealed record EmptyTicketRequest;

    private static string? BearerToken(HttpContext context)
    {
        var header = context.Request.Headers.Authorization.FirstOrDefault();
        return header?.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase) == true ? header[7..].Trim() : null;
    }

    private static async Task HandleSessionAsync(
        HttpContext context,
        IdentityRepository identityRepository,
        RealtimeTicketStore tickets,
        IOptions<RealtimeOptions> realtimeOptions,
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

        var ticket = context.Request.Query["ticket"].FirstOrDefault()
            ?? context.Request.Query["ws_ticket"].FirstOrDefault();
        var session = tickets.Consume(ticket);
        byte[]? sessionHash = session?.SessionHash;
        if (ticket is null)
        {
            var accessToken = BearerToken(context);
            if (accessToken is null && realtimeOptions.Value.AllowLegacyAccessTokenQuery)
                accessToken = context.Request.Query["access_token"].FirstOrDefault();
            if (!string.IsNullOrWhiteSpace(accessToken) && accessToken.Length <= 256)
                sessionHash = SessionToken.Hash(accessToken);
        }
        var player = sessionHash is null ? null : (await identityRepository.FindByTokenHashAsync(
            sessionHash, timeProvider.GetUtcNow(), cancellationToken)).Player;
        if (session is not null && player?.UserId != session.PlayerId) player = null;
        if (player is null)
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return;
        }

        var socket = await context.WebSockets.AcceptWebSocketAsync();
        metrics.RealtimeConnectionOpened();
        await using var connection = new RealtimeConnection(socket, metrics);
        var replaced = registry.Register(player.UserId, connection);
        var frameReader = new RealtimeFrameReader(
            requestLimits.Value.RealtimeCommandsPerSecond, requestLimits.Value.OwnedTestBypass);
        try
        {
            // Registration must always be paired with the finally cleanup,
            // including failures while restoring room state or replacing a peer.
            await roomRegistry.MarkPlayerConnectedAsync(player.UserId);
            if (replaced is not null)
            {
                var replacedEvent = eventStore.Create(
                    player.UserId,
                    "session.replaced",
                    context.TraceIdentifier,
                    new SessionReplacedEventPayload("newer_connection"));
                await replaced.RetireAsync(replacedEvent);
            }

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

            using var connectionLifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, connection.CloseDeadline);
            var monitor = MonitorSessionAsync();
            try
            {
                while (socket.State is WebSocketState.Open or WebSocketState.CloseSent && !cancellationToken.IsCancellationRequested)
                {
                    var received = await ReceiveAsync(socket, connectionLifetime.Token);
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

                    // Once a close is sent, consume only the handshake; never route more commands.
                    if (socket.State == WebSocketState.CloseSent) continue;

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

                    if (received.Status == ReceiveStatus.TimedOut)
                    {
                        await connection.CloseAsync(WebSocketCloseStatus.PolicyViolation,
                            "Fragment receive deadline exceeded", CancellationToken.None);
                        return;
                    }

                    var frame = frameReader.Read(received.Payload!, timeProvider.GetUtcNow());
                    if (frame.RateLimited) metrics.RealtimeCommandRateLimited();
                    if (frame.ErrorType is { } errorType)
                    {
                        await connection.SendAsync(
                            eventStore.Create(player.UserId, errorType, context.TraceIdentifier, null),
                            cancellationToken);
                    }
                    if (frame.Command is not { } command) continue;

                    if (!await SessionValidAsync())
                    {
                        await connection.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Session no longer valid", CancellationToken.None);
                        return;
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
            finally
            {
                await connection.CompleteCloseHandshakeAsync();
                await connectionLifetime.CancelAsync();
                try { await monitor; } catch (OperationCanceledException) { }
            }

            async Task<bool> SessionValidAsync() => registry.IsCurrent(player.UserId, connection) &&
                (await identityRepository.FindByTokenHashAsync(sessionHash!, timeProvider.GetUtcNow(), connectionLifetime.Token)).Player?.UserId == player.UserId;

            async Task MonitorSessionAsync()
            {
                try
                {
                    while (!connectionLifetime.IsCancellationRequested)
                    {
                        await Task.Delay(TimeSpan.FromSeconds(5), connectionLifetime.Token);
                        if (!await SessionValidAsync())
                        {
                            await connection.CloseAsync(WebSocketCloseStatus.PolicyViolation, "Session no longer valid", CancellationToken.None);
                            return;
                        }
                    }
                }
                catch (OperationCanceledException) when (connectionLifetime.IsCancellationRequested)
                {
                    // Normal handler shutdown must not turn an orderly close into a reset.
                }
                catch
                {
                    socket.Abort();
                    await connectionLifetime.CancelAsync();
                    throw;
                }
            }
        }
        catch (OperationCanceledException)
        {
            socket.Abort();
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

    internal static async Task<ReceiveResult> ReceiveAsync(
        WebSocket socket,
        CancellationToken cancellationToken)
    {
        var buffer = new byte[MaximumMessageBytes];
        var count = 0;
        var fragmentStarted = false;
        using var fragments = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        while (true)
        {
            ValueWebSocketReceiveResult result;
            try { result = await socket.ReceiveAsync(buffer.AsMemory(count), fragments.Token); }
            catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
            { return new ReceiveResult(ReceiveStatus.TimedOut, null); }
            if (result.MessageType == WebSocketMessageType.Close)
            {
                return new ReceiveResult(ReceiveStatus.Closed, null);
            }

            if (result.MessageType != WebSocketMessageType.Binary)
            {
                return new ReceiveResult(ReceiveStatus.InvalidType, null);
            }

            if (!fragmentStarted && !result.EndOfMessage)
            {
                fragmentStarted = true;
                fragments.CancelAfter(TimeSpan.FromSeconds(10));
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

    internal enum ReceiveStatus
    {
        Complete,
        Closed,
        InvalidType,
        TooLarge,
        TimedOut
    }

    internal sealed record ReceiveResult(ReceiveStatus Status, byte[]? Payload);
}
