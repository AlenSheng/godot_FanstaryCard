using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresCombatMeasurementTelemetryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private static CombatCardCatalog Catalog()=>new([new("low",new CombatCardEffect(DirectDamage:3))]);

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualCheckpointKeepsPveAndPvpCountersSeparateAndPrivateReadProjectionDoesNotChangeAssets()
    {
        await using var db=await Open("combat-counter-checkpoints");var start=DateTimeOffset.UtcNow;var (room,first,second)=await Fixture(db,start);var pve=room.GetPlayer(first).Pve!.BattleId;
        room.GetPlayer(first).Combat.Heal(5);room.GetPlayer(first).Combat.GainShield(100);room.Advance(TimeSpan.FromSeconds(1),start.AddSeconds(1));
        var duel=room.StartDuel(first,second,start.AddSeconds(1));room.Advance(TimeSpan.FromSeconds(2),start.AddSeconds(3));room.EndDuelSurvived(duel.DuelId,DuelEndReason.MutualLeave);room.Advance(TimeSpan.FromSeconds(1),start.AddSeconds(4));
        using var metrics=new ServerMetrics();var snapshots=new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics);await snapshots.SaveIfDueAsync(room.Capture(),Ct);
        var saved=(await new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics).GetAsync(room.RoomId,Ct))!;
        room=BattleRoom.Restore(saved,Catalog(),73);var previousRevision=room.Revision;
        // Match the original100ms actor cadence and10-revision checkpoint budget.
        for(var step=1;step<=10;step++)room.Advance(TimeSpan.FromMilliseconds(100),start.AddSeconds(4).AddMilliseconds(100*step));
        Assert.True(room.Revision-previousRevision>=10);await snapshots.SaveIfDueAsync(room.Capture(),Ct);
        var fingerprint=await Fingerprint(db);var repository=new RoomEventTelemetryRepository(db.DataSource);var report=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        Assert.True(report.FullyObserved);Assert.Equal(0,report.RoomsWithoutCombatObservations);Assert.Equal("0",report.OmittedCombatMeasurements);Assert.False(report.CombatRowsTruncated);
        var rows=report.CombatMeasurements!;var original=Assert.Single(rows,r=>r.PlayerId==first&&r.BattleId==pve);var pvp=Assert.Single(rows,r=>r.PlayerId==first&&r.BattleId==duel.DuelId);
        Assert.Equal(TimeSpan.FromSeconds(3).Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture),original.Counters[nameof(CombatMetric.AdvancedTicks)]);
        Assert.Equal(TimeSpan.FromSeconds(2).Ticks.ToString(System.Globalization.CultureInfo.InvariantCulture),pvp.Counters[nameof(CombatMetric.AdvancedTicks)]);
        Assert.Equal("5",original.Counters[nameof(CombatMetric.HealOverflow)]);Assert.Equal("65",original.Counters[nameof(CombatMetric.ShieldOverflow)]);Assert.Equal("3",pvp.Counters[nameof(CombatMetric.OpeningEffective)]);
        Assert.False(original.Partial);Assert.False(pvp.Partial);Assert.Equal(fingerprint,await Fingerprint(db));
        Assert.Equal(JsonSerializer.Serialize(report),JsonSerializer.Serialize(await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct)));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-combat-counter-checkpoints",report,readOnlyFingerprintUnchanged=true,originalPveSurvivesPvp=true,recreatedDomainContinues=true,declaredNoncombatCommandFixture=true,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task MissingAndInvalidHistoricalCountersAreExplicitAndNeverReconstructedFromCurrentCombatState()
    {
        await using var db=await Open("combat-counter-history");var start=DateTimeOffset.UtcNow;var (room,_,_)=await Fixture(db,start);using var metrics=new ServerMetrics();var snapshot=room.Capture();
        await new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics).SaveIfDueAsync(snapshot with{Observations=snapshot.Observations! with{Combat=null}},Ct);
        var repository=new RoomEventTelemetryRepository(db.DataSource);var fingerprint=await Fingerprint(db);var missing=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        Assert.Equal(1,missing.RoomsWithoutCombatObservations);Assert.Empty(missing.CombatMeasurements!);Assert.Equal(fingerprint,await Fingerprint(db));
        await CraftingTestInputs.SqlAsync(db,"UPDATE room_snapshots SET snapshot_json=jsonb_set(snapshot_json,'{observations,combat}','{\"schemaVersion\":999,\"rows\":[],\"omittedMeasurements\":0}'::jsonb) WHERE room_id=$1",room.RoomId);
        fingerprint=await Fingerprint(db);var invalid=await repository.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);Assert.Equal(1,invalid.InvalidRooms);Assert.Empty(invalid.CombatMeasurements!);Assert.Equal(fingerprint,await Fingerprint(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-combat-counter-history",missing,invalid,noCurrentStateBackfill=true,readOnlyFingerprintUnchanged=true,successfulPlayerCasts=0,completedGameplayCampaigns=0});
    }

    private static async Task<PostgresTestSchema> Open(string label)
    {
        var db=await PostgresTestSchema.CreateAsync(false);
        try{PostgresSeasonMarketTests.RecordTelemetrySchema(db,label);await db.MigrateAsync();return db;}
        catch{await db.DisposeAsync();throw;}
    }
    private static async Task<(BattleRoom Room,Guid First,Guid Second)> Fixture(PostgresTestSchema db,DateTimeOffset start)
    {
        var room=new BattleRoom(Guid.NewGuid(),"combat-counter-fixture",Catalog(),73);var first=Guid.NewGuid();var second=Guid.NewGuid();
        room.AddPlayer(new(first,HeroClass.Mage,Enumerable.Repeat("low",20).ToArray(),null));room.AddPlayer(new(second,HeroClass.Priest,Enumerable.Repeat("low",20).ToArray(),null));room.InitializeMap(ChaosMapGenerator.Generate(73,2),start);
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,$3,'Running',$4)",match,room.RoomId,room.ConfigVersion,start);
        foreach(var id in new[]{first,second})await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,id);
        return(room,first,second);
    }
    private static Task<string> Fingerprint(PostgresTestSchema db)=>db.ScalarAsync<string>("""
        SELECT md5(concat_ws('|',(SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id)::text,'[]') FROM player_season_wallets x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY instance_id)::text,'[]') FROM equipments x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY room_id)::text,'[]') FROM room_snapshots x)))
        """);
}
