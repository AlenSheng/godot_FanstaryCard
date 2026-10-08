using System.Diagnostics;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Tests.Persistence;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    [Theory(Skip = "Requires an owned local PostgreSQL database and A3GAME_GODOT_EXECUTABLE.", SkipUnless = nameof(HasRealClientDatabase))]
    [InlineData("cycles-middle-response-loss")]
    [InlineData("cycles-middle-uncommitted-loss")]
    [InlineData("stop-before-commit")]
    [InlineData("stop-after-commit")]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_load_runner_counts_three_games_once_and_STOP_during_ACK_never_completes(string mode)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        // This outer fixture deadline includes three real 30s matchmaker waits.
        // Original client 60s match/240s game/22s cleanup and server limits stay unchanged.
        using var deadline = Deadline(480);
        var ct = deadline.Token;
        var deviceId = "ack-cycle-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create();
        var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "AckCycle", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var equipmentId = await database.InsertWornFeetAsync(player.UserId, HeroClass.Mage, ct);
        var port = ReservePort();
        using var client = Client(port, token);
        await using var host = FullHost.Start(database.ConnectionString, port, "ack-cycle-" + mode);
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        var fixture = CreateAckClientFixture("runner-" + mode);
        foreach (var relative in new[] { "tests/gameplay_load_client.gd", "tests/pr13_ack_stop_cycles.gd" })
            CopyFixtureFile(Path.Combine(RepositoryRoot(), "client"), fixture, Path.Combine(RepositoryRoot(), "client", relative));
        var originalFiles = Directory.EnumerateFiles(fixture, "*", SearchOption.AllDirectories)
            .Where(path => !path.EndsWith("source-manifest.json", StringComparison.Ordinal))
            .Order(StringComparer.Ordinal).Select(path => new { path = Path.GetRelativePath(fixture, path), bytes = new FileInfo(path).Length,
                sha256 = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(path))) });
        File.WriteAllText(Path.Combine(fixture, "runner-source-manifest.json"), JsonSerializer.Serialize(originalFiles));
        await using var proxy = new AckFaultProxy(port, mode, Path.Combine(fixture, "STOP"));
        try { await RunCycleGodotAsync(fixture, proxy.Port, deviceId, mode, ct); }
        finally
        {
            Record("ACK-CYCLE-attempts-" + mode, new { mode, attempts = proxy.Attempts.ToArray(), errors = proxy.Errors.ToArray(), fixture });
            foreach (var directory in Directory.EnumerateDirectories(fixture)
                .Where(path => Path.GetFileName(path) is ".godot" or "assets" || Path.GetFileName(path).StartsWith("user-", StringComparison.Ordinal)))
                Directory.Delete(directory, recursive: true);
        }
        Assert.Empty(proxy.Errors);
        var cycles = mode.StartsWith("cycles-middle-", StringComparison.Ordinal);
        var expectedGames = cycles ? 3 : 1;
        using var accounting = JsonDocument.Parse(File.ReadAllText(Path.Combine(fixture, "load-result.json.accounting.json")));
        var entered = accounting.RootElement.GetProperty("entered_matches").EnumerateArray()
            .Select(value => Guid.Parse(value.GetString()!).ToString("D")).Order(StringComparer.Ordinal).ToArray();
        var persisted = await database.ScalarAsync<string>(
            "SELECT string_agg(match_id::text,',' ORDER BY match_id) FROM match_settlements WHERE player_id=$1 AND acknowledged_at IS NOT NULL", player.UserId);
        Assert.Equal(string.Join(',', entered), persisted);
        Assert.Equal(expectedGames, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1", player.UserId));
        Assert.Equal(expectedGames, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1 AND acknowledged_at IS NOT NULL", player.UserId));
        Assert.Equal(expectedGames, await database.ScalarAsync<long>("SELECT count(DISTINCT match_id) FROM match_settlements WHERE player_id=$1", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1 AND status IN ('Active','Queued','Matched')", player.UserId));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE owner_id=$1 AND location IN ('PreparationLocked','InMatchEquipped','InMatchBackpack')", player.UserId));
        var attempts = proxy.Attempts.ToArray();
        Assert.Equal(cycles ? 4 : 1, attempts.Length);
        Assert.All(attempts.Where(attempt => attempt.Forwarded), attempt => Assert.Equal(200, attempt.BackendStatus));
        if (cycles)
        {
            Assert.True(attempts[1].Dropped); Assert.False(attempts[2].Dropped);
            Assert.Equal(attempts[1].KeySha256, attempts[2].KeySha256);
            Assert.Equal(3, attempts.Select(attempt => attempt.KeySha256).Distinct().Count());
            Assert.Equal(mode == "cycles-middle-response-loss", attempts[1].Forwarded);
            Assert.All(attempts.Where(attempt => attempt != attempts[1]), attempt => Assert.True(attempt.Forwarded));
            if (attempts[1].Forwarded) Assert.Equal(attempts[1].ResponseSha256, attempts[2].ResponseSha256);
            else Assert.Null(attempts[1].BackendStatus);
        }
        else Assert.All(attempts, attempt => Assert.True(attempt.Forwarded));
        Record("ACK-CYCLE-" + mode, new { mode, host.ProcessId, playerId = player.UserId, equipmentId, expectedGames, entered, persisted,
            equipmentLocation = await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId),
            partition = accounting.RootElement.GetProperty("partition").Clone(), attempts,
            expectedCompletions = cycles ? 3 : 0,
            canonical = "LOAD-05.4-T03 / PR13-A03.3-T01,T02 (STOP await support; no dedicated canonical STOP-ACK case)",
            profile = "OFFLINE+POSTGRES; actual production runner/preparation/queue/ticket WS/READY/legal terminal/ACK; additional legal extract/abandon driver; three full gameplay routes/LIVE/RENDER/Boss not exercised" });
    }

    private static async Task RunCycleGodotAsync(string fixture, int proxyPort, string deviceId, string mode, CancellationToken ct)
    {
        var reportPath = Path.Combine(fixture, "load-result.json");
        foreach (var import in new[] { true, false })
        {
            var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("A3GAME_GODOT_EXECUTABLE")!)
            { WorkingDirectory = fixture, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var argument in new[] { "--headless", "--max-fps", "60", "--path", fixture }) start.ArgumentList.Add(argument);
            if (import) foreach (var argument in new[] { "--editor", "--import", "--quit" }) start.ArgumentList.Add(argument);
            else { start.ArgumentList.Add("--script"); start.ArgumentList.Add("res://tests/pr13_ack_stop_cycles.gd"); }
            ConfigureOwnedProcessEnvironment(start, fixture);
            foreach (var name in new[] { "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME" })
            { var directory = Path.Combine(fixture, "user-" + name.ToLowerInvariant()); Directory.CreateDirectory(directory); start.Environment[name] = directory; }
            start.Environment["FANTASYCARD_SERVER_URL"] = $"http://127.0.0.1:{proxyPort}";
            start.Environment["FANTASYCARD_LOAD_RUN_ID"] = "owned-ack-cycle-fault";
            start.Environment["FANTASYCARD_LOAD_CLIENT_ID"] = mode;
            start.Environment["FANTASYCARD_LOAD_PROCESS_EPOCH"] = "1";
            start.Environment["FANTASYCARD_LOAD_MAX_CYCLES"] = mode.StartsWith("cycles-middle-", StringComparison.Ordinal) ? "3" : "1";
            start.Environment["FANTASYCARD_LOAD_REPORT"] = reportPath;
            start.Environment["FANTASYCARD_LOAD_STOP_FILE"] = Path.Combine(fixture, "STOP");
            start.Environment["FANTASYCARD_LOAD_PROFILE"] = "cyclic-gameplay";
            start.Environment["PR13_ACK_FAULT_MODE"] = mode;
            start.Environment["PR13_ACK_DEVICE_ID"] = deviceId;
            using var process = Process.Start(start)!;
            var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None); var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
            try { await process.WaitForExitAsync(ct); }
            finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
            var output = await stdout + "\n" + await stderr;
            File.WriteAllText(Path.Combine(fixture, import ? "runner-import.log" : "runner-client.log"), output);
            Record("ack-runner-process-stop", new { mode, import, process.Id, process.ExitCode, fixture });
            Assert.Equal(0, process.ExitCode); Assert.DoesNotContain("SCRIPT ERROR", output); Assert.DoesNotContain("Parse Error", output);
            if (import) File.AppendAllText(Path.Combine(fixture, "project.godot"), "\n[autoload]\nGame=\"*res://state/game_store.gd\"\n");
        }
        using var accounting = JsonDocument.Parse(File.ReadAllText(reportPath + ".accounting.json"));
        Assert.True(accounting.RootElement.GetProperty("ok").GetBoolean(), accounting.RootElement.ToString());
    }
}
