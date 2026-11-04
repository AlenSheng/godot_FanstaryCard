using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class EconomyRepository
{
    private const string ExpiredMarketCondition="""
        (l.expires_at<=$2 OR (l.season_ends_at IS NOT NULL AND l.season_ends_at<=$2)
            OR (l.season_id IS NULL AND EXISTS(SELECT 1 FROM season_definitions d WHERE d.ruleset_id='season-v1' AND d.starts_at<=$2)))
        """;

    private static async Task<string?> MarketReturnScopeAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,EquipmentResponse item,DateTimeOffset now,CancellationToken ct)
    {
        if(item.SeasonId is null)return null;
        await using var query=new NpgsqlCommand("SELECT starts_at,ends_at FROM season_definitions WHERE season_id=$1",connection,transaction);
        query.Parameters.AddWithValue(item.SeasonId);await using var reader=await query.ExecuteReaderAsync(ct);
        if(!await reader.ReadAsync(ct))throw new InvalidOperationException("The return item's original season is missing.");
        if(reader.GetFieldValue<DateTimeOffset>(0)>now)throw new DomainValidationException("The return item's season has not started.");
        return reader.GetFieldValue<DateTimeOffset>(1)>now && item.AssetScope=="ActiveSeason"?"ActiveSeason":"ArchivedSeason";
    }

    private static async Task ReturnMarketItemAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,StoredMarketListing listing,
        string reason,string? requestId,DateTimeOffset now,CancellationToken ct)
    {
        var seller=listing.Response.SellerId;
        var item=await ReadMarketEquipmentAsync(connection,transaction,listing.Response.EquipmentId,seller,ct);
        if(item.Location!="MarketListed")throw new DomainValidationException("The returning listing no longer owns its equipment.");
        var scope=await MarketReturnScopeAsync(connection,transaction,item,now,ct);
        var destination=await MarketInventoryCountAsync(connection,transaction,seller,item.SeasonId,ct)>=50?"MarketReturnPending":"Inventory";
        await using(var update=new NpgsqlCommand("UPDATE equipments SET location=$2,asset_scope=$3,version=version+1 WHERE instance_id=$1",connection,transaction))
        {
            update.Parameters.AddWithValue(item.InstanceId);update.Parameters.AddWithValue(destination);
            update.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)scope??DBNull.Value);await update.ExecuteNonQueryAsync(ct);
        }
        if(destination=="MarketReturnPending")
        {
            await using var hold=new NpgsqlCommand("INSERT INTO market_return_holds(return_id,listing_id,equipment_id,player_id,season_id,state,created_at) VALUES($1,$2,$3,$4,$5,'Pending',$6)",connection,transaction);
            hold.Parameters.AddWithValue(Guid.CreateVersion7());hold.Parameters.AddWithValue(listing.Response.ListingId);hold.Parameters.AddWithValue(item.InstanceId);
            hold.Parameters.AddWithValue(seller);hold.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)item.SeasonId??DBNull.Value);hold.Parameters.AddWithValue(now);
            await hold.ExecuteNonQueryAsync(ct);
        }
        await WriteMarketMovementAsync(connection,transaction,seller,item.InstanceId,"MarketListed",destination,reason,requestId,item.SeasonId,now,ct);
    }

    private static async Task<IReadOnlyList<Guid>> SellerExpiredListingIdsAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid sellerId,DateTimeOffset now,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand("SELECT l.listing_id FROM market_listings l WHERE l.seller_id=$1 AND l.status='Active' AND "+ExpiredMarketCondition+" ORDER BY l.listing_id",connection,transaction);
        query.Parameters.AddWithValue(sellerId);query.Parameters.AddWithValue(now);await using var reader=await query.ExecuteReaderAsync(ct);var ids=new List<Guid>();
        while(await reader.ReadAsync(ct))ids.Add(reader.GetGuid(0));return ids;
    }

    private static async Task<IReadOnlyList<Guid>> ExpireSellerMarketListingsAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid sellerId,DateTimeOffset now,CancellationToken ct)
    {
        var ids=await SellerExpiredListingIdsAsync(connection,transaction,sellerId,now,ct);var expired=new List<Guid>();
        foreach(var id in ids)
        {
            var listing=await ReadLockedMarketListingAsync(connection,transaction,id,ct);
            if(listing.Response.Status!="Active")continue;
            await using(var update=new NpgsqlCommand("UPDATE market_listings SET status='Expired',version=version+1 WHERE listing_id=$1",connection,transaction))
            {update.Parameters.AddWithValue(id);await update.ExecuteNonQueryAsync(ct);}
            await ReturnMarketItemAsync(connection,transaction,listing,"market.expired",null,now,ct);expired.Add(id);
        }
        return expired;
    }

    public async Task CancelListingAsync(Guid sellerId,Guid listingId,string requestId,CancellationToken cancellationToken)
    {
        RequireMarketRequestId(requestId);var hash=PersistentIdempotency.Hash(new {listingId});
        await using var connection=await dataSource.OpenConnectionAsync(cancellationToken);await using var transaction=await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection,transaction,sellerId,cancellationToken);
        var replay=await MarketReplayAsync<IdempotencyAcknowledgement>(connection,transaction,sellerId,"market.cancel",requestId,hash,cancellationToken)
            ??await PersistentIdempotency.ReadAsync<IdempotencyAcknowledgement>(connection,transaction,sellerId,"market.cancel",requestId,hash,cancellationToken);
        if(replay is not null){await transaction.CommitAsync(cancellationToken);return;}
        var listing=await ReadLockedMarketListingAsync(connection,transaction,listingId,cancellationToken);
        if(listing.Response.SellerId!=sellerId)throw new DomainValidationException("Listing does not belong to the seller.");
        if(listing.Response.Status=="Active")
        {
            await using(var update=new NpgsqlCommand("UPDATE market_listings SET status='Cancelled',version=version+1 WHERE listing_id=$1",connection,transaction))
            {update.Parameters.AddWithValue(listingId);await update.ExecuteNonQueryAsync(cancellationToken);}
            await ReturnMarketItemAsync(connection,transaction,listing,"market.cancelled",requestId,timeProvider.GetUtcNow(),cancellationToken);
        }
        else if(listing.Response.Status is not ("Cancelled" or "Expired"))throw new DomainValidationException("Listing is not active.");
        await MarketReceiptAsync(connection,transaction,sellerId,"market.cancel",requestId,hash,new IdempotencyAcknowledgement(),listing.SeasonId,timeProvider.GetUtcNow(),cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<IReadOnlyList<Guid>> ExpireListingsAsync(CancellationToken cancellationToken)
    {
        var now=timeProvider.GetUtcNow();
        var condition=ExpiredMarketCondition.Replace("$2","$1",StringComparison.Ordinal);var sellers=new List<Guid>();
        await using(var candidates=dataSource.CreateCommand("SELECT DISTINCT l.seller_id FROM market_listings l WHERE l.status='Active' AND "+condition+" ORDER BY l.seller_id LIMIT 100"))
        {
            candidates.Parameters.AddWithValue(now);await using var reader=await candidates.ExecuteReaderAsync(cancellationToken);
            while(await reader.ReadAsync(cancellationToken))sellers.Add(reader.GetGuid(0));
        }
        var expired=new List<Guid>();
        // Lock the account before its listing/item rows, just like purchases and
        // cancellation. Independent sellers do not share a long global transaction.
        foreach(var seller in sellers)
        {
            await using var connection=await dataSource.OpenConnectionAsync(cancellationToken);await using var transaction=await connection.BeginTransactionAsync(cancellationToken);
            await LockPlayerAsync(connection,transaction,seller,cancellationToken);
            expired.AddRange(await ExpireSellerMarketListingsAsync(connection,transaction,seller,now,cancellationToken));
            await transaction.CommitAsync(cancellationToken);
        }
        return expired;
    }

    public async Task<EquipmentResponse> ClaimMarketReturnAsync(Guid playerId,Guid returnId,string requestId,ClaimMarketReturnRequest request,CancellationToken ct)
    {
        RequireMarketRequestId(requestId);var hash=PersistentIdempotency.Hash(new {returnId,request});
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,playerId,ct);
        var replay=await MarketReplayAsync<EquipmentResponse>(connection,transaction,playerId,"market.return",requestId,hash,ct);
        if(replay is not null){await transaction.CommitAsync(ct);return replay;}
        Guid equipmentId;string? season;string state;
        await using(var hold=new NpgsqlCommand("SELECT equipment_id,season_id,state FROM market_return_holds WHERE return_id=$1 AND player_id=$2 FOR UPDATE",connection,transaction))
        {
            hold.Parameters.AddWithValue(returnId);hold.Parameters.AddWithValue(playerId);await using var reader=await hold.ExecuteReaderAsync(ct);
            if(!await reader.ReadAsync(ct))throw new DomainValidationException("The return hold does not belong to the player.");
            equipmentId=reader.GetGuid(0);season=Text(reader,1);state=reader.GetString(2);
        }
        if(state!="Pending" || season!=request.SeasonId)throw new DomainValidationException("The original return has already been claimed or belongs to another season.");
        var item=await ReadMarketEquipmentAsync(connection,transaction,equipmentId,playerId,ct);
        if(item.Location!="MarketReturnPending" || item.Version!=request.ExpectedEquipmentVersion || item.SeasonId!=season)
            throw new DomainValidationException("The original return item changed. Reload and retry.");
        if(await MarketInventoryCountAsync(connection,transaction,playerId,season,ct)>=50)throw new DomainValidationException("The original-season equipment inventory is full. The return remains held.");
        var now=timeProvider.GetUtcNow();var scope=await MarketReturnScopeAsync(connection,transaction,item,now,ct);
        await using(var update=new NpgsqlCommand("UPDATE equipments SET location='Inventory',asset_scope=$2,version=version+1 WHERE instance_id=$1",connection,transaction))
        {update.Parameters.AddWithValue(equipmentId);update.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)scope??DBNull.Value);await update.ExecuteNonQueryAsync(ct);}
        await using(var claim=new NpgsqlCommand("UPDATE market_return_holds SET state='Claimed',claimed_at=$2 WHERE return_id=$1",connection,transaction))
        {claim.Parameters.AddWithValue(returnId);claim.Parameters.AddWithValue(now);await claim.ExecuteNonQueryAsync(ct);}
        var result=item with {Location="Inventory",AssetScope=scope,Version=item.Version+1};
        await WriteMarketMovementAsync(connection,transaction,playerId,equipmentId,"MarketReturnPending","Inventory","market.return",requestId,season,now,ct);
        await MarketReceiptAsync(connection,transaction,playerId,"market.return",requestId,hash,result,season,now,ct);
        await transaction.CommitAsync(ct);return result;
    }
}
