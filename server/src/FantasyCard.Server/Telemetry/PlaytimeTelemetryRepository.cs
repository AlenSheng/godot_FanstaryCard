using System.Data;
using System.Globalization;
using System.Numerics;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Telemetry;

public sealed record PlaytimeTelemetryReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,string Currency,string WalletScope,string? WalletSeasonId,
    IReadOnlyList<PlaytimeRateDistribution> Groups,int KnownPlayers,int FlowPlayersWithoutKnownClock,string NetWithoutKnownClock,
    int MissingStartedAtClocks,int UnknownTerminalClocks,int InvalidClocks,int ZeroLengthClocks,int RightCensoredClocks,
    long UnlocatedAppliedRefreshTimes,bool SourceTruncated,bool RatesAvailable,bool CompleteForWindow,
    string ClockBasis="Authoritative room clock, clipped and unioned per player; includes in-room waiting/disconnect and simulated recovery time, not measured human activity.",
    string NetBasis="Account currency delta excluding temporary refresh reserve/refund, minus refresh reserve committed within this window. Includes player market transfers; unknown durations are never assigned zero rates.");

public sealed class PlaytimeTelemetryRepository(NpgsqlDataSource dataSource)
{
    public static string ValidateScope(string currency,string? season,bool legacy)
    {
        if(!EconomyFlow.KnownCurrency(currency))throw new ArgumentException("A supported exact currency is required.");
        if(EconomyFlow.IsPermanent(currency)&&season is null&&!legacy)return "Permanent";
        if(legacy&&season is null&&currency is "Gold" or "EquipmentFragments")return "LegacyUnspecified";
        if(!legacy&&!EconomyFlow.IsPermanent(currency)&&season is{Length:>=1 and <=80}&&season.All(c=>char.IsAsciiLetterOrDigit(c)||c is '-' or '_' or '.'))return "Season";
        throw new ArgumentException("Specify an explicit seasonal wallet, an eligible legacy wallet, or a permanent currency without season filtering.");
    }

    public async Task<PlaytimeTelemetryReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,string currency,string? season,bool legacy,CancellationToken cancellationToken)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);var scope=ValidateScope(currency,season,legacy);from=from.ToUniversalTime();to=to.ToUniversalTime();
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var config=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await config.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout=5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        var net=new Dictionary<Guid,BigInteger>();var clocks=new List<PlaytimeInterval>();var truncated=false;var missingStart=0;var invalid=0;long missingRefresh=0;
        await using(var query=Query("""
            SELECT player_id,sum(delta)::text FROM economy_ledger
            WHERE created_at >= $1 AND created_at < $2 AND currency=$3
              AND reason NOT IN('reward.choice.refresh.reserve','reward.choice.refresh.refund')
              AND ($4='Permanent' OR $4='LegacyUnspecified' AND season_id IS NULL OR $4='Season' AND season_id=$5)
            GROUP BY player_id ORDER BY player_id LIMIT 10001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct)){if(++count>10000){truncated=true;break;}net[reader.GetGuid(0)]=EconomyFlow.Parse(reader.GetString(1));}
        }
        if(currency=="Gold")
        {
            await using(var query=Query("""
                SELECT player_id,sum(account_gold)::text FROM reward_refresh_operations
                WHERE state='Applied' AND applied_at >= $1 AND applied_at < $2 AND $3='Gold'
                  AND ($4='Season' AND funding_scope='SeasonWallet' AND season_id=$5
                    OR $4='LegacyUnspecified' AND funding_scope='LegacyWallet' AND season_id IS NULL)
                GROUP BY player_id ORDER BY player_id LIMIT 10001
                """))
            await using(var reader=await query.ExecuteReaderAsync(ct))
            {
                var count=0;while(await reader.ReadAsync(ct)){if(++count>10000){truncated=true;break;}var player=reader.GetGuid(0);net[player]=net.GetValueOrDefault(player)-EconomyFlow.Parse(reader.GetString(1));}
            }
            await using var unknown=new NpgsqlCommand("SELECT count(*) FROM reward_refresh_operations WHERE state='Applied' AND applied_at IS NULL",connection,transaction);
            missingRefresh=(long)(await unknown.ExecuteScalarAsync(ct))!;
        }
        await using(var query=Query("""
            SELECT s.snapshot_json->>'startedAtUtc',s.snapshot_json->>'elapsed',p.value->>'playerId',p.value->>'heroClass',
                p.value->>'phase',p.value->>'isBot',p.value->>'terminalRoomElapsed'
            FROM room_snapshots s JOIN matches m ON m.room_id=s.room_id
            CROSS JOIN LATERAL jsonb_array_elements(CASE WHEN jsonb_typeof(s.snapshot_json->'players')='array' THEN s.snapshot_json->'players' ELSE '[]'::jsonb END)p(value)
            WHERE s.updated_at >= $1 AND m.created_at < $2 AND $3::text IS NOT NULL
              AND ($4='Permanent' OR $4='LegacyUnspecified' AND m.season_id IS NULL OR $4='Season' AND m.season_id=$5)
            ORDER BY m.room_id,p.value->>'playerId' LIMIT 10001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                if(++count>10000){truncated=true;break;}
                if(reader.IsDBNull(0)){missingStart++;continue;}
                if(!DateTimeOffset.TryParse(reader.GetString(0),CultureInfo.InvariantCulture,DateTimeStyles.None,out var start)||reader.IsDBNull(1)||
                    !TimeSpan.TryParseExact(reader.GetString(1),"c",CultureInfo.InvariantCulture,out var elapsed)||reader.IsDBNull(2)||!Guid.TryParse(reader.GetString(2),out var player)||reader.IsDBNull(4))
                {invalid++;continue;}
                TimeSpan? ended=null;
                if(!reader.IsDBNull(6))
                {
                    if(!TimeSpan.TryParseExact(reader.GetString(6),"c",CultureInfo.InvariantCulture,out var value)){invalid++;continue;}ended=value;
                }
                var phase=reader.GetString(4);if(phase is not("Dead" or "Extracted" or "ActionBar" or "Choice" or "Pve" or "Pvp")){invalid++;continue;}
                var kind=reader.IsDBNull(5)?"Unknown":reader.GetString(5) switch{"true"=>"Bot","false"=>"Human",_=>"Unknown"};
                clocks.Add(new(player,kind,reader.IsDBNull(3)?"Unknown":reader.GetString(3),start,elapsed,ended,phase is "Dead" or "Extracted"));
            }
        }
        await using(var query=Query("""
            SELECT count(*) FROM room_snapshots s JOIN matches m ON m.room_id=s.room_id
            WHERE s.updated_at >= $1 AND m.created_at < $2 AND $3::text IS NOT NULL
              AND ($4='Permanent' OR $4='LegacyUnspecified' AND m.season_id IS NULL OR $4='Season' AND m.season_id=$5)
              AND coalesce(jsonb_typeof(s.snapshot_json->'players'),'null')<>'array'
            """))invalid+=checked((int)(long)(await query.ExecuteScalarAsync(ct))!);
        await transaction.CommitAsync(ct);
        var projection=PlaytimeStatistics.Project(clocks,from,to,net);var known=projection.Samples.Select(s=>s.PlayerId).ToHashSet();
        var absent=net.Where(p=>!known.Contains(p.Key)).ToArray();var absentNet=absent.Aggregate(BigInteger.Zero,(sum,p)=>sum+p.Value);
        var complete=!truncated&&missingStart==0&&projection.UnknownTerminalClocks==0&&invalid+projection.InvalidClocks==0&&projection.ZeroLengthClocks==0&&projection.RightCensoredClocks==0&&absent.Length==0&&missingRefresh==0;
        return new(from,to,currency,scope,season,PlaytimeStatistics.Distributions(projection.Samples),projection.Samples.Count,absent.Length,
            absentNet.ToString(CultureInfo.InvariantCulture),missingStart,projection.UnknownTerminalClocks,invalid+projection.InvalidClocks,projection.ZeroLengthClocks,
            projection.RightCensoredClocks,missingRefresh,truncated,projection.Samples.Count>0,complete);

        NpgsqlCommand Query(string sql)
        {
            var command=new NpgsqlCommand(sql,connection,transaction);command.Parameters.AddWithValue(from);command.Parameters.AddWithValue(to);command.Parameters.AddWithValue(currency);
            command.Parameters.AddWithValue(scope);command.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)season??DBNull.Value);return command;
        }
    }
}
