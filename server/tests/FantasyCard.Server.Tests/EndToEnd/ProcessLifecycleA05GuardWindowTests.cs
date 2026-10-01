using System.Net;
using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private static string? A05RuntimeSourceSha => Environment.GetEnvironmentVariable("FANTASYCARD_PROCESS_SOURCE_SHA") ?? Environment.GetEnvironmentVariable("GITHUB_SHA");

    [Theory(Skip = "Requires owned local PostgreSQL and production Godot.", SkipUnless = nameof(HasRealClientDatabase))]
    [InlineData("ordinary", "success")]
    [InlineData("recovered", "uncommitted-loss")]
    [InlineData("recovered", "committed-loss")]
    [Trait("Category", "PostgresIntegration")]
    public async Task A05_guard_preserves_ordinary_context_and_authoritative_ACK_recovery(string context, string outcome)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(90); var ct = deadline.Token;
        var label = "guard-" + context + "-" + outcome;
        var deviceId = "a05-guard-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create(); var now = DateTimeOffset.UtcNow;
        var identity = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "A05Runtime", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var playerId = identity.UserId; var equipmentId = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var (matchId, room) = await SeedRoomAsync(database, [playerId], ct, equipmentId, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        var before = await A05AssetsAsync(database, playerId, equipmentId, ct);
        await A05AuditAsync(database, label + "-before", false, ct);
        var port = ReservePort(); using var client = Client(port, token);
        await using var first = FullHost.Start(database.ConnectionString, port, label + "-before");
        var host = first;
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        await using var relay = new A05GuardRelay(port, outcome, label);
        var fixture = CreateAckClientFixture(label);
        CopyFixtureFile(Path.Combine(RepositoryRoot(), "client"), fixture, Path.Combine(RepositoryRoot(), "client/tests/pr13_a05_guard_windows.gd"));
        var control = Path.Combine(fixture, "control"); Directory.CreateDirectory(control);
        var godot = RunA05GodotAsync(fixture, relay.Port, deviceId, matchId, control, "pr13_a05_guard_windows.gd", ct);
        try
        {
            await A05WaitFileAsync(control, "running", godot, ct);
            await using var terminalCheckpoint = context == "ordinary"
                ? await A05TerminalCheckpointGate.CreateAsync(database, playerId, label, ct)
                : null;
            await using var gate = await database.DataSource.OpenConnectionAsync(ct);
            await using var transaction = await gate.BeginTransactionAsync(ct);
            await using (var command = new NpgsqlCommand("SELECT gold FROM player_wallets WHERE player_id=$1 FOR UPDATE", gate, transaction))
            { command.Parameters.AddWithValue(playerId); await command.ExecuteScalarAsync(ct); }
            await A05ControlAsync(control, "extract", new { context, outcome }, ct);
            if (terminalCheckpoint is not null)
            {
                // A Pending wallet hold does not keep the room route registered.
                // Hold only the terminal checkpoint after the real completion
                // event, so the ordinary branch reads a genuine terminal snapshot
                // before settlement observation can release its route.
                await terminalCheckpoint.WaitUntilBlockedAsync(ct);
                Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds"));
                await A05ControlAsync(control, "ordinary-pending", new { actual = "terminal checkpoint gated; genuine room route still registered" }, ct);
                await A05WaitFileAsync(control, "context-ready", godot, ct);
                await terminalCheckpoint.ReleaseAsync();
            }
            await WaitAsync(async () => await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'") == 4, ct);
            Assert.Equal(before, await A05AssetsAsync(database, playerId, equipmentId, ct));
            if (context == "recovered")
            {
                relay.BeginRestart(); await first.KillAsync();
                host = FullHost.Start(database.ConnectionString, port, label + "-after");
                await host.WaitForHealthAsync(client, "/health/live", HttpStatusCode.OK, ct);
                relay.EndRestart();
                await A05ControlAsync(control, "restarted", new { host.ProcessId }, ct);
            }
            if (context == "recovered") await A05WaitFileAsync(control, "context-ready", godot, ct);
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            if (context == "ordinary")
            {
                await A05ControlAsync(control, "pending-established", new { actual_pending_holds = 4, wallet_committed = false }, ct);
                await A05WaitFileAsync(control, "pending-verified", godot, ct);
                Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
                Assert.Equal(before, await A05AssetsAsync(database, playerId, equipmentId, ct));
                var path = Path.Combine(control, "pending-verified.json");
                Record("A05-ordinary-four-pending-client-barrier", new { context, outcome, matchId,
                    actualPendingHolds = 4, walletCommitted = false, path, phaseSha256 = A05Sha(await File.ReadAllBytesAsync(path, ct)) });
            }
            await transaction.CommitAsync(ct);
            await Task.WhenAll(relay.SettlementGetHeld.Task, relay.PollHeld.Task).WaitAsync(ct);
            relay.ReleaseSettlementGet();
            await A05ControlAsync(control, "get-released", new { actual = "unchanged authority GET released; ready poll still held" }, ct);
            await relay.AckHeld.Task.WaitAsync(ct);
            await A05ControlAsync(control, "ack-held", new { actual = "real production ACK before backend forwarding" }, ct);
            await A05WaitFileAsync(control, "ack-cleared", godot, ct);
            relay.ReleasePoll();
            await A05ControlAsync(control, "poll-released", new { actual = "old genuine ready Bootstrap returned during ACK await" }, ct);
            await A05WaitFileAsync(control, "poll-returned-during-ack", godot, ct);
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
            relay.ReleaseAck();
            await A05ControlAsync(control, "ack-released", new { actual = "owned transport gate released" }, ct);
            if (outcome == "uncommitted-loss")
            {
                await A05WaitFileAsync(control, "ack-failed-restored", godot, ct);
                Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
                Assert.Equal(23L, (await A05AssetsAsync(database, playerId, equipmentId, ct)).Gold);
                relay.ReleaseFault();
                await A05ControlAsync(control, "ack-retry", new { actual = "no DB mutation; allow the real retry" }, ct);
            }
            await godot;
            Assert.Empty(relay.Errors);
            var attempts = relay.Attempts.ToArray();
            Assert.Equal(outcome == "success" ? 1 : outcome == "committed-loss" ? 3 : 4, attempts.Length);
            Assert.All(attempts, value => Assert.Equal(attempts[0].BodySha256, value.BodySha256));
            var firstAttempts = attempts.Take(outcome == "success" ? 1 : 3).ToArray();
            Assert.Single(firstAttempts.Select(value => value.KeySha256).Distinct());
            if (outcome == "uncommitted-loss")
            {
                Assert.All(firstAttempts, value => Assert.False(value.Forwarded));
                Assert.True(attempts[3].Forwarded); Assert.False(attempts[3].Dropped);
                Assert.NotEqual(attempts[0].KeySha256, attempts[3].KeySha256);
                Assert.Contains(relay.Bootstraps, value => value.AfterAckAttempts >= 3 && value.UnfinishedSettlementId is not null);
            }
            else
            {
                Assert.All(attempts, value => { Assert.True(value.Forwarded); Assert.Equal(200, value.BackendStatus); });
                Assert.Single(attempts.Select(value => value.ResponseSha256).Distinct());
                Assert.Contains(relay.Bootstraps, value => value.AfterAckAttempts >= attempts.Length && value.UnfinishedSettlementId is null);
            }
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Committed'"));
            var after = await A05AssetsAsync(database, playerId, equipmentId, ct);
            Assert.Equal(before.Gold + 23, after.Gold); Assert.Equal(before.Potions + 2, after.Potions);
            Assert.Equal(before.Owner, after.Owner); Assert.Equal("Equipped", after.Location);
            Assert.Equal(1L, after.GoldLedger); Assert.Equal(1L, after.Movements);
            await A05AuditAsync(database, label + "-after", true, ct);
            Record("A05-guard-window-passed", new { context, outcome, sourceSha = A05RuntimeSourceSha, matchId, room.RoomId,
                playerId, equipmentId, before, after, attempts, bootstraps = relay.Bootstraps.ToArray(),
                pids = ReferenceEquals(host, first) ? new[] { first.ProcessId } : new[] { first.ProcessId, host.ProcessId },
                profiles = A05Profiles, acceptedBy = (string?)null, scope = "actual Program, production Game, unchanged real PB response gates; owned audit" });
        }
        finally
        {
            relay.ReleaseSettlementGet(); relay.ReleasePoll(); relay.ReleaseAck(); relay.ReleaseFault();
            if (!godot.IsCompleted) { try { await godot; } catch when (ct.IsCancellationRequested) { } }
            if (!ReferenceEquals(host, first)) await host.DisposeAsync();
            A05CleanFixture(fixture);
            Record("A05-guard-relay-cleanup", new { context, outcome, errors = relay.Errors.ToArray(),
                expectedRestartTransportFailures = relay.ExpectedRestartTransportFailures.ToArray() });
        }
    }
}
