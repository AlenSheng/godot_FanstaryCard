using System.Security.Cryptography;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Seasons;

namespace FantasyCard.Server.Tests.Persistence;

internal sealed class CraftingClock(DateTimeOffset now):TimeProvider
{
    public DateTimeOffset Now{get;set;}=now;
    public override DateTimeOffset GetUtcNow()=>Now;
}
internal sealed record CraftingPlayer(Guid Player,SeasonDefinition Season,CraftingClock Clock,SeasonRepository Seasons,ProgressionRepository Progression);
internal static class CraftingTestInputs
{
    internal static CancellationToken Ct=>TestContext.Current.CancellationToken;
    internal static async Task<CraftingPlayer> CreateAsync(PostgresTestSchema db,Func<int,int>? random=null)
    {
        var config=GameConfigCatalog.Current;
        var season=SeasonDefinition.FromCalendarDays("crafting-season",new(2026,11,1),config.Version,"season-equipment-v1",highestOpenDifficulty:5);
        var clock=new CraftingClock(season.StartsAtUtc.AddHours(2));
        var player=await PlayerAsync(db,clock);var seasons=new SeasonRepository(db.DataSource,clock);
        await seasons.PublishAsync(season,config.ContentHash,Ct);await seasons.EnsurePlayerAsync(player,season.ContextFor(0),Ct);
        await SqlAsync(db,"UPDATE player_season_state SET highest_unlocked_difficulty=5 WHERE player_id=$1",player);
        await seasons.ApplyAsync(player,season.ContextFor(0),0,5000,77,"test.legacy-marks","legacy",SeasonWalletPurpose.General,Ct);
        return new(player,season,clock,seasons,new(db.DataSource,clock,craftingRandom:random));
    }
    internal static async Task<Guid> PlayerAsync(PostgresTestSchema db,CraftingClock clock)=>(await new IdentityRepository(db.DataSource,new PlayerProvisioningService())
        .SignInLocalAsync(Guid.NewGuid().ToString("N"),"Craft-"+Guid.NewGuid().ToString("N")[..10],RandomNumberGenerator.GetBytes(32),clock.Now,clock.Now.AddHours(1),Ct)).UserId;
    internal static async Task<SeasonWalletSnapshot> FundAsync(PostgresTestSchema db,CraftingPlayer player,long blue,long orange,string key="blueprints")
    {
        await using var connection=await db.DataSource.OpenConnectionAsync(Ct);await using var transaction=await connection.BeginTransactionAsync(Ct);
        var result=await SeasonRepository.ApplyWithinTransactionAsync(connection,transaction,player.Player,player.Season.ContextFor(0),0,0,0,
            "test.blueprints",key,SeasonWalletPurpose.General,player.Clock.Now,new string('a',64),Ct,blue,orange);
        await transaction.CommitAsync(Ct);return result;
    }
    internal static async Task<Guid> ItemAsync(PostgresTestSchema db,CraftingPlayer player,string quality="Purple",string slot="Chest",string element="Fire",
        string? effect="Piercing",int level=0,bool bound=false,string source="NaturalDrop",string secondary="DrawInterval")
    {
        var id=Guid.NewGuid();
        await SqlAsync(db,"""
            INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,generated_difficulty)
            VALUES($1,$2,$3,$4,$5,$6,'Inventory',1,$7,$8,$9,$10,$11,$11,'ActiveSeason','season-equipment-v1',$12,5)
            """,id,player.Player,slot,quality,level,bound,player.Clock.Now,element,(object?)effect??DBNull.Value,secondary,player.Season.SeasonId,source);
        return id;
    }
    internal static async Task SqlAsync(PostgresTestSchema db,string sql,params object[] values)
    {
        await using var command=db.DataSource.CreateCommand(sql);
        foreach(var value in values)
            if(value is DBNull)command.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar,value);
            else command.Parameters.AddWithValue(value);
        await command.ExecuteNonQueryAsync(Ct);
    }
}
