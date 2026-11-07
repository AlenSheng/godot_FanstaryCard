using System.Data;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonJourneyRepository
{
    private const string SeasonColumns="d.season_id,d.ruleset_id,d.config_version,d.stats_version,d.starts_at,d.ends_at,d.highest_open_difficulty,d.config_sha256";
    private const string EligibleSeason="d.ruleset_id='season-v1' AND (d.ends_at>$2 OR EXISTS(SELECT 1 FROM player_season_journeys j WHERE j.player_id=$1 AND j.season_id=d.season_id))";
    private const string SeasonOrder="CASE WHEN d.starts_at<=$2 AND d.ends_at>$2 THEN 0 WHEN d.starts_at>$2 THEN 1 ELSE 2 END,CASE WHEN d.ends_at>$2 THEN d.starts_at END,d.ends_at DESC,d.season_id";
    private sealed record JourneySeason(SeasonDefinition Definition,string Hash);
    private sealed record HeldWeekly(string Kind,int Target,int Reward,int Progress,int Credited,DateTimeOffset OpensAt,DateTimeOffset? CompletedAt);
    private static JourneySeason ReadSeason(NpgsqlDataReader r)=>new(new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3),
        r.GetFieldValue<DateTimeOffset>(4),r.GetFieldValue<DateTimeOffset>(5),r.GetInt16(6)),r.GetString(7));
    private static string State(SeasonDefinition s,DateTimeOffset now)=>now<s.StartsAtUtc?"Upcoming":now<s.EndsAtUtc?"Active":"Ended";

    public async Task<SeasonJourneyResponse> GetAsync(Guid player,CancellationToken ct,string? seasonId=null,int limit=50,int offset=0)
    {
        if(seasonId?.Length>80||limit is <1 or >100||offset is <0 or >1000000)throw new DomainValidationException("Journey history paging is invalid.");
        var now=clock.GetUtcNow();await using var c=await dataSource.OpenConnectionAsync(ct);
        await using var t=await c.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        var seasons=new List<JourneySeason>();
        await using(var q=new NpgsqlCommand("SELECT "+SeasonColumns+" FROM season_definitions d WHERE "+EligibleSeason+" ORDER BY "+SeasonOrder+" LIMIT $3 OFFSET $4",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(now);q.Parameters.AddWithValue(limit+1);q.Parameters.AddWithValue(offset);
            await using var r=await q.ExecuteReaderAsync(ct);while(await r.ReadAsync(ct))seasons.Add(ReadSeason(r));
        }
        var more=seasons.Count>limit;if(more)seasons.RemoveAt(seasons.Count-1);
        var history=seasons.Select(s=>new JourneySeasonResponse(s.Definition.SeasonId,State(s.Definition,now),s.Definition.ConfigVersion,s.Definition.StartsAtUtc,s.Definition.EndsAtUtc)).ToArray();
        JourneySeason? original=null;
        await using(var q=new NpgsqlCommand("SELECT "+SeasonColumns+" FROM season_definitions d WHERE "+
            (seasonId is null?EligibleSeason:"d.ruleset_id='season-v1' AND d.season_id=$3")+" ORDER BY "+SeasonOrder+" LIMIT 1",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(now);
            if(seasonId is not null)q.Parameters.AddWithValue(seasonId);
            await using var r=await q.ExecuteReaderAsync(ct);if(await r.ReadAsync(ct))original=ReadSeason(r);
        }
        if(original is null)
        {
            await t.CommitAsync(ct);
            return Empty("None",null,0,0,history,more?offset+limit:null);
        }
        var definition=original.Definition;var experience=0;long version=0;string? storedVersion=null;
        await using(var q=new NpgsqlCommand("SELECT experience,version,config_version FROM player_season_journeys WHERE player_id=$1 AND season_id=$2",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(definition.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            if(await r.ReadAsync(ct)){experience=r.GetInt32(0);version=r.GetInt64(1);storedVersion=r.GetString(2);}
        }
        SeasonJourneyConfig? policy=null;
        var unavailable=false;
        try
        {
            var config=configurations.Resolve(definition.ConfigVersion);
            unavailable=config.ContentHash!=original.Hash||(storedVersion is not null&&storedVersion!=config.Version);
            if(!unavailable)policy=config.SeasonJourney;
        }
        catch(Exception e) when(e is IOException or DomainValidationException){unavailable=true;}
        if(policy is null)
        {
            await t.CommitAsync(ct);
            return Empty(unavailable?"Unavailable":"Disabled",definition,experience,version,history,more?offset+limit:null);
        }
        var held=new Dictionary<(int Week,string Id),HeldWeekly>();
        await using(var q=new NpgsqlCommand("SELECT week_number,contract_id,completion_kind,target,experience_reward,progress,credited_experience,opens_at,completed_at FROM player_season_weekly_contracts WHERE player_id=$1 AND season_id=$2",c,t))
        {
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(definition.SeasonId);await using var r=await q.ExecuteReaderAsync(ct);
            while(await r.ReadAsync(ct))held.Add((r.GetInt32(0),r.GetString(1)),new(r.GetString(2),r.GetInt32(3),r.GetInt32(4),r.GetInt32(5),r.GetInt32(6),
                r.GetFieldValue<DateTimeOffset>(7),r.IsDBNull(8)?null:r.GetFieldValue<DateTimeOffset>(8)));
        }
        var state=State(definition,now);var day=now<definition.StartsAtUtc?0:definition.NaturalDayAt(now>=definition.EndsAtUtc?definition.EndsAtUtc.AddTicks(-1):now);
        var contracts=new List<WeeklyContractResponse>();
        for(var week=1;week<=(day==0?0:(day-1)/7+1);week++)
        {
            foreach(var rule in policy.WeeklyContracts)
            {
                var opens=definition.StartsAtUtc.AddDays((week-1)*7);
                held.TryGetValue((week,rule.ContractId),out var row);
                if(row is not null&&(row.Kind!=rule.CompletionKind||row.Target!=rule.Target||row.Reward!=rule.Experience||row.OpensAt!=opens))
                    throw new InvalidDataException("The original weekly contract snapshot changed.");
                var complete=row?.CompletedAt is not null;
                contracts.Add(new(rule.ContractId,week,rule.CompletionKind,rule.Target,row?.Progress??0,rule.Experience,row?.Credited??0,opens,row?.CompletedAt,
                    complete?"Completed":state=="Ended"?"Expired":"Open"));
            }
        }
        var progress=policy.Progress(experience,definition.DurationDays);
        var reference=day==0?0:policy.ReferenceAt(definition,now>=definition.EndsAtUtc?definition.EndsAtUtc.AddTicks(-1):now);
        var levels=Enumerable.Range(1,30).Select(level=>new JourneyLevelResponse(level,policy.Cost(level-1,definition.DurationDays),
            policy.Threshold(level,definition.DurationDays),level<=policy.MainRewardLevels?"Main":"Collection",level<=progress.Level)).ToArray();
        await t.CommitAsync(ct);
        return new(state,definition.SeasonId,definition.ConfigVersion,definition.StartsAtUtc,definition.EndsAtUtc,definition.DurationDays,day,
            experience,progress.Level,progress.ExperienceIntoLevel,progress.ExperienceToNext,policy.Threshold(30,definition.DurationDays),policy.MainRewardLevels,
            reference,policy.CatchUpMultiplier,state=="Active"&&experience<reference,version,contracts,levels,history,more?offset+limit:null);
    }

    private static SeasonJourneyResponse Empty(string state,SeasonDefinition? definition,int experience,long version,
        IReadOnlyList<JourneySeasonResponse> history,int? next)=>new(state,definition?.SeasonId,definition?.ConfigVersion,definition?.StartsAtUtc,definition?.EndsAtUtc,
            definition?.DurationDays??0,0,experience,0,0,0,0,0,0,0,false,version,[],[],history,next);
}
