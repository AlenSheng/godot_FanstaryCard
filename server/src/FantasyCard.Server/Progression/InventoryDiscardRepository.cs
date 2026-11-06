using System.Text.Json;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Progression;

public sealed partial class ProgressionRepository
{
    /// <summary>Discard only explicitly versioned warehouse items; retain bodies and a durable receipt, without refunds.</summary>
    public async Task<DiscardEquipmentResponse> DiscardEquipmentAsync(Guid playerId, string requestId,
        DiscardEquipmentRequest request, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(requestId) || requestId.Length > 80 || requestId.Any(char.IsControl))
            throw new DomainValidationException("The discard request identity is invalid.");
        if (request.Items is null || request.Items.Count is < 1 or > 50 ||
            request.Items.Any(x => x is null || x.EquipmentId == Guid.Empty || x.ExpectedVersion < 0) ||
            request.Items.Select(x => x.EquipmentId).Distinct().Count() != request.Items.Count)
            throw new DomainValidationException("Select one to fifty distinct equipment items with their current versions.");
        var requested = request.Items.OrderBy(x => x.EquipmentId).ToArray();
        var hash = HashIdempotentRequest("equipment.discard", request with { Items = requested });
        await using var connection = await dataSource.OpenConnectionAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(ct);
        await LockPlayerAsync(connection, transaction, playerId, ct);
        await using (var replay = new NpgsqlCommand(
            "SELECT request_hash,response_json::text FROM inventory_discard_batches WHERE player_id=$1 AND request_id=$2", connection, transaction))
        {
            replay.Parameters.AddWithValue(playerId); replay.Parameters.AddWithValue(requestId);
            await using var reader = await replay.ExecuteReaderAsync(ct);
            if (await reader.ReadAsync(ct))
            {
                if (reader.GetString(0) != hash) throw new IdempotencyConflictException();
                var response = JsonSerializer.Deserialize<DiscardEquipmentResponse>(reader.GetString(1))!;
                await reader.DisposeAsync();
                await transaction.CommitAsync(ct);
                return response;
            }
        }

        var clock = timeProvider ?? TimeProvider.System;
        var schedule = await new SeasonRepository(dataSource, clock).GetScheduleAsync(ct);
        var season = schedule.Current;
        if (season is null && !schedule.LegacyAllowed || request.SeasonId != season?.SeasonId)
            throw new DomainValidationException("The inventory season changed or closed. Reload and retry.");
        var before = new List<EquipmentResponse>();
        foreach (var selected in requested)
        {
            var item = await ReadEnhancementEquipmentAsync(connection, transaction, playerId, selected.EquipmentId, true, ct)
                ?? throw new DomainValidationException("Equipment was not found.");
            var sameRealm = season is null ? item.SeasonId is null && item.AssetScope is null
                : item.SeasonId == season.SeasonId && item.AssetScope == "ActiveSeason" && item.StatsVersion == season.StatsVersion;
            if (item.Version != selected.ExpectedVersion || item.Location != "Inventory" || !sameRealm ||
                item.SourceKind is "BotReward" or "Borrowed")
                throw new DomainValidationException("Equipment changed, is reserved, or belongs to another season. Reload and retry.");
            before.Add(item);
        }
        await using (var loadouts = new NpgsqlCommand("""
            SELECT EXISTS(SELECT 1 FROM player_loadouts WHERE player_id=$1 AND
                (head_id=ANY($2) OR chest_id=ANY($2) OR hands_id=ANY($2) OR legs_id=ANY($2) OR feet_id=ANY($2)))
            """, connection, transaction))
        {
            loadouts.Parameters.AddWithValue(playerId);
            loadouts.Parameters.AddWithValue(NpgsqlDbType.Array | NpgsqlDbType.Uuid, requested.Select(x => x.EquipmentId).ToArray());
            if ((bool)(await loadouts.ExecuteScalarAsync(ct))!)
                throw new DomainValidationException("Remove equipment from every saved loadout before discarding it.");
        }
        var after = before.Select(x => x with { Location = "Recycled", Version = checked(x.Version + 1) }).ToArray();
        foreach (var item in after)
        {
            await using var update = new NpgsqlCommand(
                "UPDATE equipments SET location='Recycled',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='Inventory' AND version=$3", connection, transaction);
            update.Parameters.AddWithValue(item.InstanceId); update.Parameters.AddWithValue(playerId); update.Parameters.AddWithValue(item.Version - 1);
            if (await update.ExecuteNonQueryAsync(ct) != 1) throw new DomainValidationException("Equipment changed. Reload and retry.");
            await WriteInventoryMovementAsync(connection, transaction, playerId, item.InstanceId,
                "Inventory", "Recycled", "equipment.discard", ct, requestId, season?.SeasonId);
        }
        var now = clock.GetUtcNow();
        if (season is not null && !season.Contains(now) || season is null && schedule.Next is { } next && now >= next.StartsAtUtc)
            throw new DomainValidationException("The inventory season changed during discard. Reload and retry.");
        var result = new DiscardEquipmentResponse(after, season?.SeasonId);
        await using (var receipt = new NpgsqlCommand("""
            INSERT INTO inventory_discard_batches(batch_id,player_id,request_id,request_hash,season_id,before_items,response_json,created_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8)
            """, connection, transaction))
        {
            receipt.Parameters.AddWithValue(Guid.CreateVersion7()); receipt.Parameters.AddWithValue(playerId);
            receipt.Parameters.AddWithValue(requestId); receipt.Parameters.AddWithValue(hash);
            receipt.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)season?.SeasonId ?? DBNull.Value);
            receipt.Parameters.AddWithValue(NpgsqlDbType.Jsonb, JsonSerializer.Serialize(before));
            receipt.Parameters.AddWithValue(NpgsqlDbType.Jsonb, JsonSerializer.Serialize(result)); receipt.Parameters.AddWithValue(now);
            await receipt.ExecuteNonQueryAsync(ct);
        }
        await transaction.CommitAsync(ct);
        return result;
    }
}
