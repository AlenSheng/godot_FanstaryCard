using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Globalization;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public static class EconomySchedule
{
    private static readonly TimeSpan ChinaOffset = TimeSpan.FromHours(8);

    public static string GetDailyResetKey(DateTimeOffset utc)
    {
        var local = utc.ToOffset(ChinaOffset);
        if (local.Hour < 4) local = local.AddDays(-1);
        return local.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }
}

public sealed partial class EconomyMaintenanceWorker(
    EconomyRepository repository,
    EconomyReconciliationRepository reconciliationRepository,
    ServerMetrics metrics,
    TimeProvider timeProvider,
    ILogger<EconomyMaintenanceWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(1), timeProvider);
        do
        {
            try
            {
                await repository.ExpireListingsAsync(stoppingToken);
                var report = await reconciliationRepository.InspectAsync(stoppingToken);
                if (!report.IsHealthy)
                {
                    metrics.EconomyReconciliationViolated(report.TotalViolationCount);
                    ReconciliationViolation(
                        logger,
                        report.TotalViolationCount,
                        report.NegativeAccountCount,
                        report.ActiveListingAssetMismatchCount,
                        report.OrphanMarketListedEquipmentCount,
                        report.SoldListingMismatchCount,
                        report.MarketTransactionAmountMismatchCount,
                        report.LedgerChainMismatchCount);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                MaintenanceFailed(logger, exception);
            }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }

    [LoggerMessage(EventId = 4201, Level = LogLevel.Error, Message = "Economy maintenance cycle failed.")]
    private static partial void MaintenanceFailed(ILogger logger, Exception exception);

    [LoggerMessage(
        EventId = 4202,
        Level = LogLevel.Critical,
        Message = "Economy reconciliation found {Total} violation(s): negativeAccounts={NegativeAccounts}, activeListingAssetMismatches={ActiveListingAssetMismatches}, orphanMarketListedEquipment={OrphanMarketListedEquipment}, soldListingMismatches={SoldListingMismatches}, transactionAmountMismatches={TransactionAmountMismatches}, ledgerChainMismatches={LedgerChainMismatches}.")]
    private static partial void ReconciliationViolation(
        ILogger logger,
        long total,
        long negativeAccounts,
        long activeListingAssetMismatches,
        long orphanMarketListedEquipment,
        long soldListingMismatches,
        long transactionAmountMismatches,
        long ledgerChainMismatches);
}

public sealed record RewardRefreshReservation(string State, RewardRefreshReceiptSnapshot? Receipt);
public sealed record PersistedRewardRefresh(
    Guid MatchId,
    Guid RoomId,
    long ExpectedRevision,
    long AccountGold,
    string State,
    RewardRefreshReceiptSnapshot? Receipt);
public sealed record PendingRewardRefresh(Guid PlayerId, string RequestId, Guid MatchId, Guid RoomId);

public sealed class EconomyRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider)
{
    private static readonly JsonSerializerOptions RewardRefreshJsonOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    public async Task<PersistedRewardRefresh?> GetRewardRefreshAsync(
        Guid playerId,
        string requestId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT match_id,room_id,expected_revision,account_gold,state,response_json::text FROM reward_refresh_operations WHERE player_id=$1 AND request_id=$2");
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(requestId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return new(
            reader.GetGuid(0), reader.GetGuid(1), reader.GetInt64(2), reader.GetInt64(3), reader.GetString(4),
            reader.IsDBNull(5) ? null : JsonSerializer.Deserialize<RewardRefreshReceiptSnapshot>(reader.GetString(5), RewardRefreshJsonOptions));
    }

    public async Task<RewardRefreshReservation> ReserveRewardRefreshAsync(
        Guid playerId,
        Guid matchId,
        Guid roomId,
        long expectedRevision,
        long accountGold,
        string requestId,
        CancellationToken cancellationToken)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(accountGold, 0);
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        await using (var replay = new NpgsqlCommand(
            "SELECT match_id,room_id,expected_revision,account_gold,state,response_json::text FROM reward_refresh_operations WHERE player_id=$1 AND request_id=$2",
            connection, transaction))
        {
            replay.Parameters.AddWithValue(playerId);
            replay.Parameters.AddWithValue(requestId);
            await using var reader = await replay.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                if (reader.GetGuid(0) != matchId || reader.GetGuid(1) != roomId ||
                    reader.GetInt64(2) != expectedRevision || reader.GetInt64(3) != accountGold)
                    throw new IdempotencyConflictException();
                var state = reader.GetString(4);
                var receipt = reader.IsDBNull(5)
                    ? null
                    : JsonSerializer.Deserialize<RewardRefreshReceiptSnapshot>(reader.GetString(5), RewardRefreshJsonOptions);
                await reader.DisposeAsync();
                await transaction.CommitAsync(cancellationToken);
                return new(state, receipt);
            }
        }

        var balanceAfter = await SpendGoldAsync(connection, transaction, playerId, accountGold, cancellationToken);
        var now = timeProvider.GetUtcNow();
        await using (var insert = new NpgsqlCommand(
            "INSERT INTO reward_refresh_operations(player_id,request_id,match_id,room_id,expected_revision,account_gold,state,recover_after,created_at,updated_at) VALUES($1,$2,$3,$4,$5,$6,'Reserved',$7,$8,$8)",
            connection, transaction))
        {
            insert.Parameters.AddWithValue(playerId);
            insert.Parameters.AddWithValue(requestId);
            insert.Parameters.AddWithValue(matchId);
            insert.Parameters.AddWithValue(roomId);
            insert.Parameters.AddWithValue(expectedRevision);
            insert.Parameters.AddWithValue(accountGold);
            insert.Parameters.AddWithValue(now.AddSeconds(30));
            insert.Parameters.AddWithValue(now);
            await insert.ExecuteNonQueryAsync(cancellationToken);
        }
        await WriteLedgerAsync(connection, transaction, playerId, -accountGold, balanceAfter,
            "Gold", "reward.choice.refresh.reserve", cancellationToken, requestId);
        await transaction.CommitAsync(cancellationToken);
        return new("Reserved", null);
    }

    public async Task MarkRewardRefreshAppliedAsync(
        Guid playerId,
        string requestId,
        RewardRefreshReceiptSnapshot receipt,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "UPDATE reward_refresh_operations SET state='Applied',response_json=$1,room_revision=$2,updated_at=$3 WHERE player_id=$4 AND request_id=$5 AND state IN ('Reserved','Applied')");
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Jsonb,
            Value = JsonSerializer.Serialize(receipt, RewardRefreshJsonOptions)
        });
        command.Parameters.AddWithValue(receipt.RoomRevision);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(requestId);
        if (await command.ExecuteNonQueryAsync(cancellationToken) != 1)
            throw new InvalidOperationException("Reward refresh reservation was not found or was already refunded.");
    }

    public async Task<bool> RefundReservedRewardRefreshAsync(
        Guid playerId,
        string requestId,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        long amount;
        string state;
        await using (var query = new NpgsqlCommand(
            "SELECT account_gold,state FROM reward_refresh_operations WHERE player_id=$1 AND request_id=$2 FOR UPDATE",
            connection, transaction))
        {
            query.Parameters.AddWithValue(playerId);
            query.Parameters.AddWithValue(requestId);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
            {
                await reader.DisposeAsync();
                await transaction.CommitAsync(cancellationToken);
                return false;
            }
            amount = reader.GetInt64(0);
            state = reader.GetString(1);
        }
        if (state != "Reserved")
        {
            await transaction.CommitAsync(cancellationToken);
            return false;
        }
        await using var wallet = new NpgsqlCommand(
            "UPDATE player_wallets SET gold=gold+$1,version=version+1 WHERE player_id=$2 RETURNING gold",
            connection, transaction);
        wallet.Parameters.AddWithValue(amount);
        wallet.Parameters.AddWithValue(playerId);
        var balance = (long)(await wallet.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Player wallet was not found."));
        await WriteLedgerAsync(connection, transaction, playerId, amount, balance,
            "Gold", "reward.choice.refresh.refund", cancellationToken, requestId);
        await using var update = new NpgsqlCommand(
            "UPDATE reward_refresh_operations SET state='Refunded',updated_at=$1 WHERE player_id=$2 AND request_id=$3",
            connection, transaction);
        update.Parameters.AddWithValue(timeProvider.GetUtcNow());
        update.Parameters.AddWithValue(playerId);
        update.Parameters.AddWithValue(requestId);
        await update.ExecuteNonQueryAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return true;
    }

    public async Task<IReadOnlyList<PendingRewardRefresh>> GetRecoverableRewardRefreshesAsync(
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT player_id,request_id,match_id,room_id FROM reward_refresh_operations WHERE state='Reserved' AND recover_after <= $1 ORDER BY recover_after LIMIT 100");
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<PendingRewardRefresh>();
        while (await reader.ReadAsync(cancellationToken))
            result.Add(new(reader.GetGuid(0), reader.GetString(1), reader.GetGuid(2), reader.GetGuid(3)));
        return result;
    }

    public async Task<ShopResponse> GetShopAsync(Guid playerId, CancellationToken cancellationToken)
    {
        var resetKey = EconomySchedule.GetDailyResetKey(timeProvider.GetUtcNow());
        await EnsureRotationAsync(resetKey, cancellationToken);
        await using var command = dataSource.CreateCommand(
            "SELECT product_id, kind, price_gold, limit_count, payload_json::text FROM shop_rotations WHERE reset_key=$1 ORDER BY product_id");
        command.Parameters.AddWithValue(resetKey);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<ShopProductResponse>();
        while (await reader.ReadAsync(cancellationToken))
        {
            var productId = reader.GetString(0);
            result.Add(new ShopProductResponse(productId, reader.GetString(1), reader.GetInt64(2), reader.GetInt32(3),
                await PurchasedAsync(playerId, resetKey, productId, cancellationToken), reader.GetString(4)));
        }
        return new ShopResponse(resetKey, result);
    }

    public async Task<ShopPurchaseResponse> PurchaseAsync(Guid playerId, string requestId, PurchaseShopRequest request, CancellationToken cancellationToken)
    {
        if (request.Quantity is < 1 or > 10) throw new InvalidOperationException("Quantity must be between 1 and 10.");
        var resetKey = EconomySchedule.GetDailyResetKey(timeProvider.GetUtcNow());
        var hash = Hash(request);
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        await using (var replay = new NpgsqlCommand("SELECT request_hash, product_id, quantity, granted_json::text FROM shop_purchases WHERE player_id=$1 AND request_id=$2", connection, transaction))
        {
            replay.Parameters.AddWithValue(playerId); replay.Parameters.AddWithValue(requestId);
            await using var reader = await replay.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                if (reader.GetString(0) != hash) throw new IdempotencyConflictException();
                var replayProduct = reader.GetString(1);
                var replayQuantity = reader.GetInt32(2);
                var replayGranted = JsonSerializer.Deserialize<string>(reader.GetString(3)) ?? reader.GetString(3);
                await reader.DisposeAsync();
                var replayGold = await CurrentGoldAsync(connection, transaction, playerId, cancellationToken);
                await transaction.CommitAsync(cancellationToken);
                return new(replayProduct, replayQuantity, replayGold, replayGranted);
            }
        }

        await EnsureRotationAsync(resetKey, cancellationToken);
        string kind, payload; long price; int limit;
        await using (var product = new NpgsqlCommand("SELECT kind, payload_json::text, price_gold, limit_count FROM shop_rotations WHERE reset_key=$1 AND product_id=$2", connection, transaction))
        {
            product.Parameters.AddWithValue(resetKey); product.Parameters.AddWithValue(request.ProductId);
            await using var reader = await product.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken)) throw new InvalidOperationException("Shop product is unavailable.");
            kind = reader.GetString(0); payload = reader.GetString(1); price = reader.GetInt64(2); limit = reader.GetInt32(3);
        }
        var purchased = await PurchasedAsync(connection, transaction, playerId, resetKey, request.ProductId, cancellationToken);
        if (purchased + request.Quantity > limit) throw new InvalidOperationException("Daily purchase limit reached.");
        await EnsurePaidBagCapacityAsync(connection, transaction, playerId, kind, payload, request.Quantity, cancellationToken);
        var total = checked(price * request.Quantity);
        var goldAfter = await SpendGoldAsync(connection, transaction, playerId, total, cancellationToken);
        var granted = await GrantAsync(connection, transaction, playerId, kind, payload, request.Quantity, cancellationToken);
        await using (var insert = new NpgsqlCommand(
            "INSERT INTO shop_purchases(purchase_id,player_id,reset_key,product_id,request_id,request_hash,quantity,price_gold,granted_json,created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)", connection, transaction))
        {
            insert.Parameters.AddWithValue(Guid.CreateVersion7()); insert.Parameters.AddWithValue(playerId); insert.Parameters.AddWithValue(resetKey);
            insert.Parameters.AddWithValue(request.ProductId); insert.Parameters.AddWithValue(requestId); insert.Parameters.AddWithValue(hash);
            insert.Parameters.AddWithValue(request.Quantity); insert.Parameters.AddWithValue(total);
            insert.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Jsonb, Value = JsonSerializer.Serialize(granted) });
            insert.Parameters.AddWithValue(timeProvider.GetUtcNow()); await insert.ExecuteNonQueryAsync(cancellationToken);
        }
        await WriteLedgerAsync(connection, transaction, playerId, -total, goldAfter, "Gold", "shop.purchase", cancellationToken, requestId);
        await transaction.CommitAsync(cancellationToken);
        return new(request.ProductId, request.Quantity, goldAfter, granted);
    }

    public async Task<IReadOnlyList<MarketListingResponse>> GetMarketAsync(CancellationToken cancellationToken)
    {
        await ExpireListingsAsync(cancellationToken);
        await using var command = dataSource.CreateCommand("SELECT listing_id,seller_id,equipment_id,price_gold,status,version,created_at,expires_at FROM market_listings WHERE status='Active' AND expires_at > $1 ORDER BY created_at DESC");
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<MarketListingResponse>();
        while (await reader.ReadAsync(cancellationToken)) result.Add(ReadListing(reader));
        return result;
    }

    public async Task<MarketListingResponse> ListAsync(Guid sellerId, string requestId, CreateMarketListingRequest request, CancellationToken cancellationToken)
    {
        if (request.PriceGold <= 0) throw new InvalidOperationException("Price must be positive.");
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, sellerId, cancellationToken);
        var requestHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request)))).ToLowerInvariant();
        await using (var replay = new NpgsqlCommand("SELECT listing_id,seller_id,equipment_id,price_gold,status,version,created_at,expires_at,request_hash FROM market_listings WHERE seller_id=$1 AND request_id=$2", connection, transaction))
        {
            replay.Parameters.AddWithValue(sellerId); replay.Parameters.AddWithValue(requestId);
            await using var reader = await replay.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                if (reader.IsDBNull(8) || reader.GetString(8) != requestHash) throw new IdempotencyConflictException();
                var replayListing = ReadListing(reader);
                await reader.DisposeAsync();
                await transaction.CommitAsync(cancellationToken);
                return replayListing;
            }
        }
        await using (var count = new NpgsqlCommand("SELECT count(*) FROM market_listings WHERE seller_id=$1 AND status='Active'", connection, transaction))
        {
            count.Parameters.AddWithValue(sellerId);
            if ((long)(await count.ExecuteScalarAsync(cancellationToken) ?? 0) >= GameConfigCatalog.Current.Economy.MarketActiveListings)
                throw new InvalidOperationException("Market listing limit reached.");
        }
        string slot, location; bool bound;
        await using (var item = new NpgsqlCommand("SELECT slot,location,is_bound FROM equipments WHERE instance_id=$1 AND owner_id=$2 FOR UPDATE", connection, transaction))
        {
            item.Parameters.AddWithValue(request.EquipmentId); item.Parameters.AddWithValue(sellerId);
            await using var reader = await item.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken)) throw new InvalidOperationException("Equipment was not found.");
            slot = reader.GetString(0); location = reader.GetString(1); bound = reader.GetBoolean(2);
        }
        if (bound || location != "Inventory") throw new InvalidOperationException("Only an unbound inventory equipment can be listed.");
        var now = timeProvider.GetUtcNow(); var id = Guid.CreateVersion7();
        var expires = now.AddHours(GameConfigCatalog.Current.Economy.MarketDurationHours);
        await using (var update = new NpgsqlCommand("UPDATE equipments SET location='MarketListed',version=version+1 WHERE instance_id=$1", connection, transaction))
        { update.Parameters.AddWithValue(request.EquipmentId); await update.ExecuteNonQueryAsync(cancellationToken); }
        await using (var insert = new NpgsqlCommand("INSERT INTO market_listings(listing_id,seller_id,equipment_id,price_gold,status,version,request_id,request_hash,created_at,expires_at) VALUES($1,$2,$3,$4,'Active',1,$5,$6,$7,$8)", connection, transaction))
        { insert.Parameters.AddWithValue(id); insert.Parameters.AddWithValue(sellerId); insert.Parameters.AddWithValue(request.EquipmentId); insert.Parameters.AddWithValue(request.PriceGold); insert.Parameters.AddWithValue(requestId); insert.Parameters.AddWithValue(requestHash); insert.Parameters.AddWithValue(now); insert.Parameters.AddWithValue(expires); await insert.ExecuteNonQueryAsync(cancellationToken); }
        await WriteInventoryMovementAsync(
            connection, transaction, sellerId, request.EquipmentId,
            "Inventory", "MarketListed", "market.listed", cancellationToken, requestId);
        await transaction.CommitAsync(cancellationToken);
        return new(id, sellerId, request.EquipmentId, request.PriceGold, "Active", 1, now, expires);
    }

    public async Task<MarketPurchaseResponse> PurchaseMarketAsync(Guid buyerId, string requestId, Guid listingId, long expectedVersion, CancellationToken cancellationToken)
    {
        var requestHash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes($"{listingId:D}:{expectedVersion}"))).ToLowerInvariant();
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        Guid sellerId;
        await using (var sellerQuery = new NpgsqlCommand(
            "SELECT seller_id FROM market_listings WHERE listing_id=$1", connection, transaction))
        {
            sellerQuery.Parameters.AddWithValue(listingId);
            sellerId = (Guid)(await sellerQuery.ExecuteScalarAsync(cancellationToken)
                ?? throw new InvalidOperationException("Listing was not found."));
        }
        foreach (var playerId in new[] { buyerId, sellerId }.Distinct().Order())
            await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        await using (var replay = new NpgsqlCommand("SELECT l.listing_id,l.seller_id,l.equipment_id,l.price_gold,l.status,l.version,l.created_at,l.expires_at,t.request_hash FROM market_transactions t JOIN market_listings l ON l.listing_id=t.listing_id WHERE t.buyer_id=$1 AND t.request_id=$2", connection, transaction))
        {
            replay.Parameters.AddWithValue(buyerId); replay.Parameters.AddWithValue(requestId);
            await using var r = await replay.ExecuteReaderAsync(cancellationToken);
            if (await r.ReadAsync(cancellationToken))
            {
                var replayListing = ReadListing(r);
                if (r.IsDBNull(8) || r.GetString(8) != requestHash) throw new IdempotencyConflictException();
                await r.DisposeAsync();
                var replayGold = await CurrentGoldAsync(connection, transaction, buyerId, cancellationToken);
                await transaction.CommitAsync(cancellationToken);
                return new(replayListing, replayGold);
            }
        }
        MarketListingResponse listing;
        await using (var query = new NpgsqlCommand("SELECT listing_id,seller_id,equipment_id,price_gold,status,version,created_at,expires_at FROM market_listings WHERE listing_id=$1 FOR UPDATE", connection, transaction))
        { query.Parameters.AddWithValue(listingId); await using var r = await query.ExecuteReaderAsync(cancellationToken); if (!await r.ReadAsync(cancellationToken)) throw new InvalidOperationException("Listing was not found."); listing = ReadListing(r); }
        if (listing.Status != "Active" || listing.Version != expectedVersion || listing.ExpiresAt <= timeProvider.GetUtcNow() || listing.SellerId == buyerId) throw new InvalidOperationException("Listing is no longer available.");
        var buyerGold = await SpendGoldAsync(connection, transaction, buyerId, listing.PriceGold, cancellationToken);
        var fee = Math.Max(1, decimal.ToInt64(decimal.Floor(
            listing.PriceGold * Convert.ToDecimal(GameConfigCatalog.Current.Economy.MarketFeeRate))));
        var net = listing.PriceGold - fee;
        await using (var seller = new NpgsqlCommand("UPDATE player_wallets SET gold=gold+$1,version=version+1 WHERE player_id=$2", connection, transaction)) { seller.Parameters.AddWithValue(net); seller.Parameters.AddWithValue(sellerId); await seller.ExecuteNonQueryAsync(cancellationToken); }
        await using (var item = new NpgsqlCommand(
            "UPDATE equipments SET owner_id=$1,location='Inventory',version=version+1 WHERE instance_id=$2 AND owner_id=$3 AND location='MarketListed'",
            connection,
            transaction))
        {
            item.Parameters.AddWithValue(buyerId);
            item.Parameters.AddWithValue(listing.EquipmentId);
            item.Parameters.AddWithValue(sellerId);
            if (await item.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("The active listing no longer owns its equipment.");
        }
        await using (var update = new NpgsqlCommand("UPDATE market_listings SET status='Sold',version=version+1 WHERE listing_id=$1", connection, transaction)) { update.Parameters.AddWithValue(listingId); await update.ExecuteNonQueryAsync(cancellationToken); }
        await using (var insert = new NpgsqlCommand("INSERT INTO market_transactions(transaction_id,listing_id,buyer_id,seller_id,price_gold,fee_gold,seller_net_gold,request_id,request_hash,completed_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)", connection, transaction)) { insert.Parameters.AddWithValue(Guid.CreateVersion7()); insert.Parameters.AddWithValue(listingId); insert.Parameters.AddWithValue(buyerId); insert.Parameters.AddWithValue(listing.SellerId); insert.Parameters.AddWithValue(listing.PriceGold); insert.Parameters.AddWithValue(fee); insert.Parameters.AddWithValue(net); insert.Parameters.AddWithValue(requestId); insert.Parameters.AddWithValue(requestHash); insert.Parameters.AddWithValue(timeProvider.GetUtcNow()); await insert.ExecuteNonQueryAsync(cancellationToken); }
        await WriteInventoryMovementAsync(
            connection, transaction, buyerId, listing.EquipmentId,
            "MarketListed", "Inventory", "market.purchased", cancellationToken, requestId);
        await WriteLedgerAsync(connection, transaction, buyerId, -listing.PriceGold, buyerGold, "Gold", "market.purchase", cancellationToken, requestId);
        await WriteLedgerAsync(connection, transaction, sellerId, net, await CurrentGoldAsync(connection, transaction, sellerId, cancellationToken), "Gold", "market.sale", cancellationToken, requestId);
        await transaction.CommitAsync(cancellationToken);
        return new(listing with { Status = "Sold", Version = listing.Version + 1 }, buyerGold);
    }

    public async Task CancelListingAsync(Guid sellerId, Guid listingId, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, sellerId, cancellationToken);
        var now = timeProvider.GetUtcNow();
        var requestHash = PersistentIdempotency.Hash(new { listingId });
        var replay = await PersistentIdempotency.ReadAsync<IdempotencyAcknowledgement>(
            connection, transaction, sellerId, "market.cancel", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return;
        }
        Guid equipmentId;
        string status;
        await using (var query = new NpgsqlCommand("SELECT equipment_id,status FROM market_listings WHERE listing_id=$1 AND seller_id=$2 FOR UPDATE", connection, transaction))
        {
            query.Parameters.AddWithValue(listingId);
            query.Parameters.AddWithValue(sellerId);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
                throw new InvalidOperationException("Listing does not belong to the seller.");
            equipmentId = reader.GetGuid(0);
            status = reader.GetString(1);
        }
        if (status == "Cancelled")
        {
            await PersistentIdempotency.WriteAsync(
                connection, transaction, sellerId, "market.cancel", requestId, requestHash,
                new IdempotencyAcknowledgement(), now, cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            return;
        }
        if (status != "Active") throw new InvalidOperationException("Listing is not active.");
        await using (var command = new NpgsqlCommand("UPDATE market_listings SET status='Cancelled',version=version+1 WHERE listing_id=$1 AND status='Active'", connection, transaction))
        {
            command.Parameters.AddWithValue(listingId);
            if (await command.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("Listing changed while it was being cancelled.");
        }
        await using var restore = new NpgsqlCommand("UPDATE equipments SET location='Inventory',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='MarketListed'", connection, transaction);
        restore.Parameters.AddWithValue(equipmentId);
        restore.Parameters.AddWithValue(sellerId);
        if (await restore.ExecuteNonQueryAsync(cancellationToken) != 1)
            throw new InvalidOperationException("The cancelled listing no longer owns its equipment.");
        await WriteInventoryMovementAsync(connection, transaction, sellerId, equipmentId, "MarketListed", "Inventory", "market.cancelled", cancellationToken, requestId);
        await PersistentIdempotency.WriteAsync(
            connection, transaction, sellerId, "market.cancel", requestId, requestHash,
            new IdempotencyAcknowledgement(), now, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<int> ExpireListingsAsync(CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var command = new NpgsqlCommand("UPDATE market_listings SET status='Expired',version=version+1 WHERE status='Active' AND expires_at <= $1 RETURNING equipment_id,seller_id", connection, transaction);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var expired = new List<(Guid EquipmentId, Guid SellerId)>();
        while (await reader.ReadAsync(cancellationToken)) expired.Add((reader.GetGuid(0), reader.GetGuid(1)));
        await reader.DisposeAsync();
        foreach (var item in expired)
        {
            await using var restore = new NpgsqlCommand("UPDATE equipments SET location='Inventory',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='MarketListed'", connection, transaction);
            restore.Parameters.AddWithValue(item.EquipmentId); restore.Parameters.AddWithValue(item.SellerId);
            if (await restore.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("An expired listing no longer owns its equipment.");
            await WriteInventoryMovementAsync(connection, transaction, item.SellerId, item.EquipmentId, "MarketListed", "Inventory", "market.expired", cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
        return expired.Count;
    }

    private async Task EnsureRotationAsync(string resetKey, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        var config = GameConfigCatalog.Current;
        await using var command = new NpgsqlCommand("INSERT INTO shop_rotations(reset_key,product_id,kind,payload_json,price_gold,limit_count) VALUES ($1,'card_pack','Cards','{\"rarity\":\"WhiteToPurple\",\"count\":3}',250,5),($1,'warrior_soul','WarriorSoul','{\"amount\":20}',180,3),($1,'equipment_fragments','EquipmentFragments','{\"amount\":20}',120,3),($1,'priest_soul','ClassSoul','{\"heroClass\":\"Priest\",\"amount\":12}',400,1),($1,'mage_soul','ClassSoul','{\"heroClass\":\"Mage\",\"amount\":12}',400,1),($1,'guardian_soul','ClassSoul','{\"heroClass\":\"Guardian\",\"amount\":12}',400,1),($1,'health_potion','HealthPotion','{\"amount\":1}',$2,4),($1,'advanced_bag','AdvancedBag','{\"amount\":1}',$3,99),($1,'top_bag','TopBag','{\"amount\":1}',$4,99) ON CONFLICT DO NOTHING", connection, transaction);
        command.Parameters.AddWithValue(resetKey);
        command.Parameters.AddWithValue(config.Economy.HealthPotionPrice);
        command.Parameters.AddWithValue(config.Backpack("Advanced").PriceGold);
        command.Parameters.AddWithValue(config.Backpack("Top").PriceGold);
        await command.ExecuteNonQueryAsync(cancellationToken);

        var offers = CreateDailyCardOffers(resetKey, config);
        for (var index = 0; index < offers.Length; index++)
        {
            var offer = offers[index];
            await using var dailyCard = new NpgsqlCommand(
                "INSERT INTO shop_rotations(reset_key,product_id,kind,payload_json,price_gold,limit_count) VALUES($1,$2,'Cards',$3,$4,$5) ON CONFLICT DO NOTHING",
                connection,
                transaction);
            dailyCard.Parameters.AddWithValue(resetKey);
            dailyCard.Parameters.AddWithValue($"daily_card_{index + 1}");
            dailyCard.Parameters.Add(new NpgsqlParameter
            {
                NpgsqlDbType = NpgsqlDbType.Jsonb,
                Value = JsonSerializer.Serialize(new { cardId = offer.Card.CardId, quality = offer.Card.Quality, count = 1 })
            });
            dailyCard.Parameters.AddWithValue(offer.Price.PriceGold);
            dailyCard.Parameters.AddWithValue(offer.Price.DailyLimit);
            await dailyCard.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
    }

    private static DailyCardOffer[] CreateDailyCardOffers(
        string resetKey,
        GameConfigCatalog config)
    {
        var prices = config.ShopCardPrices.ToDictionary(item => item.Quality, StringComparer.Ordinal);
        var candidates = config.Cards
            .Where(card => card.IsCodex && card.Quality is not null && prices.ContainsKey(card.Quality))
            .OrderBy(card => Convert.ToHexString(SHA256.HashData(
                Encoding.UTF8.GetBytes($"{config.Version}:{resetKey}:{card.CardId}"))), StringComparer.Ordinal)
            .ThenBy(card => card.CardId, StringComparer.Ordinal)
            .Take(config.Economy.DailyCardSlots)
            .Select(card => new DailyCardOffer(card, prices[card.Quality!]))
            .ToArray();
        if (candidates.Length != config.Economy.DailyCardSlots)
            throw new InvalidOperationException("The daily shop card rotation cannot be filled.");
        return candidates;
    }

    private static string Hash(PurchaseShopRequest request) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(request)))).ToLowerInvariant();

    private static async Task LockPlayerAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid id, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", c, t); cmd.Parameters.AddWithValue(id); if (await cmd.ExecuteScalarAsync(ct) is null) throw new InvalidOperationException("Player was not found."); }

    private static async Task<int> PurchasedAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, string reset, string product, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("SELECT COALESCE(sum(quantity),0)::integer FROM shop_purchases WHERE player_id=$1 AND reset_key=$2 AND product_id=$3", c, t); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue(reset); cmd.Parameters.AddWithValue(product); return (int)(await cmd.ExecuteScalarAsync(ct) ?? 0); }
    private async Task<int> PurchasedAsync(Guid player, string reset, string product, CancellationToken ct)
    { await using var c = await dataSource.OpenConnectionAsync(ct); await using var cmd = new NpgsqlCommand("SELECT COALESCE(sum(quantity),0)::integer FROM shop_purchases WHERE player_id=$1 AND reset_key=$2 AND product_id=$3", c); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue(reset); cmd.Parameters.AddWithValue(product); return (int)(await cmd.ExecuteScalarAsync(ct) ?? 0); }

    private static async Task<long> SpendGoldAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, long amount, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("UPDATE player_wallets SET gold=gold-$1,version=version+1 WHERE player_id=$2 AND gold >= $1 RETURNING gold", c, t); cmd.Parameters.AddWithValue(amount); cmd.Parameters.AddWithValue(player); var value = await cmd.ExecuteScalarAsync(ct); if (value is null) throw new InvalidOperationException("Not enough gold."); return (long)value; }
    private static async Task<long> CurrentGoldAsync(NpgsqlConnection c, NpgsqlTransaction? t, Guid player, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("SELECT gold FROM player_wallets WHERE player_id=$1", c, t); cmd.Parameters.AddWithValue(player); return (long)(await cmd.ExecuteScalarAsync(ct) ?? 0L); }
    private static async Task WriteLedgerAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, long delta, long balance, string currency, string reason, CancellationToken ct, string? requestId = null)
    { await using var cmd = new NpgsqlCommand("INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)", c, t); cmd.Parameters.AddWithValue(Guid.CreateVersion7()); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue((object?)requestId ?? DBNull.Value); cmd.Parameters.AddWithValue(currency); cmd.Parameters.AddWithValue(delta); cmd.Parameters.AddWithValue(balance); cmd.Parameters.AddWithValue(reason); cmd.Parameters.AddWithValue(DateTimeOffset.UtcNow); await cmd.ExecuteNonQueryAsync(ct); }
    private static async Task WriteInventoryMovementAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, Guid item, string from, string to, string reason, CancellationToken ct, string? requestId = null)
    { await using var cmd = new NpgsqlCommand("INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,CURRENT_TIMESTAMP)", c, t); cmd.Parameters.AddWithValue(Guid.CreateVersion7()); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue(item); cmd.Parameters.AddWithValue(from); cmd.Parameters.AddWithValue(to); cmd.Parameters.AddWithValue(reason); cmd.Parameters.AddWithValue((object?)requestId ?? DBNull.Value); await cmd.ExecuteNonQueryAsync(ct); }
    private static MarketListingResponse ReadListing(NpgsqlDataReader r) => new(r.GetGuid(0),r.GetGuid(1),r.GetGuid(2),r.GetInt64(3),r.GetString(4),r.GetInt64(5),r.GetFieldValue<DateTimeOffset>(6),r.GetFieldValue<DateTimeOffset>(7));

    private static async Task<string> GrantAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, string kind, string payload, int quantity, CancellationToken ct)
    {
        using var json = JsonDocument.Parse(payload); var amount = json.RootElement.TryGetProperty("amount", out var a) ? a.GetInt64() * quantity : 0;
        var column = kind switch { "WarriorSoul" => "warrior_soul", "EquipmentFragments" => "equipment_fragments", "ClassSoul" => json.RootElement.GetProperty("heroClass").GetString()!.ToLowerInvariant() + "_soul", "HealthPotion" => "health_potion_count", "AdvancedBag" => "advanced_bag_count", "TopBag" => "top_bag_count", _ => null };
        if (column is not null)
        {
            var table = kind is "HealthPotion" or "AdvancedBag" or "TopBag" ? "player_consumables" : "player_materials";
            await using var command = new NpgsqlCommand($"UPDATE {table} SET {column}={column}+$1,version=version+1 WHERE player_id=$2", c, t); command.Parameters.AddWithValue(amount); command.Parameters.AddWithValue(player);
            if (await command.ExecuteNonQueryAsync(ct) != 1)
                throw new InvalidOperationException("The player grant aggregate is missing.");
        }
        if (kind == "Cards")
        {
            var count = json.RootElement.TryGetProperty("count", out var countElement) ? countElement.GetInt32() * quantity : quantity;
            var selectedCardIds = new List<string>(count);
            if (json.RootElement.TryGetProperty("cardId", out var id))
            {
                var selected = id.GetString();
                if (string.IsNullOrWhiteSpace(selected) ||
                    GameConfigCatalog.Current.Cards.SingleOrDefault(card => card.IsCodex && card.CardId == selected) is null)
                    throw new InvalidOperationException("The shop card grant references an unknown card.");
                selectedCardIds.AddRange(Enumerable.Repeat(selected, count));
            }
            else
            {
                for (var index = 0; index < count; index++) selectedCardIds.Add(RollCardPackCard().CardId);
            }

            foreach (var selected in selectedCardIds)
            {
                await using var card = new NpgsqlCommand("UPDATE player_cards SET copy_count=copy_count+1, version=version+1, unlocked=true WHERE player_id=$1 AND card_id=$2", c, t);
                card.Parameters.AddWithValue(player);
                card.Parameters.AddWithValue(selected);
                if (await card.ExecuteNonQueryAsync(ct) != 1)
                    throw new InvalidOperationException("The player card aggregate is missing the granted card.");
            }
            return $"{count} cards";
        }
        return $"{amount} {kind}";
    }

    private static CardConfigDefinition RollCardPackCard()
    {
        var roll = RandomNumberGenerator.GetInt32(100);
        var quality = roll switch
        {
            < 50 => "White",
            < 80 => "Green",
            < 95 => "Blue",
            _ => "Purple"
        };
        var candidates = GameConfigCatalog.Current.Cards
            .Where(card => card.IsCodex && card.Quality == quality &&
                           !(quality == "Purple" && card.HeroClass is not null))
            .ToArray();
        if (candidates.Length == 0)
            throw new InvalidOperationException($"The card pack has no eligible {quality} card.");
        return candidates[RandomNumberGenerator.GetInt32(candidates.Length)];
    }

    private static async Task EnsurePaidBagCapacityAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string kind,
        string payload,
        int quantity,
        CancellationToken cancellationToken)
    {
        if (kind is not ("AdvancedBag" or "TopBag")) return;

        using var json = JsonDocument.Parse(payload);
        var amount = json.RootElement.GetProperty("amount").GetInt32() * quantity;
        await using var command = new NpgsqlCommand(
            "SELECT advanced_bag_count + top_bag_count FROM player_consumables WHERE player_id=$1 FOR UPDATE",
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        var current = await command.ExecuteScalarAsync(cancellationToken);
        if (current is null) throw new InvalidOperationException("The player consumables aggregate is missing.");
        if ((int)current + amount > 3)
            throw new InvalidOperationException("Paid exploration bag storage limit reached.");
    }

    private sealed record DailyCardOffer(CardConfigDefinition Card, ShopCardPriceConfig Price);
}
