using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class EconomyRepository
{
    private static void RequireMarketRequestId(string requestId)
    {
        if(string.IsNullOrWhiteSpace(requestId) || requestId.Length>80 || requestId.Any(char.IsControl))
            throw new DomainValidationException("The market request identity is invalid.");
    }

    private static async Task<T?> MarketReplayAsync<T>(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid playerId,
        string kind,string requestId,string hash,CancellationToken ct) where T:class
    {
        RequireMarketRequestId(requestId);
        await using var query=new NpgsqlCommand("SELECT request_hash,response_json::text FROM market_action_receipts WHERE player_id=$1 AND action_kind=$2 AND request_id=$3",connection,transaction);
        query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(kind);query.Parameters.AddWithValue(requestId);
        await using var reader=await query.ExecuteReaderAsync(ct);
        if(!await reader.ReadAsync(ct))return null;
        if(reader.GetString(0)!=hash)throw new IdempotencyConflictException();
        return JsonSerializer.Deserialize<T>(reader.GetString(1))??throw new InvalidOperationException("The durable market receipt is invalid.");
    }

    private static async Task MarketReceiptAsync<T>(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid playerId,string kind,
        string requestId,string hash,T response,string? seasonId,DateTimeOffset now,CancellationToken ct) where T:class
    {
        await using var insert=new NpgsqlCommand("INSERT INTO market_action_receipts(player_id,action_kind,request_id,request_hash,response_json,season_id,created_at) VALUES($1,$2,$3,$4,$5,$6,$7)",connection,transaction);
        insert.Parameters.AddWithValue(playerId);insert.Parameters.AddWithValue(kind);insert.Parameters.AddWithValue(requestId);insert.Parameters.AddWithValue(hash);
        insert.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(response));insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)seasonId??DBNull.Value);
        insert.Parameters.AddWithValue(now);await insert.ExecuteNonQueryAsync(ct);
    }

    private static async Task<EquipmentResponse> ReadMarketEquipmentAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid equipmentId,Guid playerId,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand("""
            SELECT instance_id,slot,quality,level,is_bound,location,version,element,effect_affix,secondary_trait,
                origin_season_id,season_id,asset_scope,stats_version,source_kind,recipe_extracted,unique_affix,unique_element
            FROM equipments WHERE instance_id=$1 AND owner_id=$2 FOR UPDATE
            """,connection,transaction);
        query.Parameters.AddWithValue(equipmentId);query.Parameters.AddWithValue(playerId);await using var reader=await query.ExecuteReaderAsync(ct);
        if(!await reader.ReadAsync(ct))throw new DomainValidationException("Equipment was not found or is no longer owned by the player.");
        return new(reader.GetGuid(0),reader.GetString(1),reader.GetString(2),reader.GetInt32(3),reader.GetBoolean(4),reader.GetString(5),reader.GetInt64(6),
            Text(reader,7),Text(reader,8),Text(reader,9),Text(reader,10),Text(reader,11),Text(reader,12),Text(reader,13),Text(reader,14),
            reader.IsDBNull(11)?null:reader.GetBoolean(15),Text(reader,16),Text(reader,17));
    }

    private static async Task<StoredMarketListing> ReadLockedMarketListingAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid listingId,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand(MarketSelect+" WHERE l.listing_id=$1 FOR UPDATE OF l,e",connection,transaction);
        query.Parameters.AddWithValue(listingId);await using var reader=await query.ExecuteReaderAsync(ct);
        return await reader.ReadAsync(ct)?ReadMarketListing(reader):throw new DomainValidationException("Listing was not found.");
    }

    private static void RequireMarketItem(MarketRealm realm,EquipmentResponse item,string currency,long price,string expectedLocation)
    {
        if(item.Location!=expectedLocation || item.IsBound || item.Slot is not ("Head" or "Chest" or "Hands" or "Legs" or "Feet") ||
            item.SourceKind is "Borrowed" or "BotProjection")
        {
            if(realm.Season is null)throw new InvalidOperationException("Only an unbound inventory equipment can be listed.");
            throw new DomainValidationException("Only real unbound inventory armor can be traded.");
        }
        if(realm.Season is { } season)
        {
            if(item.SeasonId!=season.SeasonId || item.OriginSeasonId!=season.SeasonId || item.AssetScope!="ActiveSeason" || item.StatsVersion!=season.StatsVersion)
                throw new DomainValidationException("The market equipment belongs to another season or archive.");
            realm.Policy!.RequirePrice(currency,item.Quality,price);
        }
        else if(item.SeasonId is not null || item.AssetScope is not null || currency!="Gold" || price<1)
            throw new DomainValidationException("The legacy market accepts only original gold-priced inventory armor.");
    }

    private static async Task<int> MarketInventoryCountAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid playerId,string? seasonId,CancellationToken ct)
    {
        await using var query=new NpgsqlCommand("SELECT count(*)::integer FROM equipments WHERE owner_id=$1 AND location='Inventory' AND season_id IS NOT DISTINCT FROM $2",connection,transaction);
        query.Parameters.AddWithValue(playerId);query.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)seasonId??DBNull.Value);
        return (int)(await query.ExecuteScalarAsync(ct))!;
    }

    private static async Task WriteMarketMovementAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid playerId,Guid equipmentId,
        string from,string to,string reason,string? requestId,string? seasonId,DateTimeOffset now,CancellationToken ct,Guid? fromOwner=null)
    {
        await using var insert=new NpgsqlCommand("""
            INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at,
                season_id,source_kind,difficulty_id,ruleset_id,config_version,stats_version,from_owner_id,to_owner_id)
            SELECT $1,$2,$3,$4,$5,$6,$7,$8,$9,'MarketTransfer',
                CASE WHEN d.ruleset_id='season-v1' THEN 'D0' END,d.ruleset_id,d.config_version,d.stats_version,$10,$2
            FROM (VALUES(1)) seed(n) LEFT JOIN season_definitions d ON d.season_id=$9
            """,connection,transaction);
        insert.Parameters.AddWithValue(Guid.CreateVersion7());insert.Parameters.AddWithValue(playerId);insert.Parameters.AddWithValue(equipmentId);
        insert.Parameters.AddWithValue(from);insert.Parameters.AddWithValue(to);insert.Parameters.AddWithValue(reason);
        insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)requestId??DBNull.Value);insert.Parameters.AddWithValue(now);
        insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)seasonId??DBNull.Value);insert.Parameters.AddWithValue(fromOwner??playerId);await insert.ExecuteNonQueryAsync(ct);
    }

    private static async Task<StoredMarketListing> InsertMarketListingAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        MarketRealm realm,Guid sellerId,EquipmentResponse item,string currency,long price,string? requestId,string hash,Guid? replaces,CancellationToken ct)
    {
        await using(var count=new NpgsqlCommand("SELECT count(*) FROM market_listings WHERE seller_id=$1 AND status='Active'",connection,transaction))
        {
            count.Parameters.AddWithValue(sellerId);
            if((long)(await count.ExecuteScalarAsync(ct))!>=realm.SharedSlots)throw new DomainValidationException("The shared market listing limit is reached.");
        }
        var now=realm.Now.ToUniversalTime();var id=Guid.CreateVersion7();
        await using(var insert=new NpgsqlCommand("""
            INSERT INTO market_listings(listing_id,seller_id,equipment_id,price_gold,status,version,request_id,request_hash,created_at,expires_at,
                currency,price,season_id,config_version,stats_version,season_ends_at,market_rule_version,tax_basis_points,minimum_fee,replaces_listing_id)
            VALUES($1,$2,$3,$4,'Active',1,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18)
            """,connection,transaction))
        {
            insert.Parameters.AddWithValue(id);insert.Parameters.AddWithValue(sellerId);insert.Parameters.AddWithValue(item.InstanceId);
            insert.Parameters.AddWithValue(currency=="Gold"?price:0L);insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)requestId??DBNull.Value);
            insert.Parameters.AddWithValue(hash);insert.Parameters.AddWithValue(now);insert.Parameters.AddWithValue(now.AddHours(realm.ListingHours));
            insert.Parameters.AddWithValue(currency);insert.Parameters.AddWithValue(NpgsqlDbType.Bigint,realm.Season is null?DBNull.Value:price);
            insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.SeasonId??DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.ConfigVersion??DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.StatsVersion??DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlDbType.TimestampTz,(object?)realm.Season?.EndsAtUtc??DBNull.Value);
            insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,realm.Season is null?DBNull.Value:SeasonMarketConfig.RuleVersion);
            insert.Parameters.AddWithValue(NpgsqlDbType.Integer,realm.Season is null?DBNull.Value:realm.TaxBasisPoints);
            insert.Parameters.AddWithValue(NpgsqlDbType.Bigint,realm.Season is null?DBNull.Value:realm.MinimumFee);
            insert.Parameters.AddWithValue(NpgsqlDbType.Uuid,(object?)replaces??DBNull.Value);await insert.ExecuteNonQueryAsync(ct);
        }
        return await ReadLockedMarketListingAsync(connection,transaction,id,ct);
    }

    public async Task<MarketListingResponse> ListAsync(Guid sellerId,string requestId,CreateMarketListingRequest request,CancellationToken cancellationToken)
    {
        RequireMarketRequestId(requestId);var hash=PersistentIdempotency.Hash(request);var currency=request.Currency??"Gold";var price=request.Price??request.PriceGold;
        if(currency is not ("Gold" or "Diamond") || price<1 || currency=="Diamond" && request.PriceGold!=0 ||
            currency=="Gold" && request.Price is not null && request.PriceGold!=price)throw new DomainValidationException("The market price and currency disagree.");
        await using var connection=await dataSource.OpenConnectionAsync(cancellationToken);await using var transaction=await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection,transaction,sellerId,cancellationToken);
        var replay=await MarketReplayAsync<MarketListingResponse>(connection,transaction,sellerId,"market.list",requestId,hash,cancellationToken);
        if(replay is not null)
        {
            // Legacy listing reads historically return the same listing ID with
            // its current status, even after cancellation or resale.
            var response=replay.Currency is null?(await ReadLockedMarketListingAsync(connection,transaction,replay.ListingId,cancellationToken)).Response:replay;
            await transaction.CommitAsync(cancellationToken);return response;
        }
        Guid? previous=null;
        await using(var query=new NpgsqlCommand("SELECT listing_id,request_hash FROM market_listings WHERE seller_id=$1 AND request_id=$2",connection,transaction))
        {
            query.Parameters.AddWithValue(sellerId);query.Parameters.AddWithValue(requestId);await using var reader=await query.ExecuteReaderAsync(cancellationToken);
            if(await reader.ReadAsync(cancellationToken))
            {
                if(reader.IsDBNull(1) || reader.GetString(1)!=hash)throw new IdempotencyConflictException();previous=reader.GetGuid(0);
            }
        }
        if(previous is { } original)
        {
            var saved=await ReadLockedMarketListingAsync(connection,transaction,original,cancellationToken);
            await transaction.CommitAsync(cancellationToken);return saved.Response;
        }
        var realm=await ReadMarketRealmAsync(connection,transaction,timeProvider.GetUtcNow(),true,cancellationToken);
        if(realm.Season is { } season)
        {
            if(request.SeasonId!=season.SeasonId || request.ExpectedEquipmentVersion is null)throw new DomainValidationException("The listing season or equipment version changed. Reload and retry.");
            await SeasonRepository.EnsurePlayerWithinTransactionAsync(connection,transaction,sellerId,season.ContextFor(0),realm.Now,cancellationToken);
        }
        else if(request.SeasonId is not null || currency!="Gold")throw new DomainValidationException("The legacy market has no diamond or seasonal listings.");
        await ExpireSellerMarketListingsAsync(connection,transaction,sellerId,realm.Now,cancellationToken);
        var item=await ReadMarketEquipmentAsync(connection,transaction,request.EquipmentId,sellerId,cancellationToken);
        if(request.ExpectedEquipmentVersion is { } version && version!=item.Version)throw new DomainValidationException("The listing equipment changed. Reload and retry.");
        RequireMarketItem(realm,item,currency,price,"Inventory");
        await using(var update=new NpgsqlCommand("UPDATE equipments SET location='MarketListed',version=version+1 WHERE instance_id=$1",connection,transaction))
        {update.Parameters.AddWithValue(item.InstanceId);await update.ExecuteNonQueryAsync(cancellationToken);}
        var listing=await InsertMarketListingAsync(connection,transaction,realm,sellerId,item,currency,price,requestId,hash,null,cancellationToken);
        await WriteMarketMovementAsync(connection,transaction,sellerId,item.InstanceId,"Inventory","MarketListed","market.listed",requestId,item.SeasonId,realm.Now,cancellationToken);
        await MarketReceiptAsync(connection,transaction,sellerId,"market.list",requestId,hash,listing.Response,item.SeasonId,realm.Now,cancellationToken);
        await transaction.CommitAsync(cancellationToken);return listing.Response;
    }

    public async Task<MarketListingResponse> RelistMarketAsync(Guid sellerId,Guid listingId,string requestId,RelistMarketListingRequest request,CancellationToken ct)
    {
        RequireMarketRequestId(requestId);var hash=PersistentIdempotency.Hash(new {listingId,request});
        await using var connection=await dataSource.OpenConnectionAsync(ct);await using var transaction=await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection,transaction,sellerId,ct);
        var replay=await MarketReplayAsync<MarketListingResponse>(connection,transaction,sellerId,"market.relist",requestId,hash,ct);
        if(replay is not null){await transaction.CommitAsync(ct);return replay;}
        var realm=await ReadMarketRealmAsync(connection,transaction,timeProvider.GetUtcNow(),true,ct);
        var original=await ReadLockedMarketListingAsync(connection,transaction,listingId,ct);
        if(original.Response.SellerId!=sellerId || original.Response.Version!=request.ExpectedVersion || original.Response.Status!="Active" ||
            original.Response.ExpiresAt<=realm.Now || request.SeasonId!=realm.Season?.SeasonId || original.SeasonId!=realm.Season?.SeasonId)
            throw new DomainValidationException("The original listing changed or is no longer available.");
        var item=await ReadMarketEquipmentAsync(connection,transaction,original.Response.EquipmentId,sellerId,ct);
        RequireMarketItem(realm,item,request.Currency,request.Price,"MarketListed");
        await using(var cancel=new NpgsqlCommand("UPDATE market_listings SET status='Cancelled',version=version+1 WHERE listing_id=$1",connection,transaction))
        {cancel.Parameters.AddWithValue(listingId);await cancel.ExecuteNonQueryAsync(ct);}
        // The original item remains in escrow throughout this transaction. It
        // does not need a spare inventory slot between currencies.
        var replacement=await InsertMarketListingAsync(connection,transaction,realm,sellerId,item,request.Currency,request.Price,null,hash,listingId,ct);
        await WriteMarketMovementAsync(connection,transaction,sellerId,item.InstanceId,"MarketListed","MarketListed","market.relisted",requestId,item.SeasonId,realm.Now,ct);
        await MarketReceiptAsync(connection,transaction,sellerId,"market.relist",requestId,hash,replacement.Response,item.SeasonId,realm.Now,ct);
        await transaction.CommitAsync(ct);return replacement.Response;
    }

    private static async Task<long> ChangeMarketCurrencyAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,Guid playerId,MarketRealm realm,
        string currency,long delta,string reason,string operationId,string businessHash,CancellationToken ct)
    {
        if(currency=="Gold" && realm.Season is { } season)
        {
            if(delta==0)
            {
                var balances=await ReadMarketWalletAsync(connection,transaction,playerId,realm.Schedule,ct);return balances.Gold;
            }
            var wallet=await SeasonRepository.ApplyWithinTransactionAsync(connection,transaction,playerId,season.ContextFor(0),delta,0,0,reason,operationId,
                SeasonWalletPurpose.General,realm.Now,businessHash,ct);return wallet.Gold;
        }
        var column=currency switch {"Gold"=>"gold","Diamond"=>"diamond",_=>throw new DomainValidationException("Unknown market currency.")};
        var condition=delta<0?column+">= $3":column+"<= $3";
        await using var update=new NpgsqlCommand("UPDATE player_wallets SET "+column+"="+column+"+$1,version=version+1 WHERE player_id=$2 AND "+condition+" RETURNING "+column,connection,transaction);
        update.Parameters.AddWithValue(delta);update.Parameters.AddWithValue(playerId);update.Parameters.AddWithValue(delta<0?-delta:long.MaxValue-delta);
        var value=await update.ExecuteScalarAsync(ct);
        if(value is not long balance)throw new DomainValidationException(delta<0?"The selected currency balance is insufficient.":"The recipient wallet cannot accept this amount.");
        await using var ledger=new NpgsqlCommand("""
            INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at,season_id,source_kind,difficulty_id,ruleset_id,config_version,stats_version)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,'MarketTransfer',$10,$11,$12,$13)
            """,connection,transaction);
        ledger.Parameters.AddWithValue(Guid.CreateVersion7());ledger.Parameters.AddWithValue(playerId);ledger.Parameters.AddWithValue(operationId);
        ledger.Parameters.AddWithValue(currency);ledger.Parameters.AddWithValue(delta);ledger.Parameters.AddWithValue(balance);ledger.Parameters.AddWithValue(reason);ledger.Parameters.AddWithValue(realm.Now);
        ledger.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.SeasonId??DBNull.Value);ledger.Parameters.AddWithValue(realm.Season is null?"Standard":"D0");
        ledger.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.RulesetId??DBNull.Value);
        ledger.Parameters.AddWithValue(realm.Season?.ConfigVersion??GameConfigCatalog.Current.Version);
        ledger.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)realm.Season?.StatsVersion??DBNull.Value);await ledger.ExecuteNonQueryAsync(ct);return balance;
    }

    public async Task<MarketPurchaseResponse> PurchaseMarketAsync(Guid buyerId,string requestId,Guid listingId,long expectedVersion,CancellationToken cancellationToken,
        MarketPurchaseExpectation? expectation=null)
    {
        RequireMarketRequestId(requestId);
        var hash=expectation is null?Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes($"{listingId:D}:{expectedVersion}"))):PersistentIdempotency.Hash(new {listingId,expectedVersion,expectation});
        await using var connection=await dataSource.OpenConnectionAsync(cancellationToken);await using var transaction=await connection.BeginTransactionAsync(cancellationToken);
        Guid sellerId;
        await using(var seller=new NpgsqlCommand("SELECT seller_id FROM market_listings WHERE listing_id=$1",connection,transaction))
        {seller.Parameters.AddWithValue(listingId);sellerId=await seller.ExecuteScalarAsync(cancellationToken) is Guid id?id:throw new DomainValidationException("Listing was not found.");}
        foreach(var player in new[]{buyerId,sellerId}.Distinct().Order())await LockPlayerAsync(connection,transaction,player,cancellationToken);
        var replay=await MarketReplayAsync<MarketPurchaseResponse>(connection,transaction,buyerId,"market.purchase",requestId,hash,cancellationToken);
        if(replay is not null){await transaction.CommitAsync(cancellationToken);return replay;}
        Guid? previous=null;string? savedResponse=null;
        await using(var old=new NpgsqlCommand("SELECT listing_id,request_hash,response_json::text FROM market_transactions WHERE buyer_id=$1 AND request_id=$2",connection,transaction))
        {
            old.Parameters.AddWithValue(buyerId);old.Parameters.AddWithValue(requestId);await using var reader=await old.ExecuteReaderAsync(cancellationToken);
            if(await reader.ReadAsync(cancellationToken))
            {
                if(reader.IsDBNull(1) || reader.GetString(1)!=hash)throw new IdempotencyConflictException();previous=reader.GetGuid(0);savedResponse=reader.IsDBNull(2)?null:reader.GetString(2);
            }
        }
        if(previous is { } original)
        {
            if(savedResponse is not null){await transaction.CommitAsync(cancellationToken);return JsonSerializer.Deserialize<MarketPurchaseResponse>(savedResponse)!;}
            var historic=await ReadLockedMarketListingAsync(connection,transaction,original,cancellationToken);
            var balances=await ReadMarketWalletAsync(connection,transaction,buyerId,await ReadMarketScheduleAsync(connection,transaction,timeProvider.GetUtcNow(),cancellationToken),cancellationToken);
            await transaction.CommitAsync(cancellationToken);return new(historic.Response,balances.Gold);
        }
        var realm=await ReadMarketRealmAsync(connection,transaction,timeProvider.GetUtcNow(),true,cancellationToken);
        var stored=await ReadLockedMarketListingAsync(connection,transaction,listingId,cancellationToken);var listing=stored.Response;
        if(listing.Status!="Active" || listing.Version!=expectedVersion || listing.ExpiresAt<=realm.Now || sellerId==buyerId ||
            stored.SeasonId!=realm.Season?.SeasonId)throw new DomainValidationException("Listing is no longer available in the current market.");
        if(stored.Currency=="Diamond" || expectation is not null)
            if(expectation is null || expectation.Currency!=stored.Currency || expectation.Price!=stored.Price || expectation.SeasonId!=stored.SeasonId)
                throw new DomainValidationException("Confirm the original listing currency, price and season before purchasing.");
        var item=await ReadMarketEquipmentAsync(connection,transaction,listing.EquipmentId,sellerId,cancellationToken);
        RequireMarketItem(realm,item,stored.Currency,stored.Price,"MarketListed");
        if(await MarketInventoryCountAsync(connection,transaction,buyerId,item.SeasonId,cancellationToken)>=50)
            throw new DomainValidationException("The buyer equipment inventory is full.");
        if(realm.Season is { } season)
        {
            if(stored.ConfigVersion!=season.ConfigVersion || stored.StatsVersion!=season.StatsVersion || stored.RuleVersion!=SeasonMarketConfig.RuleVersion)
                throw new DomainValidationException("The original market terms differ from the active published season.");
            foreach(var player in new[]{buyerId,sellerId}.Order())await SeasonRepository.EnsurePlayerWithinTransactionAsync(connection,transaction,player,season.ContextFor(0),realm.Now,cancellationToken);
        }
        var fee=MarketFee(stored.Price,realm.TaxBasisPoints,realm.MinimumFee);var net=stored.Price-fee;
        var business=PersistentIdempotency.Hash(new {listingId,buyerId,sellerId,stored.Currency,stored.Price,fee});
        await ChangeMarketCurrencyAsync(connection,transaction,buyerId,realm,stored.Currency,-stored.Price,"market.purchase","buy:"+listingId.ToString("D"),business,cancellationToken);
        await ChangeMarketCurrencyAsync(connection,transaction,sellerId,realm,stored.Currency,net,"market.sale","sale:"+listingId.ToString("D"),business,cancellationToken);
        await using(var itemUpdate=new NpgsqlCommand("UPDATE equipments SET owner_id=$1,location='Inventory',version=version+1 WHERE instance_id=$2 AND owner_id=$3 AND location='MarketListed'",connection,transaction))
        {
            itemUpdate.Parameters.AddWithValue(buyerId);itemUpdate.Parameters.AddWithValue(item.InstanceId);itemUpdate.Parameters.AddWithValue(sellerId);
            if(await itemUpdate.ExecuteNonQueryAsync(cancellationToken)!=1)throw new DomainValidationException("The listing no longer owns its original equipment.");
        }
        await using(var update=new NpgsqlCommand("UPDATE market_listings SET status='Sold',version=version+1 WHERE listing_id=$1",connection,transaction))
        {update.Parameters.AddWithValue(listingId);await update.ExecuteNonQueryAsync(cancellationToken);}
        var wallet=await ReadMarketWalletAsync(connection,transaction,buyerId,realm.Schedule,cancellationToken);
        var response=new MarketPurchaseResponse(listing with {Status="Sold",Version=listing.Version+1},wallet.Gold,realm.Season is null?null:wallet,realm.Season?.SeasonId);
        await using(var insert=new NpgsqlCommand("""
            INSERT INTO market_transactions(transaction_id,listing_id,buyer_id,seller_id,price_gold,fee_gold,seller_net_gold,request_id,request_hash,completed_at,
                currency,price,fee,seller_net,season_id,response_json)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            """,connection,transaction))
        {
            insert.Parameters.AddWithValue(Guid.CreateVersion7());insert.Parameters.AddWithValue(listingId);insert.Parameters.AddWithValue(buyerId);insert.Parameters.AddWithValue(sellerId);
            insert.Parameters.AddWithValue(stored.Currency=="Gold"?stored.Price:0L);insert.Parameters.AddWithValue(stored.Currency=="Gold"?fee:0L);
            insert.Parameters.AddWithValue(stored.Currency=="Gold"?net:0L);insert.Parameters.AddWithValue(requestId);insert.Parameters.AddWithValue(hash);insert.Parameters.AddWithValue(realm.Now);
            insert.Parameters.AddWithValue(stored.Currency);insert.Parameters.AddWithValue(NpgsqlDbType.Bigint,realm.Season is null?DBNull.Value:stored.Price);
            insert.Parameters.AddWithValue(NpgsqlDbType.Bigint,realm.Season is null?DBNull.Value:fee);insert.Parameters.AddWithValue(NpgsqlDbType.Bigint,realm.Season is null?DBNull.Value:net);
            insert.Parameters.AddWithValue(NpgsqlDbType.Varchar,(object?)item.SeasonId??DBNull.Value);insert.Parameters.AddWithValue(NpgsqlDbType.Jsonb,JsonSerializer.Serialize(response));
            await insert.ExecuteNonQueryAsync(cancellationToken);
        }
        await WriteMarketMovementAsync(connection,transaction,buyerId,item.InstanceId,"MarketListed","Inventory","market.purchased",requestId,item.SeasonId,realm.Now,cancellationToken,sellerId);
        await MarketReceiptAsync(connection,transaction,buyerId,"market.purchase",requestId,hash,response,item.SeasonId,realm.Now,cancellationToken);
        await transaction.CommitAsync(cancellationToken);return response;
    }
}
