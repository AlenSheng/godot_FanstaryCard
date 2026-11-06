using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonJourneyRepository
{
    private static async Task<int> ProgressContract(NpgsqlConnection c,NpgsqlTransaction t,Guid player,SeasonDefinition season,
        SeasonJourneyConfig policy,SeasonJourneySource source,Guid sourceId,int experience,DateTimeOffset recordedAt,CancellationToken ct)
    {
        var rule=policy.WeeklyContracts.SingleOrDefault(r=>r.CompletionKind==source.Kind);
        if(rule is null)return experience;
        var sourceWeek=SeasonJourneyConfig.WeekAt(season,source.OccurredAt);
        for(var week=1;week<=sourceWeek;week++)
        {
            await using var q=new NpgsqlCommand("""
                INSERT INTO player_season_weekly_contracts(player_id,season_id,week_number,contract_id,completion_kind,target,experience_reward,opens_at)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8) ON CONFLICT DO NOTHING
                """,c,t);
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(week);q.Parameters.AddWithValue(rule.ContractId);
            q.Parameters.AddWithValue(rule.CompletionKind);q.Parameters.AddWithValue(rule.Target);q.Parameters.AddWithValue(rule.Experience);
            q.Parameters.AddWithValue(season.StartsAtUtc.AddDays((week-1)*7));await q.ExecuteNonQueryAsync(ct);
        }
        int selectedWeek;int progress;
        await using(var q=new NpgsqlCommand("""
            SELECT week_number,progress,target,experience_reward,opens_at FROM player_season_weekly_contracts
            WHERE player_id=$1 AND season_id=$2 AND contract_id=$3 AND week_number<=$4 AND progress<target
            ORDER BY week_number LIMIT 1 FOR UPDATE
            """,c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(rule.ContractId);q.Parameters.AddWithValue(sourceWeek);
            await using var r=await q.ExecuteReaderAsync(ct);if(!await r.ReadAsync(ct))return experience;
            selectedWeek=r.GetInt32(0);progress=r.GetInt32(1)+1;
            if(r.GetInt32(2)!=rule.Target||r.GetInt32(3)!=rule.Experience||r.GetFieldValue<DateTimeOffset>(4)!=season.StartsAtUtc.AddDays((selectedWeek-1)*7))
                throw new InvalidDataException("The original weekly contract terms changed.");
        }
        var complete=progress==rule.Target;
        var credited=complete?Math.Min(rule.Experience,policy.Threshold(30,season.DurationDays)-experience):0;
        await using(var q=new NpgsqlCommand("""
            UPDATE player_season_weekly_contracts SET progress=$1,credited_experience=$2,completed_at=$3
            WHERE player_id=$4 AND season_id=$5 AND week_number=$6 AND contract_id=$7
            """,c,t))
        {
            q.Parameters.AddWithValue(progress);q.Parameters.AddWithValue(credited);
            q.Parameters.AddWithValue(NpgsqlDbType.TimestampTz,complete?source.OccurredAt.ToUniversalTime():DBNull.Value);
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(selectedWeek);q.Parameters.AddWithValue(rule.ContractId);
            await q.ExecuteNonQueryAsync(ct);
        }
        await using(var q=new NpgsqlCommand("INSERT INTO season_weekly_contract_events(source_id,player_id,season_id,week_number,contract_id,progress_after) VALUES($1,$2,$3,$4,$5,$6)",c,t))
        {
            q.Parameters.AddWithValue(sourceId);q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(selectedWeek);
            q.Parameters.AddWithValue(rule.ContractId);q.Parameters.AddWithValue(progress);await q.ExecuteNonQueryAsync(ct);
        }
        experience+=credited;
        await Ledger(c,t,player,season.SeasonId,credited,experience,null,selectedWeek,rule.ContractId,recordedAt,ct);
        return experience;
    }
}
