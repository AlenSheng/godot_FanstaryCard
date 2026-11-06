using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
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

internal sealed record JourneyPlayer(Guid Player,SeasonDefinition Season,CraftingClock Clock,GameConfigCatalog Config,
    SeasonRepository Seasons,SeasonJourneyRepository Journey,PublishedConfigCatalogs Configurations);

internal static class JourneyTestInputs
{
    internal static CancellationToken Ct=>TestContext.Current.CancellationToken;
    internal static async Task<JourneyPlayer> Create(PostgresTestSchema db,int duration=42,GameConfigCatalog? config=null,PublishedConfigCatalogs? configurations=null)
    {
        config??=GameConfigCatalog.Current;
        var season=SeasonDefinition.FromCalendarDays("journey-season",new(2026,11,1),config.Version,"season-equipment-v1",duration);
        var clock=new CraftingClock(season.StartsAtUtc.AddDays(20).AddHours(1));var player=await CraftingTestInputs.PlayerAsync(db,clock);
        return await Existing(db,player,season,clock,config,configurations);
    }
    internal static async Task<JourneyPlayer> Existing(PostgresTestSchema db,Guid player,SeasonDefinition season,CraftingClock clock,GameConfigCatalog? config=null,PublishedConfigCatalogs? configurations=null)
    {
        config??=GameConfigCatalog.Current;var seasons=new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,config.ContentHash,Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        var catalogs=configurations??new PublishedConfigCatalogs(GameConfigCatalog.Current);
        return new(player,season,clock,config,seasons,new(db.DataSource,clock,catalogs),catalogs);
    }

    internal static async Task<ActivityCompletion> Extract(PostgresTestSchema db,JourneyPlayer p)
    {
        Assert.Equal(GameConfigCatalog.Current.Version,p.Config.Version);
        return await ActivityTestInputs.Extract(db,new(p.Player,p.Season,p.Clock,p.Seasons,
            new(db.DataSource,p.Clock,p.Configurations)));
    }
    internal static async Task Observe(PostgresTestSchema db,JourneyPlayer p,ActivityCompletion completed)
    {
        using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,p.Clock,metrics,p.Configurations);
        await new SettlementCoordinator(repository,p.Clock).ObserveAsync(completed.Match,completed.Snapshot);
        var settlement=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_players WHERE match_id=$1 AND player_id=$2",completed.Match,p.Player);
        await repository.CommitHoldsAsync(settlement,Ct);
    }

    // These are source/transaction fixtures: movement is relocated through a
    // declared server checkpoint and monsters are weakened before the final
    // real card. They are never counted as full combat routes or native games.
    internal static async Task<ActivityCompletion> DeadAfterClears(PostgresTestSchema db,JourneyPlayer p,params string[] kinds)
    {
        var admitted=p.Clock.Now;var config=p.Config;
        var deck=(await new ProgressionRepository(db.DataSource,p.Clock).GetDecksAsync(p.Player,Ct)).Single(d=>d.HeroClass==HeroClassDto.Mage);
        var prepared=await new PreparationRepository(db.DataSource,p.Clock,configurations:p.Configurations).CreateAsync(p.Player,Guid.NewGuid().ToString("N"),
            new(HeroClassDto.Mage,deck.Version,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D0",p.Season.SeasonId),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var preparation=prepared.Preparation!;
        var catalog=CombatCardCatalog.Create(config);var room=new BattleRoom(Guid.NewGuid(),config.Version,catalog,73,season:p.Season.ContextFor(0));
        room.AddPlayer(new(p.Player,HeroClass.Mage,preparation.Snapshot.CardIds,null,CardLevels:preparation.Snapshot.CardLevels,
            LootPreferenceElement:preparation.Snapshot.LootPreferenceElement));
        room.InitializeMap(ChaosMapGenerator.Generate(73,1));var used=new HashSet<MapPosition>();
        foreach(var kind in kinds)
        {
            var cell=room.Map!.Cells.First(cell=>SeasonJourneyConfig.CellKind(cell)==kind&&!used.Contains(cell.Position));used.Add(cell.Position);
            room=AtCell(room,p.Player,cell,catalog);
            var player=room.GetPlayer(p.Player);var battle=player.Pve!;
            foreach(var monster in battle.Monsters.ToArray())
            {
                monster.TakeDamage(monster.Hp+monster.Shield-1);
                var old=player.Combat.Deck.Capture();var all=old.Hand.Concat(old.Library).Concat(old.Discard).ToArray();
                var card=all.Single(c=>c.CardId=="C01");player.Combat.Deck.Restore(new([card],all.Where(c=>c.InstanceId!=card.InstanceId).ToArray(),[],0));
                p.Clock.Now=p.Clock.Now.AddSeconds(1);
                room.PlayCards(p.Player,battle.BattleId,monster.MonsterId,[card.InstanceId],room.Revision,p.Clock.Now,room.NewCombatActionId(p.Player));
                room.Advance(TimeSpan.FromMilliseconds(500),p.Clock.Now);
            }
            Assert.Equal(RoomPlayerPhase.Choice,player.Phase);
        }
        var exitCell=room.Map!.Cells.First(cell=>!used.Contains(cell.Position)&&!cell.IsBoss);
        room=AtCell(room,p.Player,exitCell,catalog);room.AbandonBattle(p.Player);
        var snapshot=room.Capture();Assert.Equal(RoomPlayerPhase.Dead,snapshot.Players[0].Phase);
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',73,$3,'Running',$4,$5,'season-v1',$6)
            """,match,room.RoomId,config.Version,admitted,p.Season.SeasonId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Active')",match,p.Player,preparation.PreparationId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",preparation.PreparationId);
        using var metrics=new ServerMetrics();await new RoomSnapshotRepository(db.DataSource,p.Clock,metrics).SaveIfDueAsync(snapshot,Ct);
        return new(match,snapshot);
    }

    private static BattleRoom AtCell(BattleRoom room,Guid player,ChaosMapCell cell,CombatCardCatalog catalog)
    {
        var snapshot=room.Capture();var pve=PveBattleFactory.Create(cell,catalog.Configuration.SeasonDifficulty(0),catalog.Configuration.SeasonThemes?.Selected);
        return BattleRoom.Restore(snapshot with {Players=snapshot.Players.Select(p=>p.PlayerId==player?p with
            {Position=cell.Position,Phase=RoomPlayerPhase.Pve,Pve=pve.Capture(),RewardChoice=null}:p).ToArray()},catalog,73);
    }
}
