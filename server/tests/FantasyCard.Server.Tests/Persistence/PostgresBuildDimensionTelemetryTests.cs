using System.Text.Json;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresBuildDimensionTelemetryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task OriginalEventAndZeroAssetDifficultyReceiptKeepFrozenBuildDimensionsWhileOldReceiptReplayDoesNotBackfill()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"build-dimension-receipt");await db.MigrateAsync();
        var p=await CraftingTestInputs.CreateAsync(db);var config=GameConfigCatalog.Current;var start=DateTimeOffset.UtcNow;p.Clock.Now=start;
        var deckVersion=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",p.Player);
        var prepared=await new PreparationRepository(db.DataSource,p.Clock).CreateAsync(p.Player,"build-observation-prepare",
            new(HeroClassDto.Mage,deckVersion,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D0",p.Season.SeasonId),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var original=prepared.Preparation!.Snapshot;
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),73,NumericalRules.ForSeason(config,0),p.Season.ContextFor(0));
        room.AddPlayer(new(p.Player,HeroClass.Mage,original.CardIds,null,WeaponLevel:original.ClassWeaponLevel,InventoryCapacity:original.BackpackCapacity,
            SafeSlots:original.SafeSlotIndexes.Count,SafeSlotIndexes:original.SafeSlotIndexes,CardLevels:original.CardLevels,BorrowedTemplateId:original.BorrowedTemplateId,
            LootPreferenceElement:original.LootPreferenceElement));room.InitializeMap(ChaosMapGenerator.Generate(73,1),start);
        var player=room.GetPlayer(p.Player);
        // Declared cleared-monster checkpoint, not a successful gameplay campaign.
        foreach(var monster in player.Pve!.Monsters)monster.TakeDamage(int.MaxValue);player.Pve.RefreshPhase();Assert.True(room.TryEnterActionBar(p.Player));
        var saved=room.Capture();var exit=saved.Map!.Cells.First(c=>c.HasEvacuation).Position;
        room=BattleRoom.Restore(saved with{Players=saved.Players.Select(x=>x with{Position=exit,Pve=null,ClearedCells=[exit]}).ToArray()},CombatCardCatalog.Create(config),73);
        var duration=room.RequestExtraction(p.Player);p.Clock.Now=start+duration;room.Advance(duration,p.Clock.Now);var final=room.Capture();var match=Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)
            """,match,room.RoomId,config.Version,start,p.Season.SeasonId,p.Season.StatsVersion);
        // Declared admission checkpoint only; use the actual immutable preparation
        // policy rather than erase the required loot preference provenance.
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",prepared.Preparation.PreparationId);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state,preparation_id) VALUES($1,$2,false,'Active',$3)",match,p.Player,prepared.Preparation.PreparationId);
        using var metrics=new ServerMetrics();await new RoomSnapshotRepository(db.DataSource,p.Clock,metrics).SaveIfDueAsync(final,Ct);
        var roomReport=await new RoomEventTelemetryRepository(db.DataSource).ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        Assert.True(roomReport.FullyObserved);Assert.Equal(2,roomReport.Events.Count);Assert.NotEmpty(roomReport.BuildProfiles!);
        Assert.All(roomReport.Events,e=>{Assert.Equal(p.Season.SeasonId,e.Dimensions.SeasonId);Assert.Equal("D0",e.Dimensions.DifficultyId);Assert.Equal("Mage",e.Dimensions.HeroClass);Assert.NotNull(e.Dimensions.BuildType);Assert.Equal("EffectiveBaseCardMaxL0",e.Dimensions.GrowthStage);});
        Assert.All(roomReport.UnknownDimensionCounts!,pair=>Assert.Equal(0,pair.Value));
        Assert.Equal("BattleStart",Assert.Single(roomReport.Events,e=>e.Event.EventName=="battle_finished").BuildProfileBasis);
        Assert.Equal("EventState",Assert.Single(roomReport.Events,e=>e.Event.EventName=="loot_extracted").BuildProfileBasis);
        var settlements=new SettlementRepository(db.DataSource,p.Clock,metrics);await new SettlementCoordinator(settlements,p.Clock).ObserveAsync(match,final);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds"));
        var fingerprint=await FingerprintAsync(db);var lifecycle=new LifecycleEventTelemetryRepository(db.DataSource);
        var receipt=await lifecycle.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);var clear=Assert.Single(receipt.Events);
        Assert.Equal(roomReport.Events[^1].Dimensions.BuildType,clear.Dimensions.BuildType);Assert.Equal("EffectiveBaseCardMaxL0",clear.Dimensions.GrowthStage);
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        // Explicit pre-observation historical receipt fixture. Replay must retain it unchanged.
        await CraftingTestInputs.SqlAsync(db,"UPDATE match_settlements SET details_json=details_json-'telemetryProfile'-'telemetryProfileBasis' WHERE match_id=$1",match);
        var historical=await db.ScalarAsync<string>("SELECT details_json::text FROM match_settlements WHERE match_id=$1",match);
        await new SettlementCoordinator(new(db.DataSource,p.Clock,metrics),p.Clock).ObserveAsync(match,final);
        Assert.Equal(historical,await db.ScalarAsync<string>("SELECT details_json::text FROM match_settlements WHERE match_id=$1",match));
        var old=await lifecycle.ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);Assert.Null(Assert.Single(old.Events).Dimensions.BuildType);Assert.Null(old.Events[0].Dimensions.GrowthStage);
        Assert.Equal(1,old.UnknownDimensionCounts!["build"]);Assert.Equal(1,old.UnknownDimensionCounts["growth"]);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-frozen-build-dimensions",roomReport,receipt,old,readOnlyFingerprintUnchanged=true,historicalReceiptNotBackfilled=true,settlementAssetHolds=0,declaredTerminalFixture=true,successfulPlayerCasts=0,completedGameplayEncounters=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task MissingOriginalEventReferencesStayUnknownEvenWithAProfileAndPlayerSnapshotAvailable()
    {
        await using var db=await PostgresTestSchema.CreateAsync(false);PostgresSeasonMarketTests.RecordTelemetrySchema(db,"build-dimension-history");await db.MigrateAsync();
        var start=DateTimeOffset.UtcNow;var room=new BattleRoom(Guid.NewGuid(),"build-history-fixture",CombatCardCatalog.CreatePrototype(),73);var player=Guid.NewGuid();
        room.AddPlayer(new(player,HeroClass.Mage,Enumerable.Repeat("common-01",20).ToArray(),null));room.InitializeMap(ChaosMapGenerator.Generate(73,1),start);room.AbandonBattle(player);
        var snapshot=room.Capture();Assert.NotEmpty(snapshot.Observations!.Profiles!);
        snapshot=snapshot with{Observations=snapshot.Observations with{Events=snapshot.Observations.Events.Select(e=>e with{BuildProfileId=null,BattleBuildProfileId=null}).ToArray()}};
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at) VALUES($1,$2,'ChaosRealm','Standard',73,$3,'Running',$4)",match,room.RoomId,room.ConfigVersion,start);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,player);
        using var metrics=new ServerMetrics();await new RoomSnapshotRepository(db.DataSource,TimeProvider.System,metrics).SaveIfDueAsync(snapshot,Ct);var fingerprint=await FingerprintAsync(db);
        var report=await new RoomEventTelemetryRepository(db.DataSource).ReadAsync(start.AddSeconds(-1),start.AddMinutes(1),Ct);
        Assert.Equal(2,report.Events.Count);Assert.All(report.Events,e=>{Assert.Null(e.Dimensions.BuildType);Assert.Null(e.Dimensions.GrowthStage);Assert.Equal("MissingOriginal",e.BuildProfileBasis);});
        Assert.Empty(report.BuildProfiles!);Assert.Equal(2,report.UnknownDimensionCounts!["build"]);Assert.Equal(fingerprint,await FingerprintAsync(db));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-build-history-no-fallback",report,indexedProfileWasAvailable=true,currentPlayerSnapshotWasAvailable=true,noBackfill=true,readOnlyFingerprintUnchanged=true,completedGameplayEncounters=0});
    }

    private static Task<string> FingerprintAsync(PostgresTestSchema db)=>db.ScalarAsync<string>("""
        SELECT md5(concat_ws('|',
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id)::text,'[]') FROM player_season_wallets x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY instance_id)::text,'[]') FROM equipments x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY settlement_id)::text,'[]') FROM match_settlements x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY room_id)::text,'[]') FROM room_snapshots x)))
        """);
}
