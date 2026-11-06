using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Persistence;

internal sealed record ActivityPlayer(Guid Player,SeasonDefinition Season,CraftingClock Clock,SeasonRepository Seasons,SeasonActivityRepository Activities);
internal sealed record ActivityCompletion(Guid Match,BattleRoomSnapshot Snapshot);
internal static class ActivityTestInputs
{
    internal static CancellationToken Ct=>TestContext.Current.CancellationToken;
    internal static async Task<ActivityPlayer> Create(PostgresTestSchema db)
    {
        var config=GameConfigCatalog.Current;var season=SeasonDefinition.FromCalendarDays("limited-event-season",new(2026,11,1),config.Version,"season-equipment-v1");
        var start=config.SeasonActivity!.Windows(season)[0].StartsAt;var clock=new CraftingClock(start.AddHours(1));
        var player=await CraftingTestInputs.PlayerAsync(db,clock);var seasons=new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,config.ContentHash,Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        return new(player,season,clock,seasons,new(db.DataSource,clock,new PublishedConfigCatalogs(config)));
    }

    internal static async Task<ActivityPlayer> ForExistingPlayer(PostgresTestSchema db,Guid player,SeasonDefinition season,CraftingClock clock)
    {
        var config=GameConfigCatalog.Current;var seasons=new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,config.ContentHash,Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        return new(player,season,clock,seasons,new(db.DataSource,clock,new PublishedConfigCatalogs(config)));
    }

    internal static async Task<ActivityCompletion> Extract(PostgresTestSchema db,ActivityPlayer p,DateTimeOffset? completionAt=null)
    {
        var at=completionAt??p.Clock.Now.AddSeconds(10);p.Clock.Now=at.AddSeconds(-5);var config=GameConfigCatalog.Current;
        var progression=new ProgressionRepository(db.DataSource,p.Clock);var deck=(await progression.GetDecksAsync(p.Player,Ct)).Single(d=>d.HeroClass==HeroClassDto.Mage);
        var prepared=await new PreparationRepository(db.DataSource,p.Clock).CreateAsync(p.Player,Guid.NewGuid().ToString("N"),
            new(HeroClassDto.Mage,deck.Version,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D0",p.Season.SeasonId),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var prep=prepared.Preparation!;
        var catalog=CombatCardCatalog.Create(config);var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:p.Season.ContextFor(0));
        room.AddPlayer(new(p.Player,HeroClass.Mage,prep.Snapshot.CardIds,null,CardLevels:prep.Snapshot.CardLevels,LootPreferenceElement:prep.Snapshot.LootPreferenceElement));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1));var snapshot=room.Capture();var boss=snapshot.Map!.Cells.Single(c=>c.IsBoss).Position;
        snapshot=snapshot with {Players=snapshot.Players.Select(player=>player with {Position=boss,Phase=RoomPlayerPhase.ActionBar,Pve=null}).ToArray()};
        room=BattleRoom.Restore(snapshot,catalog,73);room.RequestExtraction(p.Player);room.Advance(TimeSpan.FromSeconds(3),at);snapshot=room.Capture();
        Assert.Equal(at,Assert.Single(snapshot.Players).ExtractionCompletedAt);
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)
            """,match,room.RoomId,config.Version,p.Clock.Now,p.Season.SeasonId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Active')",match,p.Player,prep.PreparationId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",prep.PreparationId);
        p.Clock.Now=at;using var metrics=new ServerMetrics();await new RoomSnapshotRepository(db.DataSource,p.Clock,metrics).SaveIfDueAsync(snapshot,Ct);
        return new(match,snapshot);
    }

    internal static async Task Observe(PostgresTestSchema db,ActivityPlayer p,ActivityCompletion completion)
    {
        using var metrics=new ServerMetrics();await new SettlementCoordinator(new SettlementRepository(db.DataSource,p.Clock,metrics),p.Clock)
            .ObserveAsync(completion.Match,completion.Snapshot);
    }
    internal static async Task Earn(PostgresTestSchema db,ActivityPlayer p,int extractions=3)
    {
        for(var i=0;i<extractions;i++){var completion=await Extract(db,p);await Observe(db,p,completion);}
    }
    internal static async Task<ActivityEventResponse> First(ActivityPlayer p)=>(await p.Activities.GetAsync(p.Player,Ct,p.Season.SeasonId)).Events.OrderBy(e=>e.StartsAt).First();
    internal static ActivityExchangeRequest Request(ActivityPlayer p,ActivityEventResponse e,string rule,int quantity=1,string? hero=null)=>
        new(p.Season.SeasonId,rule,e.AccountVersion,quantity,hero);
}
