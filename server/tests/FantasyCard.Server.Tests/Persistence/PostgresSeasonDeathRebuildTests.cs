using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Settlement;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Logging.Abstractions;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

/// <summary>Actual isolated PostgreSQL death-to-template-rebuild path, explicitly budgeted outside ordinary CI.</summary>
public sealed class PostgresSeasonDeathRebuildTests
{
    public static bool Enabled=>PostgresRuntimeIntegrationTests.HasTestDatabase&&Environment.GetEnvironmentVariable("FANTASYCARD_RUN_D02_REBUILD")=="1";
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];

    [Fact(Skip="Requires explicit D02 rebuild budget and isolated PostgreSQL.",SkipUnless=nameof(Enabled))]
    public Task MageDeathAndRealBodyBackedRebuildEntersAnotherPreparedMatch()=>Verify(HeroClass.Mage);
    [Fact(Skip="Requires explicit D02 rebuild budget and isolated PostgreSQL.",SkipUnless=nameof(Enabled))]
    public Task PriestDeathAndRealBodyBackedRebuildEntersAnotherPreparedMatch()=>Verify(HeroClass.Priest);
    [Fact(Skip="Requires explicit D02 rebuild budget and isolated PostgreSQL.",SkipUnless=nameof(Enabled))]
    public Task GuardianDeathAndRealBodyBackedRebuildEntersAnotherPreparedMatch()=>Verify(HeroClass.Guardian);

    private static async Task Verify(HeroClass hero)
    {
        var root=Environment.GetEnvironmentVariable("FANTASYCARD_D02_REBUILD_OUTPUT")??throw new InvalidOperationException("Owned D02 output required.");
        var directory=Path.Combine(root,hero.ToString());Assert.False(Directory.Exists(directory));Directory.CreateDirectory(directory);
        await using var db=await PostgresTestSchema.CreateAsync(migrate:false);var schema=new NpgsqlConnectionStringBuilder(db.ConnectionString).SearchPath;
        var config=GameConfigCatalog.Current;Write(directory,"schema.original.json",new {schema,hero,config.Version,config.ContentHash});await db.MigrateAsync();
        var p=await CraftingTestInputs.CreateAsync(db);
        Write(directory,"fixture.original.json",new {schema,p.Player,hero,initial_wallet_fragments=5000,fixture_only_preowned_progression_and_items=true});
        await CraftingTestInputs.SqlAsync(db,"WITH cards AS (UPDATE player_cards SET level=5 WHERE player_id=$1 AND unlocked RETURNING player_id) UPDATE class_weapons SET level=5 WHERE player_id=$1",p.Player);
        var worn=new Guid[5];var spare=new Guid[5];var recipes=new Guid[5];
        for(var i=0;i<Slots.Length;i++)
        {
            var quality=i==0?"Orange":"Purple";var element=i<3?"Fire":"Metal";var effect=i<2?"Piercing":"Vitality";
            worn[i]=await CraftingTestInputs.ItemAsync(db,p,quality,Slots[i],element,effect,3);
            recipes[i]=(await p.Progression.LearnSeasonRecipeAsync(p.Player,"learn-"+Slots[i],new(p.Season.SeasonId,worn[i],1),Ct)).Recipe.RecipeId;
            spare[i]=await CraftingTestInputs.ItemAsync(db,p,quality,"Feet","Water","Bulwark",0);
        }
        await SaveLoadout(p,hero,worn,"before-loadout");
        var before=await StartMatch(db,p,hero,worn,"BeforeDeath",directory);
        var room=BattleRoom.Restore(before.Snapshot,CombatCardCatalog.Create(config),before.Seed);var original=room.CapturePlayer(p.Player);
        Assert.Equal(5,original.WornArmor!.Count);Assert.Equal(worn.Order(),original.WornArmor!.Select(x=>Guid.Parse(x.ItemId)).Order());
        room.AbandonBattle(p.Player);room.Advance(TimeSpan.FromMilliseconds(100),p.Clock.Now.AddMilliseconds(100));
        var dead=room.Capture();Assert.Equal(RoomPlayerPhase.Dead,dead.Players.Single(x=>x.PlayerId==p.Player).Phase);
        Write(directory,"death.original.json",dead);
        using var metrics=new ServerMetrics();var settlement=new SettlementRepository(db.DataSource,p.Clock,metrics);
        await new SettlementCoordinator(settlement,p.Clock).ObserveAsync(before.Match,dead);
        var receipt=await settlement.GetForMatchAsync(p.Player,before.Match,Ct);Assert.Equal("Dead",receipt.Result);
        var committed=await settlement.CommitHoldsAsync(receipt.SettlementId,Ct);Assert.Equal(5,committed);Assert.Equal(0,await settlement.CommitHoldsAsync(receipt.SettlementId,Ct));
        await new SettlementCoordinator(new(db.DataSource,p.Clock,metrics),p.Clock).ObserveAsync(before.Match,dead);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE player_id=$1 AND match_id=$2",p.Player,before.Match));
        Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM learned_season_recipes WHERE player_id=$1",p.Player));
        foreach(var id in worn)Assert.Equal("RelicPile",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",id));
        foreach(var id in spare)Assert.Equal("Inventory",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",id));
        Write(directory,"death-committed.original.json",new {receipt,committed,worn,spare,recipes,preparation_status=await db.ScalarAsync<string>("SELECT status FROM preparations WHERE preparation_id=$1",before.Preparation)});
        var wallet=(await p.Progression.GetSeasonCraftingAsync(p.Player,Ct)).Wallet!;
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"missing-body",new(p.Season.SeasonId,recipes[0],Guid.NewGuid(),1,wallet.Version),Ct));
        var lostVersion=await db.ScalarAsync<long>("SELECT version FROM equipments WHERE instance_id=$1",worn[0]);
        await Assert.ThrowsAsync<DomainValidationException>(()=>p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"lost-body",new(p.Season.SeasonId,recipes[0],worn[0],lostVersion,wallet.Version),Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM season_equipment_actions WHERE action_kind='equipment.reforge'"));
        for(var i=0;i<Slots.Length;i++)
        {
            var quote=await p.Progression.GetReforgeQuoteAsync(p.Player,p.Season.SeasonId,recipes[i],spare[i],Ct);
            var request=new ReforgeEquipmentRequest(p.Season.SeasonId,recipes[i],spare[i],quote.Before.Version,quote.ExpectedWalletVersion);
            var rebuilt=await p.Progression.ReforgeSeasonEquipmentAsync(p.Player,"rebuild-"+Slots[i],request,Ct);
            Assert.Equal(rebuilt,await new ProgressionRepository(db.DataSource,p.Clock).ReforgeSeasonEquipmentAsync(p.Player,"rebuild-"+Slots[i],request,Ct));
            Assert.Equal(spare[i],rebuilt.Equipment.InstanceId);Assert.Equal(0,rebuilt.Equipment.Level);Assert.Equal(Slots[i],rebuilt.Equipment.Slot);Assert.False(rebuilt.Equipment.RecipeExtracted);
            var equipment=rebuilt.Equipment;
            for(var level=0;level<3;level++)equipment=(await p.Progression.EnhanceEquipmentAsync(p.Player,spare[i],"enhance-"+Slots[i]+level,new(equipment.Version),Ct)).Equipment;
            Assert.Equal(3,equipment.Level);Write(directory,"rebuilt-"+Slots[i]+".original.json",new {quote,rebuilt,enhanced=equipment});
        }
        Assert.Equal(4934L,await db.ScalarAsync<long>("SELECT equipment_fragments FROM player_season_wallets WHERE player_id=$1 AND season_id=$2",p.Player,p.Season.SeasonId));
        Assert.Equal(6L,await db.ScalarAsync<long>("SELECT -sum(delta)::bigint FROM economy_ledger WHERE reason='equipment.reforge'"));
        Assert.Equal(5L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE source_kind='TemplateReforge' AND location='Inventory'"));
        await SaveLoadout(p,hero,spare,"after-loadout");var after=await StartMatch(db,p,hero,spare,"AfterRebuild",directory);
        Assert.NotEqual(before.Match,after.Match);var next=BattleRoom.Restore(after.Snapshot,CombatCardCatalog.Create(config),after.Seed);var player=next.GetPlayer(p.Player);
        Assert.Equal(spare.Order(),player.WornArmor.Select(x=>Guid.Parse(x.ItemId)).Order());Assert.All(player.WornArmor,x=>Assert.Equal(3,x.Equipment!.Level));
        Assert.DoesNotContain(player.WornArmor,x=>worn.Contains(Guid.Parse(x.ItemId)));Assert.Equal(2,player.Combat.WeaponLevel);
        Assert.Equal(player.Combat.MaximumHp,player.Combat.Hp);var target=player.Pve!.Monsters.First(x=>!x.IsDead);var selected=player.Combat.Deck.Hand.Select(x=>x.InstanceId).ToArray();
        var played=next.PlayCards(p.Player,player.Pve.BattleId,target.MonsterId,selected,next.Revision,p.Clock.Now,next.NewCombatActionId(p.Player));Assert.False(played.ActionReplayed);next.Advance(TimeSpan.FromMilliseconds(100),p.Clock.Now.AddMilliseconds(100));
        foreach(var id in worn)Assert.Equal("RelicPile",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",id));
        Write(directory,"result.original.json",new {passed=true,hero,schema,oldMatch=before.Match,newMatch=after.Match,worn,spare,recipes,spent_fragments=66,missing_and_lost_body_rejected=true,old_dropped_items_not_restored=true,actual_first_play=played,next_snapshot=next.Capture(),source_context=p.Season.ContextFor(2),real_storage_and_real_two_match_launches=true,OS_process_recovery_not_claimed=true});
    }

    private static async Task SaveLoadout(CraftingPlayer p,HeroClass hero,Guid[] ids,string request)
    {
        var current=await p.Progression.GetLoadoutAsync(p.Player,hero,Ct);Assert.NotNull(current);
        var result=await p.Progression.SaveLoadoutAsync(p.Player,hero,ids.Select(x=>(Guid?)x).ToArray(),request,current.Version,p.Clock.Now,Ct);Assert.Equal(SaveLoadoutStatus.Updated,result.Status);
    }

    private static async Task<(BattleRoomSnapshot Snapshot,Guid Match,int Seed,Guid Preparation)> StartMatch(PostgresTestSchema db,CraftingPlayer p,HeroClass hero,Guid[] ids,string phase,string directory)
    {
        var version=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=$2",p.Player,(short)hero);
        var prepared=await new PreparationRepository(db.DataSource,p.Clock).CreateAsync(p.Player,phase+"-prepare",new((HeroClassDto)(short)hero,version,ids.Select(x=>(Guid?)x).ToArray(),BackpackTierDto.Free,[],0,"D2",p.Season.SeasonId),Ct);Assert.Equal(CreatePreparationStatus.Created,prepared.Status);
        using var metrics=new ServerMetrics();var settings=new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string,string?>{["Matchmaking:BotFillDelaySeconds"]="0"}).Build();
        var matchmaking=new MatchmakingRepository(db.DataSource,p.Clock,metrics,settings);await matchmaking.EnqueueAsync(p.Player,phase+"-queue",new(prepared.Preparation!.PreparationId),Ct);
        var pending=Assert.IsType<PendingMatch>(await matchmaking.TryCreateMatchAsync(Ct));await matchmaking.MarkReadyAsync(p.Player,p.Clock.Now,Ct);
        File.AppendAllText(Path.Combine(directory,"attempts.original.jsonl"),JsonSerializer.Serialize(new {hero,phase,pending.MatchId,pending.RoomId,preparation=prepared.Preparation!.PreparationId})+Environment.NewLine);
        var snapshots=new RoomSnapshotRepository(db.DataSource,p.Clock,metrics);BattleRoomSnapshot snapshot;
        await using(var rooms=new RoomRegistry(p.Clock))
        {
            using var coordinator=new RoomReadyCoordinator(matchmaking,rooms,snapshots,new RealtimeEventStore(p.Clock),new ConnectionRegistry(),p.Clock,NullLogger<RoomReadyCoordinator>.Instance);
            Assert.True(await coordinator.ProcessNextAsync(p.Clock.Now,Ct));var saved=await snapshots.GetAsync(pending.RoomId,Ct);Assert.NotNull(saved);snapshot=saved;
        }
        Assert.Equal(p.Season.ContextFor(2),snapshot.Season);Assert.Equal(GameConfigCatalog.Current.Version,snapshot.ConfigVersion);
        Write(directory,phase+"-ready.original.json",new {prepared.Preparation!.PreparationId,pending.MatchId,snapshot});
        return(snapshot,pending.MatchId,await db.ScalarAsync<int>("SELECT seed FROM matches WHERE match_id=$1",pending.MatchId),prepared.Preparation!.PreparationId);
    }
    private static void Write<T>(string directory,string name,T value)
    {
        var path=Path.Combine(directory,name);Assert.False(File.Exists(path));File.WriteAllText(path,JsonSerializer.Serialize(value));
    }
}
