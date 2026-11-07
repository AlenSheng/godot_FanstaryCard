using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonBlueprintTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData(0,true,0,0)]
    [InlineData(1,true,3,0)]
    [InlineData(2,true,0,3)]
    [InlineData(5,true,0,3)]
    [InlineData(2,false,0,0)]
    [Trait("Category","PostgresIntegration")]
    public async Task TerminalSnapshotControlsCreditOwnClearsOnlyAfterSuccessfulExtractionAndReplayOnlyOnce(int difficulty,bool extracted,long blue,long orange)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var fixture=await TerminalAsync(db,p,difficulty,extracted?RoomPlayerPhase.Extracted:RoomPlayerPhase.Dead);
        var repository=new SettlementRepository(db.DataSource,p.Clock,new ServerMetrics());
        var coordinator=new SettlementCoordinator(repository,p.Clock);
        await coordinator.ObserveAsync(fixture.Match,fixture.Snapshot);await coordinator.ObserveAsync(fixture.Match,fixture.Snapshot);
        var settlement=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1",fixture.Match);
        await repository.CommitHoldsAsync(settlement,Ct);await repository.CommitHoldsAsync(settlement,Ct);
        var wallet=(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!;
        Assert.Equal(blue,wallet.BlueprintMarks);Assert.Equal(orange,wallet.OrangeBlueprintMarks);Assert.Equal(77,wallet.ChallengeMarks);
        Assert.Equal(blue+orange==0?0L:1L,await db.ScalarAsync<long>("SELECT count(*) FROM season_wallet_operations WHERE reason='settlement.blueprints'"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task WrongDifficultyKindDeathOverCapAndBotCannotSubmitBlueprintAssets()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var fixture=await TerminalAsync(db,p,1,RoomPlayerPhase.Extracted);var repository=new SettlementRepository(db.DataSource,p.Clock,new ServerMetrics());
        using var details=JsonDocument.Parse("{}");
        foreach(var input in new[]{("Dead",new SettlementAsset("BlueprintMarks","blueprint",false,1)),
            ("Extracted",new SettlementAsset("OrangeBlueprintMarks","orange-blueprint",false,1)),
            ("Extracted",new SettlementAsset("BlueprintMarks","blueprint",false,5))})
            await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.SettleAsync(fixture.Match,p.Player,input.Item1,details.RootElement,[input.Item2],Ct,p.Season.ContextFor(1),p.Season.ConfigVersion));
        await CraftingTestInputs.SqlAsync(db,"UPDATE match_players SET is_bot=true WHERE match_id=$1",fixture.Match);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.SettleAsync(fixture.Match,p.Player,"Extracted",details.RootElement,[new("BlueprintMarks","blueprint",false,1)],Ct,p.Season.ContextFor(1),p.Season.ConfigVersion));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task LateBlueprintCommitCreditsOnlyItsOriginalSeason()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var p=await CraftingTestInputs.CreateAsync(db);
        var fixture=await TerminalAsync(db,p,2,RoomPlayerPhase.Extracted);var repository=new SettlementRepository(db.DataSource,p.Clock,new ServerMetrics());
        await new SettlementCoordinator(repository,p.Clock).ObserveAsync(fixture.Match,fixture.Snapshot);
        var id=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1",fixture.Match);
        p.Clock.Now=p.Season.EndsAtUtc.AddHours(1);
        var next=SeasonDefinition.FromCalendarDays("next-crafting",new(2026,12,13),p.Season.ConfigVersion,p.Season.StatsVersion);
        await p.Seasons.PublishAsync(next,GameConfigCatalog.Current.ContentHash,Ct);await p.Seasons.EnsurePlayerAsync(p.Player,next.ContextFor(0),Ct);
        await repository.CommitHoldsAsync(id,Ct);
        Assert.Equal(3,(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!.OrangeBlueprintMarks);
        Assert.Equal(0,(await p.Seasons.GetWalletAsync(p.Player,next.ContextFor(0),Ct))!.OrangeBlueprintMarks);
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ActualScaledEliteVictoryResourcesReachTheOriginalSeasonWalletOnce()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var p=await CraftingTestInputs.CreateAsync(db);
        var fixture=await TerminalAsync(db,p,2,RoomPlayerPhase.Extracted);
        var config=GameConfigCatalog.Current;var catalog=CombatCardCatalog.Create(config);
        var deckVersion=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",p.Player);
        var prepared=await new PreparationRepository(db.DataSource,p.Clock).CreateAsync(p.Player,"elite-reward-preparation",
            new(HeroClassDto.Mage,deckVersion,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D2",p.Season.SeasonId),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var source=prepared.Preparation!.Snapshot;
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",prepared.Preparation.PreparationId);
        await CraftingTestInputs.SqlAsync(db,"UPDATE match_players SET preparation_id=$1 WHERE match_id=$2 AND player_id=$3",prepared.Preparation.PreparationId,fixture.Match,p.Player);
        var map=ChaosMapGenerator.Generate(73,1).Capture();var start=map.SpawnPositions[0];
        map=map with {Cells=map.Cells.Select(cell=>cell.Position==start?cell with {Layer=ChaosMapLayer.Core,MonsterGroupId="E1",IsBoss=false}:cell).ToArray()};
        var room=new BattleRoom(fixture.Snapshot.RoomId,config.Version,catalog,73,season:p.Season.ContextFor(2));
        var player=room.AddPlayer(new(p.Player,HeroClass.Mage,source.CardIds,null,CardLevels:source.CardLevels,
            LootPreferenceElement:source.LootPreferenceElement));room.InitializeMap(ChaosMapState.Restore(map));
        var random=new CombatRandom(0);random.Restore(room.Capture().RandomStreams!.Loot);
        _=random.Next(6,11);var fragments=random.Next(4,8)*19000/10000;
        foreach(var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp+monster.Shield-1);
            var deck=player.Combat.Deck.Capture();var all=deck.Hand.Concat(deck.Library).Concat(deck.Discard).ToArray();
            var card=all.Single(value=>value.CardId=="C01");
            player.Combat.Deck.Restore(new([card],all.Where(value=>value.InstanceId!=card.InstanceId).ToArray(),[],0));
            room.PlayCards(p.Player,player.Pve.BattleId,monster.MonsterId,[card.InstanceId],room.Revision,p.Clock.Now,room.NewCombatActionId(p.Player));
            room.Advance(TimeSpan.FromMilliseconds(500),p.Clock.Now);
        }
        Assert.Equal(RoomPlayerPhase.Choice,player.Phase);
        Assert.Equal(44,player.Inventory.GoldQuantity);
        Assert.Equal(fragments,player.Inventory.Items.Single(item=>item.Kind==ExplorationItemKind.EquipmentFragments).Quantity);
        // Declared extracted checkpoint after real reward generation; this is
        // asset/settlement interoperability, not a completed gameplay route.
        var snapshot=room.Capture();snapshot=snapshot with {Players=snapshot.Players.Select(value=>value with {Phase=RoomPlayerPhase.Extracted,Pve=null,RewardChoice=null}).ToArray()};
        using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,p.Clock,metrics);
        await new RoomSnapshotRepository(db.DataSource,p.Clock,metrics).SaveIfDueAsync(snapshot,Ct);
        var coordinator=new SettlementCoordinator(repository,p.Clock);
        await coordinator.ObserveAsync(fixture.Match,snapshot);await coordinator.ObserveAsync(fixture.Match,snapshot);
        var id=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1",fixture.Match);
        await repository.CommitHoldsAsync(id,Ct);await repository.CommitHoldsAsync(id,Ct);
        var wallet=(await p.Seasons.GetWalletAsync(p.Player,p.Season.ContextFor(0),Ct))!;
        Assert.Equal(44,wallet.Gold);Assert.Equal(5000+fragments,wallet.EquipmentFragments);
        Assert.Equal(1,wallet.OrangeBlueprintMarks);Assert.Equal(77,wallet.ChallengeMarks);
    }

    private static async Task<(Guid Match,BattleRoomSnapshot Snapshot)> TerminalAsync(PostgresTestSchema db,CraftingPlayer p,int difficulty,RoomPlayerPhase phase)
    {
        // Declared terminal checkpoint for source/transaction verification, not a gameplay-route pass.
        var room=new BattleRoom(Guid.NewGuid(),p.Season.ConfigVersion,CombatCardCatalog.Create(GameConfigCatalog.Current),73,season:p.Season.ContextFor(difficulty));
        var cards=Enumerable.Range(1,13).Select(i=>$"C{i:D2}").Concat(Enumerable.Range(1,7).Select(i=>$"MAG-{i:D2}")).ToArray();
        room.AddPlayer(new(p.Player,HeroClass.Mage,cards,null));room.InitializeMap(ChaosMapGenerator.Generate(73,1));
        var snapshot=room.Capture();var cells=snapshot.Map!.Cells.Where(cell=>cell.IsBoss).Concat(snapshot.Map.Cells.Where(cell=>cell.MonsterGroupId.StartsWith('E')).Take(1)).Select(cell=>cell.Position).ToArray();
        snapshot=snapshot with {Players=snapshot.Players.Select(player=>player with {Phase=phase,Pve=null,ClearedCells=cells.Concat(cells).ToArray()}).ToArray()};
        var match=Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm',$3,73,$4,'Running',$5,$6,$7,$8)
            """,match,room.RoomId,$"D{difficulty}",p.Season.ConfigVersion,p.Clock.Now,p.Season.SeasonId,p.Season.RulesetId,p.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,false,'Active')",match,p.Player);
        return(match,snapshot);
    }
}
