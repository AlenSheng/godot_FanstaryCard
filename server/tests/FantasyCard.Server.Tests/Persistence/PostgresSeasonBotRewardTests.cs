using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonBotRewardTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task RealVictoryCheckpointMintsOnceAndCannotFundEnhancementOrRecipeLearning()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        Kill(f.Room,f.Owner.Player,f.Bot);var reward=Assert.IsType<ExplorationItem>(f.Room.GetPlayer(f.Owner.Player).BotVictoryReward!.Equipment);
        await Extract(db,f,f.Owner.Player);
        Assert.Equal("BotReward",await db.ScalarAsync<string>("SELECT source_kind FROM equipments WHERE instance_id=$1",Guid.Parse(reward.ItemId)));
        Assert.Equal("Blue",await db.ScalarAsync<string>("SELECT quality FROM equipments WHERE instance_id=$1",Guid.Parse(reward.ItemId)));
        Assert.Equal(0,await db.ScalarAsync<int>("SELECT level FROM equipments WHERE instance_id=$1",Guid.Parse(reward.ItemId)));
        var wallet=(await f.Owner.Seasons.GetWalletAsync(f.Owner.Player,f.Owner.Season.ContextFor(0),Ct))!;
        Assert.Equal(5,wallet.Gold);Assert.Equal(5001,wallet.EquipmentFragments);Assert.Equal(77,wallet.ChallengeMarks);
        Assert.Equal(0,wallet.BlueprintMarks);Assert.Equal(0,wallet.OrangeBlueprintMarks);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Owner.Progression.GetEquipmentEnhancementQuoteAsync(f.Owner.Player,Guid.Parse(reward.ItemId),Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Owner.Progression.LearnSeasonRecipeAsync(f.Owner.Player,"bot-recipe",new(f.Owner.Season.SeasonId,Guid.Parse(reward.ItemId),1),Ct));
        var target=await CraftingTestInputs.ItemAsync(db,f.Owner,"Blue",effect:null,level:3);
        await Assert.ThrowsAsync<DomainValidationException>(()=>f.Owner.Progression.EnhanceEquipmentAsync(f.Owner.Player,target,"bot-material",new(1,Guid.Parse(reward.ItemId),MaterialExpectedVersion:1),Ct));
        Assert.Equal(5001,(await f.Owner.Seasons.GetWalletAsync(f.Owner.Player,f.Owner.Season.ContextFor(0),Ct))!.EquipmentFragments);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE loot_rule_id='season-bot-reward-v1'"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task MissingDurableReceiptRejectsTheMintAndRollsBackAnEarlierGoldHold()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        Kill(f.Room,f.Owner.Player,f.Bot);var item=f.Room.GetPlayer(f.Owner.Player).BotVictoryReward!.Equipment!;
        using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,f.Owner.Clock,metrics);
        var receipt=await repository.SettleAsync(f.Match,f.Owner.Player,"Extracted",JsonSerializer.SerializeToElement(new {f.Room.RoomId}),
            [new("Gold","gold",false,37),new("Equipment",item.ItemId,false,Equipment:item.Equipment)],Ct,f.Owner.Season.ContextFor(0),f.Owner.Season.ConfigVersion);
        await Assert.ThrowsAsync<InvalidOperationException>(()=>repository.CommitHoldsAsync(receipt.SettlementId,Ct));
        Assert.Equal(0,(await f.Owner.Seasons.GetWalletAsync(f.Owner.Player,f.Owner.Season.ContextFor(0),Ct))!.Gold);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",Guid.Parse(item.ItemId)));
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM settlement_asset_holds WHERE state='Pending'"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task OriginalBoundPlusFiveDatabaseItemSurvivesBotCustodyAndRetreatWithoutReminting()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        var id=await CraftingTestInputs.ItemAsync(db,f.Owner,"Blue","Feet","Water",null,5,true,secondary:"ForcedEscape");
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='InMatchEquipped' WHERE instance_id=$1",id);
        var item=new ExplorationItem(id.ToString("D"),ExplorationItemKind.Equipment,
            Equipment:new("Feet","Blue","Water",null,"ForcedEscape",5,true,StatsVersion:f.Owner.Season.StatsVersion),IsGenerated:false);
        Assert.True(f.Room.GetPlayer(f.Owner.Player).Inventory.TryAdd(item));f.Room.EquipInventoryItem(f.Owner.Player,item.ItemId);
        var duel=f.Room.StartDuel(f.Bot,f.Owner.Player,DateTimeOffset.UnixEpoch);f.Room.EndDuelWithDeath(duel.DuelId,f.Owner.Player);
        using var metrics=new ServerMetrics();var snapshots=new RoomSnapshotRepository(db.DataSource,f.Owner.Clock,metrics);
        await snapshots.SaveIfDueAsync(f.Room.Capture(),Ct);
        var repository=new SettlementRepository(db.DataSource,f.Owner.Clock,metrics);
        await new SettlementCoordinator(repository,f.Owner.Clock).ObserveAsync(f.Match,f.Room.Capture());
        var dead=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1 AND player_id=$2",f.Match,f.Owner.Player);
        await repository.CommitHoldsAsync(dead,Ct);
        Assert.Equal("RelicPile",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",id));
        var pile=f.Room.Capture().RelicPiles!.Single(value=>value.VictimId==f.Owner.Player.ToString("D"));
        f.Room.TakeRelicItem(f.Bot,pile.PileId,item.ItemId,pile.Version);
        var before=f.Room.Capture();var boss=before.Map!.Cells.Single(cell=>cell.IsBoss).Position;
        var positioned=before with {Players=before.Players.Select(player=>player.PlayerId==f.Bot || player.PlayerId==f.Peer
            ?player with {Position=boss,Phase=RoomPlayerPhase.ActionBar,Pve=null,BotPveRemaining=null}:player).ToArray()};
        var room=BattleRoom.Restore(positioned,CombatCardCatalog.Create(GameConfigCatalog.Current),73);
        room.RequestExtraction(f.Bot);room.Advance(TimeSpan.FromSeconds(90),DateTimeOffset.UnixEpoch.AddSeconds(90));
        Assert.Equal(RoomPlayerPhase.Extracted,room.GetPlayer(f.Bot).Phase);
        var returned=room.Capture().RelicPiles!.Single(value=>value.VictimId==f.Bot.ToString("D"));
        room.TakeRelicItem(f.Peer,returned.PileId,item.ItemId,returned.Version);
        await Extract(db,f with {Room=room},f.Peer);
        Assert.Equal(f.Peer,await db.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(5,await db.ScalarAsync<int>("SELECT level FROM equipments WHERE instance_id=$1",id));
        Assert.True(await db.ScalarAsync<bool>("SELECT is_bound FROM equipments WHERE instance_id=$1",id));
        Assert.Equal("NaturalDrop",await db.ScalarAsync<string>("SELECT source_kind FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(5,await db.ScalarAsync<short>("SELECT generated_difficulty FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE source_kind='BotReward'"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task TransferredVictoryGearRetainsTheOriginalHumanSourceAndTheDatabaseBudget()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        Kill(f.Room,f.Owner.Player,f.Bot);var item=f.Room.GetPlayer(f.Owner.Player).BotVictoryReward!.Equipment!;
        var death=f.Room.StartDuel(f.SecondBot,f.Owner.Player,DateTimeOffset.UnixEpoch);
        f.Room.EndDuelWithDeath(death.DuelId,f.Owner.Player);
        var pile=f.Room.Capture().RelicPiles!.Single(value=>value.VictimId==f.Owner.Player.ToString("D"));
        f.Room.TakeRelicItem(f.SecondBot,pile.PileId,item.ItemId,pile.Version);
        Kill(f.Room,f.Peer,f.SecondBot);
        var botPile=f.Room.Capture().RelicPiles!.Single(value=>value.VictimId==f.SecondBot.ToString("D"));
        f.Room.TakeRelicItem(f.Peer,botPile.PileId,item.ItemId,botPile.Version);
        await Extract(db,f,f.Peer);
        var id=Guid.Parse(item.ItemId);
        Assert.Equal(f.Peer,await db.ScalarAsync<Guid>("SELECT owner_id FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(f.Owner.Player.ToString("D"),await db.ScalarAsync<string>("SELECT source_loot_json->>'BotRewardOwnerId' FROM equipments WHERE instance_id=$1",id));
        var error=await Assert.ThrowsAsync<PostgresException>(()=>CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,version,created_at,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,source_match_id,generated_difficulty,stats_version,source_kind,loot_rule_id,source_loot_json)
            SELECT $2,owner_id,slot,quality,level,'Inventory',1,created_at,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,source_match_id,generated_difficulty,stats_version,source_kind,loot_rule_id,source_loot_json
            FROM equipments WHERE instance_id=$1
            """,id,Guid.NewGuid()));
        Assert.Equal(PostgresErrorCodes.UniqueViolation,error.SqlState);
        Assert.Equal("ux_season_bot_victory_human_match",error.ConstraintName);
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("Orange",0)] [InlineData("Blue",1)]
    [Trait("Category","PostgresIntegration")]
    public async Task InvalidVictoryQualityOrLevelCannotCommitWalletOrEquipment(string quality,int level)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        Kill(f.Room,f.Owner.Player,f.Bot);var item=f.Room.GetPlayer(f.Owner.Player).BotVictoryReward!.Equipment!;
        using var metrics=new ServerMetrics();var repository=new SettlementRepository(db.DataSource,f.Owner.Clock,metrics);
        var bad=item.Equipment! with {Quality=quality,Level=level,EffectAffix=quality=="Orange"?"Piercing":null};
        var receipt=await repository.SettleAsync(f.Match,f.Owner.Player,"Extracted",JsonSerializer.SerializeToElement(new {f.Room.RoomId}),
            [new("Gold","gold",false,37),new("Equipment",item.ItemId,false,Equipment:bad)],Ct,f.Owner.Season.ContextFor(0),f.Owner.Season.ConfigVersion);
        await Assert.ThrowsAsync<DomainValidationException>(()=>repository.CommitHoldsAsync(receipt.SettlementId,Ct));
        Assert.Equal(0,(await f.Owner.Seasons.GetWalletAsync(f.Owner.Player,f.Owner.Season.ContextFor(0),Ct))!.Gold);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE instance_id=$1",Guid.Parse(item.ItemId)));
    }

    private static async Task Extract(PostgresTestSchema db,Fixture f,Guid winner)
    {
        // Actual victory/transfer above, followed by a declared extracted checkpoint.
        // This proves persistence/provenance, not a full gameplay route.
        var snapshot=f.Room.Capture();snapshot=snapshot with {Revision=snapshot.Revision+20,Players=snapshot.Players.Select(player=>player.PlayerId==winner
            ?player with {Phase=RoomPlayerPhase.Extracted,Pve=null}:player).ToArray()};
        using var metrics=new ServerMetrics();await new RoomSnapshotRepository(db.DataSource,f.Owner.Clock,metrics).SaveIfDueAsync(snapshot,Ct);
        var repository=new SettlementRepository(db.DataSource,f.Owner.Clock,metrics);var coordinator=new SettlementCoordinator(repository,f.Owner.Clock);
        await coordinator.ObserveAsync(f.Match,snapshot);await coordinator.ObserveAsync(f.Match,snapshot);
        var id=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1 AND player_id=$2",f.Match,winner);
        await repository.CommitHoldsAsync(id,Ct);await repository.CommitHoldsAsync(id,Ct);
    }
    private static async Task<Fixture> Create(PostgresTestSchema db)
    {
        var owner=await CraftingTestInputs.CreateAsync(db);var peer=await CraftingTestInputs.PlayerAsync(db,owner.Clock);
        var bot=await CraftingTestInputs.PlayerAsync(db,owner.Clock);var second=await CraftingTestInputs.PlayerAsync(db,owner.Clock);
        var policy=GameConfigCatalog.Current.SeasonBotRewards!;var seed=Enumerable.Range(0,100).First(value=>new CombatRandom(unchecked(value^0x42525744)).Next(10000)<policy.EquipmentChanceBasisPoints);
        var room=new BattleRoom(Guid.NewGuid(),owner.Season.ConfigVersion,CombatCardCatalog.Create(GameConfigCatalog.Current),seed,season:owner.Season.ContextFor(0));
        var preparations=new Dictionary<Guid,Guid>();
        foreach(var human in new[]{owner.Player,peer})
        {
            var version=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",human);
            var prepared=await new PreparationRepository(db.DataSource,owner.Clock).CreateAsync(human,"bot-source-preparation",
                new(HeroClassDto.Mage,version,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D0",owner.Season.SeasonId),Ct);
            Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var source=prepared.Preparation!.Snapshot;
            preparations.Add(human,prepared.Preparation.PreparationId);
            room.AddPlayer(new(human,HeroClass.Mage,source.CardIds,null,CardLevels:source.CardLevels,LootPreferenceElement:source.LootPreferenceElement));
            await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",prepared.Preparation.PreparationId);
        }
        var cards=room.GetPlayer(owner.Player).Combat.Deck.Capture();var ids=cards.Hand.Concat(cards.Library).Concat(cards.Discard).Select(card=>card.CardId).ToArray();
        room.AddPlayer(new(bot,HeroClass.Mage,ids,null,IsBot:true));room.AddPlayer(new(second,HeroClass.Mage,ids,null,IsBot:true));
        room.InitializeMap(ChaosMapGenerator.Generate(seed,4));var snapshot=room.Capture();
        room=BattleRoom.Restore(snapshot with {Players=snapshot.Players.Select(player=>player with {Phase=RoomPlayerPhase.ActionBar,Pve=null,
            Position=snapshot.Map!.SpawnPositions[0],BotPveRemaining=null}).ToArray()},CombatCardCatalog.Create(GameConfigCatalog.Current),seed);
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D0',$3,$4,'Running',$5,$6,$7,$8)
            """,match,room.RoomId,seed,owner.Season.ConfigVersion,owner.Clock.Now,owner.Season.SeasonId,owner.Season.RulesetId,owner.Season.StatsVersion);
        foreach(var human in preparations)
            await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Active')",match,human.Key,human.Value);
        foreach(var botId in new[]{bot,second})await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,true,'Active')",match,botId);
        return new(owner,peer,bot,second,room,match);
    }
    private static void Kill(BattleRoom room,Guid winner,Guid loser)
    {
        var duel=room.StartDuel(winner,loser,DateTimeOffset.UnixEpoch);var victim=room.GetPlayer(loser);
        victim.Combat.TakeDamage(victim.Combat.Hp+victim.Combat.Shield-1);
        var deck=room.GetPlayer(winner).Combat.Deck;var old=deck.Capture();var all=old.Hand.Concat(old.Library).Concat(old.Discard).ToArray();var card=all.Single(value=>value.CardId=="C01");
        deck.Restore(new([card],all.Where(value=>value.InstanceId!=card.InstanceId).ToArray(),[],0));
        room.PlayCards(winner,duel.DuelId,loser.ToString("D"),[card.InstanceId],room.Revision,DateTimeOffset.UnixEpoch,room.NewCombatActionId(winner));
        Assert.Equal(RoomPlayerPhase.Dead,victim.Phase);
    }
    private sealed record Fixture(CraftingPlayer Owner,Guid Peer,Guid Bot,Guid SecondBot,BattleRoom Room,Guid Match);
}
