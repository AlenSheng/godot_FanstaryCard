using System.Net;
using System.Net.WebSockets;
using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Persistence;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Hosting;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Fact(Skip = "Requires owned local PostgreSQL and production Godot.", SkipUnless = nameof(HasRealClientDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Frozen_f812_actual_poll_return_during_ACK_must_not_restore_completed_receipt()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(90); var ct = deadline.Token;
        var deviceId = "a05-causal-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create(); var now = DateTimeOffset.UtcNow;
        var identity = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "A05Runtime", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var playerId = identity.UserId; var equipmentId = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var (matchId, room) = await SeedRoomAsync(database, [playerId], ct, equipmentId, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        await A05AuditAsync(database, "causal-before", false, ct);
        var port = ReservePort(); using var client = Client(port, token);
        await using var first = FullHost.Start(database.ConnectionString, port, "a05-causal-before");
        var host = first;
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        await using var relay = new A05AckPollRelay(port);
        var fixture = CreateAckClientFixture("a05-causal");
        CopyFixtureFile(Path.Combine(RepositoryRoot(), "client"), fixture, Path.Combine(RepositoryRoot(), "client/tests/pr13_a05_ack_poll_causal.gd"));
        var control = Path.Combine(fixture, "control"); Directory.CreateDirectory(control);
        var godot = RunA05GodotAsync(fixture, relay.Port, deviceId, matchId, control, "pr13_a05_ack_poll_causal.gd", ct);
        try
        {
            await A05WaitFileAsync(control, "running", godot, ct);
            await using var gate = await database.DataSource.OpenConnectionAsync(ct);
            await using var transaction = await gate.BeginTransactionAsync(ct);
            await using (var command = new NpgsqlCommand("SELECT gold FROM player_wallets WHERE player_id=$1 FOR UPDATE", gate, transaction))
            { command.Parameters.AddWithValue(playerId); await command.ExecuteScalarAsync(ct); }
            await A05ControlAsync(control, "extract", new { matchId }, ct);
            await WaitAsync(async () => await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'") == 4, ct);
            await first.KillAsync();
            Record("A05-causal-actual-host-killed", new { first.ProcessId, boundary = "actual SIGKILL while 4 durable holds Pending and owned wallet row lock held" });
            host = FullHost.Start(database.ConnectionString, port, "a05-causal-after");
            await host.WaitForHealthAsync(client, "/health/live", HttpStatusCode.OK, ct);
            await A05ControlAsync(control, "restarted", new { host.ProcessId }, ct);
            await A05WaitFileAsync(control, "recovery-M", godot, ct);
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            await transaction.CommitAsync(ct);
            await Task.WhenAll(relay.SettlementGetHeld.Task, relay.PollHeld.Task).WaitAsync(ct);
            relay.ReleaseSettlementGet();
            await A05ControlAsync(control, "get-released", new { expected = "real GET loads M; real Bootstrap poll still awaited" }, ct);
            await relay.AckHeld.Task.WaitAsync(ct);
            await A05ControlAsync(control, "ack-held", new { expected = "real production ACK awaits network, receipt cleared" }, ct);
            await A05WaitFileAsync(control, "ack-cleared", godot, ct);
            relay.ReleasePoll();
            await A05ControlAsync(control, "poll-released", new { expected = "old genuine ready Bootstrap response cannot restore ACK-pending receipt" }, ct);
            await A05WaitFileAsync(control, "poll-returned-during-ack", godot, ct);
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
            relay.ReleaseAck();
            await A05ControlAsync(control, "ack-released", new { expected = "actual backend ACK then authoritative post-ACK Bootstrap" }, ct);
            await godot;
            await A05AuditAsync(database, "causal-after", true, ct);
            Assert.Equal(23L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE reason='settlement.commit'"));
            using var result = JsonDocument.Parse(File.ReadAllText(Path.Combine(control, "result.json")));
            Record("A05-causal-counterexample", new { matchId, room.RoomId, playerId, equipmentId, host.ProcessId, fixture,
                actual = result.RootElement.Clone(), expected = "ACK success and post-ACK Bootstrap exclude M; production settlement must remain empty", productionSha = A05RuntimeSourceSha });
            Assert.False(result.RootElement.GetProperty("stale_during_ack").GetBoolean(), "Frozen f812 restored the real M receipt while the production ACK was pending.");
            Assert.False(result.RootElement.GetProperty("stale_after_ack").GetBoolean(), "Frozen f812 retained the real M receipt after confirmed completion.");
        }
        finally
        {
            relay.ReleaseSettlementGet(); relay.ReleasePoll(); relay.ReleaseAck();
            if (!godot.IsCompleted) { try { await godot; } catch when (ct.IsCancellationRequested) { } }
            if (!ReferenceEquals(host, first)) await host.DisposeAsync();
            A05CleanFixture(fixture);
        }
    }

    private sealed class A05AckPollRelay : IAsyncDisposable
    {
        private readonly IHost _listener;
        private readonly HttpClient _backend;
        private readonly CancellationTokenSource _stop = new();
        private readonly TaskCompletionSource _releaseGet = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _releasePoll = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private readonly TaskCompletionSource _releaseAck = new(TaskCreationOptions.RunContinuationsAsynchronously);
        private int _getHeld; private int _pollHeld; private int _ackHeld;
        public int Port { get; } = ReservePort();
        public TaskCompletionSource SettlementGetHeld { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource PollHeld { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource AckHeld { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public A05AckPollRelay(int port)
        {
            _backend = new() { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(15) };
            _listener = new HostBuilder().ConfigureWebHost(web => web.UseKestrel().UseUrls($"http://127.0.0.1:{Port}")
                .Configure(app => { app.UseWebSockets(); app.Run(HandleAsync); })).Build(); _listener.Start();
        }
        public void ReleaseSettlementGet() => _releaseGet.TrySetResult();
        public void ReleasePoll() => _releasePoll.TrySetResult();
        public void ReleaseAck() => _releaseAck.TrySetResult();
        private async Task HandleAsync(HttpContext context)
        {
            try
            {
                if (context.WebSockets.IsWebSocketRequest) { await WebSocketAsync(context); return; }
                var path = context.Request.Path.Value!;
                using var body = new MemoryStream(); await context.Request.Body.CopyToAsync(body, _stop.Token);
                var bytes = body.ToArray();
                using var request = new HttpRequestMessage(new HttpMethod(context.Request.Method), context.Request.Path + context.Request.QueryString);
                if (bytes.Length > 0 || context.Request.Method == "POST") request.Content = new ByteArrayContent(bytes);
                foreach (var (name, values) in context.Request.Headers)
                {
                    if (name is "Host" or "Content-Length" or "Connection") continue;
                    if (!request.Headers.TryAddWithoutValidation(name, values.ToArray())) request.Content?.Headers.TryAddWithoutValidation(name, values.ToArray());
                }
                if (path.EndsWith("/acknowledge", StringComparison.Ordinal) && Interlocked.CompareExchange(ref _ackHeld, 1, 0) == 0)
                {
                    Record("A05-causal-ack-held-before-backend", new { path, requestBodySha256 = A05Sha(bytes), keySha256 = A05Sha(context.Request.Headers["Idempotency-Key"].ToString()) });
                    AckHeld.TrySetResult(); await _releaseAck.Task.WaitAsync(_stop.Token);
                }
                using var response = await _backend.SendAsync(request, _stop.Token); var payload = await response.Content.ReadAsByteArrayAsync(_stop.Token);
                if (response.IsSuccessStatusCode && context.Request.Method == "GET" && path.StartsWith("/api/v1/settlements/", StringComparison.Ordinal) && Interlocked.CompareExchange(ref _getHeld, 1, 0) == 0)
                {
                    await File.WriteAllBytesAsync(Path.Combine(EvidenceDirectory, "causal-settlement-get.pb"), payload, _stop.Token);
                    Record("A05-causal-settlement-get-held", new { path, bodySha256 = A05Sha(payload), actual = Wire.SettlementResponse.Parser.ParseFrom(payload).SettlementId });
                    SettlementGetHeld.TrySetResult(); await _releaseGet.Task.WaitAsync(_stop.Token);
                }
                if (response.IsSuccessStatusCode && path == "/api/v1/bootstrap" && Wire.BootstrapResponse.Parser.ParseFrom(payload).UnfinishedSettlement is { } ready && Interlocked.CompareExchange(ref _pollHeld, 1, 0) == 0)
                {
                    await File.WriteAllBytesAsync(Path.Combine(EvidenceDirectory, "causal-old-ready-bootstrap.pb"), payload, _stop.Token);
                    Record("A05-causal-ready-poll-held", new { path, bodySha256 = A05Sha(payload), ready.SettlementId, ready.MatchId });
                    PollHeld.TrySetResult(); await _releasePoll.Task.WaitAsync(_stop.Token);
                }
                context.Response.StatusCode = (int)response.StatusCode; context.Response.ContentType = response.Content.Headers.ContentType?.ToString();
                context.Response.ContentLength = payload.Length; await context.Response.Body.WriteAsync(payload, _stop.Token);
                Record("A05-causal-http-forwarded", new { path, context.Request.Method, status = (int)response.StatusCode, bodySha256 = A05Sha(payload) });
            }
            catch (Exception error) when (_stop.IsCancellationRequested || error is IOException or OperationCanceledException or WebSocketException) { context.Abort(); }
            catch (HttpRequestException) { context.Abort(); }
        }
        private async Task WebSocketAsync(HttpContext context)
        {
            using var upstream = new ClientWebSocket();
            var uri = new UriBuilder(_backend.BaseAddress!) { Scheme = "ws", Path = context.Request.Path, Query = context.Request.QueryString.Value?.TrimStart('?') }.Uri;
            await upstream.ConnectAsync(uri, _stop.Token); using var downstream = await context.WebSockets.AcceptWebSocketAsync();
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            var forward = PumpAsync(upstream, downstream, linked.Token); var reverse = PumpAsync(downstream, upstream, linked.Token);
            await Task.WhenAny(forward, reverse); linked.Cancel();
            try { await Task.WhenAll(forward, reverse); } catch (Exception error) when (error is OperationCanceledException or WebSocketException) { }
        }
        private static async Task PumpAsync(WebSocket source, WebSocket destination, CancellationToken ct)
        {
            var buffer = new byte[65536];
            while (source.State == WebSocketState.Open && destination.State == WebSocketState.Open)
            {
                var frame = await source.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                if (frame.MessageType == WebSocketMessageType.Close) break;
                await destination.SendAsync(new ArraySegment<byte>(buffer, 0, frame.Count), frame.MessageType, frame.EndOfMessage, ct);
            }
        }
        public async ValueTask DisposeAsync()
        { _stop.Cancel(); await _listener.StopAsync(); _listener.Dispose(); _backend.Dispose(); _stop.Dispose(); }
    }
}
