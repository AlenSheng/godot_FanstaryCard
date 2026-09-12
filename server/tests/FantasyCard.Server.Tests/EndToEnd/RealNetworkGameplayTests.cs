using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Net.WebSockets;
using FantasyCard.Contracts.Bootstrap;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Persistence;

namespace FantasyCard.Server.Tests.EndToEnd;

public sealed partial class RealNetworkEndToEndTests
{
    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_process_pvp_relic_replay_and_extraction_survive_forced_restart()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(90));
        var ct = timeout.Token;
        var winner = await SeedNetworkPlayerAsync(database, "Winner", ct);
        var loser = await SeedNetworkPlayerAsync(database, "Loser", ct);
        var equipmentId = await database.InsertWornFeetAsync(loser.Id, HeroClass.Mage, ct);
        await ExecuteGameplaySqlAsync(database,
            "UPDATE equipments SET location='InMatchEquipped',is_bound=false WHERE instance_id=$1", ct, equipmentId);
        await database.ExecuteAsync("UPDATE player_wallets SET gold=0");

        const int seed = 811;
        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        var draft = new BattleRoom(roomId, GameConfigCatalog.Current.Version, CombatCardCatalog.CreatePrototype(), seed);
        var cards = Enumerable.Repeat("C01", 20).ToArray();
        var winnerState = draft.AddPlayer(new BattleRoomPlayerSetup(
            winner.Id, HeroClass.Mage, cards, null, DisplayName: "Winner",
            CardLevels: [2, .. Enumerable.Repeat(0, 19)]));
        var loserState = draft.AddPlayer(new BattleRoomPlayerSetup(
            loser.Id, HeroClass.Mage, cards, null, DisplayName: "Loser", WornArmor:
            [new(equipmentId.ToString("D"), ExplorationItemKind.Equipment,
                Equipment: new EquipmentRewardData("Feet", "White", "Fire", null, "DrawInterval", 0), IsGenerated: false)]));
        Assert.True(winnerState.Inventory.TryAdd(new("winner-gold", ExplorationItemKind.Gold, 7)));
        Assert.True(loserState.Inventory.TryAdd(new("victim-gold", ExplorationItemKind.Gold, 29)));
        draft.InitializeMap(ChaosMapGenerator.Generate(seed, 2));
        var setup = draft.Capture();
        var evacuation = setup.Map!.Cells.First(cell => cell.HasEvacuation).Position;
        // Seed a deterministic encounter; every subsequent action crosses the real WebSocket server.
        var room = BattleRoom.Restore(setup with
        {
            Players = setup.Players.Select(player => player with
            {
                Position = evacuation, Phase = RoomPlayerPhase.ActionBar, Pve = null,
                ClearedCells = [evacuation]
            }).ToArray()
        }, CombatCardCatalog.CreatePrototype(), seed);
        room.StartDuel(winner.Id, loser.Id, DateTimeOffset.UtcNow.AddSeconds(-1));
        room.GetPlayer(loser.Id).Combat.TakeDamage(room.GetPlayer(loser.Id).Combat.Hp - 1);
        await ExecuteGameplaySqlAsync(database,
            "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',$3,$4,'Running',CURRENT_TIMESTAMP)",
            ct, matchId, roomId, seed, GameConfigCatalog.Current.Version);
        foreach (var player in new[] { winner.Id, loser.Id })
            await ExecuteGameplaySqlAsync(database,
                "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')", ct, matchId, player);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(database.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(room.Capture(), ct);

        var port = ReserveLoopbackPort();
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}") };
        await using (var server = StartServer(database.ConnectionString, port))
        {
            await server.WaitUntilReadyAsync(client, ct);
            client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", winner.Token);
            Assert.Equal(winner.Id, (await client.GetFromJsonAsync<BootstrapResponse>("/api/v1/bootstrap", WebJson, ct))!.Player.UserId);
            using var winnerSocket = await ConnectGameplaySocketAsync(port, winner.Token, ct);
            using var loserSocket = await ConnectGameplaySocketAsync(port, loser.Token, ct);
            var before = await ReadGameplaySnapshotAsync(winnerSocket, ct);
            Assert.Equal("Pvp", before.Player.Phase);
            Assert.Equal(loser.Id, before.Duel!.OpponentId);
            var played = await SendGameplayMutationAsync(winnerSocket, "battle.play_cards", snapshot =>
                new BattlePlayCardsCommandPayload(snapshot.Duel!.DuelId, loser.Id.ToString("D"),
                    [snapshot.Player.Hand[0].InstanceId]), ct);
            var resolution = Assert.IsType<BattleComboResolvedEventPayload>(played.Event.Payload);
            Assert.True(resolution.TargetDefeated);
            Assert.True(resolution.BattleEnded);
            Assert.True(resolution.Damage > 0);
            Assert.NotEmpty(resolution.DamageSegments!);
            var combatReplay = await SendGameplayCommandAsync(winnerSocket, played.Command, ct);
            Assert.Equal(played.Event.EventId, combatReplay.EventId);
            await WaitForGameplayConditionAsync(async () => await database.ScalarAsync<string>(
                "SELECT location FROM equipments WHERE instance_id=$1", equipmentId) == "RelicPile", ct);

            foreach (var itemId in new[] { "victim-gold", equipmentId.ToString("D") })
            {
                var pileSummary = Assert.Single((await ReadGameplaySnapshotAsync(winnerSocket, ct)).CurrentCell.RelicPiles!);
                var contentsEvent = await SendGameplayCommandAsync(winnerSocket,
                    new("relic.read", Guid.NewGuid().ToString("N"), null, new RelicReadCommandPayload(pileSummary.PileId)), ct);
                var contents = Assert.IsType<RoomRelicPilePayload>(contentsEvent.Payload);
                Assert.Contains(contents.Items, item => item.ItemId == itemId);
                var taken = await SendGameplayMutationAsync(winnerSocket, "relic.take", snapshot =>
                {
                    var pile = Assert.Single(snapshot.CurrentCell.RelicPiles!);
                    return new RelicTakeCommandPayload(pile.PileId, itemId, pile.Version);
                }, ct);
                Assert.IsType<RelicTakeEventPayload>(taken.Event.Payload);
                var replay = await SendGameplayCommandAsync(winnerSocket, taken.Command, ct);
                Assert.Equal(taken.Event.EventId, replay.EventId);
            }
            var inventory = (await ReadGameplaySnapshotAsync(winnerSocket, ct)).Player.Inventory;
            Assert.Equal(36, inventory.Where(item => item.Kind == "Gold").Sum(item => item.Quantity));
            Assert.Single(inventory, item => item.ItemId == equipmentId.ToString("D"));
            var extraction = await SendGameplayMutationAsync(winnerSocket, "action.extract",
                _ => new ActionExtractCommandPayload(), ct);
            Assert.IsType<ActionExtractEventPayload>(extraction.Event.Payload);
            var extractionReplay = await SendGameplayCommandAsync(winnerSocket, extraction.Command, ct);
            Assert.Equal(extraction.Event.EventId, extractionReplay.EventId);
            BattleRoomSnapshot? checkpoint = null;
            await WaitForGameplayConditionAsync(async () =>
            {
                checkpoint = await snapshots.GetAsync(roomId, ct);
                return checkpoint?.Players.Single(player => player.PlayerId == winner.Id).ExtractionRemaining > TimeSpan.Zero;
            }, ct);
            var checkpointPlayer = checkpoint!.Players.Single(player => player.PlayerId == winner.Id);
            Assert.Single(checkpointPlayer.Inventory!.Items,
                item => item.ItemId == equipmentId.ToString("D"));
            Assert.Single(checkpointPlayer.Combat.Deck.Hand.Concat(checkpointPlayer.Combat.Deck.Library)
                .Concat(checkpointPlayer.Combat.Deck.Discard), card => card.Level == 2);
            // Dispose kills the process tree without a graceful host shutdown, during extraction.
        }

        await using (var recovered = StartServer(database.ConnectionString, port))
        {
            await recovered.WaitUntilReadyAsync(client, ct);
            await WaitForGameplayConditionAsync(async () => await database.ScalarAsync<long>(
                "SELECT count(*) FROM match_settlements s WHERE match_id=$1 AND player_id=$2 AND result='Extracted' AND NOT EXISTS (SELECT 1 FROM settlement_asset_holds h WHERE h.settlement_id=s.settlement_id AND h.state='Pending')",
                matchId, winner.Id) == 1, ct);
            var inventory = await client.GetFromJsonAsync<InventoryResponse>("/api/v1/inventory", WebJson, ct);
            Assert.Contains(inventory!.Equipments, item => item.InstanceId == equipmentId && item.Location == "Inventory");
            Assert.Equal(36L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", winner.Id));
            Assert.Equal(winner.Id, await database.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1", equipmentId));
            Assert.Equal(2L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
            Assert.Equal(0L, await database.ScalarAsync<long>(
                "SELECT count(*) FROM settlement_asset_holds h JOIN match_settlements s ON s.settlement_id=h.settlement_id WHERE s.match_id=$1 AND h.state='Pending'", matchId));
        }
        await using (var secondRestart = StartServer(database.ConnectionString, port))
        {
            await secondRestart.WaitUntilReadyAsync(client, ct);
            Assert.Equal(36L, await database.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", winner.Id));
            Assert.Equal(2L, await database.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1", matchId));
        }
    }

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.",
        SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Real_http_concurrent_card_upgrade_retries_spend_once()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(TestContext.Current.CancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(60));
        var ct = timeout.Token;
        var player = await SeedNetworkPlayerAsync(database, "Upgrade", ct);
        await ExecuteGameplaySqlAsync(database, "UPDATE player_materials SET warrior_soul=5 WHERE player_id=$1", ct, player.Id);
        var port = ReserveLoopbackPort();
        await using var server = StartServer(database.ConnectionString, port);
        using var client = new HttpClient { BaseAddress = new Uri($"http://127.0.0.1:{port}") };
        await server.WaitUntilReadyAsync(client, ct);
        client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", player.Token);
        var cards = await client.GetFromJsonAsync<CardResponse[]>("/api/v1/cards", WebJson, ct);
        var before = Assert.Single(cards!, card => card.CardId == "C01");
        var results = await Task.WhenAll(Enumerable.Range(0, 16).Select(async _ =>
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/cards/C01/upgrade");
            request.Headers.Add("Idempotency-Key", "parallel-upgrade");
            request.Content = JsonContent.Create(new CardMutationRequest(before.Version), options: WebJson);
            using var response = await client.SendAsync(request, ct);
            response.EnsureSuccessStatusCode();
            return (await response.Content.ReadFromJsonAsync<CardMutationResponse>(WebJson, ct))!;
        }));
        Assert.All(results, result => Assert.Equal(results[0], result));
        Assert.Equal(1, results[0].Card.Level);
        Assert.Equal(0, results[0].Materials.WarriorSoul);
        Assert.Equal(1L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM economy_ledger WHERE player_id=$1 AND reason='card.upgrade'", player.Id));
    }

    private static async Task<(Guid Id, string Token)> SeedNetworkPlayerAsync(
        PostgresTestSchema database, string name, CancellationToken ct)
    {
        var token = SessionToken.Create();
        var now = DateTimeOffset.UtcNow;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            "gameplay-" + Guid.NewGuid().ToString("N"), name, SessionToken.Hash(token), now, now.AddHours(1), ct);
        return (player.UserId, token);
    }

    private static async Task<ClientWebSocket> ConnectGameplaySocketAsync(int port, string token, CancellationToken ct)
    {
        var socket = new ClientWebSocket();
        try
        {
            await socket.ConnectAsync(new Uri($"ws://127.0.0.1:{port}/ws/v1/session?access_token={Uri.EscapeDataString(token)}"), ct);
            Assert.Equal("session.connected", RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, ct)).Type);
            return socket;
        }
        catch { socket.Dispose(); throw; }
    }

    private static async Task<RoomSnapshotEventPayload> ReadGameplaySnapshotAsync(ClientWebSocket socket, CancellationToken ct) =>
        Assert.IsType<RoomSnapshotEventPayload>((await SendGameplayCommandAsync(socket,
            new("room.snapshot.read", Guid.NewGuid().ToString("N"), null, new RoomSnapshotCommandPayload()), ct)).Payload);

    private static async Task<(ClientCommand Command, ServerEvent Event)> SendGameplayMutationAsync(
        ClientWebSocket socket, string type, Func<RoomSnapshotEventPayload, object> payload, CancellationToken ct)
    {
        for (var attempt = 0; attempt < 20; attempt++)
        {
            var snapshot = await ReadGameplaySnapshotAsync(socket, ct);
            var command = new ClientCommand(type, Guid.NewGuid().ToString("N"), snapshot.RoomRevision, payload(snapshot));
            var result = await SendGameplayCommandAsync(socket, command, ct);
            if (result.Payload is CommandRejectedEventPayload rejected)
            {
                if (rejected.Detail.Contains("revision conflict", StringComparison.OrdinalIgnoreCase)) continue;
                Assert.Fail($"{type}: {rejected.Code}: {rejected.Detail}");
            }
            return (command, result);
        }
        throw new InvalidOperationException("Room did not accept the command after revision refreshes.");
    }

    private static async Task<ServerEvent> SendGameplayCommandAsync(ClientWebSocket socket, ClientCommand command, CancellationToken ct)
    {
        await socket.SendAsync(RealtimeProtobufCodec.EncodeClient(command), WebSocketMessageType.Binary, true, ct);
        while (true)
        {
            var result = RealtimeProtobufCodec.DecodeServer(await ReceiveBinaryAsync(socket, ct));
            if (result.RequestId == command.RequestId) return result;
        }
    }

    private static async Task WaitForGameplayConditionAsync(Func<Task<bool>> predicate, CancellationToken ct)
    {
        while (!await predicate()) await Task.Delay(TimeSpan.FromMilliseconds(100), ct);
    }

    private static async Task ExecuteGameplaySqlAsync(PostgresTestSchema database, string sql, CancellationToken ct, params object[] values)
    {
        await using var command = database.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(ct);
    }
}
