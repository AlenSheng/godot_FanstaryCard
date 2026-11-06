using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresHistoricalEquipmentTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData(false)][InlineData(true)]
    public async Task AbsentTraitPreparesAndResumesOriginalLaunchWithoutInventingSpeedOrSpendingTwice(bool admitted)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var f=await Create(db,archive.Root,null);var preparations=new PreparationRepository(db.DataSource,f.Clock,f.Catalogs);
        var created=await preparations.CreateAsync(f.Player,"history-prepare",Request(f),Ct);Assert.Equal(CreatePreparationStatus.Created,created.Status);
        Assert.Null(Assert.Single(created.Preparation!.Snapshot.EquipmentSnapshots!).SecondaryTrait);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,f.Clock,metrics,configurations:f.Catalogs);
        await matcher.EnqueueAsync(f.Player,"history-queue",new(created.Preparation.PreparationId),Ct);f.Clock.Now=f.Clock.Now.AddSeconds(31);
        var pending=Assert.IsType<PendingMatch>(await matcher.TryCreateMatchAsync(Ct));await matcher.MarkReadyAsync(f.Player,f.Clock.Now,Ct);
        if(admitted)
        {
            Assert.False(Assert.IsType<ReadyMatchLaunch>(await matcher.ClaimReadyMatchAsync(f.Clock.Now,Ct)).Aborted);
            Assert.Equal(0,await Potions(db,f));f.Clock.Now=f.Season.EndsAtUtc.AddSeconds(1);
        }
        // Recreate repository and catalog cache over the same original database.
        var configs=new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root);
        var restarted=new MatchmakingRepository(db.DataSource,f.Clock,metrics,configurations:configs);
        await using var rooms=new RoomRegistry(f.Clock);var snapshots=new RoomSnapshotRepository(db.DataSource,f.Clock,metrics);
        using var ready=new RoomReadyCoordinator(restarted,rooms,snapshots,new RealtimeEventStore(f.Clock),new ConnectionRegistry(),f.Clock,NullLogger<RoomReadyCoordinator>.Instance,configurations:configs);
        Assert.True(await ready.ProcessNextAsync(f.Clock.Now,Ct));Assert.True(rooms.TryGetForPlayer(f.Player,out var actor));
        var room=await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);var player=Assert.Single(room.Players,p=>p.PlayerId==f.Player);
        Assert.Null(Assert.Single(player.WornArmor!).Equipment!.SecondaryTrait);Assert.Equal(0,player.Combat.Equipment!.DrawIntervalModifier);
        var state=await actor.ExecuteAsync(new GetRoomClientStateCommand(f.Player),Ct);
        var payload=RoomSnapshotProjection.Build(state,f.Player,pending.MatchId,f.Clock.Now);
        Assert.Null(Assert.Single(payload.Player.EquippedItems!).Equipment!.SecondaryTrait);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND secondary_trait IS NULL AND location='InMatchEquipped'",f.Item));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND item_id=$2 AND reason='match.start'",f.Player,f.Item));
        Assert.Equal(0,await Potions(db,f));Assert.Equal(f.Season.ConfigVersion,room.ConfigVersion);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task InvalidExplicitTraitIsRejectedBeforeMembershipOrLockAndIsNotRewritten()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var f=await Create(db,archive.Root,"ForcedEscape");
        var result=await new PreparationRepository(db.DataSource,f.Clock,f.Catalogs).CreateAsync(f.Player,"bad-head",Request(f),Ct);
        Assert.Equal(CreatePreparationStatus.AssetUnavailable,result.Status);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_season_state WHERE player_id=$1",f.Player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1",f.Player));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='Equipped' AND secondary_trait='ForcedEscape'",f.Item));
        Assert.Equal(1,await Potions(db,f));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task OldActiveInvalidSnapshotExpiresAndReleasesOriginalArmorOnlyOnceOnEnqueue()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();var f=await Create(db,archive.Root,"DrawInterval");
        var created=await new PreparationRepository(db.DataSource,f.Clock,f.Catalogs).CreateAsync(f.Player,"prepared",Request(f),Ct);Assert.Equal(CreatePreparationStatus.Created,created.Status);
        await ForgeInvalidSnapshot(db,created.Preparation!.PreparationId,f.Item);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,f.Clock,metrics,configurations:f.Catalogs);
        for(var i=0;i<2;i++)await Assert.ThrowsAsync<InvalidOperationException>(()=>matcher.EnqueueAsync(f.Player,"old-invalid-queue",new(created.Preparation.PreparationId),Ct));
        Assert.Equal("Expired",await db.ScalarAsync<string>("SELECT status FROM preparations WHERE preparation_id=$1",created.Preparation.PreparationId));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='Equipped' AND secondary_trait='ForcedEscape'",f.Item));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='preparation.release'",f.Player));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM match_tickets WHERE player_id=$1",f.Player));Assert.Equal(1,await Potions(db,f));
    }

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData(false)][InlineData(true)]
    public async Task InvalidReadyEquipmentAbortsAndRestoresPreparationWithoutAnyDebitIncludingRollbackRetry(bool fault)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();var f=await Create(db,archive.Root,"DrawInterval");
        var created=await new PreparationRepository(db.DataSource,f.Clock,f.Catalogs).CreateAsync(f.Player,"prepared",Request(f),Ct);Assert.Equal(CreatePreparationStatus.Created,created.Status);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,f.Clock,metrics,configurations:f.Catalogs);
        await matcher.EnqueueAsync(f.Player,"queue",new(created.Preparation!.PreparationId),Ct);f.Clock.Now=f.Clock.Now.AddSeconds(31);
        var pending=Assert.IsType<PendingMatch>(await matcher.TryCreateMatchAsync(Ct));await matcher.MarkReadyAsync(f.Player,f.Clock.Now,Ct);
        await ForgeInvalidSnapshot(db,created.Preparation.PreparationId,f.Item);
        if(fault)
        {
            await db.ExecuteAsync("CREATE FUNCTION abort_gear_fault() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.status='Aborted' THEN RAISE EXCEPTION 'isolated abort page fault'; END IF; RETURN NEW; END $$; CREATE TRIGGER abort_gear_fault BEFORE UPDATE ON matches FOR EACH ROW EXECUTE FUNCTION abort_gear_fault();");
            await Assert.ThrowsAsync<PostgresException>(()=>matcher.ClaimReadyMatchAsync(f.Clock.Now,Ct));
            Assert.Equal("PreparationLocked",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",f.Item));
            Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='preparation.release'"));
            await db.ExecuteAsync("DROP TRIGGER abort_gear_fault ON matches;");
        }
        await using var rooms=new RoomRegistry(f.Clock);var snapshots=new RoomSnapshotRepository(db.DataSource,f.Clock,metrics);
        using var ready=new RoomReadyCoordinator(matcher,rooms,snapshots,new RealtimeEventStore(f.Clock),new ConnectionRegistry(),f.Clock,NullLogger<RoomReadyCoordinator>.Instance,configurations:f.Catalogs);
        Assert.True(await ready.ProcessNextAsync(f.Clock.Now,Ct));Assert.Empty(rooms.GetRoomIds());
        Assert.Null(await matcher.ClaimReadyMatchAsync(f.Clock.Now,Ct));Assert.Equal("Aborted",await db.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1",pending.MatchId));
        Assert.Equal("Cancelled",await db.ScalarAsync<string>("SELECT status FROM preparations WHERE preparation_id=$1",created.Preparation.PreparationId));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1 AND location='Equipped' AND secondary_trait='ForcedEscape'",f.Item));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE reason='match.start'"));
        Assert.Equal(1,await Potions(db,f));
    }

    private sealed record Fixture(Guid Player,Guid Item,long DeckVersion,SeasonDefinition Season,CraftingClock Clock,PublishedConfigCatalogs Catalogs);
    private static CreatePreparationRequest Request(Fixture f)=>new(HeroClassDto.Mage,f.DeckVersion,[f.Item,null,null,null,null],BackpackTierDto.Free,[],1,"D0",f.Season.SeasonId);
    private static Task<int> Potions(PostgresTestSchema db,Fixture f)=>db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",f.Player);
    private static async Task<Fixture> Create(PostgresTestSchema db,string archive,string? trait)
    {
        var config=PreparationConfigTestInputs.Original();var season=SeasonDefinition.FromCalendarDays("historical-gear",new(2026,11,1),config.Version,PreparationConfigTestInputs.StatsVersion);
        var clock=new CraftingClock(season.StartsAtUtc.AddHours(1));await new SeasonRepository(db.DataSource,clock).PublishAsync(season,config.ContentHash,Ct,config);
        PublishedConfigTestInputs.Store(archive,config.Version,config.ExportPublishedBytes(),config.ContentHash);
        var player=await CraftingTestInputs.PlayerAsync(db,clock);await CraftingTestInputs.SqlAsync(db,"UPDATE player_consumables SET health_potion_count=1 WHERE player_id=$1",player);
        var item=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,secondary_trait,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES($1,$2,'Head','Green',0,'Equipped',$3,'Wood',$4,$5,$5,'ActiveSeason',$6,'Historical',0)
            """,item,player,clock.Now,(object?)trait??DBNull.Value,season.SeasonId,season.StatsVersion);
        return new(player,item,await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",player),season,clock,new(GameConfigCatalog.Current,archive));
    }
    private static async Task ForgeInvalidSnapshot(PostgresTestSchema db,Guid preparation,Guid item)
    {
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET secondary_trait='ForcedEscape' WHERE instance_id=$1",item);
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET snapshot_json=jsonb_set(snapshot_json,'{equipmentSnapshots,0,secondaryTrait}','\"ForcedEscape\"'::jsonb) WHERE preparation_id=$1",preparation);
    }
}
