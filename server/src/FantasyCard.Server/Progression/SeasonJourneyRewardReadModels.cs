using System.Data;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonJourneyRepository
{
    private sealed record RewardRealm(SeasonDefinition Season,string Hash,GameConfigCatalog? Config);

    private async Task<RewardRealm?> RewardRealmAsync(NpgsqlConnection c,NpgsqlTransaction t,string seasonId,bool required,CancellationToken ct)
    {
        JourneySeason source;
        await using(var q=new NpgsqlCommand("SELECT "+SeasonColumns+" FROM season_definitions d WHERE d.season_id=$1 AND d.ruleset_id='season-v1'",c,t))
        {
            q.Parameters.AddWithValue(seasonId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct))
            {
                if(required)throw new DomainValidationException("The original journey season is unavailable.");
                return null;
            }
            source=ReadSeason(r);
        }
        try
        {
            var config=configurations.Resolve(source.Definition.ConfigVersion);
            if(config.ContentHash!=source.Hash)throw new InvalidDataException("The original journey publication hash changed.");
            return new(source.Definition,source.Hash,config);
        }
        catch(Exception error) when(error is IOException or InvalidDataException or DomainValidationException)
        {
            if(required)throw new DomainValidationException("The original journey reward configuration is unavailable.");
            return new(source.Definition,source.Hash,null);
        }
    }

    private static async Task<(int Experience,long Version,string? ConfigVersion)> RewardProgressAsync(NpgsqlConnection c,
        NpgsqlTransaction t,Guid player,string season,bool update,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand("SELECT experience,version,config_version FROM player_season_journeys WHERE player_id=$1 AND season_id=$2"+(update?" FOR UPDATE":""),c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season);await using var r=await q.ExecuteReaderAsync(ct);
        return await r.ReadAsync(ct)?(r.GetInt32(0),r.GetInt64(1),r.GetString(2)):(0,0,null);
    }

    private static JourneyRewardResponse RewardView(HeldJourneyReward held,bool canClaim)=>new(held.RewardId,held.SeasonId,
        held.ConfigVersion,held.Definition.Level,held.RequiredExperience,held.Definition.Kind,held.Definition.Amount,
        held.Definition.Ownership,held.Definition.RequiresClassChoice,held.Definition.CosmeticId,held.State,
        canClaim&&held.State=="Pending",held.HeroClassChoice,held.CreatedAt,held.ClaimedAt);

    public async Task<JourneyRewardsResponse> GetRewardsAsync(Guid player,string seasonId,CancellationToken ct)
    {
        RequireRewardIdentity(seasonId);
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        var realm=await RewardRealmAsync(c,t,seasonId,false,ct);
        if(realm is null){await t.CommitAsync(ct);return new("None",null,null,[]);}
        var progress=await RewardProgressAsync(c,t,player,seasonId,false,ct);var held=new Dictionary<int,HeldJourneyReward>();
        await using(var q=new NpgsqlCommand("SELECT "+HeldRewardColumns+" FROM season_journey_reward_entitlements WHERE player_id=$1 AND season_id=$2 ORDER BY reward_level",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(seasonId);await using var r=await q.ExecuteReaderAsync(ct);
            while(await r.ReadAsync(ct)){var row=ReadHeldReward(r);held.Add(row.Definition.Level,row);}
        }
        var config=realm.Config;
        if(config is null||progress.ConfigVersion is not null&&progress.ConfigVersion!=realm.Season.ConfigVersion)
        {
            await t.CommitAsync(ct);return new("Unavailable",realm.Season.SeasonId,realm.Season.ConfigVersion,held.Values.Select(row=>RewardView(row,false)).ToArray());
        }
        if(config.SeasonJourneyRewards is not {} policy)
        {
            if(held.Count!=0)throw new InvalidDataException("An original season without rewards has held reward records.");
            await t.CommitAsync(ct);return new("Disabled",realm.Season.SeasonId,config.Version,[]);
        }
        var now=clock.GetUtcNow();var views=new List<JourneyRewardResponse>();var missingEarnedSource=false;
        foreach(var reward in policy.Rewards.OrderBy(r=>r.Level))
        {
            if(held.TryGetValue(reward.Level,out var row))
            {
                ValidateHeldReward(row,realm.Season,config,progress.Experience,progress.Version);
                views.Add(RewardView(row,now>=realm.Season.StartsAtUtc));
            }
            else
            {
                var threshold=config.SeasonJourney!.Threshold(reward.Level,realm.Season.DurationDays);var earned=progress.Experience>=threshold;
                missingEarnedSource|=earned;
                views.Add(new(null,seasonId,config.Version,reward.Level,threshold,reward.Kind,reward.Amount,reward.Ownership,
                    reward.RequiresClassChoice,reward.CosmeticId,earned?"Unavailable":"Locked",false));
            }
        }
        await t.CommitAsync(ct);return new(missingEarnedSource?"Unavailable":State(realm.Season,now),seasonId,config.Version,views);
    }

    private static async Task<CosmeticSelectionResponse> ReadCosmeticSelectionAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,bool update,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand("SELECT avatar_frame_id,card_back_id,title_id,version FROM player_cosmetic_profiles WHERE player_id=$1"+(update?" FOR UPDATE":""),c,t);
        q.Parameters.AddWithValue(player);await using var r=await q.ExecuteReaderAsync(ct);
        return await r.ReadAsync(ct)?new(r.IsDBNull(0)?null:r.GetString(0),r.IsDBNull(1)?null:r.GetString(1),r.IsDBNull(2)?null:r.GetString(2),r.GetInt64(3)):new(null,null,null,0);
    }

    public async Task<CosmeticsResponse> GetCosmeticsAsync(Guid player,CancellationToken ct)
    {
        await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        var owned=new List<OwnedCosmeticResponse>();
        await using(var q=new NpgsqlCommand("""
            SELECT o.cosmetic_id,o.kind,o.name_key,o.description_key,e.season_id,e.config_version,o.acquired_at
            FROM player_cosmetics o JOIN season_journey_reward_entitlements e ON e.reward_id=o.source_reward_id AND e.player_id=o.player_id
            WHERE o.player_id=$1 ORDER BY o.acquired_at,o.cosmetic_id
            """,c,t))
        {
            q.Parameters.AddWithValue(player);await using var r=await q.ExecuteReaderAsync(ct);
            while(await r.ReadAsync(ct))owned.Add(new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3),r.GetString(4),r.GetString(5),r.GetFieldValue<DateTimeOffset>(6)));
        }
        var selection=await ReadCosmeticSelectionAsync(c,t,player,false,ct);await t.CommitAsync(ct);return new(owned,selection);
    }
}
