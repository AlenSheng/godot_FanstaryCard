using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresRoomEventTelemetryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task NewestCheckpointPreservesCumulativeEventsAndRestartContinuesOriginalIdsWithoutChangingAssetsOnQuery()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"room-event-checkpoint");await db.MigrateAsync();
        var start=DateTimeOffset.UtcNow;var (match,room)=await FixtureAsync(db,start);using var metrics=new ServerMetrics();
        var snapshots=new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics);await snapshots.SaveIfDueAsync(room.Capture(),Ct);
        var ids=room.Capture().Players.Select(p=>p.PlayerId).ToArray();room.GetPlayer(ids[0]).Inventory.TryAdd(new("gold",ExplorationItemKind.Gold,9));
        room.AbandonBattle(ids[0]);room.AbandonBattle(ids[1]);
        // Deliberately save only the latest state, as the actor may coalesce the intermediate one.
        await snapshots.SaveIfDueAsync(room.Capture(),Ct);var saved=(await new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics).GetAsync(room.RoomId,Ct))!;
        Assert.Equal(4,saved.Observations!.LastSequence);var restored=BattleRoom.Restore(saved,CombatCardCatalog.CreatePrototype(),73);
        restored.AbandonBattle(ids[2]);await snapshots.SaveIfDueAsync(restored.Capture(),Ct);
        var repository=new RoomEventTelemetryRepository(db.DataSource);var fingerprint=await FingerprintAsync(db);
        var report=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);Assert.True(report.FullyObserved);Assert.Equal(6,report.Events.Count);
        Assert.Equal(6,report.Events.Select(e=>e.EventId).Distinct().Count());Assert.All(report.Events,e=>Assert.Equal(match,e.MatchId));
        var loss=Assert.Single(report.Events,e=>e.Event.EventName=="loot_lost"&&e.Event.Items.Count>0);Assert.Equal(9,Assert.Single(loss.Event.Items).Quantity);
        Assert.Equal("RelicCustodyPendingSettlement",loss.Event.Result);Assert.Equal("0",report.DroppedEvents);Assert.Equal(0,report.OmittedItems);
        Assert.Equal(JsonSerializer.Serialize(report),JsonSerializer.Serialize(await new RoomEventTelemetryRepository(db.DataSource).ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct)));
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-room-event-checkpoints",report,originalPrefixSurvivesNewestOnlySave=true,restartSequenceContinues=true,queryFingerprintUnchanged=true,declaredRoomCommandFixture=true,successfulPlayerCasts=0,completedGameplayEncounters=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task OldMissingAndCorruptObservationsRemainExplicitGapsAndReadQueriesDoNotRepairThem()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"room-event-history");await db.MigrateAsync();
        var start=DateTimeOffset.UtcNow;var (_,room)=await FixtureAsync(db,start);using var metrics=new ServerMetrics();
        await new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics).SaveIfDueAsync(room.Capture() with{Observations=null},Ct);
        var repository=new RoomEventTelemetryRepository(db.DataSource);var missing=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        Assert.Equal(1,missing.LegacyUnobservedRooms);Assert.False(missing.FullyObserved);Assert.Empty(missing.Events);
        await CraftingTestInputs.SqlAsync(db,"UPDATE room_snapshots SET snapshot_json=jsonb_set(snapshot_json,'{observations}','{\"schemaVersion\":999,\"lastSequence\":0,\"droppedEvents\":0,\"events\":[]}'::jsonb) WHERE room_id=$1",room.RoomId);
        var raw=await db.ScalarAsync<string>("SELECT (snapshot_json->'observations')::text FROM room_snapshots WHERE room_id=$1",room.RoomId);
        var fingerprint=await FingerprintAsync(db);var invalid=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        Assert.Equal(1,invalid.InvalidRooms);Assert.False(invalid.FullyObserved);Assert.Empty(invalid.Events);Assert.Equal(fingerprint,await FingerprintAsync(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-room-event-history-gaps",missing,invalid,rawCorruptObservation=raw,queryFingerprintUnchanged=true,noHistoryBackfill=true,completedGameplayEncounters=0});
    }

    private static async Task<(Guid Match,BattleRoom Room)> FixtureAsync(PostgresTestSchema db,DateTimeOffset start)
    {
        var room=new BattleRoom(Guid.NewGuid(),"observed-checkpoint-fixture",CombatCardCatalog.CreatePrototype(),73);var deck=Enumerable.Range(1,20).Select(i=>$"common-{i:D2}").ToArray();
        foreach(var hero in new[]{HeroClass.Mage,HeroClass.Priest,HeroClass.Guardian})room.AddPlayer(new(Guid.NewGuid(),hero,deck,null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,3),start);var match=Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,$3,'Running',$4)",match,room.RoomId,room.ConfigVersion,start);
        foreach(var player in room.Capture().Players)await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,player.PlayerId);
        return(match,room);
    }
    private static Task<string> FingerprintAsync(PostgresTestSchema db)=>db.ScalarAsync<string>("""
        SELECT md5(concat_ws('|',
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id)::text,'[]') FROM player_season_wallets x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY instance_id)::text,'[]') FROM equipments x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY movement_id)::text,'[]') FROM inventory_movements x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY room_id)::text,'[]') FROM room_snapshots x)))
        """);
}
