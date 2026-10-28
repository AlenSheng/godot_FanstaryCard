using System.Diagnostics;
using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    public static bool HasOwnedRollbackFixture => HasPrivateDatabase &&
        File.Exists(Environment.GetEnvironmentVariable("FANTASYCARD_PROCESS_PREVIOUS_SERVER_DLL")) &&
        (!string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_DOCKER_CONTAINER")) ||
         !string.IsNullOrWhiteSpace(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_NATIVE_PG_OWNERSHIP")));

    [Fact(Skip = "Requires an owned isolated PG fixture and an immutable previous local server binary.", SkipUnless = nameof(HasOwnedRollbackFixture))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_code_rollback_and_native_backup_restore_preserve_once_only_assets()
    {
        using var deadline = Deadline(180); var ct = deadline.Token;
        var oldDll = Path.GetFullPath(Environment.GetEnvironmentVariable("FANTASYCARD_PROCESS_PREVIOUS_SERVER_DLL")!);
        var ownedRoot = Path.GetFullPath(Path.Combine(RepositoryRoot(), "outputs", "pr13-local-20261008")) + Path.DirectorySeparatorChar;
        Assert.StartsWith(ownedRoot, oldDll, StringComparison.OrdinalIgnoreCase);
        var oldHash = Convert.ToHexStringLower(SHA256.HashData(await File.ReadAllBytesAsync(oldDll, ct)));
        Assert.Equal(Environment.GetEnvironmentVariable("FANTASYCARD_PROCESS_PREVIOUS_SERVER_SHA256"), oldHash);
        var container = Environment.GetEnvironmentVariable("FANTASYCARD_TEST_DOCKER_CONTAINER");
        var ownership = Environment.GetEnvironmentVariable("FANTASYCARD_TEST_NATIVE_PG_OWNERSHIP");
        Assert.NotEqual(string.IsNullOrWhiteSpace(container), string.IsNullOrWhiteSpace(ownership));
        NativeRollbackPostgres? native = null;
        string? containerId = null;
        if (!string.IsNullOrWhiteSpace(ownership))
            native = await NativeRollbackPostgres.VerifyAsync(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")!, ownership, ct);
        else
        {
            var inspected = await DockerTextAsync(["inspect", container!], ct);
            using var metadata = JsonDocument.Parse(inspected);
            var labels = metadata.RootElement[0].GetProperty("Config").GetProperty("Labels");
            Assert.Equal("disposable-local", labels.GetProperty("codex.scope").GetString());
            Assert.Equal("pr13-stages-20261008", labels.GetProperty("codex.task").GetString());
            containerId = metadata.RootElement[0].GetProperty("Id").GetString();
        }

        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var settings = new NpgsqlConnectionStringBuilder(db.ConnectionString);
        Assert.StartsWith("ready_stop_", settings.Database, StringComparison.Ordinal);
        Assert.StartsWith("fc_runtime_test_", settings.SearchPath, StringComparison.Ordinal);
        var player = await SeedPlayerAsync(db, "RollbackProof", ct);
        var equipment = await db.InsertWornFeetAsync(player.Id, HeroClass.Mage, ct);
        await SqlAsync(db, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipment);
        var gold = await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.Id);
        var (match, room) = await SeedRoomAsync(db, [player.Id], ct, equipment, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        var port = ReservePort(); using var client = Client(port, player.Token);
        long revision;
        await using (var current = FullHost.Start(db.ConnectionString, port, "rollback-current"))
        {
            await current.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            using var socket = await ConnectAsync(client, port, ct);
            var snapshot = await SnapshotAsync(socket, ct); Assert.Equal(match, snapshot.MatchId);
            revision = snapshot.RoomRevision; await current.KillAsync();
        }
        string receiptId;
        await using (var previous = FullHost.Start(db.ConnectionString, port, "rollback-preserved-previous", oldDll))
        {
            await previous.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            using var socket = await ConnectAsync(client, port, ct);
            var snapshot = await SnapshotAsync(socket, ct);
            Assert.Equal(match, snapshot.MatchId); Assert.Equal(room.RoomId, snapshot.RoomId); Assert.True(snapshot.RoomRevision >= revision);
            await ExtractAsync(socket, ct);
            await WaitAsync(async () => await db.ScalarAsync<long>(
                "SELECT count(*) FROM match_settlements s WHERE match_id=$1 AND NOT EXISTS (SELECT 1 FROM settlement_asset_holds h WHERE h.settlement_id=s.settlement_id AND h.state='Pending')", match) == 1, ct);
            var receipt = Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get,
                $"/api/v1/matches/{match:D}/settlement", null, ct)); receiptId = receipt.SettlementId;
            await CallAsync(client, HttpMethod.Post, $"/api/v1/settlements/{receiptId}/acknowledge", new Wire.Empty(), ct, "rollback-original-ack");
            Assert.Equal(gold + 23, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.Id));
            Assert.Equal(1L, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", player.Id));
        }
        Record("actual-code-rollback", new { oldServerSha256 = oldHash, match, receiptId,
            currentSnapshotRestoredByPreviousBinary = true, legalExtractionAfterRollback = true, originalAssetsOnce = true,
            scope = "only the declared current and retained 0cf43db binary/config pair; no production deployment or arbitrary older compatibility claim" });

        Directory.CreateDirectory(EvidenceDirectory);
        var dump = Path.GetFullPath(Path.Combine(EvidenceDirectory, "owned-rollback-backup.dump"));
        Assert.StartsWith(ownedRoot, dump, StringComparison.OrdinalIgnoreCase);
        if (native is null) await DumpAsync(container!, settings.Username!, settings.Database!, settings.SearchPath!, dump, ct);
        else await native.DumpAsync(settings.Database!, settings.SearchPath!, dump, ct);
        Assert.InRange(new FileInfo(dump).Length, 1, 64 * 1024 * 1024);
        var dumpHash = Convert.ToHexStringLower(SHA256.HashData(await File.ReadAllBytesAsync(dump, ct)));
        var restoredName = "ready_stop_" + Guid.NewGuid().ToString("N"); var created = false;
        try
        {
            if (native is null) await DockerTextAsync(["exec", container!, "createdb", "-U", settings.Username!, restoredName], ct);
            else await native.TextAsync("createdb", [restoredName], ct);
            created = true;
            if (native is null) await RestoreAsync(container!, settings.Username!, restoredName, dump, ct);
            else await native.RestoreAsync(restoredName, dump, ct);
            var restoredSettings = new NpgsqlConnectionStringBuilder(db.ConnectionString) { Database = restoredName };
            await using var restored = NpgsqlDataSource.Create(restoredSettings.ConnectionString);
            var repository = new SettlementRepository(restored, TimeProvider.System, metrics);
            var id = Guid.Parse(receiptId);
            Assert.Equal(match, (await repository.GetAsync(player.Id, id, ct)).MatchId);
            await repository.AcknowledgeAsync(player.Id, id, "rollback-original-ack", ct);
            await repository.AcknowledgeAsync(player.Id, id, "restored-ack-another-key", ct);
            Assert.Equal(0, await repository.CommitHoldsAsync(id, ct));
            await using var check = restored.CreateCommand("SELECT w.gold,e.owner_id,e.location,(SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'),(SELECT count(*) FROM settlement_asset_holds WHERE state='Pending') FROM player_wallets w JOIN equipments e ON e.owner_id=w.player_id WHERE w.player_id=$1 AND e.instance_id=$2");
            check.Parameters.AddWithValue(player.Id); check.Parameters.AddWithValue(equipment);
            await using var reader = await check.ExecuteReaderAsync(ct); Assert.True(await reader.ReadAsync(ct));
            Assert.Equal(gold + 23, reader.GetInt64(0)); Assert.Equal(player.Id, reader.GetGuid(1)); Assert.Equal("Equipped", reader.GetString(2));
            Assert.Equal(1L, reader.GetInt64(3)); Assert.Equal(0L, reader.GetInt64(4));
            Record("actual-native-backup-restore", new { containerId, nativePostmasterPid = native?.PostmasterPid, dumpSha256 = dumpHash, dumpBytes = new FileInfo(dump).Length,
                nativeTools = "pg_dump custom schema backup and pg_restore into a newly owned isolated database",
                originalBalance = gold + 23, restoredBalance = reader.GetInt64(0), committedLedgerRows = 1,
                repeatedAckAndHoldCommitDoNotCopyAssets = true, assetCorrection = false,
                scope = "same restored database scope, never combine original/clone balances or repair deleted historical ledgers" });
        }
        finally
        {
            if (created)
            {
                if (native is null) await DockerTextAsync(["exec", container!, "dropdb", "--force", "-U", settings.Username!, restoredName], CancellationToken.None);
                else await native.TextAsync("dropdb", ["--force", restoredName], CancellationToken.None);
            }
            Record("owned-restored-database-removed", new { created, removed = created, restoredName });
        }
    }

    private static ProcessStartInfo DockerStart(string[] arguments)
    {
        var start = new ProcessStartInfo("docker") { UseShellExecute = false, RedirectStandardOutput = true,
            RedirectStandardError = true, RedirectStandardInput = true, CreateNoWindow = true };
        foreach (var arg in arguments) start.ArgumentList.Add(arg);
        return start;
    }
    private static async Task<string> DockerTextAsync(string[] arguments, CancellationToken ct)
    {
        using var bounded = CancellationTokenSource.CreateLinkedTokenSource(ct);
        bounded.CancelAfter(TimeSpan.FromSeconds(30)); ct = bounded.Token;
        using var process = Process.Start(DockerStart(arguments))!;
        var output = process.StandardOutput.ReadToEndAsync(ct); var error = process.StandardError.ReadToEndAsync(ct);
        try { await process.WaitForExitAsync(ct); }
        finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
        Assert.Equal(0, process.ExitCode); await error; return await output;
    }
    private static async Task DumpAsync(string container, string user, string database, string schema, string path, CancellationToken ct)
    {
        using var process = Process.Start(DockerStart(["exec", container, "pg_dump", "-U", user, "-d", database,
            "--schema", schema, "--format=custom", "--no-owner", "--no-acl", "--lock-wait-timeout=10s"]))!;
        var error = process.StandardError.ReadToEndAsync(ct);
        try
        {
            await using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write);
            await process.StandardOutput.BaseStream.CopyToAsync(file, ct); await process.WaitForExitAsync(ct);
        }
        finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
        Assert.Equal(0, process.ExitCode); await error;
    }
    private static async Task RestoreAsync(string container, string user, string database, string path, CancellationToken ct)
    {
        using var process = Process.Start(DockerStart(["exec", "-i", container, "pg_restore", "-U", user, "-d", database,
            "--exit-on-error", "--no-owner", "--no-acl"]))!;
        var output = process.StandardOutput.ReadToEndAsync(ct); var error = process.StandardError.ReadToEndAsync(ct);
        try
        {
            await using var file = File.OpenRead(path); await file.CopyToAsync(process.StandardInput.BaseStream, ct);
            process.StandardInput.Close(); await process.WaitForExitAsync(ct);
        }
        finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
        Assert.Equal(0, process.ExitCode); await output; await error;
    }
}
