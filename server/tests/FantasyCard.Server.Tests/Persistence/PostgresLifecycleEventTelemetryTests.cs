using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresLifecycleEventTelemetryTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualDiscardAndEnhancementConsumptionAreOnceOnlyWithLobbyDifficultyUnknownAndUnclassifiedHistoryVisible()
    {
        await using var db=await OpenAsync("destruction-events");var p=await CraftingTestInputs.CreateAsync(db);
        var discarded=await CraftingTestInputs.ItemAsync(db,p);var target=await CraftingTestInputs.ItemAsync(db,p,slot:"Head",level:3);
        var material=await CraftingTestInputs.ItemAsync(db,p);var begin=DateTimeOffset.UtcNow.AddSeconds(-1);
        var discard=new DiscardEquipmentRequest([new(discarded,1)],p.Season.SeasonId);
        await Task.WhenAll(p.Progression.DiscardEquipmentAsync(p.Player,"event-discard",discard,Ct),p.Progression.DiscardEquipmentAsync(p.Player,"event-discard",discard,Ct));
        var enhance=new EnhanceEquipmentRequest(1,material,MaterialExpectedVersion:1);
        var enhanced=await p.Progression.EnhanceEquipmentAsync(p.Player,target,"event-enhance",enhance,Ct);
        Assert.Equal(4,enhanced.Equipment.Level);
        await new ProgressionRepository(db.DataSource,p.Clock).EnhanceEquipmentAsync(p.Player,target,"event-enhance",enhance,Ct);
        var end=DateTimeOffset.UtcNow.AddSeconds(1);var repository=new LifecycleEventTelemetryRepository(db.DataSource);var fingerprint=await FingerprintAsync(db);
        var report=await repository.ReadAsync(begin,end,Ct);Assert.True(report.SourcesComplete);Assert.Equal(2,report.Events.Count);
        Assert.Equal(2,report.PhysicalFlows.Sum(g=>g.Items));Assert.All(report.Events,e=>{Assert.Equal("item_destroyed",e.EventName);Assert.Equal("Destroy",e.PhysicalFlow);Assert.Equal("Purple",e.Quality);Assert.Null(e.Dimensions.DifficultyId);Assert.Equal("Lobby",e.Dimensions.CellType);});
        Assert.Equal(2,report.Events.Select(e=>e.ItemId).Distinct().Count());Assert.DoesNotContain(report.Events,e=>e.ItemId==target);
        Assert.Equal(JsonSerializer.Serialize(report),JsonSerializer.Serialize(await new LifecycleEventTelemetryRepository(db.DataSource).ReadAsync(begin,end,Ct)));
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        // Declared historical source fixtures: an unknown terminal reason and a
        // valid old discard without any original realm. Neither is relabeled.
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,created_at)
            VALUES(gen_random_uuid(),$1,$2,'Inventory','Recycled','historical.unknown',$3),
                (gen_random_uuid(),$1,$2,'Inventory','Recycled','equipment.discard',$3)
            """,p.Player,target,begin.AddMilliseconds(100));
        var incomplete=await repository.ReadAsync(begin,end,Ct);var source=Assert.Single(incomplete.Sources,c=>c.Source=="inventory_movements");
        Assert.Equal(1,source.UnclassifiedRows);Assert.Equal(1,source.MissingRealmRows);Assert.False(incomplete.SourcesComplete);
        Assert.Null(Assert.Single(incomplete.Events,e=>e.ItemId==target).Dimensions.SeasonId);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-destruction-events",report,incomplete,queryFingerprintUnchanged=true,replayOnce=true,mainItemNotDestroyed=true,gameplayCasts=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualPagedArchiveHasOriginalSeasonAndIdentityAndNeverCountsAlreadyConsumedItemsAsDestroyedAgain()
    {
        await using var db=await OpenAsync("archive-events");var p=await CraftingTestInputs.CreateAsync(db);
        var discarded=await CraftingTestInputs.ItemAsync(db,p);var survivor=await CraftingTestInputs.ItemAsync(db,p,"Orange","Head");
        await p.Progression.DiscardEquipmentAsync(p.Player,"before-archive",new([new(discarded,1)],p.Season.SeasonId),Ct);
        p.Clock.Now=p.Season.EndsAtUtc;var first=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,1,Ct);
        var second=await new SeasonRepository(db.DataSource,p.Clock).AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,1,Ct);
        var replay=await p.Seasons.AdvanceArchivePageAsync(p.Player,p.Season.SeasonId,1,Ct);Assert.Equal(0,replay.ArchivedItems);Assert.Equal(first.JobId,second.JobId);
        var repository=new LifecycleEventTelemetryRepository(db.DataSource);var fingerprint=await FingerprintAsync(db);
        var report=await repository.ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct);
        var equipmentEvents=report.Events.Where(e=>e.AssetKind=="Equipment").ToArray();
        Assert.True(report.SourcesComplete);Assert.Equal(2,equipmentEvents.Length);Assert.All(equipmentEvents,e=>{Assert.Equal("season_asset_archived",e.EventName);Assert.Equal("Archive",e.PhysicalFlow);Assert.Equal(p.Season.SeasonId,e.Dimensions.SeasonId);Assert.Equal(p.Season.ConfigVersion,e.Dimensions.ConfigVersion);Assert.Null(e.Dimensions.DifficultyId);});
        Assert.Equal("Recycled",Assert.Single(report.Events,e=>e.ItemId==discarded).ToLocation);
        Assert.Equal("SeasonArchive",Assert.Single(report.Events,e=>e.ItemId==survivor).ToLocation);
        Assert.Equal(2,report.PhysicalFlows.Sum(g=>g.Items));Assert.DoesNotContain(report.PhysicalFlows,g=>g.PhysicalFlow=="Destroy");
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        // Published definitions are immutable, so source realm cannot be silently changed later.
        var conflicting=SeasonDefinition.FromCalendarDays(p.Season.SeasonId,new(2026,11,1),"unrelated-version",p.Season.StatsVersion,highestOpenDifficulty:5);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Seasons.PublishAsync(conflicting,new string('a',64),Ct));
        Assert.Equal(JsonSerializer.Serialize(report),JsonSerializer.Serialize(await repository.ReadAsync(p.Clock.Now.AddSeconds(-1),p.Clock.Now.AddSeconds(1),Ct)));
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-equipment-archive-events",report,queryFingerprintUnchanged=true,originalDefinitionImmutable=true,alreadyDestroyedNotDestroyedAgain=true,gameplayCasts=0});
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task OriginalDifficultyReceiptHasRunSummaryHeroAndHumanKindWhileDeathAndReplayDoNotInventAnotherClear()
    {
        await using var db=await OpenAsync("difficulty-events");var p=await CraftingTestInputs.CreateAsync(db);using var metrics=new ServerMetrics();
        var fixture=await TerminalAsync(db,p,RoomPlayerPhase.Extracted);var dead=await TerminalAsync(db,p,RoomPlayerPhase.Dead);
        await new SettlementCoordinator(new(db.DataSource,p.Clock,metrics),p.Clock).ObserveAsync(fixture.Match,fixture.Snapshot);
        await new SettlementCoordinator(new(db.DataSource,p.Clock,metrics),p.Clock).ObserveAsync(fixture.Match,fixture.Snapshot);
        await new SettlementCoordinator(new(db.DataSource,p.Clock,metrics),p.Clock).ObserveAsync(dead.Match,dead.Snapshot);
        var repository=new LifecycleEventTelemetryRepository(db.DataSource);var fingerprint=await FingerprintAsync(db);
        var from=p.Clock.Now.AddSeconds(-1);var to=p.Clock.Now.AddSeconds(1);var report=await repository.ReadAsync(from,to,Ct);
        Assert.True(report.SourcesComplete);var row=Assert.Single(report.Events);Assert.Equal("difficulty_cleared",row.EventName);Assert.Equal(fixture.Match,row.MatchId);
        Assert.Equal("D0",row.Dimensions.DifficultyId);Assert.Equal("Mage",row.Dimensions.HeroClass);Assert.Equal("Human",row.Dimensions.PlayerKind);Assert.Equal("RunSummary",row.Dimensions.CellType);Assert.Equal("Extracted",row.Dimensions.Result);
        Assert.Null(row.Dimensions.BuildType);Assert.Null(row.Dimensions.GrowthStage);Assert.False(row.EliteCleared);Assert.False(row.BossCleared);Assert.Empty(report.PhysicalFlows);
        Assert.Equal(fingerprint,await FingerprintAsync(db));
        // Window is half-open: an event exactly at to is not included.
        Assert.Empty((await repository.ReadAsync(from,p.Clock.Now,Ct)).Events);
        PostgresSeasonMarketTests.WriteTelemetryProof(new{kind="actual-difficulty-events",report,queryFingerprintUnchanged=true,deathAndReplayNotClears=true,declaredTerminalCheckpointFixture=true,completedGameplayEncounters=0,gameplayCasts=0});
    }

    private static async Task<PostgresTestSchema> OpenAsync(string label)
    {
        var db=await PostgresTestSchema.CreateAsync(false);
        try{PostgresSeasonMarketTests.RecordTelemetrySchema(db,label);await db.MigrateAsync();return db;}
        catch{await db.DisposeAsync();throw;}
    }

    private static async Task<(Guid Match,BattleRoomSnapshot Snapshot)> TerminalAsync(PostgresTestSchema db,CraftingPlayer p,RoomPlayerPhase phase)
    {
        // Explicit terminal checkpoint fixture, not a completed combat route.
        var room=new BattleRoom(Guid.NewGuid(),p.Season.ConfigVersion,CombatCardCatalog.Create(GameConfigCatalog.Current),73,season:p.Season.ContextFor(0));
        var cards=Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"MAG-{i:D2}")).ToArray();
        room.AddPlayer(new(p.Player,HeroClass.Mage,cards,null));room.InitializeMap(ChaosMapGenerator.Generate(73,1));var snapshot=room.Capture();
        snapshot=snapshot with{Players=snapshot.Players.Select(player=>player with{Phase=phase,Pve=null}).ToArray()};var match=Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)
            """,match,room.RoomId,p.Season.ConfigVersion,p.Clock.Now,p.Season.SeasonId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,p.Player);
        return(match,snapshot);
    }

    private static Task<string> FingerprintAsync(PostgresTestSchema db)=>db.ScalarAsync<string>("""
        SELECT md5(concat_ws('|',
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id)::text,'[]') FROM player_season_wallets x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY instance_id)::text,'[]') FROM equipments x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY movement_id)::text,'[]') FROM inventory_movements x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY settlement_id)::text,'[]') FROM match_settlements x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY settlement_id)::text,'[]') FROM season_difficulty_completions x),
            (SELECT coalesce(jsonb_agg(to_jsonb(x) ORDER BY player_id,season_id,item_id)::text,'[]') FROM season_archive_items x)))
        """);
}
