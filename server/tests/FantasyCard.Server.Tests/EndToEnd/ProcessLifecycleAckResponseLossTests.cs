using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Net.WebSockets;
using System.Security.Cryptography;
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
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    public static bool HasRealClientDatabase => HasPrivateDatabase &&
        File.Exists(Environment.GetEnvironmentVariable("A3GAME_GODOT_EXECUTABLE"));

    [Theory(Skip = "Requires an owned local PostgreSQL database and A3GAME_GODOT_EXECUTABLE.", SkipUnless = nameof(HasRealClientDatabase))]
    [InlineData("drop-first-committed")]
    [InlineData("drop-all-committed")]
    [InlineData("drop-all-uncommitted")]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_Godot_ACK_response_loss_preserves_one_receipt_and_retryable_truth(string mode)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(120);
        var ct = deadline.Token;
        var deviceId = "ack-fault-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create();
        var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "AckFault", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var playerId = player.UserId;
        var equipmentId = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var gold = await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId);
        var potions = await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId);
        var (matchId, room) = await SeedRoomAsync(database, [playerId], ct, equipmentId, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        var port = ReservePort();
        using var client = Client(port, token);
        await using var host = FullHost.Start(database.ConnectionString, port, "ack-" + mode);
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        using (var socket = await ConnectAsync(client, port, ct)) await ExtractAsync(socket, ct);
        await WaitAsync(async () => await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_settlements s WHERE match_id=$1 AND NOT EXISTS (SELECT 1 FROM settlement_asset_holds h WHERE h.settlement_id=s.settlement_id AND h.state='Pending')", matchId) == 1, ct);
        var receipt = Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get,
            $"/api/v1/matches/{matchId:D}/settlement", null, ct));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1 AND acknowledged_at IS NOT NULL", matchId));
        await using var proxy = new AckFaultProxy(port, mode);
        var fixture = CreateAckClientFixture(mode);
        try { await RunAckGodotAsync(fixture, proxy.Port, deviceId, receipt.SettlementId, matchId, mode, ct); }
        finally
        {
            Record("ACK-FAULT-attempts-" + mode, new { mode, attempts = proxy.Attempts.ToArray(), errors = proxy.Errors.ToArray(),
                acknowledgedRows = await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1 AND acknowledged_at IS NOT NULL", matchId) });
            // Retain logs, results, exact copied source and its manifest. Original
            // font hashes remain reviewable without duplicating asset caches.
            foreach (var directory in Directory.EnumerateDirectories(fixture)
                .Where(path => Path.GetFileName(path) is ".godot" or "assets" || Path.GetFileName(path).StartsWith("user-", StringComparison.Ordinal)))
                Directory.Delete(directory, recursive: true);
        }
        // This evidence comes from real persisted state after the production
        // client returns, not a replacement HTTP result or a mocked repository.
        Assert.Equal(gold + 23, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
        Assert.Equal(potions + 2, await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId));
        Assert.Equal(playerId, await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal("Equipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1 AND acknowledged_at IS NOT NULL", matchId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
        Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Committed'"));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", playerId));
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason='settlement.extract'", equipmentId));
        var attempts = proxy.Attempts.ToArray();
        Assert.Empty(proxy.Errors);
        Assert.Equal(mode == "drop-first-committed" ? 2 : mode == "drop-all-committed" ? 3 : 4, attempts.Length);
        Assert.All(attempts, attempt => Assert.Equal(attempts[0].BodySha256, attempt.BodySha256));
        var initialAttempts = attempts.Take(mode == "drop-first-committed" ? 2 : 3).ToArray();
        Assert.All(attempts, attempt => Assert.NotEqual(Convert.ToHexStringLower(SHA256.HashData([])), attempt.KeySha256));
        Assert.Single(initialAttempts.Select(attempt => attempt.KeySha256).Distinct());
        if (mode == "drop-all-uncommitted")
        {
            Assert.All(attempts.Take(3), attempt => Assert.False(attempt.Forwarded));
            Assert.True(attempts[3].Forwarded);
            Assert.NotEqual(attempts[0].KeySha256, attempts[3].KeySha256);
        }
        else
        {
            Assert.All(attempts, attempt => Assert.True(attempt.Forwarded));
            Assert.All(attempts, attempt => Assert.Equal(200, attempt.BackendStatus));
            Assert.Single(attempts.Select(attempt => attempt.ResponseSha256).Distinct());
        }
        Record("ACK-FAULT-" + mode, new { mode, host.ProcessId, matchId, playerId, receipt.SettlementId, equipmentId,
            attempts, fixture, assetsOnce = true, acknowledged = true,
            canonical = "PR13-A03.3-T01 / PR13-A03.3-T02 / LOAD-05.4-T01",
            profiles = "OFFLINE+POSTGRES; seeded actual extraction; LIVE/RENDER and runner cycle accounting remain separate" });
    }

    private static string RepositoryRoot()
    {
        for (var directory = new DirectoryInfo(AppContext.BaseDirectory); directory is not null; directory = directory.Parent)
            if (Directory.Exists(Path.Combine(directory.FullName, "client"))) return directory.FullName;
        throw new InvalidOperationException("Cannot locate the source client beside this test build.");
    }

    private static string CreateAckClientFixture(string mode)
    {
        var source = Path.Combine(RepositoryRoot(), "client");
        var target = Path.Combine(EvidenceDirectory, "ack-client-" + mode + "-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(target);
        // Copy original dependencies byte-for-byte. No real project startup URL,
        // remembered user session, art cache, or generated build is inherited.
        foreach (var name in new[] { "network", "state", "platform", "data" })
        foreach (var path in Directory.EnumerateFiles(Path.Combine(source, name), "*", SearchOption.AllDirectories)
            .Where(path => path.EndsWith(".gd", StringComparison.Ordinal) || path.EndsWith(".json", StringComparison.Ordinal)))
            CopyFixtureFile(source, target, path);
        foreach (var relative in new[] { "ui/card_details.gd", "ui/palette.gd", "assets/fonts/SourceHanSansSC-Regular.otf",
            "assets/fonts/SourceHanSerifSC-SemiBold.otf", "tests/pr13_ack_response_loss.gd" })
            CopyFixtureFile(source, target, Path.Combine(source, relative));
        var copied = Directory.EnumerateFiles(target, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal)
            .Select(path => new { path = Path.GetRelativePath(target, path), bytes = new FileInfo(path).Length,
                sha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path))) }).ToArray();
        File.WriteAllText(Path.Combine(target, "source-manifest.json"), JsonSerializer.Serialize(copied));
        File.WriteAllText(Path.Combine(target, "project.godot"), """
            config_version=5
            [application]
            config/name="PR13 owned ACK fault fixture"
            [platform]
            development/local_auth=true
            [rendering]
            renderer/rendering_method="gl_compatibility"
            """);
        return target;
    }

    private static void CopyFixtureFile(string source, string target, string path)
    {
        var destination = Path.Combine(target, Path.GetRelativePath(source, path));
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        File.Copy(path, destination);
    }

    private static async Task RunAckGodotAsync(string fixture, int proxyPort, string deviceId, string receiptId, Guid matchId,
        string mode, CancellationToken ct)
    {
        var resultFile = Path.Combine(fixture, "ack-result.json");
        foreach (var import in new[] { true, false })
        {
            var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("A3GAME_GODOT_EXECUTABLE")!)
            { WorkingDirectory = fixture, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            start.ArgumentList.Add("--headless"); start.ArgumentList.Add("--path"); start.ArgumentList.Add(fixture);
            if (import) { start.ArgumentList.Add("--editor"); start.ArgumentList.Add("--import"); start.ArgumentList.Add("--quit"); }
            else { start.ArgumentList.Add("--script"); start.ArgumentList.Add("res://tests/pr13_ack_response_loss.gd"); }
            start.Environment.Clear();
            ConfigureWindowsChild(start, fixture);
            foreach (var name in new[] { "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME" })
            { var directory = Path.Combine(fixture, "user-" + name.ToLowerInvariant()); Directory.CreateDirectory(directory); start.Environment[name] = directory; }
            start.Environment["FANTASYCARD_SERVER_URL"] = $"http://127.0.0.1:{proxyPort}";
            start.Environment["FANTASYCARD_LOAD_RUN_ID"] = "owned-ack-fault";
            start.Environment["PR13_ACK_FAULT_MODE"] = mode;
            start.Environment["PR13_ACK_DEVICE_ID"] = deviceId;
            start.Environment["PR13_ACK_RECEIPT_ID"] = receiptId;
            start.Environment["PR13_ACK_MATCH_ID"] = matchId.ToString("D");
            start.Environment["PR13_ACK_RESULT"] = resultFile;
            using var process = Process.Start(start)!;
            var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None); var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
            try { await process.WaitForExitAsync(ct); }
            finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
            var output = await stdout + "\n" + await stderr;
            File.WriteAllText(Path.Combine(fixture, import ? "import.log" : "client.log"), output);
            Record("ack-client-process-stop", new { mode, import, process.Id, process.ExitCode, fixture });
            Assert.Equal(0, process.ExitCode);
            Assert.DoesNotContain("SCRIPT ERROR", output); Assert.DoesNotContain("Parse Error", output);
            // Godot creates autoloads before its first asset import. Register
            // the original Game only after its original font dependencies exist.
            if (import) File.AppendAllText(Path.Combine(fixture, "project.godot"), "\n[autoload]\nGame=\"*res://state/game_store.gd\"\n");
        }
        using var result = JsonDocument.Parse(File.ReadAllText(resultFile));
        Assert.True(result.RootElement.GetProperty("ok").GetBoolean(), result.RootElement.ToString());
    }

    private sealed record AckAttempt(int Index, string KeySha256, string BodySha256, bool Forwarded, bool Dropped,
        int? BackendStatus, string? ResponseSha256);

    private sealed class AckFaultProxy : IAsyncDisposable
    {
        private readonly IHost _listener;
        private readonly HttpClient _backend;
        private readonly CancellationTokenSource _stop = new();
        private readonly string _mode;
        private int _ackIndex;
        private volatile bool _released;
        private readonly string? _stopFile;
        public int Port { get; } = ReservePort();
        public ConcurrentQueue<AckAttempt> Attempts { get; } = new();
        public ConcurrentQueue<string> Errors { get; } = new();
        public AckFaultProxy(int backendPort, string mode, string? stopFile = null)
        {
            _mode = mode;
            _stopFile = stopFile;
            _backend = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{backendPort}"), Timeout = TimeSpan.FromSeconds(15) };
            // Kestrel Abort closes the socket without synthesizing an HTTP
            // error response (HttpListener can emit 411 while aborting a POST).
            _listener = new HostBuilder().ConfigureWebHost(web => web.UseKestrel().UseUrls($"http://127.0.0.1:{Port}")
                .Configure(app => { app.UseWebSockets(); app.Run(HandleAsync); })).Build();
            _listener.Start();
        }
        private async Task HandleAsync(HttpContext context)
        {
            try
            {
                var path = context.Request.Path + context.Request.QueryString;
                if (path == "/__faults/release")
                { _released = true; context.Response.StatusCode = 204; return; }
                if (context.WebSockets.IsWebSocketRequest) { await BridgeWebSocketAsync(context); return; }
                using var body = new MemoryStream(); await context.Request.Body.CopyToAsync(body, _stop.Token);
                var bytes = body.ToArray();
                var isAck = context.Request.Method == "POST" && path.StartsWith("/api/v1/settlements/", StringComparison.Ordinal) && path.EndsWith("/acknowledge", StringComparison.Ordinal);
                var index = isAck ? Interlocked.Increment(ref _ackIndex) : 0;
                var dropped = isAck && !_released && (_mode switch
                {
                    "cycles-middle-response-loss" or "cycles-middle-uncommitted-loss" => index == 2,
                    "stop-before-commit" or "stop-after-commit" => false,
                    "drop-first-committed" => index == 1,
                    _ => true
                });
                var keyHash = Hash(System.Text.Encoding.UTF8.GetBytes(context.Request.Headers["Idempotency-Key"].ToString()));
                if (dropped && _mode is "drop-all-uncommitted" or "cycles-middle-uncommitted-loss")
                { Attempts.Enqueue(new(index, keyHash, Hash(bytes), false, true, null, null)); context.Abort(); return; }
                using var request = new HttpRequestMessage(new HttpMethod(context.Request.Method), path);
                if (bytes.Length > 0 || context.Request.Method == "POST") request.Content = new ByteArrayContent(bytes);
                foreach (var (name, values) in context.Request.Headers)
                {
                    if (name.Equals("Host", StringComparison.OrdinalIgnoreCase) || name.Equals("Content-Length", StringComparison.OrdinalIgnoreCase) || name.Equals("Connection", StringComparison.OrdinalIgnoreCase)) continue;
                    if (!request.Headers.TryAddWithoutValidation(name, values.ToArray())) request.Content?.Headers.TryAddWithoutValidation(name, values.ToArray());
                }
                if (isAck && index == 1 && _mode == "stop-before-commit") await StopDuringAckAsync();
                using var response = await _backend.SendAsync(request, _stop.Token);
                var responseBytes = await response.Content.ReadAsByteArrayAsync(_stop.Token);
                if (isAck && index == 1 && _mode == "stop-after-commit") await StopDuringAckAsync();
                if (isAck) Attempts.Enqueue(new(index, keyHash, Hash(bytes), true, dropped, (int)response.StatusCode, Hash(responseBytes)));
                // Fault is applied only after the real backend has replied. The
                // front connection closes without receiving that response.
                if (dropped) { context.Abort(); return; }
                context.Response.StatusCode = (int)response.StatusCode;
                context.Response.ContentType = response.Content.Headers.ContentType?.ToString();
                foreach (var header in response.Headers)
                    if (header.Key.Equals("Retry-After", StringComparison.OrdinalIgnoreCase)) context.Response.Headers[header.Key] = string.Join(",", header.Value);
                context.Response.ContentLength = responseBytes.Length;
                await context.Response.Body.WriteAsync(responseBytes, _stop.Token);
            }
            catch (Exception error) when (_stop.IsCancellationRequested || error is WebSocketException or IOException) { context.Abort(); }
            catch (Exception error) { Errors.Enqueue(error.ToString()); context.Abort(); }
        }
        private async Task StopDuringAckAsync()
        {
            Assert.NotNull(_stopFile);
            await File.WriteAllTextAsync(_stopFile, "Owned coordinator STOP while the real ACK request is pending.", _stop.Token);
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            deadline.CancelAfter(TimeSpan.FromSeconds(3));
            while (!File.Exists(_stopFile + ".observed")) await Task.Delay(20, deadline.Token);
            using var observed = JsonDocument.Parse(await File.ReadAllTextAsync(_stopFile + ".observed", deadline.Token));
            Assert.True(observed.RootElement.GetProperty("stop_requested").GetBoolean());
            Assert.True(observed.RootElement.GetProperty("busy").GetBoolean());
            Assert.NotEmpty(observed.RootElement.GetProperty("pending_ack").GetString()!);
            Assert.Equal("settlement", observed.RootElement.GetProperty("stage").GetString());
            Assert.Equal(0, observed.RootElement.GetProperty("cycles_completed").GetInt32());
            Record("ACK-STOP-observed", new { mode = _mode, stage = "real GameStore ACK awaited by production load runner", observation = observed.RootElement.Clone() });
        }
        private async Task BridgeWebSocketAsync(HttpContext context)
        {
            using var upstream = new ClientWebSocket();
            var uri = new UriBuilder(_backend.BaseAddress!) { Scheme = "ws", Path = context.Request.Path, Query = context.Request.QueryString.Value?.TrimStart('?') }.Uri;
            await upstream.ConnectAsync(uri, _stop.Token);
            using var downstream = await context.WebSockets.AcceptWebSocketAsync();
            using var linked = CancellationTokenSource.CreateLinkedTokenSource(_stop.Token);
            var forward = PumpAsync(upstream, downstream, linked.Token);
            var reverse = PumpAsync(downstream, upstream, linked.Token);
            await Task.WhenAny(forward, reverse); linked.Cancel();
            try { await Task.WhenAll(forward, reverse); } catch (Exception error) when (error is OperationCanceledException or WebSocketException) { }
        }
        private static async Task PumpAsync(WebSocket source, WebSocket destination, CancellationToken ct)
        {
            var buffer = new byte[65536];
            while (source.State == WebSocketState.Open && destination.State == WebSocketState.Open)
            {
                var read = await source.ReceiveAsync(new ArraySegment<byte>(buffer), ct);
                if (read.MessageType == WebSocketMessageType.Close) break;
                await destination.SendAsync(new ArraySegment<byte>(buffer, 0, read.Count), read.MessageType, read.EndOfMessage, ct);
            }
        }
        private static string Hash(byte[] value) => Convert.ToHexStringLower(SHA256.HashData(value));
        public async ValueTask DisposeAsync()
        {
            _stop.Cancel(); await _listener.StopAsync(); _listener.Dispose();
            _backend.Dispose(); _stop.Dispose();
        }
    }
}
