using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonJourneyRepository
{
    private static async Task<long> GrantJourneySoulAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,HeldJourneyReward held,
        SeasonDefinition season,string currency,DateTimeOffset now,CancellationToken ct)
    {
        var column=currency switch {"WarriorSoul"=>"warrior_soul","PriestSoul"=>"priest_soul","MageSoul"=>"mage_soul","GuardianSoul"=>"guardian_soul",_=>throw new DomainValidationException("The original journey soul class is invalid.")};
        long balance;
        await using(var q=new NpgsqlCommand($"UPDATE player_materials SET {column}={column}+$1,version=version+1 WHERE player_id=$2 RETURNING {column}",c,t))
        {
            q.Parameters.AddWithValue(held.Definition.Amount);q.Parameters.AddWithValue(player);
            balance=await q.ExecuteScalarAsync(ct) is long value?value:throw new DomainValidationException("The permanent journey material aggregate is missing.");
        }
        await using var ledger=new NpgsqlCommand("""
            INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at,
                season_id,source_kind,difficulty_id,ruleset_id,config_version,stats_version)
            VALUES($1,$2,$3,$4,$5,$6,'journey.claim',$7,$8,'SeasonJourney','D0',$9,$10,$11)
            """,c,t);
        ledger.Parameters.AddWithValue(Guid.CreateVersion7());ledger.Parameters.AddWithValue(player);ledger.Parameters.AddWithValue(held.RewardId.ToString("D"));
        ledger.Parameters.AddWithValue(currency);ledger.Parameters.AddWithValue((long)held.Definition.Amount);ledger.Parameters.AddWithValue(balance);
        ledger.Parameters.AddWithValue(now);ledger.Parameters.AddWithValue(season.SeasonId);ledger.Parameters.AddWithValue(season.RulesetId);
        ledger.Parameters.AddWithValue(season.ConfigVersion);ledger.Parameters.AddWithValue(season.StatsVersion);await ledger.ExecuteNonQueryAsync(ct);return balance;
    }

    private static async Task<bool> GrantJourneyCosmeticAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,HeldJourneyReward held,
        SeasonCosmeticConfig cosmetic,DateTimeOffset now,CancellationToken ct)
    {
        int created;
        await using(var q=new NpgsqlCommand("""
            INSERT INTO player_cosmetics(player_id,cosmetic_id,kind,name_key,description_key,source_reward_id,acquired_at)
            VALUES($1,$2,$3,$4,$5,$6,$7) ON CONFLICT(player_id,cosmetic_id) DO NOTHING
            """,c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(cosmetic.CosmeticId);q.Parameters.AddWithValue(cosmetic.Kind);
            q.Parameters.AddWithValue(cosmetic.NameKey);q.Parameters.AddWithValue(cosmetic.DescriptionKey);q.Parameters.AddWithValue(held.RewardId);
            q.Parameters.AddWithValue(now);created=await q.ExecuteNonQueryAsync(ct);
        }
        if(created==0)
        {
            await using var q=new NpgsqlCommand("SELECT kind,name_key,description_key FROM player_cosmetics WHERE player_id=$1 AND cosmetic_id=$2",c,t);
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(cosmetic.CosmeticId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetString(0)!=cosmetic.Kind||r.GetString(1)!=cosmetic.NameKey||r.GetString(2)!=cosmetic.DescriptionKey)
                throw new InvalidDataException("The existing cosmetic differs from its permanent published identity.");
            return false; // Another season never turns an already owned cosmetic into currency.
        }
        await using(var q=new NpgsqlCommand("INSERT INTO player_cosmetic_profiles(player_id) VALUES($1) ON CONFLICT DO NOTHING",c,t))
        {q.Parameters.AddWithValue(player);await q.ExecuteNonQueryAsync(ct);}
        await using(var q=new NpgsqlCommand("UPDATE player_cosmetic_profiles SET version=version+1 WHERE player_id=$1",c,t))
        {q.Parameters.AddWithValue(player);await q.ExecuteNonQueryAsync(ct);}
        return true;
    }
}
