using System.Data;
using System.Globalization;
using System.Numerics;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

public sealed record PhysicalEquipmentEvent(string EventId,DateTimeOffset OccurredAtUtc,Guid ItemId,Guid? FromOwnerId,Guid? ToOwnerId,
    string Kind,string? Quality,string? OriginSeasonId,string Source,string? FromLocation,string? ToLocation,int DestroyedUnits,int TransferredUnits,
    int EscrowEntries,int EscrowReleases,int EscrowTransitions,bool SourceKnown);
public sealed record PhysicalSupplyBalance(string? OriginSeasonId,string? Quality,string Opening,string Created,string Destroyed,string Closing,string Difference,
    string UnknownTerminalTimes,string DuplicateDestructionClaims,string InconsistentLifetimes);
public sealed record PhysicalStockGroup(string? OriginSeasonId,string? AssetScope,string? Quality,string Location,string Items);
public sealed record PhysicalEquipmentTelemetryReport(DateTimeOffset FromUtc,DateTimeOffset ToUtc,DateTimeOffset ObservedAtUtc,
    IReadOnlyList<PhysicalEquipmentEvent> Events,IReadOnlyList<PhysicalSupplyBalance> Supply,IReadOnlyList<PhysicalStockGroup> CurrentStocks,
    int MissingCreationSources,int UnclassifiedMovements,int MissingTransferParties,bool SourceTruncated,bool KnownSubsetBalanced,
    string Scope="Equipment identities only. Creation rows count mint once; placement, owner/custody moves and archive are not additional mint. Supply is the known lifetime subset; current stocks are as-of-query, not opening balances or economic health.");

public sealed class PhysicalEquipmentTelemetryRepository(NpgsqlDataSource dataSource,TimeProvider clock)
{
    // Only irreversible documented transitions locate a destruction time. An
    // archive of a Recycled row is never a second destruction.
    private const string DestructionPredicate="""
        (reason='equipment.discard' AND from_location='Inventory' AND to_location='Recycled'
        OR reason IN('equipment.enhance','admin_revoke') AND from_location='Inventory' AND to_location='EnhanceMaterialConsumed'
        OR reason='reward.recycle' AND from_location IN('MatchReward','InMatchBackpack','InMatchEquipped','RelicPile') AND to_location='Recycled')
        """;

    public async Task<PhysicalEquipmentTelemetryReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,CancellationToken cancellationToken)
    {
        EconomyTelemetryRepository.ValidateWindow(from,to);from=from.ToUniversalTime();to=to.ToUniversalTime();
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var config=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await config.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout=5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        var events=new List<PhysicalEquipmentEvent>();var supply=new List<PhysicalSupplyBalance>();var stocks=new List<PhysicalStockGroup>();var missing=0;var unknown=0;var parties=0;var truncated=false;
        await using(var query=Query("""
            WITH born AS MATERIALIZED(SELECT instance_id,created_at,quality,origin_season_id FROM equipments
                WHERE created_at >= $1 AND created_at < $2 ORDER BY created_at,instance_id LIMIT 1001),
            creators AS(SELECT m.item_id,count(*) n,min(m.player_id::text) player,min(m.reason) reason FROM inventory_movements m JOIN born b ON b.instance_id=m.item_id
                WHERE (m.reason='equipment.craft' AND m.from_location='NotMinted' AND m.to_location='Inventory')
                    OR (m.reason='mail.claim' AND m.from_location='Mail' AND m.to_location='Inventory')
                    OR (m.reason='admin.grant_all_equipment' AND m.from_location='Admin' AND m.to_location='Inventory')
                    OR (m.reason='settlement.extract' AND m.from_location='MatchReward' AND m.to_location IN('Inventory','Equipped'))
                    OR (m.reason='settlement.death' AND m.from_location='MatchReward' AND m.to_location='RelicPile')
                    OR (m.reason='reward.recycle' AND m.from_location='MatchReward' AND m.to_location='Recycled') GROUP BY m.item_id)
            SELECT b.instance_id,b.created_at,b.quality,b.origin_season_id,c.n,c.player,c.reason,r.player_id,r.source
            FROM born b LEFT JOIN creators c ON c.item_id=b.instance_id LEFT JOIN season_red_drop_attempts r ON r.equipment_id=b.instance_id AND r.status='Minted'
            ORDER BY b.created_at,b.instance_id
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                ct.ThrowIfCancellationRequested();if(++count>1000){truncated=true;break;}
                Guid? owner=null;string source="UnclassifiedCreation";var known=false;
                if(!reader.IsDBNull(7)){owner=reader.GetGuid(7);source="RedQuota:"+reader.GetString(8);known=true;}
                else if(!reader.IsDBNull(4)&&reader.GetInt64(4)==1){owner=Guid.Parse(reader.GetString(5));source=reader.GetString(6);known=true;}
                if(!known)missing++;
                events.Add(new($"{reader.GetGuid(0):N}:mint",reader.GetFieldValue<DateTimeOffset>(1),reader.GetGuid(0),null,owner,"Mint",Text(reader,2),Text(reader,3),source,null,null,0,0,0,0,0,known));
            }
        }
        await using(var query=Query("""
            WITH source AS MATERIALIZED(SELECT * FROM inventory_movements WHERE created_at >= $1 AND created_at < $2 ORDER BY created_at,movement_id LIMIT 1001)
            SELECT m.movement_id,m.created_at,m.item_id,m.player_id,m.from_location,m.to_location,m.reason,e.quality,e.origin_season_id,
                m.from_owner_id,m.to_owner_id,t.seller_id,t.buyer_id
            FROM source m LEFT JOIN equipments e ON e.instance_id=m.item_id
            LEFT JOIN market_transactions t ON m.reason='market.purchased' AND t.buyer_id=m.player_id AND t.request_id=m.request_id
                AND EXISTS(SELECT 1 FROM market_listings l WHERE l.listing_id=t.listing_id AND l.equipment_id=m.item_id)
            ORDER BY m.created_at,m.movement_id
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                ct.ThrowIfCancellationRequested();if(++count>1000){truncated=true;break;}
                if(reader.IsDBNull(2)){unknown++;continue;}
                var classification=PhysicalEquipmentFlow.Classify(reader.GetString(6),Text(reader,4),Text(reader,5));
                Guid? before=reader.IsDBNull(9)?null:reader.GetGuid(9);Guid? after=reader.IsDBNull(10)?null:reader.GetGuid(10);
                if(before is null&&after is null&&!reader.IsDBNull(11)&&!reader.IsDBNull(12)){before=reader.GetGuid(11);after=reader.GetGuid(12);}
                var transferred=before is { } source&&after is { } destination&&source!=destination?1:0;
                if(classification.TransferredUnits>0&&(before is null||after is null))parties++;
                if(!classification.Known)unknown++;
                events.Add(new($"{reader.GetGuid(0):N}:movement",reader.GetFieldValue<DateTimeOffset>(1),reader.GetGuid(2),before,after,classification.Kind,Text(reader,7),Text(reader,8),reader.GetString(6),
                    Text(reader,4),Text(reader,5),classification.DestroyedUnits,transferred,classification.EscrowEntries,classification.EscrowReleases,classification.EscrowTransitions,classification.Known));
            }
        }
        var balanceSql="""
            WITH destroyed AS(SELECT item_id,min(created_at) destroyed_at,count(*) claims FROM inventory_movements WHERE __DESTROY__ GROUP BY item_id),
            facts AS(SELECT e.instance_id,e.created_at,e.origin_season_id,e.quality,e.location,d.destroyed_at,d.claims,
                (d.destroyed_at IS NULL AND e.location NOT IN('Recycled','EnhanceMaterialConsumed') OR d.destroyed_at>=e.created_at AND e.location IN('Recycled','EnhanceMaterialConsumed')) valid
                FROM equipments e LEFT JOIN destroyed d ON d.item_id=e.instance_id WHERE e.created_at < $2 OR d.destroyed_at < $2)
            SELECT origin_season_id,quality,
                count(*) FILTER(WHERE valid AND created_at<$1 AND (destroyed_at IS NULL OR destroyed_at >= $1))::text,
                count(*) FILTER(WHERE valid AND created_at >= $1 AND created_at < $2)::text,
                count(*) FILTER(WHERE valid AND destroyed_at >= $1 AND destroyed_at < $2)::text,
                count(*) FILTER(WHERE valid AND created_at<$2 AND (destroyed_at IS NULL OR destroyed_at >= $2))::text,
                count(*) FILTER(WHERE location IN('Recycled','EnhanceMaterialConsumed') AND destroyed_at IS NULL)::text,
                coalesce(sum(greatest(claims-1,0)),0)::text,
                count(*) FILTER(WHERE NOT valid AND NOT(location IN('Recycled','EnhanceMaterialConsumed') AND destroyed_at IS NULL))::text
            FROM facts GROUP BY origin_season_id,quality ORDER BY origin_season_id NULLS FIRST,quality LIMIT 1001
            """.Replace("__DESTROY__",DestructionPredicate,StringComparison.Ordinal);
        await using(var query=Query(balanceSql))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                ct.ThrowIfCancellationRequested();if(++count>1000){truncated=true;break;}
                var open=Number(reader,2);var born=Number(reader,3);var destroyed=Number(reader,4);var close=Number(reader,5);
                supply.Add(new(Text(reader,0),Text(reader,1),Str(open),Str(born),Str(destroyed),Str(close),Str(open+born-destroyed-close),reader.GetString(6),reader.GetString(7),reader.GetString(8)));
            }
        }
        await using(var query=new NpgsqlCommand("SELECT origin_season_id,asset_scope,quality,location,count(*)::text FROM equipments GROUP BY origin_season_id,asset_scope,quality,location ORDER BY origin_season_id NULLS FIRST,asset_scope NULLS FIRST,quality,location LIMIT 1001",connection,transaction))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct)){ct.ThrowIfCancellationRequested();if(++count>1000){truncated=true;break;}stocks.Add(new(Text(reader,0),Text(reader,1),Text(reader,2),reader.GetString(3),reader.GetString(4)));}
        }
        await transaction.CommitAsync(ct);
        return new(from,to,clock.GetUtcNow(),events.OrderBy(e=>e.OccurredAtUtc).ThenBy(e=>e.EventId,StringComparer.Ordinal).ToArray(),supply,stocks,missing,unknown,parties,truncated,
            !truncated&&supply.All(s=>s.Difference=="0"&&s.UnknownTerminalTimes=="0"&&s.DuplicateDestructionClaims=="0"&&s.InconsistentLifetimes=="0"));
        NpgsqlCommand Query(string sql){var command=new NpgsqlCommand(sql,connection,transaction);command.Parameters.AddWithValue(from);command.Parameters.AddWithValue(to);return command;}
    }
    private static string? Text(NpgsqlDataReader reader,int column)=>reader.IsDBNull(column)?null:reader.GetString(column);
    private static BigInteger Number(NpgsqlDataReader reader,int column)=>BigInteger.Parse(reader.GetString(column),CultureInfo.InvariantCulture);
    private static string Str(BigInteger value)=>value.ToString(CultureInfo.InvariantCulture);
}
