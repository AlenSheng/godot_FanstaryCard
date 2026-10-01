using System.Diagnostics;
using System.Net;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class ProcessLifecycleRecoveryTests
{
    private static readonly string[] A05PendingCanonical = ["PR13-A05.1-T03", "PR13-A05.3-T02"];
    private static readonly string[] A05Profiles = ["OFFLINE", "POSTGRES", "AUDIT"];
    private static readonly string[] A05HealthyCanonical = ["PR13-A05.2-T01", "PR13-A05.2-T02", "PR13-A05.2-T03", "PR13-A05.3-T03"];

    [Fact(Skip = "Requires owned local PostgreSQL and production Godot.", SkipUnless = nameof(HasRealClientDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task A05_healthy_teammate_old_room_and_new_room_survive_real_callbacks_and_OS_restart()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(180); var ct = deadline.Token;
        var deviceId = "a05-healthy-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create(); var now = DateTimeOffset.UtcNow;
        var identity = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "A05Runtime", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var playerId = identity.UserId; var teammate = await SeedPlayerAsync(database, "A05HealthyB", ct);
        var equipmentId = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var (formerMatch, initialRoom) = await SeedRoomAsync(database, [playerId, teammate.Id], ct, gold: 23, potions: 2);
        var initial = initialRoom.Capture();
        // The owned saved Running input gives only A its owned item. No item
        // identity is duplicated for B and no runtime snapshot is fabricated.
        var room = BattleRoom.Restore(initial with { Players = initial.Players.Select(player => player.PlayerId == playerId ? player with
        { WornArmor = [new(equipmentId.ToString("D"), ExplorationItemKind.Equipment, Equipment: new("Feet", "White", "Fire", null, "DrawInterval", 0), IsGenerated: false)] } : player).ToArray() },
            CombatCardCatalog.CreatePrototype(), 73);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        var before = await A05AssetsAsync(database, playerId, equipmentId, ct);
        await A05AuditAsync(database, "healthy-before", false, ct);
        var port = ReservePort(); using var client = Client(port, token); using var bClient = Client(port, teammate.Token);
        await using var relay = new A05CallbackRelay(port);
        var fixture = CreateAckClientFixture("a05-healthy");
        CopyFixtureFile(Path.Combine(RepositoryRoot(), "client"), fixture, Path.Combine(RepositoryRoot(), "client/tests/pr13_a05_healthy_old_room.gd"));
        var control = Path.Combine(fixture, "control"); Directory.CreateDirectory(control);
        FullHost? host = null; Task? godot = null; ClientWebSocket? bSocket = null;
        var nextPlayers = new List<(Guid Id, string Token)>(); var nextSockets = new List<ClientWebSocket>();
        var pids = new List<int>(); Guid? nextMatch = null; Guid? nextRoom = null;
        try
        {
            host = FullHost.Start(database.ConnectionString, port, "a05-healthy-before"); pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            bSocket = await ConnectAsync(bClient, port, ct);
            var bBefore = await SnapshotAsync(bSocket, ct);
            Assert.Equal(formerMatch, bBefore.MatchId); Assert.Equal("ActionBar", bBefore.Player.Phase);
            // Three real human accounts supply N immediately. The default
            // 30-second bot-fill and rate limits retain their original values.
            for (var index = 0; index < 3; index++)
            {
                using var anonymous = Client(port);
                var login = Wire.LocalSignInResponse.Parser.ParseFrom(await CallAsync(anonymous, HttpMethod.Post, "/api/v1/auth/local",
                    new Wire.LocalSignInRequest { DeviceId = "a05-cohort-" + Guid.NewGuid().ToString("N"), DisplayName = "A05 Next " + index }, ct));
                nextPlayers.Add((Guid.Parse(login.Player.UserId), login.AccessToken));
                using var nextClient = Client(port, login.AccessToken);
                var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(nextClient, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
                var request = new Wire.CreatePreparationRequest { HeroClass = "Mage", DeckVersion = bootstrap.Decks.First(value => value.HeroClass == "Mage").Version,
                    BackpackTier = "Free", Difficulty = "Standard" };
                request.EquipmentIds.Add(Wire.LoadoutResponse.Parser.ParseFrom(await CallAsync(nextClient, HttpMethod.Get, "/api/v1/loadouts/Mage", null, ct)).EquipmentIds);
                var preparation = Wire.PreparationResponse.Parser.ParseFrom(await CallAsync(nextClient, HttpMethod.Post, "/api/v1/preparations", request, ct));
                nextSockets.Add(await ConnectAsync(nextClient, port, ct));
                await CallAsync(nextClient, HttpMethod.Post, "/api/v1/matches/enqueue", new Wire.EnqueueMatchRequest { PreparationId = preparation.PreparationId }, ct);
            }
            godot = RunA05GodotAsync(fixture, relay.Port, deviceId, formerMatch, control, "pr13_a05_healthy_old_room.gd", ct);
            await A05WaitFileAsync(control, "running", godot, ct);
            await A05ControlAsync(control, "extract", new { formerMatch }, ct);
            var oldCallback = await relay.Held.Task.WaitAsync(ct);
            var oldReceipt = Wire.SettlementResponse.Parser.ParseFrom(oldCallback);
            Assert.Equal(formerMatch.ToString("D"), oldReceipt.MatchId);
            await A05WaitFileAsync(control, "acknowledged-M", godot, ct);
            var afterM = await A05AssetsAsync(database, playerId, equipmentId, ct);
            Assert.Equal(before.Gold + 23, afterM.Gold); Assert.Equal(before.Potions + 2, afterM.Potions);
            Assert.Equal("Equipped", afterM.Location); Assert.Equal(1L, afterM.GoldLedger); Assert.Equal(1L, afterM.Movements);
            await A05ControlAsync(control, "enqueue-N", new { previousReceiptId = oldReceipt.SettlementId }, ct);
            for (var index = 0; index < nextSockets.Count; index++)
            {
                var required = Assert.IsType<RoomReadyRequiredEventPayload>((await EventAsync(nextSockets[index], "room.ready_required", ct)).Payload);
                nextMatch ??= required.MatchId; nextRoom ??= required.RoomId;
                Assert.Equal(nextMatch, required.MatchId); Assert.Equal(4, required.RequiredPlayers);
                await CommandAsync(nextSockets[index], new("room.ready", "a05-next-ready-" + index, null, new RoomReadyCommandPayload()), ct, "room.ready_accepted");
            }
            await A05WaitFileAsync(control, "running-N", godot, ct);
            Assert.NotEqual(formerMatch, nextMatch!.Value);
            Assert.Equal("Running", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", formerMatch));
            Assert.Equal("Running", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", nextMatch.Value));
            var bDuringN = await SnapshotAsync(bSocket, ct);
            Assert.Equal(formerMatch, bDuringN.MatchId); Assert.Equal("ActionBar", bDuringN.Player.Phase); Assert.True(bDuringN.RoomRevision > bBefore.RoomRevision);
            relay.Release(); await relay.DuplicateReadyAsync(ct);
            await A05ControlAsync(control, "callbacks-released", new { previousReceiptId = oldReceipt.SettlementId }, ct);
            await A05WaitFileAsync(control, "callbacks-observed", godot, ct);
            Assert.Equal(afterM.Gold, (await A05AssetsAsync(database, playerId, equipmentId, ct)).Gold);
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1", playerId));
            Record("A05-healthy-M-and-N", new { formerMatch, formerRoom = room.RoomId, nextMatch, nextRoom, playerId, teammateId = teammate.Id,
                oldReceipt.SettlementId, before, afterM, bBeforeRevision = bBefore.RoomRevision, bCurrentRevision = bDuringN.RoomRevision,
                delayedResponseSha256 = A05Sha(oldCallback), duplicateReady = 3, host.ProcessId });
            relay.BeginRestart();
            await host.DisposeAsync(); host = null; bSocket.Dispose(); bSocket = null;
            foreach (var socket in nextSockets) socket.Dispose(); nextSockets.Clear();
            host = FullHost.Start(database.ConnectionString, port, "a05-healthy-after"); pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            relay.EndRestart();
            await A05ControlAsync(control, "restart-N", new { host.ProcessId }, ct);
            await A05WaitFileAsync(control, "recovered-N", godot, ct);
            bSocket = await ConnectAsync(bClient, port, ct);
            var bRecovered = await SnapshotAsync(bSocket, ct);
            Assert.Equal(formerMatch, bRecovered.MatchId); Assert.Equal("ActionBar", bRecovered.Player.Phase);
            await ExtractAsync(bSocket, ct);
            await WaitAsync(async () => await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", formerMatch) == "Completed" &&
                await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'") == 0, ct);
            var bReceipt = Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(bClient, HttpMethod.Get, $"/api/v1/matches/{formerMatch:D}/settlement", null, ct));
            Assert.Equal("Extracted", bReceipt.Result);
            await CallAsync(bClient, HttpMethod.Post, $"/api/v1/settlements/{bReceipt.SettlementId}/acknowledge", new Wire.Empty(), ct, "a05-B-ack");
            Assert.Equal(23L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", teammate.Id));
            await A05ControlAsync(control, "old-B-completed", new { bReceipt.SettlementId }, ct);
            await A05WaitFileAsync(control, "old-B-observed", godot, ct);
            await A05ControlAsync(control, "finish", new { ownedCleanup = "production end_session followed by durable terminal ACKs" }, ct);
            await godot;
            await WaitAsync(async () => await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", nextMatch.Value) == 4 &&
                await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'") == 0, ct);
            foreach (var nextPlayer in nextPlayers.Append((Id: playerId, Token: token)))
            {
                using var nextClient = Client(port, nextPlayer.Token);
                var receipt = Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(nextClient, HttpMethod.Get, $"/api/v1/matches/{nextMatch:D}/settlement", null, ct));
                await CallAsync(nextClient, HttpMethod.Post, $"/api/v1/settlements/{receipt.SettlementId}/acknowledge", new Wire.Empty(), ct, "a05-N-cleanup");
            }
            Assert.Empty(relay.Errors); Assert.Equal(2, pids.Distinct().Count());
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1", equipmentId));
            Assert.Equal(23L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", playerId));
            Assert.Equal(6L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE status IN ('Active','Queued','Matched')"));
            await A05AuditAsync(database, "healthy-after", true, ct);
            Record("A05-healthy-passed", new { canonical = A05HealthyCanonical, formerMatch, nextMatch, formerRoom = room.RoomId, nextRoom,
                playerId, teammateId = teammate.Id, equipmentId, pids, finalAssets = await A05AssetsAsync(database, playerId, equipmentId, ct),
                bResult = bReceipt.Result, bCredit = 23, acknowledged = 6, profiles = A05Profiles, acceptedBy = (string?)null,
                scope = "healthy saved M; A actual PB preparation/enqueue/READY enters N; unchanged real M response/frame delayed and replayed; real OS restart while B healthy; B normal extraction; N cleanup is disconnect terminal" });
        }
        finally
        {
            relay.Release(); bSocket?.Dispose(); foreach (var socket in nextSockets) socket.Dispose();
            if (host is not null) await host.DisposeAsync();
            if (godot is not null) { try { await godot; } catch when (ct.IsCancellationRequested) { } }
            A05CleanFixture(fixture);
        }
    }

    [Theory(Skip = "Requires owned local PostgreSQL and production Godot.", SkipUnless = nameof(HasRealClientDatabase))]
    [InlineData("precommit")]
    [InlineData("committed-response-loss")]
    [Trait("Category", "PostgresIntegration")]
    public async Task A05_actual_settlement_transaction_fault_recovers_without_duplicate_assets(string mode)
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(180); var ct = deadline.Token;
        var deviceId = "a05-db-fault-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create(); var now = DateTimeOffset.UtcNow;
        var identity = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "A05Runtime", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var playerId = identity.UserId;
        var equipmentId = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var (matchId, room) = await SeedRoomAsync(database, [playerId], ct, equipmentId, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        var before = await A05AssetsAsync(database, playerId, equipmentId, ct);
        await A05AuditAsync(database, "db-" + mode + "-before", false, ct);
        var settings = new NpgsqlConnectionStringBuilder(database.ConnectionString);
        await using var relay = new A05DatabaseRelay(settings.Host!, settings.Port, mode);
        settings.Host = relay.DirectoryPath; settings.SslMode = SslMode.Disable;
        var port = ReservePort(); using var client = Client(port, token);
        var fixture = CreateAckClientFixture("a05-db-" + mode);
        CopyFixtureFile(Path.Combine(RepositoryRoot(), "client"), fixture, Path.Combine(RepositoryRoot(), "client/tests/pr13_a05_persistence_fault.gd"));
        var control = Path.Combine(fixture, "control"); Directory.CreateDirectory(control);
        FullHost? host = null; Task? godot = null; var pids = new List<int>();
        try
        {
            host = FullHost.Start(settings.ConnectionString, port, "a05-db-" + mode); pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            godot = RunA05GodotAsync(fixture, port, deviceId, matchId, control, "pr13_a05_persistence_fault.gd", ct);
            await A05WaitFileAsync(control, "running", godot, ct);
            await A05ControlAsync(control, "extract", new { mode }, ct);
            await WaitAsync(() => Task.FromResult(relay.Dropped > 0), ct);
            if (mode == "precommit")
            {
                Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
                Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds"));
                Assert.Equal("Active", await database.ScalarAsync<string>("SELECT state FROM match_players WHERE match_id=$1", matchId));
                Assert.Equal(before, await A05AssetsAsync(database, playerId, equipmentId, ct));
            }
            await A05ControlAsync(control, "fault", new { mode }, ct);
            await A05WaitFileAsync(control, "fault-observed", godot, ct);
            Record("A05-transaction-fault-observed", new { mode, matchId, playerId, equipmentId, relay.Dropped,
                receipts = await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId),
                assets = await A05AssetsAsync(database, playerId, equipmentId, ct),
                durableCheckpoint = await database.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1", room.RoomId) });
            relay.Release();
            await WaitAsync(async () => await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements s WHERE match_id=$1 AND NOT EXISTS(SELECT 1 FROM settlement_asset_holds h WHERE h.settlement_id=s.settlement_id AND h.state='Pending')", matchId) == 1, ct);
            var receiptId = await database.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1", matchId);
            var durable = await CallAsync(client, HttpMethod.Get, $"/api/v1/matches/{matchId:D}/settlement", null, ct);
            await A05ControlAsync(control, "released", new { receipt_id = receiptId.ToString("D") }, ct);
            await A05WaitFileAsync(control, "ready", godot, ct);
            if (mode == "committed-response-loss")
            {
                Assert.Equal(1, relay.Dropped);
                await host.DisposeAsync(); host = null;
                host = FullHost.Start(database.ConnectionString, port, "a05-db-committed-restart"); pids.Add(host.ProcessId);
                await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
                Assert.Equal(durable, await CallAsync(client, HttpMethod.Get, $"/api/v1/matches/{matchId:D}/settlement", null, ct));
            }
            await A05ControlAsync(control, "ack", new { receipt_id = receiptId.ToString("D") }, ct);
            await godot;
            byte[]? sameAck = null;
            for (var repeat = 1; repeat <= 3; repeat++)
            {
                var body = await CallAsync(client, HttpMethod.Post, $"/api/v1/settlements/{receiptId:D}/acknowledge", new Wire.Empty(), ct, "a05-same-ack-three");
                sameAck ??= body; Assert.Equal(sameAck, body);
                Record("A05-same-ACK", new { mode, repeat, receiptId, keySha256 = A05Sha("a05-same-ack-three"),
                    requestBodySha256 = A05Sha([]), responseSha256 = A05Sha(body), assets = await A05AssetsAsync(database, playerId, equipmentId, ct) });
            }
            var after = await A05AssetsAsync(database, playerId, equipmentId, ct);
            Assert.Equal(before.Gold + 23, after.Gold); Assert.Equal(before.Potions + 2, after.Potions);
            Assert.Equal(playerId, after.Owner); Assert.Equal("Equipped", after.Location);
            Assert.Equal(1L, after.GoldLedger); Assert.Equal(1L, after.Movements);
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1 AND acknowledged_at IS NOT NULL", matchId));
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Committed'"));
            await A05AuditAsync(database, "db-" + mode + "-after", true, ct);
            Record("A05-transaction-fault-passed", new { canonical = mode == "precommit" ? "PR13-A05.1-T01" : "PR13-A05.1-T02", also = "PR13-A05.3-T01",
                mode, matchId, room.RoomId, receiptId, playerId, equipmentId, before, after, pids, relay.Dropped, profiles = A05Profiles, acceptedBy = (string?)null });
        }
        finally
        {
            if (host is not null) await host.DisposeAsync();
            if (godot is not null) { try { await godot; } catch when (ct.IsCancellationRequested) { } }
            A05CleanFixture(fixture);
        }
    }

    private static string A05Sha(string value) => A05Sha(System.Text.Encoding.UTF8.GetBytes(value));
    private static string A05Sha(byte[] value) => Convert.ToHexStringLower(SHA256.HashData(value));
    [Fact(Skip = "Requires owned local PostgreSQL and production Godot.", SkipUnless = nameof(HasRealClientDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task A05_actual_runtime_pending_holds_survive_OS_restart_without_early_completion()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(180);
        var ct = deadline.Token;
        var deviceId = "a05-pending-" + Guid.NewGuid().ToString("N");
        var token = SessionToken.Create(); var now = DateTimeOffset.UtcNow;
        var identity = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            deviceId, "A05Runtime", SessionToken.Hash(token), now, now.AddHours(1), ct);
        var playerId = identity.UserId;
        var equipmentId = await database.InsertWornFeetAsync(playerId, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var (matchId, room) = await SeedRoomAsync(database, [playerId], ct, equipmentId, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        await new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics).SaveIfDueAsync(room.Capture(), ct);
        var before = await A05AssetsAsync(database, playerId, equipmentId, ct);
        await A05AuditAsync(database, "pending-before", false, ct);
        Record("A05-runtime-before", new { matchId, room.RoomId, playerId, equipmentId, before });
        var port = ReservePort(); using var client = Client(port, token);
        var fixture = CreateAckClientFixture("a05-pending");
        CopyFixtureFile(Path.Combine(RepositoryRoot(), "client"), fixture, Path.Combine(RepositoryRoot(), "client/tests/pr13_a05_pending_runtime.gd"));
        var control = Path.Combine(fixture, "control"); Directory.CreateDirectory(control);
        FullHost? host = null; Task? godot = null;
        var pids = new List<int>();
        try
        {
            host = FullHost.Start(database.ConnectionString, port, "a05-pending-before"); pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            godot = RunA05GodotAsync(fixture, port, deviceId, matchId, control, "pr13_a05_pending_runtime.gd", ct);
            await A05WaitFileAsync(control, "running", godot, ct);
            await using var gate = await database.DataSource.OpenConnectionAsync(ct);
            await using var transaction = await gate.BeginTransactionAsync(ct);
            await using (var command = new NpgsqlCommand("SELECT gold FROM player_wallets WHERE player_id=$1 FOR UPDATE", gate, transaction))
            { command.Parameters.AddWithValue(playerId); await command.ExecuteScalarAsync(ct); }
            await A05ControlAsync(control, "extract", new { ownedGate = "player_wallets row FOR UPDATE" }, ct);
            await WaitAsync(async () => await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'") == 4, ct);
            var receiptId = await database.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1", matchId);
            Assert.Equal(before, await A05AssetsAsync(database, playerId, equipmentId, ct));
            await A05ControlAsync(control, "pending", new { receipt_id = receiptId.ToString("D") }, ct);
            await A05WaitFileAsync(control, "pending-before-restart", godot, ct);
            Record("A05-runtime-pending-before", new { matchId, receiptId, assets = await A05AssetsAsync(database, playerId, equipmentId, ct),
                pending = await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"), host.ProcessId });
            await host.DisposeAsync(); host = null;
            host = FullHost.Start(database.ConnectionString, port, "a05-pending-after"); pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/live", HttpStatusCode.OK, ct);
            await A05ControlAsync(control, "restarted", new { host.ProcessId }, ct);
            await A05WaitFileAsync(control, "pending-after-restart", godot, ct);
            Assert.Equal(before, await A05AssetsAsync(database, playerId, equipmentId, ct));
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            await transaction.CommitAsync(ct);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            await A05ControlAsync(control, "released", new { readOnly = "gate released by committing unchanged row lock" }, ct);
            await godot;
            Assert.Equal(2, pids.Distinct().Count());
            var after = await A05AssetsAsync(database, playerId, equipmentId, ct);
            Assert.Equal(before.Gold + 23, after.Gold); Assert.Equal(before.Potions + 2, after.Potions);
            Assert.Equal(playerId, after.Owner); Assert.Equal("Equipped", after.Location);
            Assert.Equal(1L, after.GoldLedger); Assert.Equal(1L, after.Movements);
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Committed'"));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE status IN ('Active','Queued','Matched')"));
            await A05AuditAsync(database, "pending-after", true, ct);
            Record("A05-runtime-passed", new { canonical = A05PendingCanonical, matchId, room.RoomId, receiptId, playerId, equipmentId,
                pids, before, after, pendingBefore = 4, committedAfter = 4, profiles = A05Profiles,
                scope = "owned saved Running input, actual Program and production Godot legal extraction; live Pending interval and actual SIGKILL restart", acceptedBy = (string?)null });
        }
        finally
        {
            if (host is not null) await host.DisposeAsync();
            if (godot is not null) { try { await godot; } catch when (ct.IsCancellationRequested) { } }
            A05CleanFixture(fixture);
        }
    }

    private sealed record A05Assets(long Gold, int Potions, Guid Owner, string Location, long GoldLedger, long Movements);
    private static async Task<A05Assets> A05AssetsAsync(PostgresTestSchema database, Guid playerId, Guid equipmentId, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        return new(await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", playerId),
            await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", playerId),
            await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipmentId),
            await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId),
            await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", playerId),
            await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason='settlement.extract'", equipmentId));
    }

    private static async Task A05ControlAsync(string directory, string name, object payload, CancellationToken ct)
    {
        var path = Path.Combine(directory, name + ".json");
        await File.WriteAllTextAsync(path + ".tmp", JsonSerializer.Serialize(payload), ct);
        File.Move(path + ".tmp", path);
    }
    private static async Task A05WaitFileAsync(string directory, string name, Task godot, CancellationToken ct)
    {
        while (!File.Exists(Path.Combine(directory, name + ".json")))
        { if (godot.IsCompleted) await godot; await Task.Delay(20, ct); }
    }
    private static void A05CleanFixture(string fixture)
    {
        foreach (var directory in Directory.EnumerateDirectories(fixture).Where(path => Path.GetFileName(path) is ".godot" or "assets" || Path.GetFileName(path).StartsWith("user-", StringComparison.Ordinal)))
            Directory.Delete(directory, recursive: true);
    }
    private static async Task RunA05GodotAsync(string fixture, int port, string deviceId, Guid matchId, string control, string script, CancellationToken ct)
    {
        foreach (var import in new[] { true, false })
        {
            var start = new ProcessStartInfo(Environment.GetEnvironmentVariable("A3GAME_GODOT_EXECUTABLE")!)
            { WorkingDirectory = fixture, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            foreach (var arg in new[] { "--headless", "--max-fps", "60", "--path", fixture }) start.ArgumentList.Add(arg);
            if (import) { start.ArgumentList.Add("--editor"); start.ArgumentList.Add("--import"); start.ArgumentList.Add("--quit"); }
            else { start.ArgumentList.Add("--script"); start.ArgumentList.Add("res://tests/" + script); }
            start.Environment.Clear();
            ConfigureWindowsChild(start, fixture);
            foreach (var name in new[] { "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME" })
            { var directory = Path.Combine(fixture, "user-" + name.ToLowerInvariant()); Directory.CreateDirectory(directory); start.Environment[name] = directory; }
            start.Environment["FANTASYCARD_SERVER_URL"] = $"http://127.0.0.1:{port}";
            start.Environment["FANTASYCARD_LOAD_RUN_ID"] = "owned-a05-runtime";
            start.Environment["PR13_A05_DEVICE_ID"] = deviceId; start.Environment["PR13_A05_MATCH_ID"] = matchId.ToString("D");
            start.Environment["PR13_A05_CONTROL"] = control;
            using var process = Process.Start(start)!;
            Record("A05-client-start", new { import, process.Id, fixture, script, executable = start.FileName });
            var stdout = process.StandardOutput.ReadToEndAsync(CancellationToken.None); var stderr = process.StandardError.ReadToEndAsync(CancellationToken.None);
            try { await process.WaitForExitAsync(ct); }
            finally { if (!process.HasExited) { process.Kill(entireProcessTree: true); await process.WaitForExitAsync(CancellationToken.None); } }
            var output = await stdout + "\n" + await stderr;
            await File.WriteAllTextAsync(Path.Combine(fixture, import ? "import.log" : "client.log"), output, CancellationToken.None);
            Record("A05-client-stop", new { import, process.Id, process.ExitCode, fixture, script });
            Assert.Equal(0, process.ExitCode); Assert.DoesNotContain("SCRIPT ERROR", output); Assert.DoesNotContain("Parse Error", output);
            if (import) File.AppendAllText(Path.Combine(fixture, "project.godot"), "\n[autoload]\nGame=\"*res://state/game_store.gd\"\n");
        }
        using var result = JsonDocument.Parse(File.ReadAllText(Path.Combine(control, "result.json")));
        Assert.True(result.RootElement.GetProperty("ok").GetBoolean(), result.RootElement.ToString());
    }
}
