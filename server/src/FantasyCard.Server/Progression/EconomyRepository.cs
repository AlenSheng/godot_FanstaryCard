using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Globalization;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Realtime;
using FantasyCard.Contracts.Realtime;
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

    // Shop refresh quotas reset at the server's UTC midnight. The regular shop
    // rotation keeps its existing 04:00 China-time schedule above.
    public static string GetServerDayKey(DateTimeOffset utc) =>
        utc.UtcDateTime.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
}

public sealed partial class EconomyMaintenanceWorker(
    EconomyRepository repository,
    EconomyReconciliationRepository reconciliationRepository,
    ConnectionRegistry connections,
    RealtimeEventStore eventStore,
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
                var expiredListings = await repository.ExpireListingsAsync(stoppingToken);
                foreach (var listingId in expiredListings)
                {
                    var listing = await repository.GetListingForEventAsync(listingId, stoppingToken);
                    if (listing is null) continue;
                    foreach (var batch in connections.ConnectedPlayerIds.Chunk(16))
                        await Task.WhenAll(batch.Select(async playerId =>
                        {
                            var message = eventStore.Create(playerId, "inventory.changed", "market.expired",
                                new InventoryChangedEventPayload("market.expired", listingId.ToString("D"), listing));
                            await connections.SendPresentationAsync(playerId, message);
                        }));
                }
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
                        report.LedgerChainMismatchCount,report.PendingMarketReturnMismatchCount,report.CardCopyLedgerMismatchCount,report.ActivityBudgetMismatchCount,report.JourneyExperienceMismatchCount);
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
        Message = "Economy reconciliation found {Total} violation(s): negativeAccounts={NegativeAccounts}, activeListingAssetMismatches={ActiveListingAssetMismatches}, orphanMarketListedEquipment={OrphanMarketListedEquipment}, soldListingMismatches={SoldListingMismatches}, transactionAmountMismatches={TransactionAmountMismatches}, ledgerChainMismatches={LedgerChainMismatches}, pendingMarketReturnMismatches={PendingMarketReturnMismatches}, cardCopyLedgerMismatches={CardCopyLedgerMismatches}, activityBudgetMismatches={ActivityBudgetMismatches}, journeyExperienceMismatches={JourneyExperienceMismatches}.")]
    private static partial void ReconciliationViolation(
        ILogger logger,
        long total,
        long negativeAccounts,
        long activeListingAssetMismatches,
        long orphanMarketListedEquipment,
        long soldListingMismatches,
        long transactionAmountMismatches,
        long ledgerChainMismatches,long pendingMarketReturnMismatches,long cardCopyLedgerMismatches,long activityBudgetMismatches,long journeyExperienceMismatches);
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
public sealed record ShopRefreshResult(ShopResponse Shop, bool Replayed);

public sealed partial class EconomyRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider,
    FantasyCard.Server.Rooms.PublishedConfigCatalogs? configurations=null,Func<int,int>? shopRandom=null) : IDisposable
{
    private readonly SemaphoreSlim _dailyStateGate = new(1, 1);
    private string? _initializedShopResetKey;
    private string? _initializedRefreshResetKey;

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

    private async Task<ShopResponse> GetLegacyShopAsync(Guid playerId, CancellationToken cancellationToken)
    {
        var now = timeProvider.GetUtcNow();
        var resetKey = EconomySchedule.GetDailyResetKey(now);
        var refreshResetKey = EconomySchedule.GetServerDayKey(now);
        await EnsureDailyReadStateAsync(resetKey, refreshResetKey, cancellationToken);
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        var state = await ReadRefreshStateAsync(connection, null, refreshResetKey, cancellationToken);
        return await ReadShopAsync(
            connection,
            null,
            playerId,
            resetKey,
            state.RotationKey,
            state.UsedCount,
            GameConfigCatalog.Current.Economy.DailyShopRefreshLimit,
            cancellationToken);
    }

    private async Task<ShopRefreshResult> RefreshLegacyShopAsync(Guid playerId, string requestId, CancellationToken cancellationToken)
    {
        var now = timeProvider.GetUtcNow();
        var shopResetKey = EconomySchedule.GetDailyResetKey(now);
        var refreshResetKey = EconomySchedule.GetServerDayKey(now);
        var config = GameConfigCatalog.Current;
        var requestHash = PersistentIdempotency.Hash(new { Action = "shop.refresh", Version = 1 });
        await EnsureDailyReadStateAsync(shopResetKey, refreshResetKey, cancellationToken);

        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var replay = await PersistentIdempotency.ReadAsync<ShopResponse>(
            connection,
            transaction,
            playerId,
            "shop.refresh",
            requestId,
            requestHash,
            cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return new(replay, true);
        }

        if(!(await ReadMarketScheduleAsync(connection,transaction,timeProvider.GetUtcNow(),cancellationToken)).LegacyAllowed)
            throw new FantasyCard.Domain.Players.DomainValidationException("The shop domain changed. Reload before refreshing.");

        var state = await ReadRefreshStateAsync(connection, transaction, refreshResetKey, cancellationToken);
        if(!(await ReadMarketScheduleAsync(connection,transaction,timeProvider.GetUtcNow(),cancellationToken)).LegacyAllowed)
            throw new FantasyCard.Domain.Players.DomainValidationException("The shop domain changed. Reload before refreshing.");
        if (state.UsedCount >= config.Economy.DailyShopRefreshLimit)
            throw new InvalidOperationException("Daily shop refresh limit reached.");

        var nextCount = state.UsedCount + 1;
        var rotationKey = $"{shopResetKey}~{nextCount}";
        await SeedRotationAsync(connection, transaction, rotationKey,
            $"{config.Version}:{shopResetKey}:refresh:{refreshResetKey}:{nextCount}", config, cancellationToken);
        await using (var update = new NpgsqlCommand(
            "UPDATE shop_refresh_states SET shop_reset_key=$1,rotation_key=$2,used_count=$3,updated_at=$4 WHERE reset_key=$5",
            connection, transaction))
        {
            update.Parameters.AddWithValue(shopResetKey);
            update.Parameters.AddWithValue(rotationKey);
            update.Parameters.AddWithValue(nextCount);
            update.Parameters.AddWithValue(now);
            update.Parameters.AddWithValue(refreshResetKey);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }
        var result = await ReadShopAsync(
            connection,
            transaction,
            playerId,
            shopResetKey,
            rotationKey,
            nextCount,
            config.Economy.DailyShopRefreshLimit,
            cancellationToken);
        await PersistentIdempotency.WriteAsync(
            connection,
            transaction,
            playerId,
            "shop.refresh",
            requestId,
            requestHash,
            result,
            now,
            cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return new(result, false);
    }

    private async Task<ShopPurchaseResponse> PurchaseLegacyShopAsync(Guid playerId, string requestId, PurchaseShopRequest request, CancellationToken cancellationToken)
    {
        if (request.Quantity is < 1 or > 10) throw new InvalidOperationException("Quantity must be between 1 and 10.");
        var resetKey = EconomySchedule.GetDailyResetKey(timeProvider.GetUtcNow());
        var refreshResetKey = EconomySchedule.GetServerDayKey(timeProvider.GetUtcNow());
        var hash = Hash(request);
        await EnsureDailyReadStateAsync(resetKey, refreshResetKey, cancellationToken);
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

        if(!(await ReadMarketScheduleAsync(connection,transaction,timeProvider.GetUtcNow(),cancellationToken)).LegacyAllowed)
            throw new FantasyCard.Domain.Players.DomainValidationException("The shop domain changed. Reload before purchasing.");
        var rotationKey = (await ReadRefreshStateAsync(connection, transaction, refreshResetKey, cancellationToken)).RotationKey;
        if(!(await ReadMarketScheduleAsync(connection,transaction,timeProvider.GetUtcNow(),cancellationToken)).LegacyAllowed)
            throw new FantasyCard.Domain.Players.DomainValidationException("The shop domain changed. Reload before purchasing.");
        string kind, payload; long price; int limit;
        await using (var product = new NpgsqlCommand("SELECT kind, payload_json::text, price_gold, limit_count FROM shop_rotations WHERE reset_key=$1 AND product_id=$2", connection, transaction))
        {
            product.Parameters.AddWithValue(rotationKey); product.Parameters.AddWithValue(request.ProductId);
            await using var reader = await product.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken)) throw new InvalidOperationException("Shop product is unavailable.");
            kind = reader.GetString(0); payload = reader.GetString(1); price = reader.GetInt64(2); limit = reader.GetInt32(3);
        }
        await EnsureCardPurchaseAvailableAsync(connection, transaction, playerId, kind, payload, request.Quantity, cancellationToken);
        var purchased = await PurchasedAsync(connection, transaction, playerId, resetKey, request.ProductId, cancellationToken);
        if (purchased + request.Quantity > limit) throw new InvalidOperationException("Daily purchase limit reached.");
        await EnsurePaidBagCapacityAsync(connection, transaction, playerId, kind, payload, request.Quantity, cancellationToken);
        var total = checked(price * request.Quantity);
        var goldAfter = await SpendGoldAsync(connection, transaction, playerId, total, cancellationToken);
        var granted = await GrantAsync(connection, transaction, playerId, kind, payload, request.Quantity, requestId, cancellationToken);
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

    private static async Task<ShopResponse> ReadShopAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction,
        Guid playerId,
        string resetKey,
        string rotationKey,
        int refreshesUsed,
        int refreshLimit,
        CancellationToken cancellationToken)
    {
        var products = new List<(string ProductId, string Kind, long PriceGold, int LimitCount, string Payload)>();
        await using (var command = new NpgsqlCommand(
            "SELECT product_id,kind,price_gold,limit_count,payload_json::text FROM shop_rotations WHERE reset_key=$1 ORDER BY product_id",
            connection,
            transaction))
        {
            command.Parameters.AddWithValue(rotationKey);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                products.Add((reader.GetString(0), reader.GetString(1), reader.GetInt64(2), reader.GetInt32(3), reader.GetString(4)));
        }

        var result = new List<ShopProductResponse>(products.Count);
        var purchaseCounts = new Dictionary<string, int>(StringComparer.Ordinal);
        await using (var purchases = new NpgsqlCommand(
            "SELECT product_id, COALESCE(sum(quantity), 0)::integer FROM shop_purchases WHERE player_id=$1 AND reset_key=$2 GROUP BY product_id",
            connection,
            transaction))
        {
            purchases.Parameters.AddWithValue(playerId);
            purchases.Parameters.AddWithValue(resetKey);
            await using var reader = await purchases.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                purchaseCounts[reader.GetString(0)] = reader.GetInt32(1);
        }

        var guaranteedCardIdsByProduct = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var product in products.Where(product => product.Kind == "Cards"))
        {
            using var payload = JsonDocument.Parse(product.Payload);
            if (payload.RootElement.TryGetProperty("cardId", out var cardId) &&
                !string.IsNullOrWhiteSpace(cardId.GetString()))
            {
                guaranteedCardIdsByProduct[product.ProductId] = cardId.GetString()!;
            }
        }

        HashSet<string> ownedCardIds = guaranteedCardIdsByProduct.Count == 0
            ? new(StringComparer.Ordinal)
            : await OwnedCardIdsAsync(connection, transaction, playerId, cancellationToken);
        foreach (var product in products)
        {
            var guaranteedCardOwned = guaranteedCardIdsByProduct.TryGetValue(product.ProductId, out var guaranteedCardId) &&
                ownedCardIds.Contains(guaranteedCardId);
            result.Add(new ShopProductResponse(
                product.ProductId,
                product.Kind,
                product.PriceGold,
                product.LimitCount,
                purchaseCounts.GetValueOrDefault(product.ProductId),
                product.Payload,
                guaranteedCardOwned));
        }
        return new ShopResponse(resetKey, result, refreshesUsed, refreshLimit);
    }

    private async Task EnsureDailyReadStateAsync(
        string shopResetKey,
        string refreshResetKey,
        CancellationToken cancellationToken)
    {
        if (string.Equals(Volatile.Read(ref _initializedShopResetKey), shopResetKey, StringComparison.Ordinal) &&
            string.Equals(Volatile.Read(ref _initializedRefreshResetKey), refreshResetKey, StringComparison.Ordinal))
            return;

        await _dailyStateGate.WaitAsync(cancellationToken);
        try
        {
            if (string.Equals(_initializedShopResetKey, shopResetKey, StringComparison.Ordinal) &&
                string.Equals(_initializedRefreshResetKey, refreshResetKey, StringComparison.Ordinal))
                return;

            await EnsureRotationAsync(shopResetKey, cancellationToken);
            await EnsureRefreshStateAsync(refreshResetKey, shopResetKey, cancellationToken);
            Volatile.Write(ref _initializedShopResetKey, shopResetKey);
            Volatile.Write(ref _initializedRefreshResetKey, refreshResetKey);
        }
        finally
        {
            _dailyStateGate.Release();
        }
    }

    private async Task EnsureRotationAsync(string resetKey, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await SeedRotationAsync(connection, transaction, resetKey, resetKey, GameConfigCatalog.Current, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    private async Task EnsureRefreshStateAsync(
        string refreshResetKey,
        string shopResetKey,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "INSERT INTO shop_refresh_states(reset_key,shop_reset_key,rotation_key,used_count,updated_at) VALUES($1,$2,$2,0,$3) " +
            "ON CONFLICT(reset_key) DO UPDATE SET shop_reset_key=EXCLUDED.shop_reset_key, " +
            "rotation_key=CASE WHEN shop_refresh_states.shop_reset_key <> EXCLUDED.shop_reset_key THEN EXCLUDED.shop_reset_key ELSE shop_refresh_states.rotation_key END, " +
            "updated_at=EXCLUDED.updated_at",
            connection);
        command.Parameters.AddWithValue(refreshResetKey);
        command.Parameters.AddWithValue(shopResetKey);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private async Task<ShopRefreshState> ReadRefreshStateAsync(
        string refreshResetKey,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        return await ReadRefreshStateAsync(connection, null, refreshResetKey, cancellationToken);
    }

    private static async Task<ShopRefreshState> ReadRefreshStateAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction? transaction,
        string refreshResetKey,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "SELECT used_count,rotation_key FROM shop_refresh_states WHERE reset_key=$1" +
            (transaction is null ? string.Empty : " FOR UPDATE"), connection, transaction);
        command.Parameters.AddWithValue(refreshResetKey);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Shop refresh state is unavailable.");
        return new ShopRefreshState(reader.GetInt32(0), reader.GetString(1));
    }

    private static async Task SeedRotationAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        string rotationKey,
        string seedKey,
        GameConfigCatalog config,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("INSERT INTO shop_rotations(reset_key,product_id,kind,payload_json,price_gold,limit_count) VALUES ($1,'card_pack','Cards','{\"rarity\":\"WhiteToPurple\",\"count\":3}',250,5),($1,'warrior_soul','WarriorSoul','{\"amount\":20}',180,3),($1,'equipment_fragments','EquipmentFragments','{\"amount\":20}',120,3),($1,'priest_soul','ClassSoul','{\"heroClass\":\"Priest\",\"amount\":12}',400,1),($1,'mage_soul','ClassSoul','{\"heroClass\":\"Mage\",\"amount\":12}',400,1),($1,'guardian_soul','ClassSoul','{\"heroClass\":\"Guardian\",\"amount\":12}',400,1),($1,'health_potion','HealthPotion','{\"amount\":1}',$2,4),($1,'advanced_bag','AdvancedBag','{\"amount\":1}',$3,99),($1,'top_bag','TopBag','{\"amount\":1}',$4,99) ON CONFLICT DO NOTHING", connection, transaction);
        command.Parameters.AddWithValue(rotationKey);
        command.Parameters.AddWithValue(config.Economy.HealthPotionPrice);
        command.Parameters.AddWithValue(config.Backpack("Advanced").PriceGold);
        command.Parameters.AddWithValue(config.Backpack("Top").PriceGold);
        await command.ExecuteNonQueryAsync(cancellationToken);

        var offers = CreateDailyCardOffers(seedKey, config);
        for (var index = 0; index < offers.Length; index++)
        {
            var offer = offers[index];
            await using var dailyCard = new NpgsqlCommand(
                "INSERT INTO shop_rotations(reset_key,product_id,kind,payload_json,price_gold,limit_count) VALUES($1,$2,'Cards',$3,$4,$5) ON CONFLICT DO NOTHING",
                connection,
                transaction);
            dailyCard.Parameters.AddWithValue(rotationKey);
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
    }

    private sealed record ShopRefreshState(int UsedCount, string RotationKey);

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

    private static async Task<int> PurchasedAsync(NpgsqlConnection c, NpgsqlTransaction? t, Guid player, string reset, string product, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("SELECT COALESCE(sum(quantity),0)::integer FROM shop_purchases WHERE player_id=$1 AND reset_key=$2 AND product_id=$3", c, t); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue(reset); cmd.Parameters.AddWithValue(product); return (int)(await cmd.ExecuteScalarAsync(ct) ?? 0); }

    private static async Task<HashSet<string>> OwnedCardIdsAsync(NpgsqlConnection c, NpgsqlTransaction? t, Guid player, CancellationToken ct)
    {
        await using var cmd = new NpgsqlCommand("SELECT card_id FROM player_cards WHERE player_id=$1 AND unlocked=true AND copy_count > 0 FOR SHARE", c, t);
        cmd.Parameters.AddWithValue(player);
        await using var reader = await cmd.ExecuteReaderAsync(ct);
        var result = new HashSet<string>(StringComparer.Ordinal);
        while (await reader.ReadAsync(ct)) result.Add(reader.GetString(0));
        return result;
    }

    private static async Task EnsureCardPurchaseAvailableAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, string kind, string payload, int quantity, CancellationToken ct)
    {
        if (kind != "Cards") return;
        using var json = JsonDocument.Parse(payload);
        var count = json.RootElement.TryGetProperty("count", out var countElement) ? countElement.GetInt32() * quantity : quantity;
        var owned = await OwnedCardIdsAsync(c, t, player, ct);
        if (json.RootElement.TryGetProperty("cardId", out var id))
        {
            var cardId = id.GetString() ?? string.Empty;
            if (count != 1 || owned.Contains(cardId))
                throw new InvalidOperationException("This card is already activated and cannot be purchased again.");
            return;
        }

        var available = GameConfigCatalog.Current.Cards.Count(card => CardPackEligible(card) && !owned.Contains(card.CardId));
        if (available < count)
            throw new InvalidOperationException("Not enough unowned cards remain for this card pack.");
    }

    private static async Task<long> SpendGoldAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, long amount, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("UPDATE player_wallets SET gold=gold-$1,version=version+1 WHERE player_id=$2 AND gold >= $1 RETURNING gold", c, t); cmd.Parameters.AddWithValue(amount); cmd.Parameters.AddWithValue(player); var value = await cmd.ExecuteScalarAsync(ct); if (value is null) throw new InvalidOperationException("Not enough gold."); return (long)value; }
    private static async Task<long> CurrentGoldAsync(NpgsqlConnection c, NpgsqlTransaction? t, Guid player, CancellationToken ct)
    { await using var cmd = new NpgsqlCommand("SELECT gold FROM player_wallets WHERE player_id=$1", c, t); cmd.Parameters.AddWithValue(player); return (long)(await cmd.ExecuteScalarAsync(ct) ?? 0L); }
    private static async Task WriteLedgerAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, long delta, long balance, string currency, string reason, CancellationToken ct, string? requestId = null)
    { await using var cmd = new NpgsqlCommand("INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8)", c, t); cmd.Parameters.AddWithValue(Guid.CreateVersion7()); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue((object?)requestId ?? DBNull.Value); cmd.Parameters.AddWithValue(currency); cmd.Parameters.AddWithValue(delta); cmd.Parameters.AddWithValue(balance); cmd.Parameters.AddWithValue(reason); cmd.Parameters.AddWithValue(DateTimeOffset.UtcNow); await cmd.ExecuteNonQueryAsync(ct); }
    private static async Task WriteInventoryMovementAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, Guid item, string from, string to, string reason, CancellationToken ct, string? requestId = null)
    { await using var cmd = new NpgsqlCommand("INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at) VALUES($1,$2,$3,$4,$5,$6,$7,CURRENT_TIMESTAMP)", c, t); cmd.Parameters.AddWithValue(Guid.CreateVersion7()); cmd.Parameters.AddWithValue(player); cmd.Parameters.AddWithValue(item); cmd.Parameters.AddWithValue(from); cmd.Parameters.AddWithValue(to); cmd.Parameters.AddWithValue(reason); cmd.Parameters.AddWithValue((object?)requestId ?? DBNull.Value); await cmd.ExecuteNonQueryAsync(ct); }

    private static async Task<string> GrantAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid player, string kind, string payload, int quantity, string requestId, CancellationToken ct)
    {
        using var json = JsonDocument.Parse(payload); var amount = json.RootElement.TryGetProperty("amount", out var a) ? a.GetInt64() * quantity : 0;
        var column = kind switch { "WarriorSoul" => "warrior_soul", "EquipmentFragments" => "equipment_fragments", "ClassSoul" => json.RootElement.GetProperty("heroClass").GetString()!.ToLowerInvariant() + "_soul", "HealthPotion" => "health_potion_count", "AdvancedBag" => "advanced_bag_count", "TopBag" => "top_bag_count", _ => null };
        if (column is not null)
        {
            var table = kind is "HealthPotion" or "AdvancedBag" or "TopBag" ? "player_consumables" : "player_materials";
            await using var command = new NpgsqlCommand($"UPDATE {table} SET {column}={column}+$1,version=version+1 WHERE player_id=$2 RETURNING {column}", c, t); command.Parameters.AddWithValue(amount); command.Parameters.AddWithValue(player);
            var balance = await command.ExecuteScalarAsync(ct);
            if (balance is null)
                throw new InvalidOperationException("The player grant aggregate is missing.");
            if (table == "player_materials")
            {
                var currency = kind == "ClassSoul"
                    ? json.RootElement.GetProperty("heroClass").GetString() + "Soul" : kind;
                await WriteLedgerAsync(c, t, player, amount, Convert.ToInt64(balance, CultureInfo.InvariantCulture),
                    currency, "shop.purchase", ct, requestId);
            }
        }
        if (kind == "Cards")
        {
            var count = json.RootElement.TryGetProperty("count", out var countElement) ? countElement.GetInt32() * quantity : quantity;
            var selectedCardIds = new List<string>(count);
            var excluded = await OwnedCardIdsAsync(c, t, player, ct);
            if (json.RootElement.TryGetProperty("cardId", out var id))
            {
                var selected = id.GetString();
                if (string.IsNullOrWhiteSpace(selected) ||
                    GameConfigCatalog.Current.Cards.SingleOrDefault(card => card.IsCodex && card.CardId == selected) is null)
                    throw new InvalidOperationException("The shop card grant references an unknown card.");
                if (count != 1 || excluded.Contains(selected))
                    throw new InvalidOperationException("This card is already activated and cannot be granted again.");
                selectedCardIds.Add(selected);
                excluded.Add(selected);
            }
            else
            {
                for (var index = 0; index < count; index++)
                {
                    var selected = RollCardPackCard(excluded).CardId;
                    selectedCardIds.Add(selected);
                    excluded.Add(selected);
                }
            }

            foreach (var selected in selectedCardIds)
            {
                await using var card = new NpgsqlCommand("UPDATE player_cards SET copy_count=1, version=version+1, unlocked=true WHERE player_id=$1 AND card_id=$2 AND (unlocked=false OR copy_count=0)", c, t);
                card.Parameters.AddWithValue(player);
                card.Parameters.AddWithValue(selected);
                if (await card.ExecuteNonQueryAsync(ct) != 1)
                    throw new InvalidOperationException("The player card aggregate is missing the granted card.");
            }
            return $"{count} cards";
        }
        return $"{amount} {kind}";
    }

    public void Dispose() => _dailyStateGate.Dispose();

    private static bool CardPackEligible(CardConfigDefinition card) =>
        card.IsCodex && (card.Quality is "White" or "Green" or "Blue" or "Purple") &&
        !(card.Quality == "Purple" && card.HeroClass is not null);

    private static CardConfigDefinition RollCardPackCard(HashSet<string> excluded)
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
                           !(quality == "Purple" && card.HeroClass is not null) && !excluded.Contains(card.CardId))
            .ToArray();
        if (candidates.Length == 0)
            candidates = GameConfigCatalog.Current.Cards.Where(card => CardPackEligible(card) && !excluded.Contains(card.CardId)).ToArray();
        if (candidates.Length == 0)
            throw new InvalidOperationException("The card pack has no unowned eligible card.");
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
