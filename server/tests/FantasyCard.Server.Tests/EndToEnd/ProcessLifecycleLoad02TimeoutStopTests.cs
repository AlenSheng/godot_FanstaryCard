using System.Diagnostics;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Tests.Persistence;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Theory(Skip = "Requires owned local PostgreSQL and A3GAME_GODOT_EXECUTABLE.", SkipUnless = nameof(HasRealClientDatabase))]
    [InlineData("timeout-before-stop", "LOAD-02.2-T01")]
    [InlineData("normal-wait-stop", "LOAD-02.2-T02")]
    [InlineData("committed-unknown-stop", "LOAD-02.2-T03")]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_LOAD02_timeout_STOP_preserves_original_business_truth(string mode, string caseId)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(180); var ct = deadline.Token;
        var deviceId = "load02-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create(); var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "Load02", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var equipmentId = await database.InsertWornFeetAsync(player.UserId, HeroClass.Mage, ct);
        var before = await Load02AssetsAsync(database, player.UserId, equipmentId);
        var port = ReservePort(); using var client = Client(port, token);
        await using var host = FullHost.Start(database.ConnectionString, port, "load02-" + mode);
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        var fixture = CreateAckClientFixture("load02-" + mode);
        var source = Path.Combine(RepositoryRoot(), "client");
        foreach (var relative in new[] { "tests/gameplay_load_client.gd", "tests/pr13_load02_timeout_stop.gd" })
            CopyFixtureFile(source, fixture, Path.Combine(source, relative));
        var report = Path.Combine(fixture, "load-result.json");
        var files = Directory.EnumerateFiles(fixture, "*", SearchOption.AllDirectories).Order(StringComparer.Ordinal)
            .Select(path => new { path = Path.GetRelativePath(fixture, path), bytes = new FileInfo(path).Length,
                sha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path))) }).ToArray();
        File.WriteAllText(Path.Combine(fixture, "load02-source-manifest.json"), JsonSerializer.Serialize(files));
        await using var relay = new Load02Relay(port, mode, report);
        try
        {
            await RunLoad02ProcessAsync(fixture, relay.Port, deviceId, mode, import: true, ct);
            var run = RunLoad02ProcessAsync(fixture, relay.Port, deviceId, mode, import: false, ct);
            try
            {
                var gateOrExit = await Task.WhenAny(relay.Gate, run).WaitAsync(ct);
                Assert.True(gateOrExit == relay.Gate, "Original runner exited before the required real gate. " + fixture);
                await relay.Gate.WaitAsync(ct);
                var atGate = await Load02AssetsAsync(database, player.UserId, equipmentId);
                Record(caseId + "-gate", new { mode, host.ProcessId, playerId = player.UserId, equipmentId, fixture,
                    before, atGate, relay.Authority, requests = relay.Requests.ToArray(), monotonicTick = Stopwatch.GetTimestamp() });
                Assert.Equal(mode == "committed-unknown-stop" ? 1L : 0L,
                    await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1 AND acknowledged_at IS NOT NULL", player.UserId));
                var stopTick = Stopwatch.GetTimestamp();
                await File.WriteAllTextAsync(Path.Combine(fixture, "STOP"), "Owned LOAD-02.2 coordinator STOP at real request gate.", ct);
                await WaitAsync(() => Task.FromResult(File.Exists(report + ".stop-observed.json")), ct);
                using var observed = JsonDocument.Parse(await File.ReadAllTextAsync(report + ".stop-observed.json", ct));
                var snapshot = observed.RootElement;
                Record(caseId + "-STOP", new { mode, stopTick, observed = snapshot.Clone(), atGate, relay.Authority });
                Assert.True(snapshot.GetProperty("stop_requested").GetBoolean());
                Assert.True(snapshot.GetProperty("scenario_started").GetBoolean());
                Assert.Equal(0, snapshot.GetProperty("partition").GetProperty("completed").GetInt32());
                if (mode == "timeout-before-stop")
                {
                    using var failed = JsonDocument.Parse(await File.ReadAllTextAsync(report + ".first-failure.json", ct));
                    Assert.True(failed.RootElement.GetProperty("monotonic_ms").GetInt64() <= snapshot.GetProperty("monotonic_ms").GetInt64());
                    Assert.Contains(failed.RootElement.GetProperty("checks").EnumerateArray(), entry => entry.GetProperty("name").GetString() == "create_free_preparation" && !entry.GetProperty("passed").GetBoolean());
                    Assert.Equal(1, snapshot.GetProperty("partition").GetProperty("failed").GetInt32());
                    Assert.Equal(0, snapshot.GetProperty("partition").GetProperty("cancelled").GetInt32());
                    Assert.NotEmpty(snapshot.GetProperty("errors").EnumerateArray());
                }
                else
                {
                    Assert.True(snapshot.GetProperty("busy").GetBoolean());
                    Assert.NotEmpty(snapshot.GetProperty("pending_ack").GetString()!);
                    Assert.Equal("settlement", snapshot.GetProperty("stage").GetString());
                    Assert.All(snapshot.GetProperty("checks").EnumerateArray(), entry => Assert.True(entry.GetProperty("passed").GetBoolean()));
                    Assert.Equal(1, snapshot.GetProperty("partition").GetProperty("pending").GetInt32());
                    Assert.Equal(0, snapshot.GetProperty("partition").GetProperty("failed").GetInt32());
                    Assert.Equal(0, snapshot.GetProperty("partition").GetProperty("cancelled").GetInt32());
                    if (mode == "committed-unknown-stop")
                    {
                        var authority = JsonSerializer.SerializeToElement(relay.Authority);
                        Assert.Equal(JsonValueKind.Null, authority.GetProperty("activePreparation").ValueKind);
                        Assert.Equal(JsonValueKind.Null, authority.GetProperty("unfinishedMatch").ValueKind);
                        Assert.Equal(JsonValueKind.Null, authority.GetProperty("unfinishedSettlement").ValueKind);
                        Assert.NotEmpty(authority.GetProperty("ConfigVersion").GetString()!);
                    }
                }
                relay.Release(); await run;
            }
            finally { relay.Release(); if (!run.IsCompleted) { deadline.Cancel(); try { await run; } catch (OperationCanceledException) { } } }
            using var accounting = JsonDocument.Parse(await File.ReadAllTextAsync(report + ".accounting.json", ct));
            using var original = JsonDocument.Parse(await File.ReadAllTextAsync(report, ct));
            using var stopObserved = JsonDocument.Parse(await File.ReadAllTextAsync(report + ".stop-observed.json", ct));
            var final = accounting.RootElement; var partition = final.GetProperty("partition");
            Record(caseId + "-original-final", new { mode, original = original.RootElement.Clone(), accounting = final.Clone() });
            Assert.Equal(mode == "timeout-before-stop" ? "failed" : "cancelled", original.RootElement.GetProperty("outcome").GetString());
            if (mode == "timeout-before-stop")
            {
                Assert.Contains(original.RootElement.GetProperty("checks").EnumerateArray(), entry => entry.GetProperty("name").GetString() == "create_free_preparation" && !entry.GetProperty("passed").GetBoolean());
                Assert.NotEmpty(original.RootElement.GetProperty("errors").EnumerateArray());
            }
            else if (mode == "normal-wait-stop") Assert.Empty(original.RootElement.GetProperty("errors").EnumerateArray());
            foreach (var name in new[] { "run_id", "client_id", "process_epoch", "cycle_id", "session_generation", "room_context_epoch" })
                Assert.Equal(stopObserved.RootElement.GetProperty(name).ToString(), final.GetProperty(name).ToString());
            Assert.Equal(1, partition.GetProperty("started").GetInt32());
            Assert.Equal(0, partition.GetProperty("completed").GetInt32());
            Assert.Equal(mode == "timeout-before-stop" ? 1 : 0, partition.GetProperty("failed").GetInt32());
            Assert.Equal(mode == "timeout-before-stop" ? 0 : 1, partition.GetProperty("cancelled").GetInt32());
            Assert.Equal(0, partition.GetProperty("pending").GetInt32()); Assert.Equal(0, partition.GetProperty("incomplete").GetInt32());
            Assert.Empty(final.GetProperty("completed_events").EnumerateArray());
            Assert.Equal("Passed", final.GetProperty("cleanup").GetProperty("state").GetString());
            var after = await Load02AssetsAsync(database, player.UserId, equipmentId);
            var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
            Assert.Null(bootstrap.ActivePreparation); Assert.Null(bootstrap.UnfinishedMatch); Assert.Null(bootstrap.UnfinishedSettlement);
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1 AND status IN ('Active','Queued','Matched')", player.UserId));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location IN ('PreparationLocked','InMatchEquipped','InMatchBackpack')", player.UserId));
            if (mode == "timeout-before-stop") Assert.Equal(before.ToString(), after.ToString());
            else
            {
                Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1", player.UserId));
                Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1 AND acknowledged_at IS NOT NULL", player.UserId));
                Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM (SELECT currency,count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit' GROUP BY currency HAVING count(*)>1) x", player.UserId));
                Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason IN ('settlement.extract','settlement.death')", equipmentId));
            }
            // Actual next entry and cancel prove the account route and owned asset
            // reservations are reusable; the business cycle under test is over.
            var loadout = Wire.LoadoutResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/loadouts/Mage", null, ct));
            var nextRequest = new Wire.CreatePreparationRequest { HeroClass = "Mage", DeckVersion = bootstrap.Decks.First(deck => deck.HeroClass == "Mage").Version, BackpackTier = "Free", Difficulty = "Standard" };
            nextRequest.EquipmentIds.Add(loadout.EquipmentIds);
            var next = Wire.PreparationResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post, "/api/v1/preparations", nextRequest, ct, "load02-next-prepare"));
            using var cancelRequest = new HttpRequestMessage(HttpMethod.Delete, "/api/v1/preparations/" + next.PreparationId);
            cancelRequest.Headers.Add("Idempotency-Key", "load02-next-cancel");
            using (var cancelled = await client.SendAsync(cancelRequest, ct))
            {
                Assert.Equal(HttpStatusCode.NoContent, cancelled.StatusCode);
                Assert.Empty(await cancelled.Content.ReadAsByteArrayAsync(ct));
            }
            var finalBootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
            Assert.Null(finalBootstrap.ActivePreparation); Assert.Null(finalBootstrap.UnfinishedMatch); Assert.Null(finalBootstrap.UnfinishedSettlement);
            var preparations = relay.Requests.Where(entry => entry.Method == "POST" && entry.Path == "/api/v1/preparations").ToArray();
            var acknowledgements = relay.Requests.Where(entry => entry.Method == "POST" && entry.Path.EndsWith("/acknowledge", StringComparison.Ordinal) && entry.Forwarded).ToArray();
            if (mode == "timeout-before-stop")
            {
                Assert.Equal(3, preparations.Length); Assert.All(preparations, entry => Assert.False(entry.Forwarded));
                Assert.Single(preparations.Select(entry => entry.KeySha256).Distinct());
                var logical = original.RootElement.GetProperty("operations").EnumerateArray().Single(entry => entry.GetProperty("path").GetString() == "/api/v1/preparations" && entry.GetProperty("method").GetInt32() == 2);
                Assert.False(logical.GetProperty("ok").GetBoolean()); Assert.InRange(logical.GetProperty("duration_ms").GetInt64(), 29500, 34000);
                var timeouts = original.RootElement.GetProperty("telemetry").EnumerateArray().Where(entry => entry.GetProperty("event_type").GetString() == "http_attempt" && entry.GetProperty("route").GetString() == "/api/v1/preparations" && entry.GetProperty("result").GetString() == "timeout").ToArray();
                Assert.Equal(3, timeouts.Length); Assert.InRange(timeouts[0].GetProperty("duration_ms").GetInt64(), 9800, 11500);
            }
            else
            {
                Assert.Equal(mode == "committed-unknown-stop" ? 3 : 1, acknowledgements.Length);
                Assert.All(acknowledgements, entry => Assert.Equal(200, entry.BackendStatus));
                Assert.Single(acknowledgements.Select(entry => entry.KeySha256).Distinct());
                Assert.Single(acknowledgements.Select(entry => entry.BodySha256).Distinct());
                if (mode == "committed-unknown-stop") Assert.Single(acknowledgements.Select(entry => entry.ResponseSha256).Distinct());
            }
            Assert.Empty(relay.Errors);
            Record(caseId, new { status = "Passed", mode, host.ProcessId, playerId = player.UserId, equipmentId, fixture,
                before, after, finalAssets = await Load02AssetsAsync(database, player.UserId, equipmentId),
                partition = partition.Clone(), authority = relay.Authority, bootstrap.ConfigVersion,
                nextPreparationId = next.PreparationId, nextPrepareCancelVerified = true,
                profiles = "OFFLINE+POSTGRES", algorithm_version = "load02-observer-v1",
                productionTimeoutsMs = new { attempt = 10000, logical = 30000, cleanup = 22000 },
                limitations = "legal extraction/abandon driver; not full Boss or three routes; S6 parent independent review pending" });
        }
        finally
        {
            relay.Release();
            Record(caseId + "-relay-finally", new { mode, requests = relay.Requests.ToArray(), errors = relay.Errors.ToArray(), relay.Authority, fixture });
            foreach (var directory in Directory.EnumerateDirectories(fixture).Where(path => Path.GetFileName(path) is ".godot" or "assets" || Path.GetFileName(path).StartsWith("user-", StringComparison.Ordinal)))
                Directory.Delete(directory, recursive: true);
        }
    }

    private static async Task<JsonElement> Load02AssetsAsync(PostgresTestSchema database, Guid playerId, Guid equipmentId)
    {
        var json = await database.ScalarAsync<string>("""
            SELECT json_build_object(
              'wallet',(SELECT row_to_json(w) FROM player_wallets w WHERE player_id=$1),
              'consumables',(SELECT row_to_json(c) FROM player_consumables c WHERE player_id=$1),
              'equipment',(SELECT row_to_json(e) FROM equipments e WHERE instance_id=$2),
              'settlements',(SELECT coalesce(json_agg(s ORDER BY settlement_id),'[]'::json) FROM match_settlements s WHERE player_id=$1),
              'holds',(SELECT coalesce(json_agg(h ORDER BY hold_id),'[]'::json) FROM settlement_asset_holds h JOIN match_settlements s ON s.settlement_id=h.settlement_id WHERE s.player_id=$1),
              'ledger',(SELECT coalesce(json_agg(l ORDER BY ledger_id),'[]'::json) FROM economy_ledger l WHERE player_id=$1),
              'movements',(SELECT coalesce(json_agg(m ORDER BY movement_id),'[]'::json) FROM inventory_movements m WHERE item_id=$2),
              'preparations',(SELECT coalesce(json_agg(p ORDER BY preparation_id),'[]'::json) FROM preparations p WHERE player_id=$1),
              'tickets',(SELECT coalesce(json_agg(t ORDER BY ticket_id),'[]'::json) FROM match_tickets t WHERE player_id=$1))::text
            """, playerId, equipmentId);
        using var document = JsonDocument.Parse(json); return document.RootElement.Clone();
    }

    private static async Task RunLoad02ProcessAsync(string fixture, int port, string deviceId, string mode, bool import, CancellationToken ct)
    {
        var report = Path.Combine(fixture, "load-result.json");
        var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("A3GAME_GODOT_EXECUTABLE")!)
        { WorkingDirectory = fixture, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
        foreach (var argument in new[] { "--headless", "--max-fps", "60", "--path", fixture }) start.ArgumentList.Add(argument);
        if (import) foreach (var argument in new[] { "--editor", "--import", "--quit" }) start.ArgumentList.Add(argument);
        else { start.ArgumentList.Add("--script"); start.ArgumentList.Add("res://tests/pr13_load02_timeout_stop.gd"); }
        start.Environment.Clear();
        foreach (var name in new[] { "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME" })
        { var directory = Path.Combine(fixture, "user-" + name.ToLowerInvariant()); Directory.CreateDirectory(directory); start.Environment[name] = directory; }
        start.Environment["FANTASYCARD_SERVER_URL"] = $"http://127.0.0.1:{port}";
        start.Environment["FANTASYCARD_LOAD_RUN_ID"] = "owned-load02-" + Path.GetFileName(fixture);
        start.Environment["FANTASYCARD_LOAD_CLIENT_ID"] = mode;
        start.Environment["FANTASYCARD_LOAD_PROCESS_EPOCH"] = "1";
        start.Environment["FANTASYCARD_LOAD_MAX_CYCLES"] = "1";
        start.Environment["FANTASYCARD_LOAD_REPORT"] = report;
        start.Environment["FANTASYCARD_LOAD_STOP_FILE"] = Path.Combine(fixture, "STOP");
        start.Environment["FANTASYCARD_LOAD_PROFILE"] = "cyclic-gameplay";
        start.Environment["PR13_LOAD02_MODE"] = mode; start.Environment["PR13_LOAD02_DEVICE_ID"] = deviceId;
        using var process = Process.Start(start)!;
        var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None); var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
        try { await process.WaitForExitAsync(ct); }
        finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
        var output = await stdout + "\n" + await stderr;
        await File.WriteAllTextAsync(Path.Combine(fixture, import ? "import.log" : "client.log"), output, CancellationToken.None);
        Record("LOAD02-process-exit", new { mode, import, process.Id, process.ExitCode, fixture });
        Assert.Equal(!import && mode == "timeout-before-stop" ? 1 : 0, process.ExitCode);
        Assert.DoesNotContain("SCRIPT ERROR", output); Assert.DoesNotContain("Parse Error", output);
        if (import) File.AppendAllText(Path.Combine(fixture, "project.godot"), "\n[autoload]\nGame=\"*res://state/game_store.gd\"\n");
    }
}
