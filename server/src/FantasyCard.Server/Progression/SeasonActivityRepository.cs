using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class SeasonActivityRepository(NpgsqlDataSource dataSource,TimeProvider clock,PublishedConfigCatalogs configurations)
{
    private sealed record EventRealm(SeasonDefinition Season,string Hash,SeasonActivityWindow Window,GameConfigCatalog? Config)
    { public SeasonActivityConfig? Policy=>Config?.SeasonActivity; }
    private const string EventSelect="""
        SELECT e.season_id,e.event_id,e.config_version,e.config_sha256,e.ruleset_id,e.stats_version,e.starts_at,e.ends_at,
            d.config_version,d.config_sha256,d.ruleset_id,d.stats_version,d.starts_at,d.ends_at,d.highest_open_difficulty
        FROM season_activity_events e JOIN season_definitions d USING(season_id)
        """;
    private static async Task LockPlayer(NpgsqlConnection c,NpgsqlTransaction t,Guid player,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE",c,t);q.Parameters.AddWithValue(player);
        if(await q.ExecuteScalarAsync(ct) is null)throw new DomainValidationException("The activity account is unavailable.");
    }
    private static void RequireKey(string key)
    {
        if(string.IsNullOrWhiteSpace(key)||key.Length>80||key.Any(char.IsControl))throw new DomainValidationException("Activity request identity is invalid.");
    }
    internal static async Task EnsureEventsWithinTransactionAsync(NpgsqlConnection c,NpgsqlTransaction t,SeasonDefinition season,
        GameConfigCatalog config,CancellationToken ct)
    {
        var policy=config.SeasonActivity??throw new DomainValidationException("This original season has no activity policy.");
        if(config.Version!=season.ConfigVersion)throw new DomainValidationException("Activity configuration differs from its original season.");
        await using(var source=new NpgsqlCommand("SELECT config_sha256 FROM season_definitions WHERE season_id=$1 AND config_version=$2",c,t))
        {source.Parameters.AddWithValue(season.SeasonId);source.Parameters.AddWithValue(config.Version);if(await source.ExecuteScalarAsync(ct) as string!=config.ContentHash)throw new DomainValidationException("Activity publication hash differs from its original configuration.");}
        foreach(var window in policy.Windows(season))
        {
            await using var q=new NpgsqlCommand("""
                INSERT INTO season_activity_events(season_id,event_id,config_version,config_sha256,ruleset_id,stats_version,activity_rule,
                    starts_at,ends_at,token_cap,completion_tokens,exchange_json)
                VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12) ON CONFLICT(season_id,event_id) DO NOTHING
                """,c,t);
            q.Parameters.AddWithValue(season.SeasonId);q.Parameters.AddWithValue(window.EventId);q.Parameters.AddWithValue(config.Version);
            q.Parameters.AddWithValue(config.ContentHash);q.Parameters.AddWithValue(season.RulesetId);q.Parameters.AddWithValue(season.StatsVersion);
            q.Parameters.AddWithValue(SeasonActivityConfig.Version);q.Parameters.AddWithValue(window.StartsAt);q.Parameters.AddWithValue(window.EndsAt);
            q.Parameters.AddWithValue(policy.TokenCap);q.Parameters.AddWithValue(policy.TokensPerCompletion);q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(policy.Exchanges));
            await q.ExecuteNonQueryAsync(ct);
        }
    }

    private async Task<EventRealm> Realm(NpgsqlConnection c,NpgsqlTransaction? t,string seasonId,string eventId,bool required,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand(EventSelect+" WHERE e.season_id=$1 AND e.event_id=$2",c,t);q.Parameters.AddWithValue(seasonId);q.Parameters.AddWithValue(eventId);
        await using var r=await q.ExecuteReaderAsync(ct);
        if(!await r.ReadAsync(ct))throw new DomainValidationException("The original activity is unavailable.");
        var season=new SeasonDefinition(r.GetString(0),r.GetString(10),r.GetString(8),r.GetString(11),r.GetFieldValue<DateTimeOffset>(12),r.GetFieldValue<DateTimeOffset>(13),r.GetInt16(14));
        var window=new SeasonActivityWindow(r.GetString(1),r.GetFieldValue<DateTimeOffset>(6),r.GetFieldValue<DateTimeOffset>(7));
        var hash=r.GetString(3);var matches=r.GetString(2)==season.ConfigVersion&&hash==r.GetString(9)&&r.GetString(4)==season.RulesetId&&r.GetString(5)==season.StatsVersion;
        await r.DisposeAsync();
        try
        {
            var config=configurations.Resolve(season.ConfigVersion);
            if(!matches||config.ContentHash!=hash||config.SeasonActivity is not {} policy||!policy.Windows(season).Contains(window))
                throw new DomainValidationException("The activity differs from its original published rules.");
            return new(season,hash,window,config);
        }
        catch(Exception e) when(e is IOException or DomainValidationException)
        {
            if(required)throw new DomainValidationException("The original activity configuration is unavailable.");
            return new(season,hash,window,null);
        }
    }

    private static async Task<(int Earned,int Spent,long Version)> Account(NpgsqlConnection c,NpgsqlTransaction? t,Guid player,string season,string activity,bool update,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand("SELECT earned,spent,version FROM player_season_activity_accounts WHERE player_id=$1 AND season_id=$2 AND event_id=$3"+(update?" FOR UPDATE":""),c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season);q.Parameters.AddWithValue(activity);await using var r=await q.ExecuteReaderAsync(ct);
        return await r.ReadAsync(ct)?(r.GetInt32(0),r.GetInt32(1),r.GetInt64(2)):(0,0,0);
    }

    private static async Task<T?> Replay<T>(NpgsqlConnection c,NpgsqlTransaction t,Guid player,string action,string key,string hash,CancellationToken ct) where T:class
    {
        await using var q=new NpgsqlCommand("SELECT request_hash,response_json::text FROM season_activity_action_receipts WHERE player_id=$1 AND action_kind=$2 AND request_id=$3",c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(action);q.Parameters.AddWithValue(key);await using var r=await q.ExecuteReaderAsync(ct);
        if(!await r.ReadAsync(ct))return null;if(r.GetString(0)!=hash)throw new IdempotencyConflictException();
        return JsonSerializer.Deserialize<T>(r.GetString(1))??throw new InvalidOperationException("The durable activity receipt is invalid.");
    }
    private static async Task Receipt<T>(NpgsqlConnection c,NpgsqlTransaction t,Guid player,string action,string key,string hash,T result,DateTimeOffset now,CancellationToken ct)
    {
        await using var q=new NpgsqlCommand("INSERT INTO season_activity_action_receipts(player_id,action_kind,request_id,request_hash,response_json,created_at) VALUES($1,$2,$3,$4,$5,$6)",c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(action);q.Parameters.AddWithValue(key);q.Parameters.AddWithValue(hash);
        q.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(result));q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
    }
    private static async Task TokenLedger(NpgsqlConnection c,NpgsqlTransaction t,Guid player,string season,string activity,int delta,int balance,string reason,Guid source,DateTimeOffset now,CancellationToken ct)
    {
        if(delta==0)return;
        await using var q=new NpgsqlCommand("INSERT INTO season_activity_token_ledger(player_id,season_id,event_id,delta,balance_after,reason,source_id,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)",c,t);
        q.Parameters.AddWithValue(player);q.Parameters.AddWithValue(season);q.Parameters.AddWithValue(activity);q.Parameters.AddWithValue(delta);q.Parameters.AddWithValue(balance);
        q.Parameters.AddWithValue(reason);q.Parameters.AddWithValue(source);q.Parameters.AddWithValue(now);await q.ExecuteNonQueryAsync(ct);
    }

    internal static async Task CreditCompletionWithinTransactionAsync(NpgsqlConnection c,NpgsqlTransaction t,Guid player,Guid match,Guid settlement,
        Guid room,long revision,SeasonDefinition season,GameConfigCatalog config,int difficulty,DateTimeOffset occurredAt,DateTimeOffset recordedAt,CancellationToken ct)
    {
        var policy=config.SeasonActivity;if(policy is null)return;
        var window=policy.Windows(season).SingleOrDefault(w=>w.Contains(occurredAt));if(window is null)return;
        await EnsureEventsWithinTransactionAsync(c,t,season,config,ct);
        await using(var replay=new NpgsqlCommand("SELECT season_id,event_id,occurred_at,source_room_id FROM season_activity_completions WHERE player_id=$1 AND match_id=$2",c,t))
        {
            replay.Parameters.AddWithValue(player);replay.Parameters.AddWithValue(match);await using var r=await replay.ExecuteReaderAsync(ct);
            if(await r.ReadAsync(ct))
            {
                if(r.GetString(0)!=season.SeasonId||r.GetString(1)!=window.EventId||r.GetFieldValue<DateTimeOffset>(2)!=occurredAt||r.GetGuid(3)!=room)
                    throw new DomainValidationException("Activity completion replay changed its original source.");
                return;
            }
        }
        await using(var put=new NpgsqlCommand("INSERT INTO player_season_activity_accounts(player_id,season_id,event_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING",c,t))
        {put.Parameters.AddWithValue(player);put.Parameters.AddWithValue(season.SeasonId);put.Parameters.AddWithValue(window.EventId);await put.ExecuteNonQueryAsync(ct);}
        var account=await Account(c,t,player,season.SeasonId,window.EventId,true,ct);var amount=Math.Min(policy.TokensPerCompletion,policy.TokenCap-account.Earned);
        await using(var put=new NpgsqlCommand("INSERT INTO season_activity_completions(player_id,match_id,settlement_id,season_id,event_id,difficulty_id,config_version,occurred_at,credited_tokens,source_room_id,source_revision) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)",c,t))
        {
            put.Parameters.AddWithValue(player);put.Parameters.AddWithValue(match);put.Parameters.AddWithValue(settlement);put.Parameters.AddWithValue(season.SeasonId);put.Parameters.AddWithValue(window.EventId);
            put.Parameters.AddWithValue($"D{difficulty}");put.Parameters.AddWithValue(config.Version);put.Parameters.AddWithValue(occurredAt.ToUniversalTime());put.Parameters.AddWithValue(amount);
            put.Parameters.AddWithValue(room);put.Parameters.AddWithValue(revision);await put.ExecuteNonQueryAsync(ct);
        }
        if(amount==0)return;
        await using(var update=new NpgsqlCommand("UPDATE player_season_activity_accounts SET earned=earned+$1,version=version+1 WHERE player_id=$2 AND season_id=$3 AND event_id=$4",c,t))
        {update.Parameters.AddWithValue(amount);update.Parameters.AddWithValue(player);update.Parameters.AddWithValue(season.SeasonId);update.Parameters.AddWithValue(window.EventId);await update.ExecuteNonQueryAsync(ct);}
        await TokenLedger(c,t,player,season.SeasonId,window.EventId,amount,account.Earned+amount-account.Spent,"completion",match,recordedAt,ct);
    }
}
