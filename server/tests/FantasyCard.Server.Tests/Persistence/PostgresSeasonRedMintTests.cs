using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Persistence;
using FantasyCard.Server.Settlement;
using Npgsql;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonRedMintTests
{
    public static bool HasTestDatabase=>PostgresMigrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task ConcurrentMintAndCrashBeforeDeliveryRecoverTheOriginalFullBagItemWithoutRefundingItsWeek()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        var pending=f.Room.GetPlayer(f.Owner.Player).PendingRedEvaluation!;
        var results=await Task.WhenAll(Enumerable.Range(0,4).Select(_=>Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending,Ct)));
        var original=results[0];Assert.Equal("Minted",original.Status);Assert.All(results,result=>Assert.Equal(original,result));
        var id=Guid.Parse(original.Equipment!.ItemId);
        Assert.Equal(1L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE mint_id=$1",pending.AttemptId));
        Assert.Equal("InMatchBackpack",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(f.Match,await db.ScalarAsync<Guid>("SELECT source_match_id FROM equipments WHERE instance_id=$1",id));
        Assert.Equal("primary",await db.ScalarAsync<string>("SELECT quota_scope FROM equipments WHERE instance_id=$1",id));
        Assert.Equal("RedBoss",await db.ScalarAsync<string>("SELECT source_kind FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(f.Owner.Season.SeasonId,await db.ScalarAsync<string>("SELECT origin_season_id FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM match_settlements WHERE match_id=$1",f.Match));
        // Recreate both the room and coordinator after the database commit but
        // before any in-memory delivery. The durable pending checkpoint is the authority.
        using var metrics=new ServerMetrics();var snapshots=new RoomSnapshotRepository(db.DataSource,f.Owner.Clock,metrics);
        var recovered=BattleRoom.Restore((await snapshots.GetAsync(f.Room.RoomId,Ct))!,CombatCardCatalog.Create(GameConfigCatalog.Current),f.Seed);
        var coordinator=new SeasonRedDropCoordinator(Repository(db,f),snapshots);
        await using var actor=new RoomActor(recovered,f.Owner.Clock,startTicker:false,authoritativeProcessor:value=>coordinator.ProcessAsync(f.Match,value));
        var acknowledged=await actor.ExecuteAsync(new GetRoomSnapshotCommand(),cancellationToken:Ct);
        Assert.Equal(original.Equipment,acknowledged.Players.Single().PendingRedItem);
        var player=recovered.GetPlayer(f.Owner.Player);Assert.Equal(original.Equipment,player.PendingRedItem);
        var replaced=player.Inventory.Items[0];
        await actor.ExecuteAsync(new ClaimRewardCommand(f.Owner.Player,"red:"+id.ToString("D"),replaced.ItemId,false),cancellationToken:Ct);
        var persisted=(await snapshots.GetAsync(recovered.RoomId,Ct))!.Players.Single();
        Assert.Null(persisted.PendingRedItem);Assert.Single(persisted.Inventory!.Items,item=>item.ItemId==id.ToString("D"));
        Assert.Equal(original,persisted.RedReward);
        await actor.ExecuteAsync(new SetPlayerConnectionCommand(f.Owner.Player,false),cancellationToken:Ct);
        var dead=await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(61),f.Owner.Clock.Now.AddSeconds(61)),cancellationToken:Ct);
        Assert.Equal(RoomPlayerPhase.Dead,dead.Players.Single().Phase);
        Assert.Single(dead.RelicPiles!.SelectMany(pile=>pile.Items),item=>item.ItemId==id.ToString("D"));
        await snapshots.SaveIfDueAsync(dead,Ct);
        var settlement=new SettlementRepository(db.DataSource,f.Owner.Clock,metrics);
        await new SettlementCoordinator(settlement,f.Owner.Clock).ObserveAsync(f.Match,dead);
        var settlementId=await db.ScalarAsync<Guid>("SELECT settlement_id FROM match_settlements WHERE match_id=$1 AND player_id=$2",f.Match,f.Owner.Player);
        await settlement.CommitHoldsAsync(settlementId,Ct);
        Assert.Equal("RelicPile",await db.ScalarAsync<string>("SELECT location FROM equipments WHERE instance_id=$1",id));
        Assert.Equal("RedBoss",await db.ScalarAsync<string>("SELECT source_kind FROM equipments WHERE instance_id=$1",id));
        Assert.Equal(pending.AttemptId,await db.ScalarAsync<Guid>("SELECT mint_id FROM equipments WHERE instance_id=$1",id));
        // Loss/destruction changes custody only; it never clears the quota or
        // creates an extraction-time mint. New repository instances see the same claim.
        await CraftingTestInputs.SqlAsync(db,"UPDATE equipments SET location='Recycled' WHERE instance_id=$1",id);
        var quota=await new RedEquipmentQuotaRepository(db.DataSource,f.Owner.Clock).GetCurrentAsync(Ct);
        Assert.True(quota.IsClaimed);Assert.Equal(id,quota.EquipmentId);
        Assert.Equal(original,await Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending,Ct));
        await Assert.ThrowsAsync<DomainValidationException>(()=>Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending with {EquipmentSeed=pending.EquipmentSeed+1},Ct));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task FailureAfterQuotaAndItemInsertRollsBackEverythingAndRetryUsesTheOriginalSeed()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db);
        await db.ExecuteAsync("""
            CREATE FUNCTION fail_red_attempt() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'red attempt fault'; END $$;
            CREATE TRIGGER fail_red_attempt BEFORE INSERT ON season_red_drop_attempts FOR EACH ROW EXECUTE FUNCTION fail_red_attempt();
            """);
        var pending=f.Room.GetPlayer(f.Owner.Player).PendingRedEvaluation!;
        var error=await Assert.ThrowsAsync<PostgresException>(()=>Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending,Ct));
        Assert.Equal(PostgresErrorCodes.RaiseException,error.SqlState);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM red_equipment_weekly_quotas"));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE mint_id=$1",pending.AttemptId));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM season_red_drop_attempts"));
        await db.ExecuteAsync("DROP TRIGGER fail_red_attempt ON season_red_drop_attempts");
        var result=await Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending,Ct);
        Assert.Equal("Minted",result.Status);
        Assert.Equal(SeasonRedConfig.Equipment(pending.EquipmentSeed,f.Owner.Season.StatsVersion,f.Room.GetPlayer(f.Owner.Player).LootPreferenceElement,
            GameConfigCatalog.Current.SeasonLootPreference),result.Equipment!.Equipment);
    }

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("Closed")] [InlineData("Miss")] [InlineData("Exhausted")]
    [Trait("Category","PostgresIntegration")]
    public async Task ExpiredSeasonLosingRollAndConsumedWeekRecordAStableNonMintedResult(string expected)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);var f=await Create(db,winning:expected!="Miss");
        if(expected=="Closed")f.Owner.Clock.Now=f.Owner.Season.EndsAtUtc;
        if(expected=="Exhausted")
        {
            await using var connection=await db.DataSource.OpenConnectionAsync(Ct);await using var tx=await connection.BeginTransactionAsync(Ct);
            Assert.True(await RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,f.Owner.Clock.Now,RedEquipmentDropSource.Activity,Guid.NewGuid(),null,Guid.NewGuid(),Ct));
            await tx.CommitAsync(Ct);
        }
        var pending=f.Room.GetPlayer(f.Owner.Player).PendingRedEvaluation!;
        var result=await Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending,Ct);
        Assert.Equal(expected,result.Status);Assert.Null(result.Equipment);
        f.Owner.Clock.Now=f.Owner.Clock.Now.AddDays(7);
        Assert.Equal(result,await Repository(db,f).ResolveBossAsync(f.Match,f.Owner.Player,f.Room.Season!,pending,Ct));
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE mint_id=$1",pending.AttemptId));
        Assert.Equal(expected=="Exhausted"?1L:0L,await db.ScalarAsync<long>("SELECT count(*) FROM red_equipment_weekly_quotas"));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task EveryChannelSharesTheDurableEconomyBindingAndMondayFourAmBoundary()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var monday=new DateTimeOffset(2026,11,1,20,0,0,TimeSpan.Zero);
        var attempts=Enumerable.Range(0,9).Select(async index=>
        {
            await using var connection=await db.DataSource.OpenConnectionAsync(Ct);await using var tx=await connection.BeginTransactionAsync(Ct);
            var result=await RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,monday.AddTicks(-1),(RedEquipmentDropSource)(index%3),Guid.NewGuid(),null,Guid.NewGuid(),Ct);
            await tx.CommitAsync(Ct);return result;
        });
        Assert.Single(await Task.WhenAll(attempts),value=>value);
        await using(var connection=await db.DataSource.OpenConnectionAsync(Ct))
        await using(var tx=await connection.BeginTransactionAsync(Ct))
        {
            Assert.True(await RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,monday,RedEquipmentDropSource.ShopChest,Guid.NewGuid(),null,Guid.NewGuid(),Ct));
            await tx.CommitAsync(Ct);
        }
        await using(var connection=await db.DataSource.OpenConnectionAsync(Ct))
        await using(var tx=await connection.BeginTransactionAsync(Ct))
        {
            var error=await Assert.ThrowsAsync<PostgresException>(()=>RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,monday,RedEquipmentDropSource.Activity,
                Guid.NewGuid(),null,Guid.NewGuid(),Ct,"invented-new-channel"));
            Assert.Equal(PostgresErrorCodes.ForeignKeyViolation,error.SqlState);
        }
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM red_equipment_weekly_quotas"));
        Assert.Equal("2026-10-26",RedEquipmentQuotaSchedule.GetWeekKey(monday.AddTicks(-1)));
        Assert.Equal("2026-11-02",RedEquipmentQuotaSchedule.GetWeekKey(monday));
    }

    [Fact(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [Trait("Category","PostgresIntegration")]
    public async Task UpgradingAPopulatedPreviousSchemaPreservesItsClaimAgainstNewMatchAndSourceIds()
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:false);
        var assembly=typeof(DatabaseMigrator).Assembly;
        var resources=assembly.GetManifestResourceNames().Where(name=>name.Contains(".Migrations.V",StringComparison.Ordinal) && name.EndsWith(".sql",StringComparison.Ordinal))
            .Order(StringComparer.Ordinal).ToArray();
        var previous=new List<string>();string? upgrade=null;
        foreach(var name in resources)
        {
            await using var stream=assembly.GetManifestResourceStream(name)!;using var reader=new StreamReader(stream);
            var sql=await reader.ReadToEndAsync(Ct);
            if(name.Contains(".V042__",StringComparison.Ordinal))upgrade=sql;else previous.Add(sql);
        }
        Assert.NotNull(upgrade);
        // Run exact embedded old SQL as a single explicit schema fixture; the
        // separate migration tests exercise the normal migrator and checksums.
        await db.ExecuteAsync(string.Join('\n',previous));
        var now=new DateTimeOffset(2026,11,1,20,0,0,TimeSpan.Zero);var player=Guid.NewGuid();var original=Guid.NewGuid();var oldMatch=Guid.NewGuid();
        await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO red_equipment_weekly_quotas(week_key,red_dropped_this_week,source,player_id,match_id,equipment_id,claimed_at)
            VALUES('2026-11-02',1,'ChaosBoss',$1,$2,$3,$4)
            """,player,oldMatch,original,now);
        await db.ExecuteAsync(upgrade);
        var quota=await new RedEquipmentQuotaRepository(db.DataSource,new CraftingClock(now)).GetCurrentAsync(Ct);
        Assert.Equal(original,quota.EquipmentId);Assert.Equal(oldMatch,quota.MatchId);Assert.Equal(player,quota.PlayerId);Assert.True(quota.IsClaimed);
        await using var connection=await db.DataSource.OpenConnectionAsync(Ct);await using var tx=await connection.BeginTransactionAsync(Ct);
        Assert.False(await RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,now.AddDays(2),RedEquipmentDropSource.Activity,Guid.NewGuid(),Guid.NewGuid(),Guid.NewGuid(),Ct));
        Assert.True(await RedEquipmentQuotaRepository.TryClaimAsync(connection,tx,now.AddDays(7),RedEquipmentDropSource.ShopChest,Guid.NewGuid(),Guid.NewGuid(),Guid.NewGuid(),Ct));
        await tx.CommitAsync(Ct);
        Assert.Equal(2L,await db.ScalarAsync<long>("SELECT count(*) FROM red_equipment_weekly_quotas"));
    }

    private static SeasonRedMintRepository Repository(PostgresTestSchema db,Fixture f)=>
        new(db.DataSource,f.Owner.Clock,new PublishedConfigCatalogs(GameConfigCatalog.Current));
    private static async Task<Fixture> Create(PostgresTestSchema db,bool winning=true)
    {
        var owner=await CraftingTestInputs.CreateAsync(db);var config=GameConfigCatalog.Current;
        var seed=Enumerable.Range(0,10000).First(value=>(new CombatRandom(unchecked(value^0x52454431)).Next(10000)<40)==winning);
        var version=await db.ScalarAsync<long>("SELECT version FROM player_decks WHERE player_id=$1 AND hero_class=2",owner.Player);
        var prepared=await new PreparationRepository(db.DataSource,owner.Clock).CreateAsync(owner.Player,"red-source-preparation",
            new(HeroClassDto.Mage,version,[null,null,null,null,null],BackpackTierDto.Free,[],0,"D2",owner.Season.SeasonId),Ct);
        Assert.Equal(CreatePreparationStatus.Created,prepared.Status);var source=prepared.Preparation!.Snapshot;
        var room=new BattleRoom(Guid.NewGuid(),config.Version,CombatCardCatalog.Create(config),seed,season:owner.Season.ContextFor(2));
        var player=room.AddPlayer(new(owner.Player,HeroClass.Mage,source.CardIds,null,CardLevels:source.CardLevels,LootPreferenceElement:source.LootPreferenceElement));
        var map=ChaosMapGenerator.Generate(seed,1).Capture();var start=map.SpawnPositions[0];
        map=map with {Cells=map.Cells.Select(cell=>cell.Position==start?cell with {Layer=ChaosMapLayer.Core,IsBoss=true,MonsterGroupId="BOSS"}:cell).ToArray()};
        room.InitializeMap(ChaosMapState.Restore(map));
        foreach(var monster in player.Pve!.Monsters.ToArray())
        {
            monster.TakeDamage(monster.Hp+monster.Shield-1);var deck=player.Combat.Deck;var old=deck.Capture();
            var cards=old.Hand.Concat(old.Library).Concat(old.Discard).ToArray();var card=cards.Single(value=>value.CardId=="C01");
            deck.Restore(new([card],cards.Where(value=>value.InstanceId!=card.InstanceId).ToArray(),[],0));
            room.PlayCards(owner.Player,player.Pve.BattleId,monster.MonsterId,[card.InstanceId],room.Revision,owner.Clock.Now,room.NewCombatActionId(owner.Player));
            room.Advance(TimeSpan.FromMilliseconds(500),owner.Clock.Now);
        }
        Assert.NotNull(player.PendingRedEvaluation);
        while(player.Inventory.FreeSlots>0)Assert.True(player.Inventory.TryAdd(new(Guid.NewGuid().ToString("D"),ExplorationItemKind.HealthPotion)));
        var match=Guid.NewGuid();await CraftingTestInputs.SqlAsync(db,"""
            INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,season_id,ruleset_id,stats_version)
            VALUES($1,$2,'ChaosRealm','D2',$3,$4,'Running',$5,$6,$7,$8)
            """,match,room.RoomId,seed,config.Version,owner.Clock.Now,owner.Season.SeasonId,owner.Season.RulesetId,owner.Season.StatsVersion);
        await CraftingTestInputs.SqlAsync(db,"UPDATE preparations SET status='Matched' WHERE preparation_id=$1",prepared.Preparation.PreparationId);
        await CraftingTestInputs.SqlAsync(db,"INSERT INTO match_players(match_id,player_id,preparation_id,is_bot,state) VALUES($1,$2,$3,false,'Active')",match,owner.Player,prepared.Preparation.PreparationId);
        using var metrics=new ServerMetrics();await new RoomSnapshotRepository(db.DataSource,owner.Clock,metrics).SaveIfDueAsync(room.Capture(),Ct);
        return new(owner,room,match,seed);
    }
    private sealed record Fixture(CraftingPlayer Owner,BattleRoom Room,Guid Match,int Seed);
}
