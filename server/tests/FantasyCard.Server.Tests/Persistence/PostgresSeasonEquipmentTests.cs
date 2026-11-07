using System.Security.Cryptography;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Seasons;
using Microsoft.Extensions.Logging.Abstractions;
using NpgsqlTypes;

namespace FantasyCard.Server.Tests.Persistence;

public sealed class PostgresSeasonEquipmentTests
{
    public static bool HasTestDatabase=>PostgresRuntimeIntegrationTests.HasTestDatabase;
    private static CancellationToken Ct=>TestContext.Current.CancellationToken;
    private static readonly string[] Slots=["Head","Chest","Hands","Legs","Feet"];

    [Theory(Skip="Requires isolated PostgreSQL.",SkipUnless=nameof(HasTestDatabase))]
    [InlineData("Inferno")] [InlineData("RapidDraw")] [InlineData("Scavenge")] [InlineData("ChainDraw")] [InlineData("GoldenCicada")]
    [Trait("Category","PostgresIntegration")]
    public async Task ExistingRedUniqueSurvivesPreparationLaunchAndRecoveryWithActualNewStats(string unique)
    {
        await using var db=await PostgresTestSchema.CreateAsync(migrate:true);
        var config=GameConfigCatalog.Current;var definition=SeasonDefinition.FromCalendarDays("equipment",new DateOnly(2026,11,2),config.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var clock=new Clock(definition.StartsAtUtc);var seasons=new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(definition,new string('a',64),Ct);
        var key=Guid.NewGuid().ToString("N");var player=(await new IdentityRepository(db.DataSource,new PlayerProvisioningService()).SignInLocalAsync(
            key,"Gear "+key[..8],RandomNumberGenerator.GetBytes(32),clock.Now,clock.Now.AddHours(1),Ct)).UserId;
        await seasons.EnsurePlayerAsync(player,definition.ContextFor(0),Ct);
        await using(var unlock=db.DataSource.CreateCommand("UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1"))
        {unlock.Parameters.AddWithValue(player);await unlock.ExecuteNonQueryAsync(Ct);}
        Guid?[] ids=new Guid?[5];var redIndex=unique=="GoldenCicada"?4:0;
        for(var index=0;index<5;index++)
        {
            var id=Guid.NewGuid();ids[index]=id;
            // Declared pre-existing owned red control. This does not exercise or claim C11 mint/quota acceptance.
            await using var seed=db.DataSource.CreateCommand("""
                INSERT INTO equipments(instance_id,owner_id,slot,quality,level,location,created_at,element,effect_affix,secondary_trait,
                    origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty,unique_affix,unique_element,mint_id)
                VALUES($1,$2,$3,$4,5,'Equipped',now(),'Fire','Piercing','DrawInterval','equipment','equipment','ActiveSeason',
                    'season-equipment-v1','ControlledExistingItem',5,$5,$6,$7)
                """);
            seed.Parameters.AddWithValue(id);seed.Parameters.AddWithValue(player);seed.Parameters.AddWithValue(Slots[index]);seed.Parameters.AddWithValue(index==redIndex?"Red":"Purple");
            seed.Parameters.AddWithValue(NpgsqlDbType.Varchar,index==redIndex?unique:DBNull.Value);
            seed.Parameters.AddWithValue(NpgsqlDbType.Varchar,index==redIndex && unique=="Inferno"?"Fire":DBNull.Value);
            seed.Parameters.AddWithValue(NpgsqlDbType.Uuid,index==redIndex?Guid.NewGuid():DBNull.Value);await seed.ExecuteNonQueryAsync(Ct);
        }
        var inventory=await new ProgressionRepository(db.DataSource,clock).GetInventoryAsync(player,Ct);
        Assert.Equal(unique,Assert.Single(inventory.Equipments,item=>item.Quality=="Red").UniqueAffix);
        var preparation=(await new PreparationRepository(db.DataSource,clock).CreateAsync(player,"prepare",new(HeroClassDto.Mage,0,ids,BackpackTierDto.Free,[],0,"D5",definition.SeasonId,true),Ct)).Preparation!;
        var red=Assert.Single(preparation.Snapshot.EquipmentSnapshots!,item=>item.Quality=="Red");
        Assert.Equal(unique,red.UniqueAffix);Assert.Equal(definition.StatsVersion,red.StatsVersion);
        using var metrics=new ServerMetrics();var matcher=new MatchmakingRepository(db.DataSource,clock,metrics);
        await matcher.EnqueueAsync(player,"queue",new(preparation.PreparationId),Ct);clock.Now=clock.Now.AddSeconds(31);
        var pending=Assert.IsType<PendingMatch>(await matcher.TryCreateMatchAsync(Ct));await matcher.MarkReadyAsync(player,clock.Now,Ct);
        var snapshots=new RoomSnapshotRepository(db.DataSource,clock,metrics);
        await using(var rooms=new RoomRegistry(clock))
        {
            using var coordinator=new RoomReadyCoordinator(matcher,rooms,snapshots,new RealtimeEventStore(clock),new ConnectionRegistry(),clock,NullLogger<RoomReadyCoordinator>.Instance);
            Assert.True(await coordinator.ProcessNextAsync(clock.Now,Ct));Assert.True(rooms.ContainsRoom(pending.RoomId));
        }
        var saved=(await snapshots.GetAsync(pending.RoomId,Ct))!;var owner=Assert.Single(saved.Players,value=>value.PlayerId==player);
        var profile=owner.Combat.Equipment!;Assert.Equal(definition.StatsVersion,profile.StatsVersion);
        Assert.Equal(.71,profile.RawElements!.FireResistance,8);Assert.Equal(.6,profile.Elements.FireResistance,8);
        Assert.Equal(unique=="Inferno"?1.77:1.62,profile.Elements.FireDamageBonus,8);
        Assert.Equal(unique=="RapidDraw"?-.55:-.51,profile.DrawIntervalModifier,8);
        Assert.Equal(unique,Assert.Single(owner.WornArmor!,item=>item.ItemId==ids[redIndex]!.Value.ToString("D")).Equipment!.UniqueAffix);
        Assert.Equal(unique=="Scavenge"?4:3,owner.Combat.Deck.Hand.Count);
        var health=new RoomRecoveryState();await using var restarted=new RoomRegistry(clock);
        await new RoomRecoveryWorker(snapshots,restarted,health,clock,NullLogger<RoomRecoveryWorker>.Instance).StartAsync(Ct);
        Assert.True(health.Capture().IsHealthy);Assert.True(restarted.TryGetForPlayer(player,out var actor));
        var recovered=await actor!.ExecuteAsync(new GetRoomSnapshotCommand(),Ct);
        var resumed=Assert.Single(recovered.Players,value=>value.PlayerId==player);
        Assert.Equal(owner.Combat.Equipment,resumed.Combat.Equipment);
        Assert.Equal(owner.Combat.LastOpeningBattleId,resumed.Combat.LastOpeningBattleId);
        Assert.Equal(0L,await db.ScalarAsync<long>("SELECT count(*) FROM equipments WHERE source_kind IN ('NaturalDrop','BotReward')"));
    }

    private sealed class Clock(DateTimeOffset now):TimeProvider
    {
        public DateTimeOffset Now{get;set;}=now;
        public override DateTimeOffset GetUtcNow()=>Now;
    }
}
