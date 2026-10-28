using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresBotOnlyRoomTerminationTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Bot_only_actor_tick_completes_match_without_creating_player_assets()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var matchId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "no-human-lifecycle", CombatCardCatalog.CreatePrototype(), 771);
        var cards = Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray();
        var botIds = new[] { Guid.NewGuid(), Guid.NewGuid() };
        room.AddPlayer(new(botIds[0], HeroClass.Mage, cards, null, IsBot: true));
        room.AddPlayer(new(botIds[1], HeroClass.Guardian, cards, null, IsBot: true));
        room.InitializeMap(ChaosMapGenerator.Generate(771, botIds.Length));
        Assert.All(room.Capture().Players, player => Assert.Equal(RoomPlayerPhase.Pve, player.Phase));

        await using (var insert = database.DataSource.CreateCommand(
            """
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at)
            VALUES($1,$2,'ChaosRealm','Standard',771,'no-human-lifecycle','Running',CURRENT_TIMESTAMP)
            """))
        {
            insert.Parameters.AddWithValue(matchId);
            insert.Parameters.AddWithValue(room.RoomId);
            await insert.ExecuteNonQueryAsync(ct);
        }
        foreach (var botId in botIds)
        {
            await using var insert = database.DataSource.CreateCommand(
                "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,true,'Active')");
            insert.Parameters.AddWithValue(matchId);
            insert.Parameters.AddWithValue(botId);
            await insert.ExecuteNonQueryAsync(ct);
        }

        using var metrics = new ServerMetrics();
        var repository = new SettlementRepository(database.DataSource, TimeProvider.System, metrics);
        var coordinator = new SettlementCoordinator(repository);
        Assert.Empty(await repository.GetTerminalRoomIdsAsync([room.RoomId], ct));
        BattleRoomSnapshot terminal;
        await using (var actor = new RoomActor(room, TimeProvider.System, startTicker: false,
            snapshotObserver: snapshot => coordinator.ObserveAsync(matchId, snapshot)))
        {
            terminal = await actor.ExecuteAsync(new AdvanceRoomTimeCommand(RoomActor.TickInterval), ct);
            await actor.ExecuteAsync(new AdvanceRoomTimeCommand(RoomActor.TickInterval), ct);
        }

        Assert.All(terminal.Players, player =>
        {
            Assert.True(player.IsBot);
            Assert.Equal(RoomPlayerPhase.Extracted, player.Phase);
            Assert.Null(player.Pve);
            Assert.Null(player.BotPveRemaining);
            Assert.Null(player.RewardChoice);
        });
        Assert.Empty(terminal.Duels);
        Assert.Equal("Completed", await database.ScalarAsync<string>(
            "SELECT status FROM matches WHERE match_id=$1", matchId));
        Assert.Equal(2L, await database.ScalarAsync<long>(
            "SELECT count(*) FROM match_players WHERE match_id=$1 AND is_bot AND state='Settled' AND settled_at IS NOT NULL", matchId));
        Assert.Equal(new[] { room.RoomId }, await repository.GetTerminalRoomIdsAsync([room.RoomId], ct));
        var settledTimes = await database.ScalarAsync<string>(
            "SELECT json_agg(settled_at ORDER BY player_id)::text FROM match_players WHERE match_id=$1", matchId);

        // A fresh coordinator models replay after the in-memory completion cache is lost.
        await new SettlementCoordinator(repository).ObserveAsync(matchId, terminal);

        Assert.Equal(settledTimes, await database.ScalarAsync<string>(
            "SELECT json_agg(settled_at ORDER BY player_id)::text FROM match_players WHERE match_id=$1", matchId));
        foreach (var table in new[]
        {
            "players", "match_settlements", "settlement_asset_holds", "economy_ledger",
            "inventory_movements", "equipments", "player_wallets", "player_cards", "player_materials",
            "relic_piles", "relic_items"
        })
            Assert.Equal(0L, await database.ScalarAsync<long>($"SELECT count(*) FROM {table}"));
    }
}
