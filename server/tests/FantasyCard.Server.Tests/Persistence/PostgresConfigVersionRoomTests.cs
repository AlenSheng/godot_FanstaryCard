using System.Security.Cryptography;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresConfigVersionRoomTests
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct => TestContext.Current.CancellationToken;

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData("valid")]
    [InlineData("missing")]
    [InlineData("corrupt")]
    [Trait("Category","PostgresIntegration")]
    public async Task RecoveryUsesActualArchivedValuesAndQuarantinesOnlyTheUnavailableVersion(string archiveState)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        using var archive = new ConfigArchiveDirectory();
        var old = PublishedConfigTestInputs.Create("recovery-old");
        var next = PublishedConfigTestInputs.Create("recovery-next",true);
        var begins = SeasonDefinition.FromCalendarDays("calendar-control",new DateOnly(2026,9,1),old.Catalog.Version,"archive-control-stats").StartsAtUtc;
        var clock = new Clock(begins.AddDays(43));
        var oldSeason = new SeasonDefinition("old-config-season","season-v1",old.Catalog.Version,"archive-control-stats",begins,begins.AddDays(42),5);
        var nextSeason = new SeasonDefinition("next-config-season","season-v1",next.Catalog.Version,"archive-control-stats",begins.AddDays(42),begins.AddDays(84),5);
        var seasons = new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(oldSeason,new string('a',64),Ct);
        await seasons.PublishAsync(nextSeason,new string('b',64),Ct);
        var first = await CreateRoomAsync(db,clock,old.Catalog,oldSeason.ContextFor(5));
        var second = await CreateRoomAsync(db,clock,next.Catalog,nextSeason.ContextFor(5));
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource,clock,metrics);
        await snapshots.SaveIfDueAsync(first.Room.Capture(),Ct);
        await snapshots.SaveIfDueAsync(second.Room.Capture(),Ct);
        var raw = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",first.Room.RoomId);
        if (archiveState != "missing")
        {
            var bytes = old.Bytes.ToArray();
            if (archiveState == "corrupt") bytes[^1] ^= 1;
            PublishedConfigTestInputs.Store(archive.Root,old.Catalog.Version,bytes,old.Hash);
        }
        var configurations = new PublishedConfigCatalogs(next.Catalog,archive.Root);
        var health = new RoomRecoveryState();
        await using var rooms = new RoomRegistry(clock);
        await new RoomRecoveryWorker(snapshots,rooms,health,clock,NullLogger<RoomRecoveryWorker>.Instance,configurations).StartAsync(Ct);
        Assert.True(rooms.ContainsRoom(second.Room.RoomId));
        await AssertCastAsync(rooms,second.Player.UserId,345,22,clock);
        if (archiveState == "valid")
        {
            Assert.True(health.Capture().IsHealthy);
            await AssertCastAsync(rooms,first.Player.UserId,172,21,clock);
        }
        else
        {
            Assert.False(health.Capture().IsHealthy);
            Assert.Equal([first.Room.RoomId],health.Capture().FailedRoomIds);
            Assert.False(rooms.ContainsRoom(first.Room.RoomId));
            Assert.Equal(raw,await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",first.Room.RoomId));
        }
        Assert.Equal(1,await db.ScalarAsync<int>("SELECT level FROM player_cards WHERE player_id=$1 AND card_id='C01'",first.Player.UserId));
    }

    [Theory(Skip = "Requires isolated PostgreSQL.", SkipUnless = nameof(HasTestDatabase))]
    [InlineData(true)]
    [InlineData(false)]
    [Trait("Category","PostgresIntegration")]
    public async Task TerminalReadRequiresTheArchivedCatalogAndNeverRegistersOrRewritesTheRoom(bool available)
    {
        await using var db = await PostgresTestSchema.CreateAsync(migrate:true);
        using var archive = new ConfigArchiveDirectory();
        var old = PublishedConfigTestInputs.Create("terminal-old");
        var next = PublishedConfigTestInputs.Create("terminal-next",true);
        var begins = SeasonDefinition.FromCalendarDays("calendar-control",new DateOnly(2026,9,1),old.Catalog.Version,"archive-control-stats").StartsAtUtc;
        var clock = new Clock(begins.AddDays(43));
        var season = new SeasonDefinition("terminal-season","season-v1",old.Catalog.Version,"archive-control-stats",begins,begins.AddDays(42),5);
        await new SeasonRepository(db.DataSource,clock).PublishAsync(season,new string('c',64),Ct);
        var fixture = await CreateRoomAsync(db,clock,old.Catalog,season.ContextFor(5));
        var snapshot = fixture.Room.Capture();
        snapshot = snapshot with { Players = snapshot.Players.Select(p => p with { Phase = RoomPlayerPhase.Extracted,Pve = null }).ToArray() };
        await Sql(db,"UPDATE match_players SET state='Settled' WHERE match_id=$1",fixture.Match);
        using var metrics = new ServerMetrics();
        var snapshots = new RoomSnapshotRepository(db.DataSource,clock,metrics);
        await snapshots.SaveIfDueAsync(snapshot,Ct);
        var raw = await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",fixture.Room.RoomId);
        if (available) PublishedConfigTestInputs.Store(archive.Root,old.Catalog.Version,old.Bytes,old.Hash);
        await using var rooms = new RoomRegistry(clock);
        var router = new RealtimeCommandRouter(new RealtimeEventStore(clock),clock,rooms,
            roomSnapshotRepository:snapshots,configurations:new PublishedConfigCatalogs(next.Catalog,archive.Root));
        var response = await router.RouteAsync(fixture.Player,new("room.snapshot.read","old-read",null,new RoomSnapshotCommandPayload(),
            fixture.Room.RoomId,fixture.Match),"config-archive-test",Ct);
        Assert.Equal(available?"room.snapshot":"error.command_rejected",Assert.Single(response).Type);
        if (available) Assert.Equal(old.Catalog.Version,Assert.IsType<RoomSnapshotEventPayload>(response[0].Payload).ConfigVersion);
        Assert.False(rooms.ContainsRoom(fixture.Room.RoomId));
        Assert.Equal(raw,await db.ScalarAsync<string>("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1",fixture.Room.RoomId));
    }

    private static async Task AssertCastAsync(RoomRegistry rooms,Guid playerId,int damage,int capacity,Clock clock)
    {
        Assert.True(rooms.TryGetForPlayer(playerId,out var actor,out _));
        var snapshot = await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);
        var player = snapshot.Players.Single(p => p.PlayerId == playerId);
        Assert.Equal(capacity,player.Inventory!.Capacity);
        await actor.ExecuteAsync(new PlayRoomCardsCommand(playerId,player.Pve!.BattleId,"fire-bat",
            player.Combat.Deck.Hand.Select(c => c.InstanceId).ToArray(),snapshot.Revision,clock.GetUtcNow(),$"1:{Guid.NewGuid():N}"),Ct);
        var after = await actor.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);
        Assert.Equal(1000-damage,Assert.Single(after.Players.Single(p => p.PlayerId == playerId).Pve!.Monsters).Hp);
    }

    private static async Task<(BattleRoom Room,Guid Match,PlayerProfile Player)> CreateRoomAsync(PostgresTestSchema db,Clock clock,
        GameConfigCatalog configuration,SeasonContext context)
    {
        var player = await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(
            Guid.NewGuid().ToString("N"),"Archive "+Guid.NewGuid().ToString("N")[..8],RandomNumberGenerator.GetBytes(32),clock.GetUtcNow(),clock.GetUtcNow().AddHours(1),Ct);
        await Sql(db,"UPDATE player_cards SET level=1 WHERE player_id=$1 AND unlocked",player.UserId);
        var room = PublishedConfigTestInputs.WithTarget(PublishedConfigTestInputs.Room(configuration,player.UserId,withMap:true),configuration);
        PublishedConfigTestInputs.PutC01InHand(room.GetPlayer(player.UserId));
        room = BattleRoom.Restore(room.Capture() with { Season = context },CombatCardCatalog.Create(configuration),73);
        var match = Guid.NewGuid();
        await Sql(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm',$3,73,$4,'Running',$5,$6,$7,$8)
            """,match,room.RoomId,context.DifficultyId,configuration.Version,clock.GetUtcNow(),context.SeasonId,context.RulesetId,context.StatsVersion);
        await Sql(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,player.UserId);
        return (room,match,player);
    }

    private static async Task Sql(PostgresTestSchema db,string sql,params object[] values)
    {
        await using var command = db.DataSource.CreateCommand(sql);
        foreach (var value in values) command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }

    private sealed class Clock(DateTimeOffset now) : TimeProvider
    {
        public override DateTimeOffset GetUtcNow() => now;
    }
}
