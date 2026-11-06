using System.Data;
using System.Globalization;
using System.Numerics;
using Npgsql;

namespace FantasyCard.Server.Telemetry;

/// <summary>Repeatable-read currency supply projection. It never repairs or rewrites source rows.</summary>
public sealed class EconomyTelemetryRepository(NpgsqlDataSource dataSource,TimeProvider clock)
{
    private const int MaximumSourceGroups=10000;
    public static void ValidateWindow(DateTimeOffset from,DateTimeOffset to)
    {
        if(from>=to||to-from>TimeSpan.FromDays(7))throw new ArgumentException("Use a nonempty interval of at most seven days.");
    }

    public async Task<EconomyFlowReport> ReadAsync(DateTimeOffset from,DateTimeOffset to,CancellationToken cancellationToken)
    {
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);deadline.CancelAfter(TimeSpan.FromSeconds(5));var ct=deadline.Token;
        ValidateWindow(from,to);from=from.ToUniversalTime();to=to.ToUniversalTime();var observed=clock.GetUtcNow();
        var rows=new List<EconomyFlowRow>();var truncated=false;long unmatched=0,invalidApplied=0;
        await using var connection=await dataSource.OpenConnectionAsync(ct);
        await using var transaction=await connection.BeginTransactionAsync(IsolationLevel.RepeatableRead,ct);
        await using(var configure=new NpgsqlCommand("SET TRANSACTION READ ONLY",connection,transaction))await configure.ExecuteNonQueryAsync(ct);
        await using(var timeout=new NpgsqlCommand("SET LOCAL statement_timeout = 5000",connection,transaction))await timeout.ExecuteNonQueryAsync(ct);
        await using(var query=Query("""
            SELECT currency,season_id,reason,source_kind,sum(delta)::text,count(*)
            FROM economy_ledger WHERE created_at >= $1 AND created_at < $2
            GROUP BY currency,season_id,reason,source_kind,(delta>0),(delta=0)
            ORDER BY currency,season_id,reason,source_kind,(delta>0),(delta=0) LIMIT 10001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                if(++count>MaximumSourceGroups){truncated=true;break;}
                rows.Add(EconomyFlow.Ledger(reader.GetString(0),reader.IsDBNull(1)?null:reader.GetString(1),reader.GetString(2),
                    reader.IsDBNull(3)?null:reader.GetString(3),reader.GetString(4),reader.GetInt64(5)));
            }
        }
        await using(var query=Query("""
            SELECT m.currency,coalesce(m.price,m.price_gold)::text,coalesce(m.fee,m.fee_gold)::text,
                coalesce(m.seller_net,m.seller_net_gold)::text,b.n,s.n,b.season_id,s.season_id,b.delta,s.delta
            FROM market_transactions m
            LEFT JOIN LATERAL(SELECT count(*) n,min(season_id) season_id,sum(delta)::text delta FROM economy_ledger
                WHERE player_id=m.buyer_id AND reason='market.purchase' AND currency=m.currency AND request_id='buy:'||m.listing_id::text)b ON true
            LEFT JOIN LATERAL(SELECT count(*) n,min(season_id) season_id,sum(delta)::text delta FROM economy_ledger
                WHERE player_id=m.seller_id AND reason='market.sale' AND currency=m.currency AND request_id='sale:'||m.listing_id::text)s ON true
            WHERE m.completed_at >= $1 AND m.completed_at < $2 ORDER BY m.completed_at,m.transaction_id LIMIT 10001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                if(++count>MaximumSourceGroups){truncated=true;break;}
                var currency=reader.GetString(0);var price=EconomyFlow.Parse(reader.GetString(1));var fee=EconomyFlow.Parse(reader.GetString(2));var net=EconomyFlow.Parse(reader.GetString(3));
                var buyerSeason=reader.IsDBNull(6)?null:reader.GetString(6);var sellerSeason=reader.IsDBNull(7)?null:reader.GetString(7);
                var paired=EconomyFlow.MarketLegsKnown(currency,price,net,reader.GetInt64(4),buyerSeason,reader.IsDBNull(8)?null:EconomyFlow.Parse(reader.GetString(8)),
                    reader.GetInt64(5),sellerSeason,reader.IsDBNull(9)?null:EconomyFlow.Parse(reader.GetString(9)));
                var valid=price>0&&fee>0&&net>=0&&fee+net==price&&EconomyFlow.KnownCurrency(currency);
                if(!paired||!valid)unmatched++;
                var wallet=EconomyFlow.Wallet(currency,buyerSeason);
                var scope=paired?wallet.Scope:"UnspecifiedMarketFunding";
                rows.Add(new(currency,scope,wallet.Season,valid?EconomyFlowKind.Transfer:EconomyFlowKind.Unclassified,"Market",Text(valid?net:BigInteger.Abs(price)),"0",1,paired&&valid));
                if(valid)rows.Add(new(currency,scope,wallet.Season,EconomyFlowKind.SystemBurn,"MarketTax",Text(fee),"0",0,paired));
            }
        }
        // Reservation/refund ledger legs are frozen account movements. Only a
        // first Applied transition consumes escrow and recognizes the NPC burn.
        await using(var query=Query("""
            SELECT funding_scope,season_id,account_gold::text,response_json->>'requestId',request_id
            FROM reward_refresh_operations WHERE state='Applied' AND applied_at >= $1 AND applied_at < $2
            ORDER BY applied_at,player_id,request_id LIMIT 10001
            """))
        await using(var reader=await query.ExecuteReaderAsync(ct))
        {
            var count=0;while(await reader.ReadAsync(ct))
            {
                if(++count>MaximumSourceGroups){truncated=true;break;}
                var funding=reader.IsDBNull(0)?null:reader.GetString(0);var season=reader.IsDBNull(1)?null:reader.GetString(1);var reserved=EconomyFlow.Parse(reader.GetString(2));
                var valid=reserved>0&&!reader.IsDBNull(3)&&reader.GetString(3)==reader.GetString(4);
                var spent=reserved;
                if(!valid){invalidApplied++;continue;}
                var known=funding is "LegacyWallet" or "SeasonWallet"&&(funding=="SeasonWallet"?season is not null:season is null);
                var wallet=EconomyFlow.Wallet("Gold",season);var scope=known?wallet.Scope:"UnspecifiedRefreshFunding";
                rows.Add(new("Gold",scope,wallet.Season,EconomyFlowKind.SystemBurn,"Refresh",Text(spent),"0",1,known));
                rows.Add(new("Gold",scope,wallet.Season,EconomyFlowKind.EscrowConsumed,"Refresh",Text(spent),"0",0,known));
            }
        }
        long unknownTime;
        await using(var query=new NpgsqlCommand("SELECT count(*) FROM reward_refresh_operations WHERE state='Applied' AND applied_at IS NULL",connection,transaction))
            unknownTime=(long)(await query.ExecuteScalarAsync(ct))!;
        await transaction.CommitAsync(ct);
        var totals=EconomyFlow.Summarize(rows);
        var complete=!truncated&&unknownTime==0&&invalidApplied==0&&unmatched==0&&totals.All(r=>r.CoverageComplete);
        return new(from,to,observed,totals,EconomyFlow.Breakdown(rows),truncated,unknownTime,unmatched,invalidApplied,complete);

        NpgsqlCommand Query(string sql)
        {
            var command=new NpgsqlCommand(sql,connection,transaction);command.Parameters.AddWithValue(from);command.Parameters.AddWithValue(to);return command;
        }
        static string Text(BigInteger value)=>value.ToString(CultureInfo.InvariantCulture);
    }
}
