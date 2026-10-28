using System.Security.Cryptography;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresTerminalContextTests
{
    public static bool HasTestDatabase => PostgresMigrationTests.HasTestDatabase;

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(RoomPlayerPhase.Dead)]
    [InlineData(RoomPlayerPhase.Extracted)]
    [Trait("Category", "PostgresIntegration")]
    public async Task Owned_terminal_fallback_reads_old_match_and_cancels_without_mutating_new_room_or_assets(RoomPlayerPhase phase)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await PlayerAsync(db);
        var match = Guid.NewGuid();
        var oldRoom = CreateRoom(player.UserId);
        var snapshot = oldRoom.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(value => value with { Phase = phase, Pve = null }).ToArray() };
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',17,'test','Running',now())", match, oldRoom.RoomId);
        await Sql(db, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Settled')", match, player.UserId);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        await snapshots.SaveIfDueAsync(snapshot, ct);
        var newRoom = CreateRoom(player.UserId);
        var newBefore = newRoom.Capture();
        var walletBefore = await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId);
        var ledgerBefore = await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger");
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(newRoom, Guid.NewGuid(), startTicker: false);
        var router = new RealtimeCommandRouter(new RealtimeEventStore(TimeProvider.System), TimeProvider.System, registry, roomSnapshotRepository: snapshots);

        var read = await router.RouteAsync(player, new("room.snapshot.read", "old-read", null, new RoomSnapshotCommandPayload(), oldRoom.RoomId, match), "trace", ct);
        Assert.Equal("room.snapshot", Assert.Single(read).Type);
        var projected = Assert.IsType<RoomSnapshotEventPayload>(read[0].Payload);
        Assert.Equal((oldRoom.RoomId, match), (projected.RoomId, projected.MatchId));
        var command = new ClientCommand("battle.abandon", "old-write", snapshot.Revision, new BattleAbandonCommandPayload(), oldRoom.RoomId, match);
        var cancelled = await router.RouteAsync(player, command, "trace", ct);
        Assert.Collection(cancelled,
            message => Assert.Equal("room.command_cancelled", message.Type),
            message => Assert.Equal("room.snapshot", message.Type));
        Assert.Equivalent(cancelled, await router.RouteAsync(player, command, "trace", ct), strict: true);
        Assert.Equivalent(newBefore, newRoom.Capture(), strict: true);
        Assert.Equivalent(snapshot, await snapshots.GetAsync(oldRoom.RoomId, ct), strict: true);
        Assert.Equal(walletBefore, await db.ScalarAsync<long>("SELECT gold FROM player_wallets WHERE player_id=$1", player.UserId));
        Assert.Equal(ledgerBefore, await db.ScalarAsync<long>("SELECT count(*) FROM economy_ledger"));
    }

    [Fact(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Membership_match_pair_bot_and_durable_phase_are_all_required()
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var owner = await PlayerAsync(db);
        var foreign = await PlayerAsync(db);
        var match = Guid.NewGuid();
        var room = CreateRoom(owner.UserId);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource, TimeProvider.System, metrics);
        await Sql(db, "INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',17,'test','Running',now())", match, room.RoomId);
        await Sql(db, "INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Settled')", match, owner.UserId);
        await snapshots.SaveIfDueAsync(room.Capture(), ct);
        Assert.Null(await snapshots.GetOwnedTerminalAsync(owner.UserId, room.RoomId, match, ct));
        room.AbandonBattle(owner.UserId);
        await snapshots.SaveIfDueAsync(room.Capture(), ct);
        Assert.NotNull(await snapshots.GetOwnedTerminalAsync(owner.UserId, room.RoomId, match, ct));
        Assert.Null(await snapshots.GetOwnedTerminalAsync(foreign.UserId, room.RoomId, match, ct));
        Assert.Null(await snapshots.GetOwnedTerminalAsync(owner.UserId, room.RoomId, Guid.NewGuid(), ct));
        Assert.Null(await snapshots.GetOwnedTerminalAsync(owner.UserId, Guid.NewGuid(), match, ct));
        await Sql(db, "UPDATE match_players SET state='Active' WHERE match_id=$1", match);
        Assert.Null(await snapshots.GetOwnedTerminalAsync(owner.UserId, room.RoomId, match, ct));
        await Sql(db, "UPDATE match_players SET state='Settled',is_bot=true WHERE match_id=$1", match);
        Assert.Null(await snapshots.GetOwnedTerminalAsync(owner.UserId, room.RoomId, match, ct));
    }

    private static BattleRoom CreateRoom(Guid playerId)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 17);
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(17, 1));
        return room;
    }

    private static async Task<PlayerProfile> PlayerAsync(PostgresTestSchema db)
    {
        var now = DateTimeOffset.UtcNow;
        return await new IdentityRepository(db.DataSource, new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"), "Terminal " + Guid.NewGuid().ToString("N")[..8], RandomNumberGenerator.GetBytes(32), now, now.AddHours(1), TestContext.Current.CancellationToken);
    }

    private static async Task Sql(PostgresTestSchema db, string sql, params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(TestContext.Current.CancellationToken);
    }
}
