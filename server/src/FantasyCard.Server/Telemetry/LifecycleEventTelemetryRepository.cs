using System.Data;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

public sealed record DurableLifecycleEvent(string EventId,string Source,DateTimeOffset OccurredAtUtc,Guid PlayerId,
    Guid? MatchId,Guid? ItemId,string EventName,SeasonEventDimensions Dimensions,string? Quality,string PhysicalFlow,
    string? FromLocation,string? ToLocation,bool? EliteCleared=null,bool? BossCleared=null);
public sealed record LifecycleSourceCoverage(string Source,int Rows,int UnclassifiedRows,int MissingRealmRows,int MissingQualityRows,bool Truncated);
public sealed record LifecycleFlowCount(string PhysicalFlow,string? SeasonId,string? Quality,string? ConfigVersion,int Items);
public sealed record LifecycleEventTelemetryReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,IReadOnlyList<DurableLifecycleEvent> Events,
    IReadOnlyList<LifecycleSourceCoverage> Sources,IReadOnlyList<LifecycleFlowCount> PhysicalFlows,int EventsWithUnknownCombatDimensions,
    bool SourcesComplete,string Scope="Difficulty completion, equipment destruction and equipment archive receipts only. Wallet/recipe archive and other physical flows are outside this report. Lobby/archive dimensions are not played difficulty. Archive is a domain move, not a second destruction or new mint.",
    IReadOnlyDictionary<string,int>? UnknownDimensionCounts=null);

/// <summary>Projects original receipts without writing a second ledger or guessing historical state.</summary>
public sealed class LifecycleEventTelemetryRepository(NpgsqlDataSource dataSource)
{
    private const int MaximumRowsPerSource=1000;

    public async Task<LifecycleEventTelemetryReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,CancellationToken cancellationToken)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);from=from.ToUniversalTime();to=to.ToUniversalTime();
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var config=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await config.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout=5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        var events=new List<DurableLifecycleEvent>();var coverage=new List<LifecycleSourceCoverage>();

        await using(var query=Query("""
            SELECT c.settlement_id,c.player_id,c.match_id,c.completed_at,c.season_id,c.difficulty_id,c.ruleset_id,c.config_version,c.stats_version,
                s.details_json->>'heroClass',p.is_bot,c.elite_cleared,c.boss_cleared,(s.details_json->'telemetryProfile')::text
            FROM season_difficulty_completions c
            LEFT JOIN match_settlements s ON s.settlement_id=c.settlement_id
            LEFT JOIN match_players p ON p.match_id=c.match_id AND p.player_id=c.player_id
            WHERE c.completed_at >= $1 AND c.completed_at < $2 ORDER BY c.completed_at,c.settlement_id LIMIT 1001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;var missing=0;var truncated=false;
            while(await reader.ReadAsync(ct))
            {
                if(count==MaximumRowsPerSource){truncated=true;break;}count++;
                var dimensions=Dimensions(reader,4,5,6,7,8,"RunSummary","Extracted",Text(reader,9),reader.IsDBNull(10)?"Unknown":reader.GetBoolean(10)?"Bot":"Human");
                var profile=SeasonEventDimensionRules.StoredProfile(Text(reader,13));
                dimensions=dimensions with{BuildType=profile?.BuildType,GrowthStage=profile?.GrowthStage};
                if(MissingRealm(dimensions))missing++;
                events.Add(new($"{reader.GetGuid(0):N}:difficulty_cleared","season_difficulty_completions",reader.GetFieldValue<DateTimeOffset>(3),reader.GetGuid(1),reader.GetGuid(2),null,
                    "difficulty_cleared",dimensions,null,"Completion",null,null,reader.GetBoolean(11),reader.GetBoolean(12)));
            }
            coverage.Add(new("season_difficulty_completions",count,0,missing,0,truncated));
        }

        await using(var query=Query("""
            SELECT a.job_id,a.player_id,a.item_id,a.archived_at,a.season_id,d.ruleset_id,d.config_version,d.stats_version,
                e.quality,a.from_location,a.to_location
            FROM season_archive_items a
            LEFT JOIN season_definitions d ON d.season_id=a.season_id
            LEFT JOIN equipments e ON e.instance_id=a.item_id
            WHERE a.archived_at >= $1 AND a.archived_at < $2 ORDER BY a.archived_at,a.job_id,a.item_id LIMIT 1001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;var missing=0;var qualityMissing=0;var truncated=false;
            while(await reader.ReadAsync(ct))
            {
                if(count==MaximumRowsPerSource){truncated=true;break;}count++;
                // Original published season definitions are immutable; generated
                // item difficulty and today's account/loadout are not action dimensions.
                var dimensions=Dimensions(reader,4,null,5,6,7,"Archive","Archived");var quality=Quality(Text(reader,8));
                if(MissingRealm(dimensions))missing++;if(quality is null)qualityMissing++;
                events.Add(new($"{reader.GetGuid(0):N}:{reader.GetGuid(2):N}:season_asset_archived","season_archive_items",reader.GetFieldValue<DateTimeOffset>(3),reader.GetGuid(1),null,reader.GetGuid(2),
                    "season_asset_archived",dimensions,quality,"Archive",Text(reader,9),Text(reader,10)));
            }
            coverage.Add(new("season_archive_items",count,0,missing,qualityMissing,truncated));
        }

        await using(var query=Query("""
            SELECT m.movement_id,m.player_id,m.item_id,m.created_at,m.season_id,m.difficulty_id,m.ruleset_id,m.config_version,m.stats_version,
                e.quality,m.from_location,m.to_location,m.reason
            FROM inventory_movements m LEFT JOIN equipments e ON e.instance_id=m.item_id
            WHERE m.created_at >= $1 AND m.created_at < $2 AND m.to_location IN('Recycled','EnhanceMaterialConsumed')
                AND m.reason<>'season.archive' AND m.from_location IS DISTINCT FROM m.to_location
            ORDER BY m.created_at,m.movement_id LIMIT 1001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;var missing=0;var qualityMissing=0;var unclassified=0;var truncated=false;
            while(await reader.ReadAsync(ct))
            {
                if(count==MaximumRowsPerSource){truncated=true;break;}count++;
                var before=Text(reader,10);var after=Text(reader,11);var reason=reader.GetString(12);
                var known=(reason,before,after) switch
                {
                    ("equipment.discard","Inventory","Recycled")=>true,
                    ("equipment.enhance","Inventory","EnhanceMaterialConsumed")=>true,
                    ("reward.recycle","MatchReward" or "InMatchBackpack" or "InMatchEquipped" or "RelicPile","Recycled")=>true,
                    _=>false
                };
                if(!known||reader.IsDBNull(2)){unclassified++;continue;}
                var isLobby=reason is "equipment.discard" or "equipment.enhance";
                var dimensions=Dimensions(reader,4,isLobby?null:5,6,7,8,isLobby?"Lobby":"RunSummary","Destroyed");var quality=Quality(Text(reader,9));
                if(MissingRealm(dimensions))missing++;if(quality is null)qualityMissing++;
                events.Add(new($"{reader.GetGuid(0):N}:item_destroyed","inventory_movements",reader.GetFieldValue<DateTimeOffset>(3),reader.GetGuid(1),null,reader.GetGuid(2),
                    "item_destroyed",dimensions,quality,"Destroy",before,after));
            }
            coverage.Add(new("inventory_movements",count,unclassified,missing,qualityMissing,truncated));
        }
        await transaction.CommitAsync(ct);
        var ordered=events.OrderBy(e=>e.OccurredAtUtc).ThenBy(e=>e.EventId,StringComparer.Ordinal).ToArray();
        var flows=ordered.Where(e=>e.ItemId is not null).GroupBy(e=>(e.PhysicalFlow,e.Dimensions.SeasonId,e.Quality,e.Dimensions.ConfigVersion))
            .OrderBy(g=>g.Key.PhysicalFlow,StringComparer.Ordinal).ThenBy(g=>g.Key.SeasonId,StringComparer.Ordinal).ThenBy(g=>g.Key.Quality,StringComparer.Ordinal).ThenBy(g=>g.Key.ConfigVersion,StringComparer.Ordinal)
            .Select(g=>new LifecycleFlowCount(g.Key.PhysicalFlow,g.Key.SeasonId,g.Key.Quality,g.Key.ConfigVersion,g.Count())).ToArray();
        return new(from,to,ordered,coverage,flows,ordered.Count(e=>e.Dimensions.HeroClass is null||e.Dimensions.BuildType is null||e.Dimensions.GrowthStage is null||e.Dimensions.PlayerKind=="Unknown"),
            coverage.All(c=>!c.Truncated&&c.UnclassifiedRows==0&&c.MissingRealmRows==0&&c.MissingQualityRows==0),
            UnknownDimensionCounts:SeasonEventDimensionRules.UnknownCounts(ordered.Select(e=>e.Dimensions)));

        NpgsqlCommand Query(string sql)
        {
            var command=new NpgsqlCommand(sql,connection,transaction);command.Parameters.AddWithValue(from);command.Parameters.AddWithValue(to);return command;
        }
    }

    private static SeasonEventDimensions Dimensions(NpgsqlDataReader reader,int season,int? difficulty,int rules,int config,int stats,string cell,string result,string? hero=null,string playerKind="Unknown")
        =>new(Text(reader,season),difficulty is { } column?Text(reader,column):null,hero is "Mage" or "Priest" or "Guardian"?hero:null,null,null,playerKind,cell,Text(reader,rules),Text(reader,config),Text(reader,stats),result);
    private static bool MissingRealm(SeasonEventDimensions d)=>d.SeasonId is null||d.RulesetId is null||d.ConfigVersion is null||d.StatsVersion is null;
    private static string? Quality(string? value)=>value is "White" or "Green" or "Blue" or "Purple" or "Orange" or "Red"?value:null;
    private static string? Text(NpgsqlDataReader reader,int column)=>reader.IsDBNull(column)?null:reader.GetString(column);
}
