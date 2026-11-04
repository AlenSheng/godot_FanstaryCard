using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Players;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonActivityRepository
{
    public async Task<SeasonActivitiesResponse> GetAsync(Guid player,CancellationToken ct,string? selectedSeason=null,int limit=50,int offset=0)
    {
        if(limit is <1 or >100||offset is <0 or >1000000||selectedSeason?.Length>80)throw new DomainValidationException("Activity paging is invalid.");
        var now=clock.GetUtcNow();await using var c=await dataSource.OpenConnectionAsync(ct);await using var t=await c.BeginTransactionAsync(ct);
        SeasonDefinition? current=null;
        await using(var q=new NpgsqlCommand("""
            SELECT season_id,ruleset_id,config_version,stats_version,starts_at,ends_at,highest_open_difficulty,config_sha256
            FROM season_definitions WHERE ruleset_id='season-v1' AND (($1::varchar IS NULL AND ends_at>$2) OR season_id=$1)
            ORDER BY starts_at LIMIT 1
            """,c,t))
        {
            q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)selectedSeason??DBNull.Value);q.Parameters.AddWithValue(now);await using var r=await q.ExecuteReaderAsync(ct);
            if(await r.ReadAsync(ct))current=new(r.GetString(0),r.GetString(1),r.GetString(2),r.GetString(3),r.GetFieldValue<DateTimeOffset>(4),r.GetFieldValue<DateTimeOffset>(5),r.GetInt16(6));
        }
        if(current is not null)
        {
            try
            {
                var config=configurations.Resolve(current.ConfigVersion);
                if(config.SeasonActivity is not null)await EnsureEventsWithinTransactionAsync(c,t,current,config,ct);
            }
            catch(IOException) { /* Existing history is still readable; mutation fails closed. */ }
        }
        var ids=new List<(string Season,string Event)>();
        await using(var q=new NpgsqlCommand("""
            SELECT e.season_id,e.event_id FROM season_activity_events e
            WHERE ($1::varchar IS NOT NULL AND e.season_id=$1) OR ($1::varchar IS NULL AND
                (e.season_id=$2 OR EXISTS(SELECT 1 FROM player_season_activity_accounts a WHERE a.player_id=$3 AND a.season_id=e.season_id AND a.event_id=e.event_id)))
            ORDER BY e.starts_at DESC,e.season_id,e.event_id LIMIT $4 OFFSET $5
            """,c,t))
        {
            q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)selectedSeason??DBNull.Value);q.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)current?.SeasonId??DBNull.Value);
            q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(limit+1);q.Parameters.AddWithValue(offset);await using var r=await q.ExecuteReaderAsync(ct);
            while(await r.ReadAsync(ct))ids.Add((r.GetString(0),r.GetString(1)));
        }
        var more=ids.Count>limit;if(more)ids.RemoveAt(ids.Count-1);var result=new List<ActivityEventResponse>();
        foreach(var id in ids)
        {
            var realm=await Realm(c,t,id.Season,id.Event,false,ct);var account=await Account(c,t,player,id.Season,id.Event,false,ct);
            var rewards=new List<ActivityRewardResponse>();
            await using(var q=new NpgsqlCommand(RewardSelect+" WHERE player_id=$1 AND season_id=$2 AND event_id=$3 ORDER BY created_at,reward_id",c,t))
            {
                q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(id.Season);q.Parameters.AddWithValue(id.Event);await using var r=await q.ExecuteReaderAsync(ct);
                while(await r.ReadAsync(ct))rewards.Add(Reward(r,realm.Config is not null));
            }
            var policy=realm.Policy;var canExchange=policy is not null&&now>=realm.Window.StartsAt&&(now<realm.Window.EndsAt||policy.LateExchange);
            var options=policy?.Exchanges.Select(rule=>new ActivityExchangeOptionResponse(rule.RuleId,rule.TokenCost,rule.RewardKind,rule.RewardCount,rule.EventLimit,
                rewards.Where(r=>r.RuleId==rule.RuleId).Sum(r=>r.Quantity))).ToArray()??[];
            var state=policy is null?"Unavailable":now<realm.Window.StartsAt?"Upcoming":now<realm.Window.EndsAt?"Active":"Ended";
            result.Add(new(id.Season,id.Event,state,realm.Window.StartsAt,realm.Window.EndsAt,account.Earned,account.Spent,
                account.Earned-account.Spent,12,account.Version,canExchange,realm.Season.ConfigVersion,options,rewards));
        }
        await t.CommitAsync(ct);return new(result,more?offset+limit:null);
    }
}
