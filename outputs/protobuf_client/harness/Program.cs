using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using Client = Game.Protocol;
using Server = FantasyCard.Contracts.Realtime;

// ============================================================================
// FantasyCard realtime protobuf client verification harness.
//   dotnet run                      -> codec parity tests only
//   dotnet run -- --live            -> parity + live E2E against local server
// Verifies the Unity client codec against the server codec byte-for-byte,
// then (with --live) exercises the real /ws/v1/session endpoint end to end.
// ============================================================================

var failures = 0;
void Check(bool condition, string name)
{
    Console.WriteLine($"{(condition ? "PASS" : "FAIL")}  {name}");
    if (!condition) failures++;
}

// ==================== Part 1: codec parity (client <-> server) ====================

Console.WriteLine("---- [1] client encode -> server decode ----");

var ping = new Client.ClientCommand("ping", "ping-00000001");
var pingBytes = ping.ToProtobuf();
var pingBack = Server.RealtimeProtobufCodec.DecodeClient(pingBytes);
Check(pingBack.Type == "ping", "ping type");
Check(pingBack.RequestId == "ping-00000001", "ping requestId");
Check(pingBack.Payload is null, "ping payload null");
Check(pingBack.ExpectedRevision is null, "ping expectedRevision null");

var resume = new Client.ClientCommand(
    "session.resume", "resume-00000001", new Client.SessionResumePayload(42), 7);
var resumeBytes = resume.ToProtobuf();
var resumeBack = Server.RealtimeProtobufCodec.DecodeClient(resumeBytes);
Check(resumeBack.Type == "session.resume", "resume type");
Check(resumeBack.ExpectedRevision == 7, "resume expectedRevision=7");
var resumePayload = resumeBack.Payload as Server.SessionResumeCommandPayload;
Check(resumePayload is not null && resumePayload.LastSequence == 42, "resume lastSequence=42");

// byte-stability: re-encoded decode must be identical bytes
var resumeReencoded = Server.RealtimeProtobufCodec.EncodeClient(resumeBack);
Check(resumeReencoded.SequenceEqual(resumeBytes), "resume bytes round-trip stable");

Console.WriteLine("---- [2] server encode -> client decode ----");

var playerId = Guid.Parse("018f90dc-19a3-7a3d-989c-6f49a1093e21");
var occurredAt = DateTimeOffset.FromUnixTimeMilliseconds(1788344345123L);
var traceId = "trace-harness-42";

ServerEventRoundTrip(
    new Server.ServerEvent("session.connected", traceId,
        new Server.SessionConnectedEventPayload(playerId), "evt-1", 1, occurredAt),
    "session.connected",
    env =>
    {
        var p = env.Payload as Client.SessionConnectedEventPayload;
        return p is not null && p.PlayerId == playerId;
    });

ServerEventRoundTrip(
    new Server.ServerEvent("session.replaced", traceId,
        new Server.SessionReplacedEventPayload("newer_connection"), "evt-2", 2, occurredAt),
    "session.replaced",
    env =>
    {
        var p = env.Payload as Client.SessionReplacedEventPayload;
        return p is not null && p.Reason == "newer_connection";
    });

var pongTime = DateTimeOffset.FromUnixTimeMilliseconds(1788344345999L);
ServerEventRoundTrip(
    new Server.ServerEvent("pong", traceId,
        new Server.PongEventPayload(pongTime), "evt-3", 3, occurredAt, "ping-00000001"),
    "pong",
    env =>
    {
        var p = env.Payload as Client.PongEventPayload;
        return p is not null && p.ServerTime == pongTime && env.RequestId == "ping-00000001";
    });

ServerEventRoundTrip(
    new Server.ServerEvent("session.snapshot", traceId,
        new Server.SessionSnapshotEventPayload(playerId, 12, "Mage", "event_buffer_gap", 3),
        "evt-4", 4, occurredAt, "resume-00000001", 9),
    "session.snapshot",
    env =>
    {
        var p = env.Payload as Client.SessionSnapshotEventPayload;
        return p is not null && p.PlayerId == playerId && p.PlayerVersion == 12 &&
               p.SelectedClass == "Mage" && p.Reason == "event_buffer_gap" &&
               p.PreviousLastSequence == 3 && env.RoomRevision == 9 &&
               env.RequestId == "resume-00000001";
    });

ServerEventRoundTrip(
    new Server.ServerEvent("error.command_rejected", traceId,
        new Server.CommandRejectedEventPayload("UNSUPPORTED_COMMAND", "not implemented"), "evt-5", 5, occurredAt, "cmd-1"),
    "error.command_rejected",
    env =>
    {
        var p = Client.CommandRejectedPayload.From(env);
        return p is not null && p.Code == "UNSUPPORTED_COMMAND" && p.Detail == "not implemented";
    });

ServerEventRoundTrip(
    new Server.ServerEvent("error.invalid_message", traceId, null, "evt-6", 6, occurredAt),
    "error.invalid_message",
    env => env.Payload is null);

void ServerEventRoundTrip(Server.ServerEvent message, string label, Func<Client.ServerEventEnvelope, bool> verifyPayload)
{
    var bytes = Server.RealtimeProtobufCodec.EncodeServer(message);
    var envelope = Client.ServerEventEnvelope.Parse(bytes);
    Check(envelope.Type == label, $"{label} type");
    Check(envelope.TraceId == traceId, $"{label} traceId");
    Check(envelope.EventId == message.EventId, $"{label} eventId");
    Check(envelope.Sequence == message.Sequence, $"{label} sequence");
    Check(envelope.OccurredAt == occurredAt, $"{label} occurredAt");
    Check(envelope.RequestId == message.RequestId, $"{label} requestId");
    Check(envelope.RoomRevision == message.RoomRevision, $"{label} roomRevision");
    Check(verifyPayload(envelope), $"{label} payload");
}

// ==================== Part 2: live E2E (optional) ====================

if (args.Contains("--live"))
{
    Console.WriteLine("---- [3] live E2E ----");
    await RunLiveAsync();
}

Console.WriteLine(failures == 0 ? "ALL CHECKS PASSED" : $"{failures} CHECK(S) FAILED");
return failures == 0 ? 0 : 1;

static async Task RunLiveAsync()
{
    // --- REST local sign-in ---
    using var http = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:5080") };
    var body = JsonSerializer.Serialize(new { deviceId = "proto-harness-01", displayName = "ProtoHarness" });
    using var response = await http.PostAsync("/api/v1/auth/local",
        new StringContent(body, Encoding.UTF8, "application/json"));
    response.EnsureSuccessStatusCode();
    var json = await response.Content.ReadAsStringAsync();
    using var doc = JsonDocument.Parse(json);
    var token = doc.RootElement.GetProperty("accessToken").GetString();
    var playerId = doc.RootElement.GetProperty("player").GetProperty("userId").GetString();
    Console.WriteLine($"login ok, player={playerId}");
    if (string.IsNullOrEmpty(token)) throw new InvalidOperationException("no accessToken");

    var wsUrl = "ws://127.0.0.1:5080/ws/v1/session?access_token=" + Uri.EscapeDataString(token);
    using var ws = new ClientWebSocket();
    await ws.ConnectAsync(new Uri(wsUrl), CancellationToken.None);
    Console.WriteLine("ws connected");

    // unique per run: server caches responses by requestId (idempotency)
    var rid = "h" + DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    var lastSequence = 0L;

    // --- session.connected ---
    var connected = await ReceiveAsync(ws);
    lastSequence = Math.Max(lastSequence, connected.Sequence);
    Console.WriteLine($"recv {connected.Type} seq={connected.Sequence}");
    if (connected.Type != "session.connected") throw new InvalidOperationException("expected session.connected");
    var connectedPayload = connected.Payload as Client.SessionConnectedEventPayload;
    Console.WriteLine($"  playerId matches login: {connectedPayload?.PlayerId.ToString("D") == playerId}");

    // --- ping -> pong (requestId echo + serverTime) ---
    for (var i = 1; i <= 3; i++)
    {
        var requestId = $"{rid}-ping-{i}";
        var sent = DateTime.UtcNow;
        await ws.SendAsync(new ArraySegment<byte>(new Client.ClientCommand("ping", requestId).ToProtobuf()),
            WebSocketMessageType.Binary, true, CancellationToken.None);
        Client.ServerEventEnvelope pong = null;
        while (pong is null)
        {
            var next = await ReceiveAsync(ws);
            lastSequence = Math.Max(lastSequence, next.Sequence);
            if (next.Type == "pong") pong = next;
        }
        var pongPayload = pong.Payload as Client.PongEventPayload;
        Console.WriteLine($"pong #{i}: requestId echo={pong.RequestId == requestId}, " +
                          $"serverTime lag={(pongPayload!.ServerTime - sent).TotalMilliseconds:F0}ms, seq={pong.Sequence}");
    }

    // --- unsupported command -> error.command_rejected(UNSUPPORTED_COMMAND) ---
    await ws.SendAsync(new ArraySegment<byte>(new Client.ClientCommand("match.enqueue", $"{rid}-cmd-1").ToProtobuf()),
        WebSocketMessageType.Binary, true, CancellationToken.None);
    Client.ServerEventEnvelope rejected = null;
    while (rejected is null)
    {
        var next = await ReceiveAsync(ws);
        lastSequence = Math.Max(lastSequence, next.Sequence);
        if (next.Type == "error.command_rejected") rejected = next;
    }
    var rejectedPayload = Client.CommandRejectedPayload.From(rejected);
    Console.WriteLine($"unsupported command rejected: code={rejectedPayload.Code} " +
                      $"(expect UNSUPPORTED_COMMAND), requestId={rejected.RequestId}");

    // --- session.resume with no gap -> server replays the buffered events after lastSequence ---
    // (lastSequence-2 so exactly two events are expected back; no receive-timeout is used
    //  because cancelling a ClientWebSocket receive aborts the whole socket)
    await ws.SendAsync(new ArraySegment<byte>(new Client.ClientCommand(
        "session.resume", $"{rid}-resume-1", new Client.SessionResumePayload(lastSequence - 2)).ToProtobuf()),
        WebSocketMessageType.Binary, true, CancellationToken.None);
    for (var expected = lastSequence - 1; expected <= lastSequence; expected++)
    {
        var replayed = await ReceiveAsync(ws);
        lastSequence = Math.Max(lastSequence, replayed.Sequence);
        Console.WriteLine($"resume(no gap) replayed: {replayed.Type} seq={replayed.Sequence} (expect seq={expected})");
    }

    // --- overflow the 256-event buffer, then resume(0) -> session.snapshot(event_buffer_gap) ---
    for (var i = 0; i < 260; i++)
    {
        await ws.SendAsync(new ArraySegment<byte>(new Client.ClientCommand("ping", $"{rid}-bulk-{i}").ToProtobuf()),
            WebSocketMessageType.Binary, true, CancellationToken.None);
    }
    var pongs = 0;
    while (pongs < 260)
    {
        var next = await ReceiveAsync(ws);
        lastSequence = Math.Max(lastSequence, next.Sequence);
        if (next.Type == "pong") pongs++;
    }
    Console.WriteLine($"drained {pongs}/260 bulk pongs (flood + buffer eviction ok), lastSequence={lastSequence}");

    await ws.SendAsync(new ArraySegment<byte>(new Client.ClientCommand(
        "session.resume", $"{rid}-resume-2", new Client.SessionResumePayload(0)).ToProtobuf()),
        WebSocketMessageType.Binary, true, CancellationToken.None);
    Client.ServerEventEnvelope snapshot = null;
    while (snapshot is null)
    {
        var next = await ReceiveAsync(ws);
        if (next.RequestId == $"{rid}-resume-2") snapshot = next;
    }
    var snapshotPayload = snapshot.Payload as Client.SessionSnapshotEventPayload;
    Console.WriteLine($"resume(gap) -> {snapshot.Type} reason={snapshotPayload?.Reason} " +
                      $"(expect event_buffer_gap), playerVersion={snapshotPayload?.PlayerVersion}, " +
                      $"previousLastSequence={snapshotPayload?.PreviousLastSequence}");

    // --- second connection replaces the first: old socket gets session.replaced ---
    using var ws2 = new ClientWebSocket();
    await ws2.ConnectAsync(new Uri(wsUrl), CancellationToken.None);
    var replaced = await ReceiveAsync(ws);
    Console.WriteLine($"old socket after takeover: {replaced.Type} " +
                      $"(expect session.replaced), reason={(replaced.Payload as Client.SessionReplacedEventPayload)?.Reason}");
    var close = await ws.ReceiveAsync(new byte[1024], CancellationToken.None);
    Console.WriteLine($"old socket close: {close.CloseStatus} (expect PolicyViolation)");
    // 模拟已修复的客户端（RealtimeGateway）：收到 Close 后回显完成握手，
    // 服务端 CloseAsync 才能解除等待、继续向新连接下发 session.connected
    await ws.CloseOutputAsync(WebSocketCloseStatus.NormalClosure, "Client closed", CancellationToken.None);

    // --- ws2 的 session.connected 尚未读取，先排掉 ---
    var ws2Connected = await ReceiveAsync(ws2);
    Console.WriteLine($"new socket first event: {ws2Connected.Type} (expect session.connected)");

    // --- text frame on the second socket -> InvalidMessageType close ---
    await ws2.SendAsync(new ArraySegment<byte>(Encoding.UTF8.GetBytes("{\"type\":\"ping\"}")),
        WebSocketMessageType.Text, true, CancellationToken.None);
    WebSocketReceiveResult close2;
    while (true)
    {
        close2 = await ws2.ReceiveAsync(new byte[1024], CancellationToken.None);
        if (close2.MessageType == WebSocketMessageType.Close) break;
        Console.WriteLine($"(skip unexpected data frame: {close2.MessageType} {close2.Count}B)");
    }
    Console.WriteLine($"text frame close: {close2.CloseStatus} (expect InvalidMessageType)");
}

static async Task<Client.ServerEventEnvelope> ReceiveAsync(ClientWebSocket ws, CancellationToken cancellationToken = default)
{
    var buffer = new byte[16 * 1024];
    using var message = new MemoryStream();
    while (true)
    {
        var result = await ws.ReceiveAsync(new ArraySegment<byte>(buffer), cancellationToken);
        if (result.MessageType != WebSocketMessageType.Binary)
            throw new InvalidOperationException($"unexpected frame type {result.MessageType}, close={result.CloseStatus}");
        message.Write(buffer, 0, result.Count);
        if (result.EndOfMessage)
            return Client.ServerEventEnvelope.Parse(message.ToArray());
    }
}
