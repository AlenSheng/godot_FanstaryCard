using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Tests.Config;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresPreparationConfigVersionTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private const string Required="Requires isolated PostgreSQL.";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData(false)][InlineData(true)]
    public async Task StillOpenArchivedSeasonPreparesQueuesAndLaunchesUsingItsOwnCatalog(bool borrowed)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var source=PreparationConfigTestInputs.Original();var season=Definition(source);var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,source.ContentHash,Ct,source);
        PublishedConfigTestInputs.Store(archive.Root,source.Version,source.ExportPublishedBytes(),source.ContentHash);
        var catalogs=new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root);var preparations=new PreparationRepository(db.DataSource,clock,catalogs);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,clock,metrics,configurations:catalogs);
        var players=new List<Player>();
        for(var i=0;i<4;i++)
        {
            var p=await PlayerAsync(db,clock,season,"Green");players.Add(p);await seasons.EnsurePlayerAsync(p.Id,season.ContextFor(0),Ct);
            await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1 AND season_id=$2",p.Id,season.SeasonId);
            var result=await preparations.CreateAsync(p.Id,"prepare-archive",Request(p,season,borrowed),Ct);
            Assert.Equal(CreatePreparationStatus.Created,result.Status);var snapshot=result.Preparation!.Snapshot;
            Assert.Equal(source.Version,snapshot.ConfigVersion);Assert.Equal(21,snapshot.BackpackCapacity);Assert.Equal("Wood",snapshot.LootPreferenceElement);
            if(borrowed)
            {
                Assert.Equal(source.BorrowedDeck(HeroClass.Mage).CardIds,snapshot.CardIds);Assert.Contains("C30",snapshot.CardIds);
            }
            else
            {
                Assert.DoesNotContain("C30",snapshot.CardIds);Assert.Contains("C13",snapshot.CardIds);
            }
            Assert.Equal(borrowed?"archive-loan-mage":null,snapshot.BorrowedTemplateId);Assert.Equal(1,snapshot.ClassWeaponLevel);
            Assert.All(snapshot.CardLevels!,level=>Assert.Equal(1,level));Assert.All(snapshot.ActualCardLevels!,level=>Assert.Equal(3,level));
            Assert.Equal(PreparationConfigTestInputs.StatsVersion,Assert.Single(snapshot.EquipmentSnapshots!).StatsVersion);
            await matcher.EnqueueAsync(p.Id,"queue-archive",new(result.Preparation.PreparationId),Ct);
        }
        var pending=Assert.IsType<PendingMatch>(await matcher.TryCreateMatchAsync(Ct));
        foreach(var p in players)await matcher.MarkReadyAsync(p.Id,clock.Now,Ct);
        await using var rooms=new RoomRegistry(clock);var snapshots=new RoomSnapshotRepository(db.DataSource,clock,metrics);
        using var ready=new RoomReadyCoordinator(matcher,rooms,snapshots,new RealtimeEventStore(clock),new ConnectionRegistry(),clock,NullLogger<RoomReadyCoordinator>.Instance,configurations:catalogs);
        Assert.True(await ready.ProcessNextAsync(clock.Now,Ct));Assert.True(rooms.TryGetForPlayer(players[0].Id,out var actor));
        var room=await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);Assert.Equal(source.Version,room.ConfigVersion);Assert.Equal(season.ContextFor(1),room.Season);
        Assert.Equal(4,room.Players.Count);Assert.All(room.Players,p=>
        {
            Assert.False(p.IsBot);Assert.Equal(21,p.Inventory!.Capacity);Assert.Equal("Wood",p.LootPreferenceElement);
            Assert.Equal(borrowed?"archive-loan-mage":null,p.BorrowedTemplateId);
            Assert.Equal(PreparationConfigTestInputs.StatsVersion,Assert.Single(p.WornArmor!).Equipment!.StatsVersion);
        });
        var seed=await db.ScalarAsync<int>("SELECT seed FROM matches WHERE match_id=$1",pending.MatchId);
        Assert.Equal(ChaosMapGenerator.Generate(seed,4,source.SeasonThemes).Capture().Cells,room.Map!.Cells);
        Assert.Equal(4L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE season_id=$1 AND location='InMatchEquipped'",season.SeasonId));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_cards WHERE level<>3"));
    }

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData("missing")][InlineData("corrupt")][InlineData("hash")]
    public async Task UnavailableOrWrongOriginalSourceCannotCreateMembershipOrLockEquipment(string failure)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var source=PreparationConfigTestInputs.Original();var season=Definition(source);var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));
        await new SeasonRepository(db.DataSource,clock).PublishAsync(season,source.ContentHash,Ct,source);
        var p=await PlayerAsync(db,clock,season,"Green");
        if(failure!="missing")
        {
            var bytes=source.ExportPublishedBytes();if(failure=="corrupt")bytes[^1]^=1;
            PublishedConfigTestInputs.Store(archive.Root,source.Version,bytes,source.ContentHash);
        }
        if(failure=="hash")await CraftingTestInputs.SqlAsync(db,"UPDATE season_definitions SET config_sha256=$1 WHERE season_id=$2",new string('a',64),season.SeasonId);
        var preparations=new PreparationRepository(db.DataSource,clock,new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root));
        await Assert.ThrowsAsync<DomainValidationException>(()=>preparations.CreateAsync(p.Id,"bad-original",Request(p,season,false) with {Difficulty="D0"},Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM player_season_state WHERE player_id=$1",p.Id));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM preparations WHERE player_id=$1",p.Id));
        Assert.Equal("Equipped",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",p.Equipment));
        Assert.Equal(1,await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",p.Id));
    }

    [Theory(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    [InlineData("config")][InlineData("stats")]
    public async Task MatchmakingChecksOriginalSeasonDefinitionRatherThanAcceptingTheLobbyLabel(string field)
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var source=PreparationConfigTestInputs.Original();var season=Definition(source);var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,source.ContentHash,Ct,source);
        PublishedConfigTestInputs.Store(archive.Root,source.Version,source.ExportPublishedBytes(),source.ContentHash);
        var catalogs=new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root);var p=await PlayerAsync(db,clock,season,"Green");
        await seasons.EnsurePlayerAsync(p.Id,season.ContextFor(0),Ct);await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",p.Id);
        var prepared=await new PreparationRepository(db.DataSource,clock,catalogs).CreateAsync(p.Id,"prepare",Request(p,season,false),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);
        await CraftingTestInputs.SqlAsync(db,field=="config"?"UPDATE preparations SET config_version=$1 WHERE preparation_id=$2":"UPDATE preparations SET stats_version=$1 WHERE preparation_id=$2",field=="config"?GameConfigCatalog.Current.Version:"wrong-stats",prepared.Preparation!.PreparationId);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,clock,metrics,configurations:catalogs);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>matcher.EnqueueAsync(p.Id,"bad-queue",new(prepared.Preparation.PreparationId),Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM match_tickets WHERE player_id=$1",p.Id));
        Assert.Equal("Equipped",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",p.Equipment));
        Assert.Equal(1,await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",p.Id));
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task EntryQualityComesFromTheActualOriginalControlRatherThanTheLobby()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var source=PreparationConfigTestInputs.Original();var season=Definition(source);var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,source.ContentHash,Ct,source);
        PublishedConfigTestInputs.Store(archive.Root,source.Version,source.ExportPublishedBytes(),source.ContentHash);
        var p=await PlayerAsync(db,clock,season,"Blue");await seasons.EnsurePlayerAsync(p.Id,season.ContextFor(0),Ct);
        await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",p.Id);
        Assert.Equal(3,GameConfigCatalog.Current.SeasonDifficulty(1).EntryQualityCap);Assert.Equal(1,source.SeasonDifficulty(1).EntryQualityCap);
        var preparations=new PreparationRepository(db.DataSource,clock,new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root));
        var declined=await preparations.CreateAsync(p.Id,"original-cap-reject",Request(p,season,false),Ct);
        Assert.Equal(CreatePreparationStatus.AssetUnavailable,declined.Status);
        Assert.Equal("Equipped",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",p.Equipment));
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET quality='Green',version=version+1 WHERE instance_id=$1",p.Equipment);
        Assert.Equal(CreatePreparationStatus.Created,(await preparations.CreateAsync(p.Id,"original-cap-accept",Request(p,season,false),Ct)).Status);
    }

    [Fact(Skip=Required,SkipUnless=nameof(HasTestDatabase))][Trait("Category","PostgresIntegration")]
    public async Task AlreadyAdmittedArchivedLaunchDrainsAfterTheSeasonEndsWithoutASecondAssetSpend()
    {
        await using var db=await PostgresTestSchema.CreateAsync(true);using var archive=new ConfigArchiveDirectory();
        var source=PreparationConfigTestInputs.Original();var season=Definition(source);var clock=new CraftingClock(season.EndsAtUtc.AddSeconds(-45));
        var seasons=new SeasonRepository(db.DataSource,clock);await seasons.PublishAsync(season,source.ContentHash,Ct,source);
        PublishedConfigTestInputs.Store(archive.Root,source.Version,source.ExportPublishedBytes(),source.ContentHash);
        var catalogs=new PublishedConfigCatalogs(GameConfigCatalog.Current,archive.Root);var p=await PlayerAsync(db,clock,season,"Green");
        await seasons.EnsurePlayerAsync(p.Id,season.ContextFor(0),Ct);await CraftingTestInputs.SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",p.Id);
        var prepared=await new PreparationRepository(db.DataSource,clock,catalogs).CreateAsync(p.Id,"prepare",Request(p,season,true),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,clock,metrics,configurations:catalogs);
        await matcher.EnqueueAsync(p.Id,"queue",new(prepared.Preparation!.PreparationId),Ct);clock.Now=clock.Now.AddSeconds(31);
        var pending=Assert.IsType<PendingMatch>(await matcher.TryCreateMatchAsync(Ct));await matcher.MarkReadyAsync(p.Id,clock.Now,Ct);
        var launching=Assert.IsType<ReadyMatchLaunch>(await matcher.ClaimReadyMatchAsync(clock.Now,Ct));Assert.False(launching.Aborted);
        Assert.Equal(source.Version,launching.Assignment.ConfigVersion);
        Assert.Equal(0,await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",p.Id));
        clock.Now=season.EndsAtUtc.AddSeconds(1);
        await using var rooms=new RoomRegistry(clock);var snapshots=new RoomSnapshotRepository(db.DataSource,clock,metrics);
        using var ready=new RoomReadyCoordinator(matcher,rooms,snapshots,new RealtimeEventStore(clock),new ConnectionRegistry(),clock,NullLogger<RoomReadyCoordinator>.Instance,configurations:catalogs);
        Assert.True(await ready.ProcessNextAsync(clock.Now,Ct));Assert.True(rooms.TryGetForPlayer(p.Id,out var actor));
        Assert.Equal(source.Version,(await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct)).ConfigVersion);
        Assert.Equal(0,await db.ScalarAsync<int>("SELECT health_potion_count FROM player_consumables WHERE player_id=$1",p.Id));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM inventory_movements WHERE player_id=$1 AND reason='match.start' AND item_id=$2",p.Id,p.Equipment));
        Assert.Equal("Running",await db.ScalarAsync<string>("SELECT status FROM matches WHERE match_id=$1",pending.MatchId));
    }

    private sealed record Player(Guid Id,Guid Equipment,long DeckVersion);
    private static SeasonDefinition Definition(GameConfigCatalog source)=>SeasonDefinition.FromCalendarDays("active-archived-source",new(2026,11,1),source.Version,PreparationConfigTestInputs.StatsVersion,highestOpenDifficulty:5);
    private static CreatePreparationRequest Request(Player p,SeasonDefinition season,bool borrowed)=>new(HeroClassDto.Mage,p.DeckVersion,[p.Equipment,null,null,null,null],BackpackTierDto.Free,[],1,"D1",season.SeasonId,borrowed);
    private static async Task<Player> PlayerAsync(PostgresTestSchema db,CraftingClock clock,SeasonDefinition season,string quality)
    {
        var id=await CraftingTestInputs.PlayerAsync(db,clock);
        await CraftingTestInputs.SqlAsync(db,"""
            WITH cards AS(UPDATE player_cards SET level=3 WHERE player_id=$1 RETURNING player_id),
                weapons AS(UPDATE class_weapons SET level=3 WHERE player_id=$1 RETURNING player_id)
            UPDATE player_consumables SET health_potion_count=1 WHERE player_id=$1
            """,id);
        var item=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES($1,$2,'Head',$3,0,'Equipped',$4,'Wood',$5,$5,'ActiveSeason',$6,'NaturalDrop',1)
            """,item,id,quality,clock.Now,season.SeasonId,season.StatsVersion);
        return new(id,item,await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",id));
}
