using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Net.Sockets;
using System.Net.WebSockets;
using System.Text.Json;
using FantasyCard.Contracts.Http;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Tests.Persistence;
using Google.Protobuf;
using Npgsql;
using Wire = FantasyCard.Contracts.Http.V1;

namespace FantasyCard.Server.Tests.EndToEnd;

// These cases launch the actual Program host in separate OS processes. Database
// fixtures are intentionally declared here: they are not an HTTP entry flow.
public sealed class ProcessLifecycleRecoveryTests
{
    public static bool HasPrivateDatabase =>
        PostgresRuntimeIntegrationTests.HasTestDatabase &&
        IsLocalDatabase(new NpgsqlConnectionStringBuilder(Environment.GetEnvironmentVariable("FANTASYCARD_TEST_POSTGRES")).Host);

    // CI owns a PostgreSQL service on loopback; local offline runs own a Unix
    // socket. Neither gate permits a remote host or an inherited production DB.
    private static bool IsLocalDatabase(string? host) => host?.StartsWith('/') == true ||
        host is "127.0.0.1" or "::1" || string.Equals(host, "localhost", StringComparison.OrdinalIgnoreCase);

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an owned local isolated database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_Running_room_resumes_after_abrupt_OS_process_restart()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(60);
        var ct = deadline.Token;
        var player = await SeedPlayerAsync(database, "Running", ct);
        var (matchId, room) = await SeedRoomAsync(database, [player.Id], ct);
        var initial = room.Capture();
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(initial, ct);
        var port = ReservePort();
        using var client = Client(port, player.Token);
        int firstPid;
        long firstRevision;
        await using (var first = FullHost.Start(database.ConnectionString, port, "running-1"))
        {
            firstPid = first.ProcessId;
            await first.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            using var socket = await ConnectAsync(client, port, ct);
            var actual = await SnapshotAsync(socket, ct);
            Assert.Equal(room.RoomId, actual.RoomId);
            Assert.Equal(matchId, actual.MatchId);
            Assert.Equal("ActionBar", actual.Player.Phase);
            Assert.Equal(initial.Players[0].Combat.Deck.Hand.Select(card => card.InstanceId), actual.Player.Hand.Select(card => card.InstanceId));
            firstRevision = actual.RoomRevision;
            var resume = await CommandAsync(socket, new("session.resume", "running-resume-before", null,
                new SessionResumeCommandPayload(0, room.RoomId, 0)), ct, "room.snapshot");
            Assert.Equal(matchId, Assert.IsType<RoomSnapshotEventPayload>(resume.Payload).MatchId);
            // Kill while the websocket remains owned by the old server process.
            await first.KillAsync();
        }
        await using (var second = FullHost.Start(database.ConnectionString, port, "running-2"))
        {
            Assert.NotEqual(firstPid, second.ProcessId);
            await second.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            using var socket = await ConnectAsync(client, port, ct);
            var actual = await SnapshotAsync(socket, ct);
            Assert.Equal(room.RoomId, actual.RoomId);
            Assert.Equal(matchId, actual.MatchId);
            Assert.True(actual.RoomRevision >= firstRevision);
            Assert.Equal(initial.Players[0].Combat.Deck.Hand.Select(card => card.InstanceId), actual.Player.Hand.Select(card => card.InstanceId));
            Assert.Equal(initial.RandomStreams, (await snapshots.GetAsync(room.RoomId, ct))!.RandomStreams);
            Assert.Equal("Running", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", matchId));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
            Record("PROC-01", new { matchId, room.RoomId, firstPid, secondPid = second.ProcessId, firstRevision, actual.RoomRevision,
                expected = "same room/match, hand and RNG preserved, no settlement", actual = "matched" });
        }
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an owned local isolated database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_extraction_then_two_restarts_preserve_assets_and_duplicate_ACK()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(60);
        var ct = deadline.Token;
        var player = await SeedPlayerAsync(database, "Extract", ct);
        var equipmentId = await database.InsertWornFeetAsync(player.Id, HeroClass.Mage, ct);
        await SqlAsync(database, "UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1", ct, equipmentId);
        var beforeGold = await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.Id);
        var beforePotions = await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.Id);
        var (matchId, room) = await SeedRoomAsync(database, [player.Id], ct, equipmentId, gold: 23, potions: 2);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(room.Capture(), ct);
        var port = ReservePort();
        using var client = Client(port, player.Token);
        var pids = new List<int>();
        Wire.SettlementResponse? durable = null;
        Wire.SettlementAcknowledgementResponse? acknowledged = null;
        for (var restart = 0; restart < 3; restart++)
        {
            await using var host = FullHost.Start(database.ConnectionString, port, $"extraction-{restart}");
            pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            if (restart == 0)
            {
                using var socket = await ConnectAsync(client, port, ct);
                var extraction = await ExtractAsync(socket, ct);
                Assert.IsType<ActionExtractEventPayload>(extraction.Payload);
                await WaitAsync(async () => await database.ScalarAsync<long>(
                    "SELECT count(*) FROM match_settlements s WHERE match_id=$1 AND NOT EXISTS (SELECT 1 FROM settlement_asset_holds h WHERE h.settlement_id=s.settlement_id AND h.state='Pending')", matchId) == 1, ct);
            }
            Assert.Equal(beforeGold + 23, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.Id));
            Assert.Equal(beforePotions + 2, await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", player.Id));
            Assert.Equal(player.Id, await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipmentId));
            Assert.Equal("Equipped", await database.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1", equipmentId));
            Assert.Equal(equipmentId, await database.ScalarAsync<Guid>("SELECT feet_id FROM player_loadouts WHERE player_id=$1 AND hero_class=$2", player.Id, (short)HeroClass.Mage));
            Assert.Equal("Completed", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", matchId));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Committed'"));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", player.Id));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE item_id=$1 AND reason='settlement.extract'", equipmentId));
            Record("PROC-02-assets-before-wire", new { restart, matchId, equipmentId, host.ProcessId,
                goldCredit = 23, returnedPotions = 2, ownedArmor = "Equipped", pendingHolds = 0, committedHolds = 4, settlements = 1, ledgerRows = 1, movementRows = 1,
                persistedDetailsJson = await database.ScalarAsync<string>("SELECT details_json::text FROM match_settlements WHERE match_id=$1", matchId) });
            var receipt = Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get,
                $"/api/v1/matches/{matchId:D}/settlement", null, ct));
            durable ??= receipt;
            Assert.Equal(durable, receipt);
            Assert.Equal("Extracted", receipt.Result);
            var wireArmor = Assert.Single(receipt.Details.Items, item => item.Equipped).Item.Equipment;
            Assert.Equal("Feet", wireArmor.SlotName);
            Assert.Equal("White", wireArmor.QualityName);
            Assert.Equal("Fire", wireArmor.ElementName);
            Assert.Equal("DrawInterval", wireArmor.SecondaryTrait);
            var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
            Assert.Null(bootstrap.UnfinishedMatch);
            if (restart < 2) Assert.Equal(receipt.SettlementId, bootstrap.UnfinishedSettlement?.SettlementId);
            if (restart > 0)
            {
                var ack = Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post,
                    $"/api/v1/settlements/{receipt.SettlementId}/acknowledge", new Wire.Empty(), ct, "ack-extracted"));
                acknowledged ??= ack;
                Assert.Equal(acknowledged, ack);
                var duplicate = Wire.SettlementAcknowledgementResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post,
                    $"/api/v1/settlements/{receipt.SettlementId}/acknowledge", new Wire.Empty(), ct, "ack-extracted"));
                Assert.Equal(ack, duplicate);
                Assert.Null(Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct)).UnfinishedSettlement);
            }
        }
        Assert.Equal(3, pids.Distinct().Count());
        Record("PROC-02", new { matchId, room.RoomId, playerId = player.Id, equipmentId, pids, durable!.SettlementId,
            expected = "one receipt/credit/equipment movement, 4 holds committed, ACK timestamp persists over restart", actual = "matched" });
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an owned local isolated database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_cold_start_commits_durable_pending_holds_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(60);
        var ct = deadline.Token;
        var player = await SeedPlayerAsync(database, "Pending", ct);
        var (matchId, room) = await SeedRoomAsync(database, [player.Id], ct);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(room.Capture() with
        { Players = room.Capture().Players.Select(value => value with { Phase = RoomPlayerPhase.Extracted }).ToArray() }, ct);
        using var details = JsonDocument.Parse("{}");
        var pending = await new SettlementRepository(database.DataSource, TimeProvider.System, metrics).SettleAsync(
            matchId, player.Id, "Extracted", details.RootElement, [new SettlementAsset("Gold", "gold", false, 17)], ct);
        var before = await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.Id);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
        var port = ReservePort();
        using var client = Client(port, player.Token);
        var pids = new List<int>();
        for (var restart = 0; restart < 2; restart++)
        {
            await using var host = FullHost.Start(database.ConnectionString, port, $"pending-{restart}");
            pids.Add(host.ProcessId);
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            Assert.Equal(before + 17, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.Id));
            Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
            Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='settlement.commit'", player.Id));
            var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
            Assert.Equal(pending.SettlementId.ToString("D"), bootstrap.UnfinishedSettlement?.SettlementId);
            Assert.Null(bootstrap.UnfinishedMatch);
        }
        Assert.Equal(2, pids.Distinct().Count());
        Record("PROC-03", new { matchId, room.RoomId, pending.SettlementId, pids,
            expected = "durable Pending hold committed by actual host cold start; second start credits zero additional", actual = "matched" });
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an owned local isolated database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_quarantines_contradictory_terminal_checkpoint_but_recovers_next_room()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var deadline = Deadline(60);
        var ct = deadline.Token;
        var player = await SeedPlayerAsync(database, "Next", ct);
        var teammate = await SeedPlayerAsync(database, "Former", ct);
        var (formerMatch, former) = await SeedRoomAsync(database, [player.Id, teammate.Id], ct);
        var (nextMatch, next) = await SeedRoomAsync(database, [player.Id], ct);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(former.Capture(), ct);
        using var details = JsonDocument.Parse("{}");
        await new SettlementRepository(database.DataSource, TimeProvider.System, metrics).SettleAsync(
            formerMatch, player.Id, "Extracted", details.RootElement, [], ct);
        await snapshots.SaveIfDueAsync(next.Capture(), ct);
        var port = ReservePort();
        using var client = Client(port, player.Token);
        await using var host = FullHost.Start(database.ConnectionString, port, "quarantine");
        await host.WaitForHealthAsync(client, "/health/live", HttpStatusCode.OK, ct);
        await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.ServiceUnavailable, ct);
        using var socket = await ConnectAsync(client, port, ct);
        var restored = await SnapshotAsync(socket, ct);
        Assert.Equal(next.RoomId, restored.RoomId);
        Assert.Equal(nextMatch, restored.MatchId);
        Assert.Equal("ActionBar", restored.Player.Phase);
        using var teammateClient = Client(port, teammate.Token);
        using var teammateSocket = await ConnectAsync(teammateClient, port, ct);
        var rejected = await CommandAsync(teammateSocket,
            new("room.snapshot.read", "quarantined-room-read", null, new RoomSnapshotCommandPayload()), ct);
        Assert.IsType<CommandRejectedEventPayload>(rejected.Payload);
        Assert.Equal(RoomPlayerPhase.ActionBar, (await snapshots.GetAsync(former.RoomId, ct))!.Players.Single(value => value.PlayerId == player.Id).Phase);
        Assert.Equal(1L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", formerMatch));
        Assert.Contains($"Running room {former.RoomId}", host.CapturedOutput, StringComparison.Ordinal);
        Record("PROC-04", new { formerMatch, formerRoom = former.RoomId, nextMatch, nextRoom = next.RoomId, host.ProcessId,
            expected = "live 200, ready 503; old actor unavailable; next room WS snapshot retained; no extra settlement", actual = "matched" });
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an owned local isolated database.", SkipUnless = nameof(HasPrivateDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Full_host_three_entry_cycles_duplicate_READY_and_ACK_release_owned_locks()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: false);
        using var deadline = Deadline(180);
        var ct = deadline.Token;
        var port = ReservePort();
        using var client = Client(port);
        var players = new List<(Guid Id, string Token)>();
        var matchIds = new List<Guid>();
        var firstPreparationAt = Stopwatch.GetTimestamp();
        var host = FullHost.Start(database.ConnectionString, port, "entry-three");
        try
        {
            await host.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
            for (var index = 0; index < 4; index++)
            {
                client.DefaultRequestHeaders.Authorization = null;
                var login = Wire.LocalSignInResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post, "/api/v1/auth/local",
                    new Wire.LocalSignInRequest { DeviceId = Guid.NewGuid().ToString("N"), DisplayName = $"Process Cycle {index}" }, ct));
                players.Add((Guid.Parse(login.Player.UserId), login.AccessToken));
            }
            // Owned private fixture supply only; there is no remote account or ledger repair.
            await SqlAsync(database, "UPDATE player_consumables SET health_potion_count=3 WHERE player_id=$1", ct, players[0].Id);
            for (var cycle = 0; cycle < 3; cycle++)
            {
                // Pace before any member enters the queue. Waiting on a 429
                // halfway through a cohort would correctly trigger 30s bot fill.
                if (cycle == 2)
                {
                    var remaining = TimeSpan.FromSeconds(61) - Stopwatch.GetElapsedTime(firstPreparationAt);
                    if (remaining > TimeSpan.Zero)
                    {
                        Record("entry-window-pacing", new { cycle = cycle + 1, delaySeconds = remaining.TotalSeconds, action = "wait before cohort queues; rate limits and 30s bot fill unchanged" });
                        await Task.Delay(remaining, ct);
                    }
                }
                var sockets = new List<ClientWebSocket>();
                try
                {
                    foreach (var player in players)
                    {
                        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", player.Token);
                        var bootstrap = Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct));
                        Assert.Null(bootstrap.UnfinishedMatch);
                        var deck = bootstrap.Decks.First(value => value.HeroClass == "Priest");
                        var loadout = Wire.LoadoutResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/loadouts/Priest", null, ct));
                        var request = new Wire.CreatePreparationRequest
                        { HeroClass = "Priest", DeckVersion = deck.Version, BackpackTier = "Free", Difficulty = "Standard", PotionCount = player.Id == players[0].Id ? 1 : 0 };
                        request.EquipmentIds.Add(loadout.EquipmentIds);
                        if (cycle == 0 && player.Id == players[0].Id) firstPreparationAt = Stopwatch.GetTimestamp();
                        var preparation = Wire.PreparationResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post, "/api/v1/preparations", request, ct));
                        var socket = await ConnectAsync(client, port, ct);
                        sockets.Add(socket);
                        await CallAsync(client, HttpMethod.Post, "/api/v1/matches/enqueue", new Wire.EnqueueMatchRequest { PreparationId = preparation.PreparationId }, ct);
                    }
                    Guid? matchId = null;
                    Guid? roomId = null;
                    for (var index = 0; index < sockets.Count; index++)
                    {
                        var required = Assert.IsType<RoomReadyRequiredEventPayload>((await EventAsync(sockets[index], "room.ready_required", ct)).Payload);
                        Assert.Equal(4, required.RequiredPlayers);
                        matchId ??= required.MatchId;
                        roomId ??= required.RoomId;
                        Assert.Equal(matchId, required.MatchId);
                        var readyCommand = new ClientCommand("room.ready", $"ready-{cycle}-{index}", null, new RoomReadyCommandPayload());
                        var accepted = await CommandAsync(sockets[index], readyCommand, ct, "room.ready_accepted");
                        Assert.IsType<RoomReadyAcceptedEventPayload>(accepted.Payload);
                        // Duplicate before the last READY launches: no timing race is assumed.
                        if (index == 0)
                        {
                            var duplicate = await CommandAsync(sockets[index], readyCommand, ct, accepted.Type);
                            Assert.Equal(accepted.EventId, duplicate.EventId);
                            Assert.Equal(1, Assert.IsType<RoomReadyAcceptedEventPayload>(duplicate.Payload).ReadyPlayers);
                        }
                    }
                    matchIds.Add(matchId!.Value);
                    await WaitAsync(async () => await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", matchId.Value) == "Running", ct);
                    for (var index = 0; index < sockets.Count; index++)
                    {
                        var entered = await SnapshotAsync(sockets[index], ct);
                        Assert.Equal(matchId, entered.MatchId);
                        Assert.Equal(roomId, entered.RoomId);
                        Assert.Equal(players[index].Id, entered.Player.PlayerId);
                        Assert.Equal(4, entered.MapPlayerCount);
                    }
                    Assert.Equal(4L, await database.ScalarAsync<long>("SELECT count(*) FROM match_players WHERE match_id=$1 AND is_bot=false", matchId.Value));
                    foreach (var socket in sockets) socket.Abort();
                    await WaitAsync(async () => await database.ScalarAsync<long>(
                        "SELECT count(*) FROM match_settlements s WHERE match_id=$1 AND NOT EXISTS (SELECT 1 FROM settlement_asset_holds h WHERE h.settlement_id=s.settlement_id AND h.state='Pending')", matchId.Value) == 4, ct);
                    Assert.Equal("Completed", await database.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1", matchId.Value));
                    Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE status IN ('Active','Queued','Matched')"));
                    Assert.Equal(2 - cycle, await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", players[0].Id));
                    foreach (var player in players)
                    {
                        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", player.Token);
                        var receipt = Wire.SettlementResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, $"/api/v1/matches/{matchId:D}/settlement", null, ct));
                        Assert.Equal("Dead", receipt.Result);
                        var path = $"/api/v1/settlements/{receipt.SettlementId}/acknowledge";
                        var ack = await CallAsync(client, HttpMethod.Post, path, new Wire.Empty(), ct, $"ack-entry-cycle-{cycle}");
                        Assert.Equal(ack, await CallAsync(client, HttpMethod.Post, path, new Wire.Empty(), ct, $"ack-entry-cycle-{cycle}"));
                        Assert.Null(Wire.BootstrapResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Get, "/api/v1/bootstrap", null, ct)).UnfinishedSettlement);
                    }
                    Record($"PROC-05-cycle-{cycle + 1}", new { cycle = cycle + 1, matchId, roomId, host.ProcessId,
                        expected = "four PB preparations/entry; first READY replay; disconnect death; four durable ACK replays; no active prep locks", actual = "matched" });
                }
                finally { foreach (var socket in sockets) socket.Dispose(); }
            }
        }
        finally { await host.DisposeAsync(); }
        await using var restarted = FullHost.Start(database.ConnectionString, port, "entry-three-restart");
        Assert.NotEqual(host.ProcessId, restarted.ProcessId);
        await restarted.WaitForHealthAsync(client, "/health/ready", HttpStatusCode.OK, ct);
        Assert.Equal(3, matchIds.Distinct().Count());
        Assert.Equal(12L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements"));
        Assert.Equal(12L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE acknowledged_at IS NOT NULL"));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
        Assert.Equal(0L, await database.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE status IN ('Active','Queued','Matched')"));
        Assert.Equal(0, await database.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1", players[0].Id));
        Record("PROC-05", new { matchIds, previousPid = host.ProcessId, restarted.ProcessId,
            expected = "3 distinct matches, 12 settled/ACKed players and zero active locks/pending holds persist through actual restart", actual = "matched",
            scope = "three entry/disconnect-death cycles, not three full gameplay cycles or LIVE acceptance" });
    }

    private static CancellationTokenSource Deadline(int seconds)
    {
        var deadline = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        return deadline;
    }

    private static async Task<(Guid Id, string Token)> SeedPlayerAsync(PostgresTestSchema database, string name, CancellationToken ct)
    {
        var token = SessionToken.Create();
        var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            "process-" + Guid.NewGuid().ToString("N"), name, SessionToken.Hash(token), now, now.AddHours(1), ct);
        return (player.UserId, token);
    }

    private static async Task<(Guid MatchId, BattleRoom Room)> SeedRoomAsync(PostgresTestSchema database, Guid[] players, CancellationToken ct,
        Guid? equipmentId = null, int gold = 0, int potions = 0)
    {
        const int seed = 73;
        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        await SqlAsync(database,
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,$3,'Running',CURRENT_TIMESTAMP)",
            ct, matchId, roomId, GameConfigCatalog.Current.Version);
        var room = new BattleRoom(roomId, GameConfigCatalog.Current.Version, CombatCardCatalog.CreatePrototype(), seed);
        foreach (var playerId in players)
        {
            await SqlAsync(database, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", ct, matchId, playerId);
            var player = room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(), null,
                WornArmor: equipmentId is null ? [] : [new(equipmentId.Value.ToString("D"), ExplorationItemKind.Equipment,
                    Equipment: new("Feet", "White", "Fire", null, "DrawInterval", 0), IsGenerated: false)]));
            if (gold > 0) Assert.True(player.Inventory.TryAdd(new("fixture-gold", ExplorationItemKind.Gold, gold)));
            for (var potion = 0; potion < potions; potion++)
                Assert.True(player.Inventory.TryAdd(new($"health_potion:{potion + 1}", ExplorationItemKind.HealthPotion)));
        }
        room.InitializeMap(ChaosMapGenerator.Generate(seed, players.Length));
        var snapshot = room.Capture();
        var evacuation = snapshot.Map!.Cells.First(cell => cell.HasEvacuation).Position;
        return (matchId, BattleRoom.Restore(snapshot with
        { Players = snapshot.Players.Select(player => player with { Position = evacuation, Phase = RoomPlayerPhase.ActionBar, Pve = null, ClearedCells = [evacuation] }).ToArray() },
            CombatCardCatalog.CreatePrototype(), seed));
    }

    private static async Task SqlAsync(PostgresTestSchema database, string sql, CancellationToken ct, params object[] values)
    {
        await using var command = database.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(ct);
    }

    private static int ReservePort()
    {
        using var listener = new TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        return ((IPEndPoint)listener.LocalEndpoint).Port;
    }

    private static HttpClient Client(int port, string? token = null)
    {
        var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}"), Timeout = TimeSpan.FromSeconds(10) };
        client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue(HttpProtocolRegistry.MediaType));
        if (token is not null) client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return client;
    }

    private static async Task<byte[]> CallAsync(HttpClient client, HttpMethod method, string path, IMessage? body, CancellationToken ct, string? requestId = null)
    {
        var key = requestId ?? Guid.NewGuid().ToString("N");
        for (var attempt = 0; attempt < 2; attempt++)
        {
            using var request = new HttpRequestMessage(method, path);
            request.Headers.Add("Idempotency-Key", key);
            if (method != HttpMethod.Get)
            {
                request.Content = new ByteArrayContent((body ?? new Wire.Empty()).ToByteArray());
                request.Content.Headers.ContentType = new MediaTypeHeaderValue(HttpProtocolRegistry.MediaType);
            }
            using var response = await client.SendAsync(request, ct);
            // Respect the real default IP-wide fixed window; never raise limits.
            if (response.StatusCode == HttpStatusCode.TooManyRequests && attempt == 0)
            {
                var delay = response.Headers.RetryAfter?.Delta ?? TimeSpan.FromSeconds(60);
                Record("http-rate-limit", new { path, delaySeconds = delay.TotalSeconds, action = "wait Retry-After with same request id; defaults unchanged" });
                await Task.Delay(delay, ct);
                continue;
            }
            Assert.True(response.IsSuccessStatusCode, $"{method} {path}: {(int)response.StatusCode}");
            Assert.Equal(HttpProtocolRegistry.MediaType, response.Content.Headers.ContentType?.MediaType);
            return await response.Content.ReadAsByteArrayAsync(ct);
        }
        throw new InvalidOperationException("HTTP retry did not complete.");
    }

    private static async Task<ClientWebSocket> ConnectAsync(HttpClient client, int port, CancellationToken ct)
    {
        var ticket = Wire.RealtimeTicketResponse.Parser.ParseFrom(await CallAsync(client, HttpMethod.Post, "/api/v1/realtime/ticket", new Wire.Empty(), ct));
        var socket = new ClientWebSocket();
        try
        {
            await socket.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/ws/v1/session?ticket={Uri.EscapeDataString(ticket.Ticket)}"), ct);
            Assert.Equal("session.connected", (await ReceiveAsync(socket, ct)).Type);
            return socket;
        }
        catch { socket.Dispose(); throw; }
    }

    private static async Task<ServerEvent> ReceiveAsync(ClientWebSocket socket, CancellationToken ct)
    {
        var bytes = new byte[16 * 1024];
        var count = 0;
        while (true)
        {
            var frame = await socket.ReceiveAsync(bytes.AsMemory(count), ct);
            Assert.Equal(WebSocketMessageType.Binary, frame.MessageType);
            count += frame.Count;
            Assert.True(count < bytes.Length || frame.EndOfMessage);
            if (frame.EndOfMessage) return RealtimeProtobufCodec.DecodeServer(bytes.AsSpan(0, count));
        }
    }

    private static async Task<ServerEvent> EventAsync(ClientWebSocket socket, string type, CancellationToken ct)
    {
        while (true)
        {
            var result = await ReceiveAsync(socket, ct);
            if (result.Type == type) return result;
        }
    }

    private static async Task<ServerEvent> CommandAsync(ClientWebSocket socket, ClientCommand command, CancellationToken ct, string? expectedType = null)
    {
        await socket.SendAsync(RealtimeProtobufCodec.EncodeClient(command), WebSocketMessageType.Binary, true, ct);
        while (true)
        {
            var result = await ReceiveAsync(socket, ct);
            if (result.RequestId == command.RequestId &&
                (expectedType is null || result.Type == expectedType || result.Payload is CommandRejectedEventPayload)) return result;
        }
    }

    private static async Task<RoomSnapshotEventPayload> SnapshotAsync(ClientWebSocket socket, CancellationToken ct) =>
        Assert.IsType<RoomSnapshotEventPayload>((await CommandAsync(socket,
            new("room.snapshot.read", Guid.NewGuid().ToString("N"), null, new RoomSnapshotCommandPayload()), ct)).Payload);

    private static async Task<ServerEvent> ExtractAsync(ClientWebSocket socket, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 20; attempt++)
        {
            var snapshot = await SnapshotAsync(socket, ct);
            var result = await CommandAsync(socket,
                new("action.extract", Guid.NewGuid().ToString("N"), snapshot.RoomRevision, new ActionExtractCommandPayload()), ct);
            if (result.Payload is CommandRejectedEventPayload rejected && rejected.Detail.Contains("revision conflict", StringComparison.OrdinalIgnoreCase)) continue;
            Assert.False(result.Payload is CommandRejectedEventPayload, JsonSerializer.Serialize(result.Payload));
            return result;
        }
        throw new InvalidOperationException("Extraction did not accept a current room revision.");
    }

    private static async Task WaitAsync(Func<Task<bool>> predicate, CancellationToken ct)
    {
        while (!await predicate()) await Task.Delay(TimeSpan.FromMilliseconds(100), ct);
    }

    private static readonly object EvidenceGate = new();
    private static string EvidenceDirectory => Environment.GetEnvironmentVariable("FANTASYCARD_PROCESS_EVIDENCE") ??
        Path.Combine(AppContext.BaseDirectory, "process-recovery-evidence");

    private static void Record(string caseId, object evidence)
    {
        var json = JsonSerializer.Serialize(new { caseId, recordedAt = DateTimeOffset.UtcNow, evidence });
        lock (EvidenceGate)
        {
            Directory.CreateDirectory(EvidenceDirectory);
            File.AppendAllText(Path.Combine(EvidenceDirectory, "receipts.jsonl"), json + Environment.NewLine);
        }
        TestContext.Current.TestOutputHelper?.WriteLine(json);
    }

    private sealed class FullHost : IAsyncDisposable
    {
        private readonly Process _process;
        private readonly Task<string> _stdout;
        private readonly Task<string> _stderr;
        private readonly string _label;
        private bool _disposed;
        public int ProcessId { get; }
        public string CapturedOutput => _stdout.IsCompletedSuccessfully ? _stdout.Result : ReadLog();
        private readonly List<string> _lines = [];
        private readonly object _gate = new();

        private FullHost(Process process, string label)
        {
            _process = process;
            ProcessId = process.Id;
            _label = label;
            _stdout = CaptureAsync(process.StandardOutput);
            _stderr = CaptureAsync(process.StandardError);
        }

        public static FullHost Start(string connectionString, int port, string label)
        {
            var settings = new NpgsqlConnectionStringBuilder(connectionString);
            Assert.True(IsLocalDatabase(settings.Host) && settings.SearchPath?.StartsWith("fc_runtime_test_", StringComparison.Ordinal) == true,
                "Process tests require an owned local database and the owned randomized schema.");
            var dll = Environment.GetEnvironmentVariable("FANTASYCARD_PROCESS_SERVER_DLL") ??
                typeof(FantasyCard.Server.Persistence.DatabaseMigrator).Assembly.Location;
            Assert.True(File.Exists(dll));
            var dotnetRoot = Environment.GetEnvironmentVariable("DOTNET_ROOT");
            var executable = dotnetRoot is null ? "dotnet" : Path.Combine(dotnetRoot, "dotnet");
            var start = new ProcessStartInfo(executable)
            { WorkingDirectory = Path.GetDirectoryName(dll)!, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
            start.ArgumentList.Add(dll);
            // Child host receives only the explicit local fixture configuration.
            start.Environment.Clear();
            if (dotnetRoot is not null) start.Environment["DOTNET_ROOT"] = dotnetRoot;
            start.Environment["ASPNETCORE_ENVIRONMENT"] = "Development";
            start.Environment["ASPNETCORE_URLS"] = $"http://127.0.0.1:{port}";
            start.Environment["ConnectionStrings__Postgres"] = connectionString;
            start.Environment["Identity__EnableLocalAuth"] = "true";
            start.Environment["ProtobufHttp__AllowLegacyJson"] = "false";
            start.Environment["Realtime__AllowLegacyAccessTokenQuery"] = "false";
            start.Environment["Matchmaking__BotFillDelaySeconds"] = "30";
            var process = Process.Start(start) ?? throw new InvalidOperationException("Host process did not start.");
            Record("process-start", new { label, process.Id, executable, dll, port, settings.SearchPath,
                environment = "explicit local fixture only; PB default; ticket WS; bot fill 30s" });
            return new(process, label);
        }

        public async Task WaitForHealthAsync(HttpClient client, string path, HttpStatusCode status, CancellationToken ct)
        {
            while (true)
            {
                Assert.False(_process.HasExited, $"Host {_label} exited before {path}: {ReadLog()}");
                try
                {
                    using var response = await client.GetAsync(path, ct);
                    if (response.StatusCode == status) return;
                }
                catch (HttpRequestException) { }
                await Task.Delay(TimeSpan.FromMilliseconds(100), ct);
            }
        }

        private async Task<string> CaptureAsync(StreamReader stream)
        {
            while (await stream.ReadLineAsync() is { } line)
            {
                lock (_gate) _lines.Add(line);
            }
            return ReadLog();
        }

        private string ReadLog() { lock (_gate) return string.Join(Environment.NewLine, _lines); }

        public async Task KillAsync()
        {
            if (!_process.HasExited) _process.Kill(entireProcessTree: true);
            await _process.WaitForExitAsync();
            await Task.WhenAll(_stdout, _stderr);
        }

        public async ValueTask DisposeAsync()
        {
            if (_disposed) return;
            _disposed = true;
            await KillAsync();
            Directory.CreateDirectory(EvidenceDirectory);
            var logPath = Path.Combine(EvidenceDirectory, $"{_label}-{ProcessId}.log");
            await File.WriteAllTextAsync(logPath, ReadLog());
            Record("process-stop", new { label = _label, ProcessId, _process.ExitCode, termination = "Process.Kill(entireProcessTree:true)", logPath });
            _process.Dispose();
        }
    }
}
