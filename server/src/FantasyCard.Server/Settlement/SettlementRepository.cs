using System.Text.Json;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Settlement;

public static class SettlementModule
{
    public static IServiceCollection AddSettlementModule(this IServiceCollection services)
    {
        services.AddSingleton<SettlementRepository>();
        services.AddSingleton<SettlementCoordinator>();
        services.AddSingleton<SettlementEventPublisher>();
        services.AddSingleton<SettlementRecoveryState>();
        services.AddHealthChecks().AddCheck<SettlementRecoveryHealthCheck>("settlement-recovery", tags: ["ready"]);
        services.AddHostedService<SettlementWorker>();
        return services;
    }
}

public sealed partial class SettlementWorker(
    SettlementRepository repository,
    SettlementEventPublisher eventPublisher,
    RoomRegistry rooms,
    SettlementRecoveryState recoveryState,
    ServerMetrics metrics,
    ILogger<SettlementWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                await ProcessNextAsync(stoppingToken);
                await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                recoveryState.FailScan(exception);
                metrics.SettlementFailed();
                HoldProcessingFailed(logger, exception);
                await Task.Delay(TimeSpan.FromSeconds(2), stoppingToken);
            }
        }
    }

    internal async Task<int> ProcessNextAsync(CancellationToken cancellationToken)
    {
        var pending = await repository.GetPendingHoldsAsync(cancellationToken);
        metrics.ObserveSettlementPendingHolds(pending.Count);
        var settlementIds = pending.Select(hold => hold.SettlementId).Distinct().ToArray();
        var failedSettlementIds = new List<Guid>();
        await SettlementBatchProcessor.ProcessAsync(
            settlementIds,
            repository.CommitHoldsAsync,
            (_, count) => metrics.SettlementHoldsCommitted(count),
            (settlementId, exception) =>
            {
                failedSettlementIds.Add(settlementId);
                metrics.SettlementFailed();
                SettlementCommitFailed(logger, settlementId, exception);
            },
            cancellationToken);
        await eventPublisher.PublishReadyAsync(playerId: null, cancellationToken);
        var registeredRoomIds = rooms.GetRoomIds();
        foreach (var roomId in await repository.GetTerminalRoomIdsAsync(registeredRoomIds, cancellationToken))
            await rooms.RemoveAsync(roomId);
        recoveryState.Complete(failedSettlementIds);
        return settlementIds.Length;
    }

    [LoggerMessage(EventId = 4101, Level = LogLevel.Error, Message = "Settlement hold processing failed.")]
    private static partial void HoldProcessingFailed(ILogger logger, Exception exception);

    [LoggerMessage(EventId = 4102, Level = LogLevel.Error, Message = "Settlement {SettlementId} asset commit failed; later settlements will continue processing.")]
    private static partial void SettlementCommitFailed(ILogger logger, Guid settlementId, Exception exception);
}

public sealed record SettlementRecord(
    Guid SettlementId,
    Guid MatchId,
    Guid PlayerId,
    string Result,
    string DetailsJson,
    DateTimeOffset CreatedAt,
    bool Created);

public sealed record SettlementHoldRecord(
    Guid HoldId,
    Guid SettlementId,
    Guid PlayerId,
    string AssetKind,
    string AssetId,
    string State,
    string AssetSnapshot);

public sealed record SettlementNotification(
    Guid SettlementId,
    Guid PlayerId,
    Guid MatchId,
    string Result);

public sealed class SettlementNotFoundException : InvalidOperationException;

public sealed class SettlementNotReadyException : InvalidOperationException;

public sealed class SettlementRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider, ServerMetrics metrics)
{
    public async Task<IReadOnlyList<Guid>> GetTerminalRoomIdsAsync(
        IReadOnlyCollection<Guid> roomIds,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(roomIds);
        if (roomIds.Count == 0) return [];
        await using var command = dataSource.CreateCommand(
            "SELECT room_id FROM matches WHERE room_id=ANY($1) AND status IN ('Completed','Aborted') ORDER BY room_id");
        command.Parameters.AddWithValue(roomIds.ToArray());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<Guid>();
        while (await reader.ReadAsync(cancellationToken)) result.Add(reader.GetGuid(0));
        return result;
    }

    public async Task CompleteBotAsync(
        Guid matchId,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var bot = new NpgsqlCommand(
            "UPDATE match_players SET state='Settled',settled_at=$1 WHERE match_id=$2 AND player_id=$3 AND is_bot=true AND state <> 'Settled'",
            connection,
            transaction))
        {
            bot.Parameters.AddWithValue(timeProvider.GetUtcNow());
            bot.Parameters.AddWithValue(matchId);
            bot.Parameters.AddWithValue(playerId);
            await bot.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var match = new NpgsqlCommand(
            "UPDATE matches SET status='Completed' WHERE match_id=$1 AND NOT EXISTS (SELECT 1 FROM match_players WHERE match_id=$1 AND state NOT IN ('Settled','Removed'))",
            connection,
            transaction))
        {
            match.Parameters.AddWithValue(matchId);
            await match.ExecuteNonQueryAsync(cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<IReadOnlyList<SettlementHoldRecord>> GetPendingHoldsAsync(CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT hold_id,settlement_id,player_id,asset_kind,asset_ref,state,asset_snapshot::text FROM settlement_asset_holds WHERE state='Pending' ORDER BY created_at,hold_id");
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<SettlementHoldRecord>();
        while (await reader.ReadAsync(cancellationToken))
            result.Add(new(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetString(3), reader.GetString(4), reader.GetString(5), reader.GetString(6)));
        return result;
    }

    public async Task<int> CommitHoldsAsync(Guid settlementId, CancellationToken cancellationToken) =>
        await TransitionHoldsAsync(settlementId, "Committed", cancellationToken);

    public async Task<int> ReleaseHoldsAsync(Guid settlementId, CancellationToken cancellationToken) =>
        await TransitionHoldsAsync(settlementId, "Released", cancellationToken);

    public async Task<IReadOnlyList<SettlementNotification>> GetReadyNotificationsAsync(
        Guid? playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT o.settlement_id,o.player_id,o.match_id,o.result
            FROM settlement_notification_outbox o
            WHERE o.published_at IS NULL
              AND ($1::uuid IS NULL OR o.player_id=$1)
              AND NOT EXISTS (
                  SELECT 1 FROM settlement_asset_holds h
                  WHERE h.settlement_id=o.settlement_id AND h.state='Pending')
            ORDER BY o.created_at,o.settlement_id
            LIMIT 100
            """);
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Uuid,
            Value = playerId ?? (object)DBNull.Value
        });
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<SettlementNotification>();
        while (await reader.ReadAsync(cancellationToken))
            result.Add(new(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetString(3)));
        return result;
    }

    public async Task MarkNotificationPublishedAsync(Guid settlementId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "UPDATE settlement_notification_outbox SET published_at=$1 WHERE settlement_id=$2 AND published_at IS NULL");
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        command.Parameters.AddWithValue(settlementId);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<SettlementResponse> GetAsync(Guid playerId, Guid settlementId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT settlement_id,match_id,player_id,result,details_json::text,created_at FROM match_settlements WHERE settlement_id=$1 AND player_id=$2");
        command.Parameters.AddWithValue(settlementId);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) throw new InvalidOperationException("Settlement was not found.");
        return ReadResponse(reader);
    }

    public async Task<SettlementResponse> GetForMatchAsync(Guid playerId, Guid matchId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT settlement_id,match_id,player_id,result,details_json::text,created_at FROM match_settlements WHERE match_id=$1 AND player_id=$2");
        command.Parameters.AddWithValue(matchId);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) throw new InvalidOperationException("Settlement was not found.");
        return ReadResponse(reader);
    }

    public async Task<SettlementAcknowledgementResponse> AcknowledgeAsync(
        Guid playerId,
        Guid settlementId,
        string requestId,
        CancellationToken cancellationToken)
    {
        if (playerId == Guid.Empty) throw new ArgumentException("Player id is required.", nameof(playerId));
        if (settlementId == Guid.Empty) throw new ArgumentException("Settlement id is required.", nameof(settlementId));

        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        const string scope = "settlement.acknowledge";
        var requestHash = PersistentIdempotency.Hash(new { settlementId });
        var replay = await PersistentIdempotency.ReadAsync<SettlementAcknowledgementResponse>(
            connection, transaction, playerId, scope, requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }
        DateTimeOffset? acknowledgedAt;
        await using (var select = new NpgsqlCommand(
            """
            SELECT s.acknowledged_at,
                   EXISTS (
                       SELECT 1 FROM settlement_asset_holds h
                       WHERE h.settlement_id=s.settlement_id AND h.state='Pending')
            FROM match_settlements s
            WHERE s.settlement_id=$1 AND s.player_id=$2
            FOR UPDATE
            """, connection, transaction))
        {
            select.Parameters.AddWithValue(settlementId);
            select.Parameters.AddWithValue(playerId);
            await using var reader = await select.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken)) throw new SettlementNotFoundException();
            acknowledgedAt = reader.IsDBNull(0) ? null : reader.GetFieldValue<DateTimeOffset>(0);
            if (reader.GetBoolean(1)) throw new SettlementNotReadyException();
        }

        if (acknowledgedAt is null)
        {
            acknowledgedAt = timeProvider.GetUtcNow();
            await using var update = new NpgsqlCommand(
                "UPDATE match_settlements SET acknowledged_at=$1 WHERE settlement_id=$2 AND acknowledged_at IS NULL",
                connection,
                transaction);
            update.Parameters.AddWithValue(acknowledgedAt.Value);
            update.Parameters.AddWithValue(settlementId);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }

        var response = new SettlementAcknowledgementResponse(settlementId, acknowledgedAt.Value);
        await PersistentIdempotency.WriteAsync(
            connection, transaction, playerId, scope, requestId, requestHash, response,
            timeProvider.GetUtcNow(), cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return response;
    }

    public async Task<SettlementRecord> SettleAsync(
        Guid matchId,
        Guid playerId,
        string result,
        JsonElement details,
        IReadOnlyList<SettlementAsset> assets,
        CancellationToken cancellationToken)
    {
        if (matchId == Guid.Empty || playerId == Guid.Empty) throw new ArgumentException("Match and player are required.");
        if (result is not ("Extracted" or "Dead" or "Aborted")) throw new ArgumentException("Unknown settlement result.", nameof(result));
        ArgumentNullException.ThrowIfNull(assets);

        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        Guid? existingId;
        await using (var lockPlayer = new NpgsqlCommand(
            "SELECT settlement_id FROM match_players WHERE match_id=$1 AND player_id=$2 FOR UPDATE", connection, transaction))
        {
            lockPlayer.Parameters.AddWithValue(matchId);
            lockPlayer.Parameters.AddWithValue(playerId);
            var value = await lockPlayer.ExecuteScalarAsync(cancellationToken);
            if (value is null) throw new InvalidOperationException("The player is not assigned to this match.");
            existingId = value is DBNull ? null : (Guid?)value;
        }
        if (existingId is { } id)
        {
            var replay = await ReadAsync(connection, transaction, id, cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            metrics.SettlementIdempotencyHit();
            return replay;
        }

        var settlementId = Guid.CreateVersion7();
        var createdAt = timeProvider.GetUtcNow();
        var detailsJson = details.GetRawText();
        await using (var insert = new NpgsqlCommand(
            "INSERT INTO match_settlements(settlement_id,match_id,player_id,result,details_json,created_at) VALUES($1,$2,$3,$4,$5,$6)", connection, transaction))
        {
            insert.Parameters.AddWithValue(settlementId);
            insert.Parameters.AddWithValue(matchId);
            insert.Parameters.AddWithValue(playerId);
            insert.Parameters.AddWithValue(result);
            insert.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Jsonb, Value = detailsJson });
            insert.Parameters.AddWithValue(createdAt);
            await insert.ExecuteNonQueryAsync(cancellationToken);
        }
        foreach (var asset in assets)
        {
            await using var hold = new NpgsqlCommand(
                "INSERT INTO settlement_asset_holds(hold_id,settlement_id,player_id,asset_kind,asset_ref,asset_snapshot,state,created_at) VALUES($1,$2,$3,$4,$5,$6,'Pending',$7)", connection, transaction);
            hold.Parameters.AddWithValue(Guid.CreateVersion7());
            hold.Parameters.AddWithValue(settlementId);
            hold.Parameters.AddWithValue(playerId);
            hold.Parameters.AddWithValue(asset.AssetKind);
            hold.Parameters.AddWithValue(asset.AssetId);
            hold.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Jsonb, Value = JsonSerializer.Serialize(asset) });
            hold.Parameters.AddWithValue(createdAt);
            await hold.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var outbox = new NpgsqlCommand(
            "INSERT INTO settlement_notification_outbox(settlement_id,player_id,match_id,result,created_at) VALUES($1,$2,$3,$4,$5)",
            connection,
            transaction))
        {
            outbox.Parameters.AddWithValue(settlementId);
            outbox.Parameters.AddWithValue(playerId);
            outbox.Parameters.AddWithValue(matchId);
            outbox.Parameters.AddWithValue(result);
            outbox.Parameters.AddWithValue(createdAt);
            await outbox.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var update = new NpgsqlCommand(
            "UPDATE match_players SET state='Settled',settled_at=$1,settlement_id=$2 WHERE match_id=$3 AND player_id=$4", connection, transaction))
        {
            update.Parameters.AddWithValue(createdAt);
            update.Parameters.AddWithValue(settlementId);
            update.Parameters.AddWithValue(matchId);
            update.Parameters.AddWithValue(playerId);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var preparation = new NpgsqlCommand(
            "UPDATE preparations SET status='Settled' WHERE preparation_id=(SELECT preparation_id FROM match_players WHERE match_id=$1 AND player_id=$2) AND status='Matched'", connection, transaction))
        {
            preparation.Parameters.AddWithValue(matchId);
            preparation.Parameters.AddWithValue(playerId);
            await preparation.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var match = new NpgsqlCommand(
            "UPDATE matches SET status='Completed' WHERE match_id=$1 AND NOT EXISTS (SELECT 1 FROM match_players WHERE match_id=$1 AND state NOT IN ('Settled','Removed'))", connection, transaction))
        {
            match.Parameters.AddWithValue(matchId);
            await match.ExecuteNonQueryAsync(cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
        metrics.SettlementCreated();
        return new SettlementRecord(settlementId, matchId, playerId, result, detailsJson, createdAt, true);
    }

    private static async Task<SettlementRecord> ReadAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, Guid settlementId, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "SELECT settlement_id,match_id,player_id,result,details_json::text,created_at FROM match_settlements WHERE settlement_id=$1", connection, transaction);
        command.Parameters.AddWithValue(settlementId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) throw new InvalidOperationException("The settlement record is missing.");
        return new(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetString(3), reader.GetString(4), reader.GetFieldValue<DateTimeOffset>(5), false);
    }

    private static SettlementResponse ReadResponse(NpgsqlDataReader reader) =>
        new(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetString(3),
            JsonDocument.Parse(reader.GetString(4)).RootElement.Clone(), reader.GetFieldValue<DateTimeOffset>(5));

    private async Task<int> TransitionHoldsAsync(Guid settlementId, string state, CancellationToken cancellationToken)
    {
        if (settlementId == Guid.Empty) throw new ArgumentException("Settlement id is required.", nameof(settlementId));
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        var holds = new List<SettlementHoldRecord>();
        await using (var select = new NpgsqlCommand(
            "SELECT hold_id,settlement_id,player_id,asset_kind,asset_ref,state,asset_snapshot::text FROM settlement_asset_holds WHERE settlement_id=$1 AND state='Pending' FOR UPDATE", connection, transaction))
        {
            select.Parameters.AddWithValue(settlementId);
            await using var reader = await select.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                holds.Add(new(reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetString(3), reader.GetString(4), reader.GetString(5), reader.GetString(6)));
        }
        if (state == "Committed")
        {
            foreach (var playerId in holds.Select(hold => hold.PlayerId).Distinct().Order())
            {
                await using var playerLock = new NpgsqlCommand(
                    "SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction);
                playerLock.Parameters.AddWithValue(playerId);
                if (await playerLock.ExecuteScalarAsync(cancellationToken) is null)
                    throw new InvalidOperationException("The settlement player is missing.");
            }
            foreach (var hold in holds)
                await ApplyCommittedAssetAsync(connection, transaction, hold, cancellationToken);
            if (holds.Count > 0)
                await RestoreExtractionLoadoutAsync(connection, transaction, settlementId, holds, cancellationToken);
            await EnsureDeathReplacementShoesAsync(connection, transaction, settlementId, cancellationToken);
        }
        var count = 0;
        foreach (var hold in holds)
        {
            await using var command = new NpgsqlCommand(
                "UPDATE settlement_asset_holds SET state=$1 WHERE hold_id=$2 AND state='Pending'", connection, transaction);
            command.Parameters.AddWithValue(state);
            command.Parameters.AddWithValue(hold.HoldId);
            count += await command.ExecuteNonQueryAsync(cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
        return count;
    }

    private static async Task ApplyCommittedAssetAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, SettlementHoldRecord hold, CancellationToken cancellationToken)
    {
        var asset = JsonSerializer.Deserialize<SettlementAsset>(hold.AssetSnapshot)
            ?? throw new InvalidOperationException("Settlement asset snapshot is invalid.");
        if (asset.Quantity <= 0) throw new InvalidOperationException("Settlement asset quantity is invalid.");
        if (asset.AssetKind == "Equipment")
        {
            if (!Guid.TryParse(asset.AssetId, out var equipmentId)) throw new InvalidOperationException("Equipment asset id is invalid.");
            var destination = asset.Destination ?? "Inventory";
            if (destination is not ("Inventory" or "Equipped" or "RelicPile" or "Recycled"))
                throw new InvalidOperationException("Equipment settlement destination is invalid.");
            // A looter may finish before the victim's worker; commit the earlier custody transfer first.
            await using (var predecessor = new NpgsqlCommand(
                """
                SELECT EXISTS (
                    SELECT 1 FROM settlement_asset_holds h
                    JOIN match_settlements earlier ON earlier.settlement_id=h.settlement_id
                    JOIN match_settlements current ON current.settlement_id=$1
                    WHERE h.asset_kind='Equipment' AND h.asset_ref=$2 AND h.state='Pending'
                      AND (earlier.created_at,earlier.settlement_id) < (current.created_at,current.settlement_id))
                """, connection, transaction))
            {
                predecessor.Parameters.AddWithValue(hold.SettlementId);
                predecessor.Parameters.AddWithValue(asset.AssetId);
                if (await predecessor.ExecuteScalarAsync(cancellationToken) is true)
                    throw new InvalidOperationException("An earlier settlement still holds this equipment.");
            }
            if (asset.Equipment is { } generated)
            {
                if (!EquipmentRewardRules.IsValid(generated))
                    throw new InvalidOperationException("Generated equipment attributes are invalid.");
                await using var create = new NpgsqlCommand(
                    """
                    INSERT INTO equipments(
                        instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,
                        element,effect_affix,secondary_trait)
                    VALUES($1,$2,$3,$4,$9,$10,$5,1,CURRENT_TIMESTAMP,$6,$7,$8)
                    ON CONFLICT (instance_id) DO NOTHING
                    """, connection, transaction);
                create.Parameters.AddWithValue(equipmentId);
                create.Parameters.AddWithValue(hold.PlayerId);
                create.Parameters.AddWithValue(generated.Slot);
                create.Parameters.AddWithValue(generated.Quality);
                create.Parameters.AddWithValue(destination);
                create.Parameters.AddWithValue(generated.Element);
                create.Parameters.AddWithValue(generated.EffectAffix ?? (object)DBNull.Value);
                create.Parameters.AddWithValue(generated.SecondaryTrait);
                create.Parameters.AddWithValue(generated.Level);
                create.Parameters.AddWithValue(generated.IsBound);
                if (await create.ExecuteNonQueryAsync(cancellationToken) == 1)
                {
                    await WriteEquipmentMovementAsync(connection, transaction, hold.PlayerId, equipmentId,
                        "MatchReward", destination, EquipmentSettlementReason(destination), cancellationToken);
                    return;
                }
            }
            Guid previousOwner;
            string source;
            await using (var select = new NpgsqlCommand(
                "SELECT owner_id,location,slot,quality,level,is_bound,element,effect_affix,secondary_trait FROM equipments WHERE instance_id=$1 FOR UPDATE", connection, transaction))
            {
                select.Parameters.AddWithValue(equipmentId);
                await using var reader = await select.ExecuteReaderAsync(cancellationToken);
                if (!await reader.ReadAsync(cancellationToken))
                    throw new InvalidOperationException("The settlement equipment is missing.");
                previousOwner = reader.GetGuid(0);
                source = reader.GetString(1);
                if (asset.Equipment is { } expected &&
                    (reader.GetString(2) != expected.Slot || reader.GetString(3) != expected.Quality ||
                     reader.GetInt32(4) != expected.Level || reader.GetBoolean(5) != expected.IsBound ||
                     reader.GetString(6) != expected.Element ||
                     (reader.IsDBNull(7) ? null : reader.GetString(7)) != expected.EffectAffix ||
                     (reader.IsDBNull(8) ? null : reader.GetString(8)) != expected.SecondaryTrait))
                    throw new InvalidOperationException("The existing equipment does not match its reward snapshot.");
            }
            if (source is not ("InMatchBackpack" or "InMatchEquipped" or "RelicPile"))
                throw new InvalidOperationException("The settlement equipment is no longer held by the match.");
            var validTransition = (source, destination) switch
            {
                ("InMatchBackpack", "Inventory" or "Equipped" or "RelicPile" or "Recycled") => true,
                ("InMatchEquipped", "Equipped" or "Inventory" or "RelicPile" or "Recycled") => true,
                ("RelicPile", "Inventory" or "Equipped" or "RelicPile" or "Recycled") => true,
                _ => false
            };
            if (!validTransition)
                throw new InvalidOperationException("The settlement equipment transition is invalid.");
            if (source != "RelicPile" && previousOwner != hold.PlayerId)
                throw new InvalidOperationException("The settlement equipment belongs to another player.");
            await using (var equipment = new NpgsqlCommand(
                "UPDATE equipments SET owner_id=$1,location=$2,version=version+1 WHERE instance_id=$3", connection, transaction))
            {
                equipment.Parameters.AddWithValue(hold.PlayerId);
                equipment.Parameters.AddWithValue(destination);
                equipment.Parameters.AddWithValue(equipmentId);
                await equipment.ExecuteNonQueryAsync(cancellationToken);
            }
            if (destination != "Equipped" || previousOwner != hold.PlayerId)
                await RemoveEquipmentFromLoadoutsAsync(connection, transaction, previousOwner, equipmentId, cancellationToken);
            await WriteEquipmentMovementAsync(connection, transaction, hold.PlayerId, equipmentId,
                source, destination, EquipmentSettlementReason(destination), cancellationToken);
            return;
        }
        if (asset.AssetKind == "Gold")
        {
            await using var wallet = new NpgsqlCommand("UPDATE player_wallets SET gold=gold+$1,version=version+1 WHERE player_id=$2 RETURNING gold", connection, transaction);
            wallet.Parameters.AddWithValue(asset.Quantity);
            wallet.Parameters.AddWithValue(hold.PlayerId);
            var balance = await wallet.ExecuteScalarAsync(cancellationToken);
            if (balance is not long goldAfter)
                throw new InvalidOperationException("The settlement wallet is missing.");
            await WriteEconomyLedgerAsync(connection, transaction, hold, asset.Quantity, goldAfter, "Gold", cancellationToken);
            return;
        }
        var materialColumn = SettlementMaterialMapping.GetColumn(asset);
        if (materialColumn is not null)
        {
            await using var materials = new NpgsqlCommand($"UPDATE player_materials SET {materialColumn}={materialColumn}+$1,version=version+1 WHERE player_id=$2 RETURNING {materialColumn}", connection, transaction);
            materials.Parameters.AddWithValue(asset.Quantity);
            materials.Parameters.AddWithValue(hold.PlayerId);
            var balance = await materials.ExecuteScalarAsync(cancellationToken);
            if (balance is not long materialAfter)
                throw new InvalidOperationException("The settlement material account is missing.");
            var currency = materialColumn switch
            {
                "warrior_soul" => "WarriorSoul",
                "equipment_fragments" => "EquipmentFragments",
                "priest_soul" => "PriestSoul",
                "mage_soul" => "MageSoul",
                "guardian_soul" => "GuardianSoul",
                _ => "ClassSoul"
            };
            await WriteEconomyLedgerAsync(connection, transaction, hold, asset.Quantity, materialAfter, currency, cancellationToken);
            return;
        }
        if (asset.AssetKind == "HealthPotion")
        {
            await using var consumable = new NpgsqlCommand("UPDATE player_consumables SET health_potion_count=health_potion_count+$1,version=version+1 WHERE player_id=$2", connection, transaction);
            consumable.Parameters.AddWithValue(checked((int)asset.Quantity));
            consumable.Parameters.AddWithValue(hold.PlayerId);
            if (await consumable.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("The settlement consumable account is missing.");
            return;
        }
        if (asset.AssetKind == "Backpack")
        {
            var column = asset.AssetId switch
            {
                "Advanced" => "advanced_bag_count",
                "Top" => "top_bag_count",
                _ => throw new InvalidOperationException("Settlement backpack tier is invalid.")
            };
            await using var consumable = new NpgsqlCommand(
                $"UPDATE player_consumables SET {column}={column}-$1,version=version+1 WHERE player_id=$2 AND {column}>=$1", connection, transaction);
            consumable.Parameters.AddWithValue(checked((int)asset.Quantity));
            consumable.Parameters.AddWithValue(hold.PlayerId);
            if (await consumable.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("The settlement consumable account is missing.");
            return;
        }
        throw new InvalidOperationException($"Unsupported settlement asset kind '{asset.AssetKind}'.");
    }

    private static string EquipmentSettlementReason(string destination) => destination switch
    {
        "RelicPile" => "settlement.death",
        "Recycled" => "reward.recycle",
        _ => "settlement.extract"
    };

    private static async Task RestoreExtractionLoadoutAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid settlementId,
        List<SettlementHoldRecord> holds,
        CancellationToken cancellationToken)
    {
        string? className;
        await using (var metadata = new NpgsqlCommand(
            "SELECT details_json->>'heroClass' FROM match_settlements WHERE settlement_id=$1 AND result='Extracted'",
            connection, transaction))
        {
            metadata.Parameters.AddWithValue(settlementId);
            className = await metadata.ExecuteScalarAsync(cancellationToken) as string;
        }
        // Settlements written before room equipment changes did not contain a class-specific loadout.
        if (className is null) return;
        if (!Enum.TryParse<HeroClass>(className, out var heroClass) || !Enum.IsDefined(heroClass))
            throw new InvalidOperationException("The settlement loadout class is invalid.");
        var assets = holds.Select(hold => JsonSerializer.Deserialize<SettlementAsset>(hold.AssetSnapshot)!).ToArray();
        var equippedIds = assets.Where(asset => asset.AssetKind == "Equipment" && asset.Destination == "Equipped")
            .Select(asset => Guid.Parse(asset.AssetId)).ToArray();
        var playerId = holds[0].PlayerId;
        var equipped = new Dictionary<string, Guid>(StringComparer.Ordinal);
        var valuableCount = 0;
        await using (var select = new NpgsqlCommand(
            "SELECT instance_id,slot,quality FROM equipments WHERE instance_id=ANY($1) AND owner_id=$2 AND location='Equipped' FOR UPDATE",
            connection, transaction))
        {
            select.Parameters.AddWithValue(equippedIds);
            select.Parameters.AddWithValue(playerId);
            await using var reader = await select.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                if (!equipped.TryAdd(reader.GetString(1), reader.GetGuid(0)))
                    throw new InvalidOperationException("The settlement has multiple armor pieces in one slot.");
                if (reader.GetString(2) is "Orange" or "Red") valuableCount++;
            }
        }
        if (equipped.Count != equippedIds.Length || valuableCount > 1)
            throw new InvalidOperationException("The settlement loadout equipment is invalid.");
        await using var update = new NpgsqlCommand(
            "UPDATE player_loadouts SET head_id=$1,chest_id=$2,hands_id=$3,legs_id=$4,feet_id=$5,version=version+1 WHERE player_id=$6 AND hero_class=$7",
            connection, transaction);
        foreach (var slot in new[] { "Head", "Chest", "Hands", "Legs", "Feet" })
            update.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Uuid,
                Value = equipped.TryGetValue(slot, out var itemId) ? itemId : DBNull.Value });
        update.Parameters.AddWithValue(playerId);
        update.Parameters.AddWithValue((short)heroClass);
        if (await update.ExecuteNonQueryAsync(cancellationToken) != 1)
            throw new InvalidOperationException("The settlement loadout is missing.");
    }

    private static async Task EnsureDeathReplacementShoesAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid settlementId,
        CancellationToken cancellationToken)
    {
        string result;
        Guid playerId;
        await using (var metadata = new NpgsqlCommand(
            "SELECT result, player_id FROM match_settlements WHERE settlement_id=$1",
            connection, transaction))
        {
            metadata.Parameters.AddWithValue(settlementId);
            await using var reader = await metadata.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
                throw new InvalidOperationException("The settlement record is missing.");
            result = reader.GetString(0);
            playerId = reader.GetGuid(1);
        }
        if (result != "Dead") return;

        await using (var playerLock = new NpgsqlCommand(
            "SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction))
        {
            playerLock.Parameters.AddWithValue(playerId);
            if (await playerLock.ExecuteScalarAsync(cancellationToken) is null)
                throw new InvalidOperationException("The settlement player is missing.");
        }

        int inventoryShoes;
        await using (var count = new NpgsqlCommand(
            """
            SELECT count(*)::integer
            FROM equipments
            WHERE owner_id=$1 AND slot=$2 AND location='Inventory'
            """, connection, transaction))
        {
            count.Parameters.AddWithValue(playerId);
            count.Parameters.AddWithValue(DeathReturnRules.ReplacementSlot);
            inventoryShoes = (int)(await count.ExecuteScalarAsync(cancellationToken) ?? 0);
        }

        var emptyClasses = new List<short>();
        await using (var empty = new NpgsqlCommand(
            "SELECT hero_class FROM player_loadouts WHERE player_id=$1 AND feet_id IS NULL ORDER BY hero_class FOR UPDATE",
            connection, transaction))
        {
            empty.Parameters.AddWithValue(playerId);
            await using var reader = await empty.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                emptyClasses.Add(reader.GetInt16(0));
        }

        foreach (var heroClass in emptyClasses)
        {
            if (!DeathReturnRules.ShouldGrantBoundWhiteShoes(
                    loadoutFeetEmpty: true,
                    hasWearableInventoryShoes: inventoryShoes > 0))
                return;

            var shoeId = Guid.CreateVersion7();
            await using (var create = new NpgsqlCommand(
                """
                INSERT INTO equipments(
                    instance_id, owner_id, slot, quality, level, is_bound, location, version, created_at,
                    element, effect_affix, secondary_trait)
                VALUES ($1, $2, $3, $4, $5, $6, 'Equipped', 1, CURRENT_TIMESTAMP, $7, NULL, $8)
                """, connection, transaction))
            {
                create.Parameters.AddWithValue(shoeId);
                create.Parameters.AddWithValue(playerId);
                create.Parameters.AddWithValue(DeathReturnRules.ReplacementSlot);
                create.Parameters.AddWithValue(DeathReturnRules.ReplacementQuality);
                create.Parameters.AddWithValue(DeathReturnRules.ReplacementLevel);
                create.Parameters.AddWithValue(DeathReturnRules.ReplacementBound);
                create.Parameters.AddWithValue(DeathReturnRules.ReplacementElement);
                create.Parameters.AddWithValue(DeathReturnRules.ReplacementSecondaryTrait);
                await create.ExecuteNonQueryAsync(cancellationToken);
            }

            await using (var loadout = new NpgsqlCommand(
                "UPDATE player_loadouts SET feet_id=$1, version=version+1 WHERE player_id=$2 AND hero_class=$3 AND feet_id IS NULL",
                connection, transaction))
            {
                loadout.Parameters.AddWithValue(shoeId);
                loadout.Parameters.AddWithValue(playerId);
                loadout.Parameters.AddWithValue(heroClass);
                if (await loadout.ExecuteNonQueryAsync(cancellationToken) != 1)
                    throw new InvalidOperationException("The death replacement loadout was not empty.");
            }

            await WriteEquipmentMovementAsync(
                connection, transaction, playerId, shoeId,
                DeathReturnRules.MovementSource, "Equipped", DeathReturnRules.MovementReason,
                cancellationToken);
        }
    }

    private static async Task RemoveEquipmentFromLoadoutsAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        Guid equipmentId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            UPDATE player_loadouts
            SET head_id=CASE WHEN head_id=$1 THEN NULL ELSE head_id END,
                chest_id=CASE WHEN chest_id=$1 THEN NULL ELSE chest_id END,
                hands_id=CASE WHEN hands_id=$1 THEN NULL ELSE hands_id END,
                legs_id=CASE WHEN legs_id=$1 THEN NULL ELSE legs_id END,
                feet_id=CASE WHEN feet_id=$1 THEN NULL ELSE feet_id END,
                version=version+1
            WHERE player_id=$2 AND $1 IN (head_id,chest_id,hands_id,legs_id,feet_id)
            """, connection, transaction);
        command.Parameters.AddWithValue(equipmentId);
        command.Parameters.AddWithValue(playerId);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task WriteEquipmentMovementAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        Guid equipmentId,
        string fromLocation,
        string toLocation,
        string reason,
        CancellationToken cancellationToken)
    {
        await using var movement = new NpgsqlCommand(
            "INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,created_at) VALUES($1,$2,$3,$4,$5,$6,CURRENT_TIMESTAMP)",
            connection,
            transaction);
        movement.Parameters.AddWithValue(Guid.CreateVersion7());
        movement.Parameters.AddWithValue(playerId);
        movement.Parameters.AddWithValue(equipmentId);
        movement.Parameters.AddWithValue(fromLocation);
        movement.Parameters.AddWithValue(toLocation);
        movement.Parameters.AddWithValue(reason);
        await movement.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task WriteEconomyLedgerAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        SettlementHoldRecord hold,
        long delta,
        long balanceAfter,
        string currency,
        CancellationToken cancellationToken)
    {
        await using var ledger = new NpgsqlCommand(
            "INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at) VALUES($1,$2,$3,$4,$5,$6,'settlement.commit',CURRENT_TIMESTAMP)",
            connection,
            transaction);
        ledger.Parameters.AddWithValue(Guid.CreateVersion7());
        ledger.Parameters.AddWithValue(hold.PlayerId);
        ledger.Parameters.AddWithValue(hold.HoldId.ToString("D"));
        ledger.Parameters.AddWithValue(currency);
        ledger.Parameters.AddWithValue(delta);
        ledger.Parameters.AddWithValue(balanceAfter);
        await ledger.ExecuteNonQueryAsync(cancellationToken);
    }
}
