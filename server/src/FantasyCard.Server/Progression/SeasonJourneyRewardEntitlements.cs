using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

internal sealed record HeldJourneyReward(Guid RewardId,Guid PlayerId,string SeasonId,string ConfigVersion,string ConfigHash,
    string RulesetId,string StatsVersion,int RequiredExperience,int ExperienceAtUnlock,long JourneyVersionAtUnlock,
    SeasonJourneyRewardConfig Definition,IReadOnlyList<string> PackCardIds,string State,DateTimeOffset CreatedAt,
    DateTimeOffset? ClaimedAt,string? HeroClassChoice,string? GrantJson,string? ResponseJson);

public sealed partial class SeasonJourneyRepository
{
    private const string HeldRewardColumns="""
        reward_id,player_id,season_id,config_version,config_sha256,ruleset_id,stats_version,required_experience,
        experience_at_unlock,journey_version_at_unlock,reward_key,reward_level,reward_kind,reward_amount,
        ownership,requires_class_choice,cosmetic_id,pack_card_ids::text,state,created_at,claimed_at,hero_class_choice,grant_json::text,response_json::text
        """;

    private static HeldJourneyReward ReadHeldReward(NpgsqlDataReader r)=>new(r.GetGuid(0),r.GetGuid(1),r.GetString(2),
        r.GetString(3),r.GetString(4),r.GetString(5),r.GetString(6),r.GetInt32(7),r.GetInt32(8),r.GetInt64(9),
        new(r.GetString(10),r.GetInt16(11),r.GetString(12),r.GetInt32(13),r.GetString(14),r.GetBoolean(15),r.IsDBNull(16)?null:r.GetString(16)),
        JsonSerializer.Deserialize<string[]>(r.GetString(17))??throw new InvalidDataException("The original journey pack result is invalid."),
        r.GetString(18),r.GetFieldValue<DateTimeOffset>(19),r.IsDBNull(20)?null:r.GetFieldValue<DateTimeOffset>(20),
        r.IsDBNull(21)?null:r.GetString(21),r.IsDBNull(22)?null:r.GetString(22),r.IsDBNull(23)?null:r.GetString(23));

    /// <summary>The caller owns the player lock and the original experience/settlement transaction.</summary>
    internal static async Task EnsureRewardsWithinTransactionAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,
        SeasonDefinition season,GameConfigCatalog config,DateTimeOffset now,Func<int,int> random,CancellationToken ct)
    {
        var rewards=config.SeasonJourneyRewards;
        if(rewards is null)return; // No current-policy fallback for an older published season.
        var journey=config.SeasonJourney??throw new InvalidDataException("The original journey experience policy is unavailable.");
        int experience;long version;
        await using(var q=new NpgsqlCommand("""
            SELECT j.experience,j.version,j.config_version,d.config_version,d.config_sha256,d.ruleset_id,d.stats_version,d.starts_at,d.ends_at
            FROM player_season_journeys j JOIN season_definitions d USING(season_id)
            WHERE j.player_id=$1 AND j.season_id=$2 FOR UPDATE OF j
            """,c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetString(2)!=config.Version||r.GetString(3)!=config.Version||season.ConfigVersion!=config.Version||
                r.GetString(4)!=config.ContentHash||r.GetString(5)!=season.RulesetId||season.RulesetId!="season-v1"||
                r.GetString(6)!=season.StatsVersion||r.GetFieldValue<DateTimeOffset>(7)!=season.StartsAtUtc||
                r.GetFieldValue<DateTimeOffset>(8)!=season.EndsAtUtc||now<season.StartsAtUtc)
                throw new InvalidDataException("Journey rewards differ from their original durable season and experience source.");
            experience=r.GetInt32(0);version=r.GetInt64(1);
        }
        var unlocked=journey.Progress(experience,season.DurationDays).Level;var held=new Dictionary<int,HeldJourneyReward>();
        await using(var q=new NpgsqlCommand("SELECT "+HeldRewardColumns+" FROM season_journey_reward_entitlements WHERE player_id=$1 AND season_id=$2 ORDER BY reward_level FOR UPDATE",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            while(await r.ReadAsync(ct))
            {
                var row=ReadHeldReward(r);ValidateHeldReward(row,season,config,experience,version);
                if(row.Definition.Level>unlocked)throw new InvalidDataException("A journey reward exceeds its original earned experience.");
                held.Add(row.Definition.Level,row);
            }
        }
        for(var level=1;level<=unlocked;level++)
        {
            if(held.ContainsKey(level))continue;
            var definition=rewards.At(level);
            var cards=definition.Kind=="CardPack"?rewards.Draw(level,null,config,random).CardIds:Array.Empty<string>();
            await using var q=new NpgsqlCommand("""
                INSERT INTO season_journey_reward_entitlements(reward_id,player_id,season_id,reward_level,reward_key,
                    config_version,config_sha256,ruleset_id,stats_version,required_experience,experience_at_unlock,
                    journey_version_at_unlock,reward_kind,reward_amount,ownership,requires_class_choice,cosmetic_id,pack_card_ids,created_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                """,c,t);
            q.Parameters.AddWithValue(Guid.CreateVersion7());q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);
            q.Parameters.AddWithValue((short)level);q.Parameters.AddWithValue(definition.RewardId);q.Parameters.AddWithValue(config.Version);
            q.Parameters.AddWithValue(config.ContentHash);q.Parameters.AddWithValue(season.RulesetId);q.Parameters.AddWithValue(season.StatsVersion);
            q.Parameters.AddWithValue(journey.Threshold(level,season.DurationDays));q.Parameters.AddWithValue(experience);q.Parameters.AddWithValue(version);
            q.Parameters.AddWithValue(definition.Kind);q.Parameters.AddWithValue(definition.Amount);q.Parameters.AddWithValue(definition.Ownership);
            q.Parameters.AddWithValue(definition.RequiresClassChoice);q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)definition.CosmeticId??DBNull.Value);
            q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(cards));q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
        }
    }

    private static void ValidateHeldReward(HeldJourneyReward held,SeasonDefinition season,GameConfigCatalog config,int experience,long version)
    {
        var policy=config.SeasonJourneyRewards??throw new InvalidDataException("The original journey reward policy is unavailable.");
        var expected=policy.At(held.Definition.Level);
        if(held.SeasonId!=season.SeasonId||held.ConfigVersion!=config.Version||held.ConfigHash!=config.ContentHash||
            held.RulesetId!=season.RulesetId||held.StatsVersion!=season.StatsVersion||held.Definition!=expected||
            held.RequiredExperience!=config.SeasonJourney!.Threshold(expected.Level,season.DurationDays)||
            held.ExperienceAtUnlock<held.RequiredExperience||held.ExperienceAtUnlock>experience||held.JourneyVersionAtUnlock>version||
            held.CreatedAt<season.StartsAtUtc||held.PackCardIds.Count!=(expected.Kind=="CardPack"?3:0)||
            held.PackCardIds.Any(id=>!config.Cards.Any(card=>card.CardId==id&&SeasonShopConfig.PackEligible(card))))
            throw new InvalidDataException("The held journey reward differs from its original configuration, experience or frozen pack.");
    }
}
