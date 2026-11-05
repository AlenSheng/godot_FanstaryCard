using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Rooms;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

internal sealed record SeasonJourneySource(string Key,string Kind,Guid? BattleId,DateTimeOffset OccurredAt);

public sealed partial class SeasonJourneyRepository(NpgsqlDataSource dataSource,TimeProvider clock,PublishedConfigCatalogs configurations)
{
    /// <summary>The settlement caller owns the player row lock and the entire transaction.</summary>
    internal static async Task CreditWithinTransactionAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,Guid match,
        Guid settlement,Guid room,SeasonDefinition season,GameConfigCatalog config,int difficulty,
        IReadOnlyList<SeasonJourneySource> sources,DateTimeOffset recordedAt,long sourceRevision,CancellationToken ct)
    {
        var policy=config.SeasonJourney??throw new InvalidDataException("The original journey policy is missing.");
        await using(var q=new NpgsqlCommand("SELECT config_sha256 FROM season_definitions WHERE season_id=$1 AND config_version=$2",c,t))
        {
            q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(config.Version);
            if(await q.ExecuteScalarAsync(ct) as string!=config.ContentHash)
                throw new InvalidDataException("Journey source differs from the original published season.");
        }
        await using(var q=new NpgsqlCommand("INSERT INTO player_season_journeys(player_id,season_id,config_version) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(config.Version);await q.ExecuteNonQueryAsync(ct);
        }
        int experience;
        await using(var q=new NpgsqlCommand("SELECT experience,config_version FROM player_season_journeys WHERE player_id=$1 AND season_id=$2 FOR UPDATE",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            if(!await r.ReadAsync(ct)||r.GetString(1)!=config.Version)throw new InvalidDataException("Journey aggregate has another original configuration.");
            experience=r.GetInt32(0);
        }
        foreach(var source in sources.OrderBy(s=>s.OccurredAt).ThenBy(s=>s.Key,StringComparer.Ordinal))
        {
            if(!season.Contains(source.OccurredAt))continue;
            await using(var q=new NpgsqlCommand("SELECT season_id,completion_kind,occurred_at,battle_id FROM season_journey_sources WHERE player_id=$1 AND room_id=$2 AND source_key=$3",c,t))
            {
                q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(room);q.Parameters.AddWithValue(source.Key);await using var r=await q.ExecuteReaderAsync(ct);
                if(await r.ReadAsync(ct))
                {
                    if(r.GetString(0)!=season.SeasonId||r.GetString(1)!=source.Kind||r.GetFieldValue<DateTimeOffset>(2)!=source.OccurredAt||
                        (r.IsDBNull(3)?null:(Guid?)r.GetGuid(3))!=source.BattleId)
                        throw new InvalidDataException("Journey replay changed its original completion source.");
                    continue;
                }
            }
            var grant=policy.Grant(season,source.OccurredAt,experience,source.Kind);var sourceId=Guid.CreateVersion7();
            await using(var q=new NpgsqlCommand("""
                INSERT INTO season_journey_sources(source_id,player_id,season_id,room_id,match_id,settlement_id,source_key,
                    completion_kind,battle_id,config_version,difficulty_id,occurred_at,base_experience,catch_up_experience,
                    credited_experience,experience_before,experience_after,recorded_at,source_revision)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
                """,c,t))
            {
                q.Parameters.AddWithValue(sourceId);q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);
                q.Parameters.AddWithValue(room);q.Parameters.AddWithValue(match);q.Parameters.AddWithValue(settlement);
                q.Parameters.AddWithValue(source.Key);q.Parameters.AddWithValue(source.Kind);
                q.Parameters.AddWithValue(NpgsqlDbType.Uuid,(object?)source.BattleId??DBNull.Value);
                q.Parameters.AddWithValue(config.Version);q.Parameters.AddWithValue($"D{difficulty}");q.Parameters.AddWithValue(source.OccurredAt.ToUniversalTime());
                q.Parameters.AddWithValue(grant.BaseExperience);q.Parameters.AddWithValue(grant.CatchUpExperience);q.Parameters.AddWithValue(grant.CreditedExperience);
                q.Parameters.AddWithValue(experience);q.Parameters.AddWithValue(grant.ExperienceAfter);q.Parameters.AddWithValue(recordedAt);
                q.Parameters.AddWithValue(sourceRevision);await q.ExecuteNonQueryAsync(ct);
            }
            experience=grant.ExperienceAfter;
            await Ledger(c,t,player,season.SeasonId,grant.CreditedExperience,experience,sourceId,null,null,recordedAt,ct);
            experience=await ProgressContract(c,t,player,season,policy,source,sourceId,experience,recordedAt,ct);
            await using var update=new NpgsqlCommand("UPDATE player_season_journeys SET experience=$1,version=version+1 WHERE player_id=$2 AND season_id=$3",c,t);
            update.Parameters.AddWithValue(experience);update.Parameters.AddWithValue(player);update.Parameters.AddWithValue(season.SeasonId);await update.ExecuteNonQueryAsync(ct);
        }
        await EnsureRewardsWithinTransactionAsync(c,t,player,season,config,recordedAt,System.Security.Cryptography.RandomNumberGenerator.GetInt32,ct);
    }

    private static async Task Ledger(NpgsqlConnection c,NpgsqlTransaction t,Guid player,string season,int amount,int balance,
        Guid? source,int? week,string? contract,DateTimeOffset now,CancellationToken ct)
    {
        if(amount==0)return;
        await using var q=new NpgsqlCommand("INSERT INTO season_journey_ledger(player_id,season_id,amount,balance_after,source_id,contract_week,contract_id,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)",c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season);q.Parameters.AddWithValue(amount);q.Parameters.AddWithValue(balance);
        q.Parameters.AddWithValue(NpgsqlDbType.Uuid,(object?)source??DBNull.Value);q.Parameters.AddWithValue(NpgsqlDbType.Integer,(object?)week??DBNull.Value);
        q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)contract??DBNull.Value);q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
    }
}
