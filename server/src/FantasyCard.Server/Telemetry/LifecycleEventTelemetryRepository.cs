using System.Data;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

public sealed record DurableLifecycleEvent(string EventId,string Source,DateTimeOffset OccurredAtUtc,Guid PlayerId,
    Guid? MatchId,Guid? ItemId,string EventName,SeasonEventDimensions Dimensions,string? Quality,string PhysicalFlow,
    string? FromLocation,string? ToLocation,bool? EliteCleared=null,bool? BossCleared=null,
    Guid? SourceHoldId=null,string? BuildProfileBasis=null,string AssetKind="Equipment",string? AssetRef=null);
public sealed record LifecycleSourceCoverage(string Source,int Rows,int UnclassifiedRows,int MissingRealmRows,int MissingQualityRows,bool Truncated);
public sealed record LifecycleFlowCount(string PhysicalFlow,string? SeasonId,string? Quality,string? ConfigVersion,int Items);
public sealed record LifecycleEventTelemetryReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,IReadOnlyList<DurableLifecycleEvent> Events,
    IReadOnlyList<LifecycleSourceCoverage> Sources,IReadOnlyList<LifecycleFlowCount> PhysicalFlows,int EventsWithUnknownCombatDimensions,
    bool SourcesComplete,string Scope="Difficulty completion, committed destruction and original asset-domain archive markers. Wallet balances are not archival amount snapshots. Lobby/archive dimensions are not played difficulty; archive is not destruction or mint.",
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
                    "difficulty_cleared",dimensions,null,"Completion",null,null,reader.GetBoolean(11),reader.GetBoolean(12),AssetKind:"RunSummary"));
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
            WITH wallets AS MATERIALIZED(
                SELECT 'SeasonWallet'::text kind,w.player_id,w.season_id,w.season_id::text ref,w.archived_at,d.ruleset_id,d.config_version,d.stats_version,NULL::text quality
                FROM player_season_wallets w JOIN season_definitions d USING(season_id)
                WHERE w.archived_at >= $1 AND w.archived_at < $2 ORDER BY w.archived_at,w.player_id,w.season_id LIMIT 1001),
            recipes AS MATERIALIZED(
                SELECT 'Recipe'::text,r.player_id,r.season_id,r.recipe_id::text,s.archived_at,d.ruleset_id,d.config_version,r.stats_version,r.quality
                FROM learned_season_recipes r JOIN player_season_state s USING(player_id,season_id) JOIN season_definitions d USING(season_id)
                WHERE s.archived_at >= $1 AND s.archived_at < $2 AND r.learned_at <= s.archived_at ORDER BY s.archived_at,r.recipe_id LIMIT 1001),
            wishes AS MATERIALIZED(
                SELECT 'CraftingWish'::text,w.player_id,w.season_id,concat_ws('/',w.quality,w.slot,w.element,w.wished_effect),s.archived_at,d.ruleset_id,d.config_version,d.stats_version,w.quality
                FROM player_crafting_wishes w JOIN player_season_state s USING(player_id,season_id) JOIN season_definitions d USING(season_id)
                WHERE s.archived_at >= $1 AND s.archived_at < $2 AND w.updated_at <= s.archived_at ORDER BY s.archived_at,w.player_id,w.season_id,w.quality,w.slot,w.element,w.wished_effect LIMIT 1001),
            loadouts AS MATERIALIZED(
                SELECT 'SavedLoadout'::text,l.player_id,l.season_id,l.hero_class::text,l.archived_at,d.ruleset_id,d.config_version,d.stats_version,NULL::text
                FROM season_archive_loadouts l JOIN season_definitions d USING(season_id)
                WHERE l.archived_at >= $1 AND l.archived_at < $2 ORDER BY l.archived_at,l.player_id,l.season_id,l.hero_class LIMIT 1001)
            SELECT * FROM wallets UNION ALL SELECT * FROM recipes UNION ALL SELECT * FROM wishes UNION ALL SELECT * FROM loadouts
            ORDER BY kind,archived_at,player_id,ref
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var counts=new Dictionary<string,int>(StringComparer.Ordinal);var missing=new Dictionary<string,int>(StringComparer.Ordinal);var truncated=new HashSet<string>(StringComparer.Ordinal);
            while(await reader.ReadAsync(ct))
            {
                var kind=reader.GetString(0);var count=counts.GetValueOrDefault(kind);
                if(count==MaximumRowsPerSource){truncated.Add(kind);continue;}counts[kind]=count+1;
                var dimensions=Dimensions(reader,2,null,5,6,7,"Archive","Archived");if(MissingRealm(dimensions))missing[kind]=missing.GetValueOrDefault(kind)+1;
                var reference=reader.GetString(3);events.Add(new($"{reader.GetGuid(1):N}:{reader.GetString(2)}:{kind}:{reference}:season_asset_archived",
                    "archive_domain_"+kind,reader.GetFieldValue<DateTimeOffset>(4),reader.GetGuid(1),null,null,"season_asset_archived",dimensions,Quality(Text(reader,8)),
                    "ArchiveDomain",null,null,AssetKind:kind,AssetRef:reference));
            }
            foreach(var kind in new[]{"SeasonWallet","Recipe","CraftingWish","SavedLoadout"})coverage.Add(new("archive_domain_"+kind,counts.GetValueOrDefault(kind),0,missing.GetValueOrDefault(kind),0,truncated.Contains(kind)));
        }

        await using(var query=Query("""
            WITH source AS MATERIALIZED(
                SELECT * FROM inventory_movements WHERE created_at >= $1 AND created_at < $2 AND to_location IN('Recycled','EnhanceMaterialConsumed')
                    AND reason<>'season.archive' AND from_location IS DISTINCT FROM to_location
                ORDER BY created_at,movement_id LIMIT 1001)
            SELECT m.movement_id,m.player_id,m.item_id,m.created_at,m.season_id,m.difficulty_id,m.ruleset_id,m.config_version,m.stats_version,
                e.quality,m.from_location,m.to_location,m.reason,h.hold_id,s.match_id,s.details_json->>'heroClass',p.is_bot,
                (s.details_json->'telemetryProfile')::text,s.details_json->>'telemetryProfileBasis'
            FROM source m LEFT JOIN equipments e ON e.instance_id=m.item_id
            LEFT JOIN settlement_asset_holds h ON h.hold_id=CASE WHEN m.reason='reward.recycle'
                AND m.request_id ~ '^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$' THEN m.request_id::uuid END
                AND h.player_id=m.player_id AND h.asset_kind='Equipment' AND h.asset_ref=m.item_id::text AND h.state='Committed'
                AND h.season_id IS NOT DISTINCT FROM m.season_id AND h.difficulty_id IS NOT DISTINCT FROM m.difficulty_id
                AND h.ruleset_id IS NOT DISTINCT FROM m.ruleset_id AND h.config_version IS NOT DISTINCT FROM m.config_version AND h.stats_version IS NOT DISTINCT FROM m.stats_version
            LEFT JOIN match_settlements s ON s.settlement_id=h.settlement_id AND s.player_id=h.player_id
            LEFT JOIN match_players p ON p.match_id=s.match_id AND p.player_id=s.player_id
            ORDER BY m.created_at,m.movement_id
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
                    ("equipment.enhance" or "admin_revoke","Inventory","EnhanceMaterialConsumed")=>true,
                    ("reward.recycle","MatchReward" or "InMatchBackpack" or "InMatchEquipped" or "RelicPile","Recycled")=>true,
                    _=>false
                };
                if(!known||reader.IsDBNull(2)){unclassified++;continue;}
                var isLobby=reason is "equipment.discard" or "equipment.enhance" or "admin_revoke";
                var dimensions=Dimensions(reader,4,isLobby?null:5,6,7,8,isLobby?"Lobby":"RunSummary","Destroyed");var quality=Quality(Text(reader,9));
                if(!isLobby&&!reader.IsDBNull(13))
                {
                    var profile=SeasonEventDimensionRules.StoredProfile(Text(reader,17));
                    dimensions=dimensions with{HeroClass=Text(reader,15) is "Mage" or "Priest" or "Guardian"?Text(reader,15):null,
                        PlayerKind=reader.IsDBNull(16)?"Unknown":reader.GetBoolean(16)?"Bot":"Human",BuildType=profile?.BuildType,GrowthStage=profile?.GrowthStage};
                }
                if(MissingRealm(dimensions))missing++;if(quality is null)qualityMissing++;
                events.Add(new($"{reader.GetGuid(0):N}:item_destroyed","inventory_movements",reader.GetFieldValue<DateTimeOffset>(3),reader.GetGuid(1),reader.IsDBNull(14)?null:reader.GetGuid(14),reader.GetGuid(2),
                    "item_destroyed",dimensions,quality,"Destroy",before,after,SourceHoldId:reader.IsDBNull(13)?null:reader.GetGuid(13),BuildProfileBasis:Text(reader,18)));
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
