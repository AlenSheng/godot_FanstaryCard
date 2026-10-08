using System.Collections.Concurrent;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Server.Common;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Rooms;

public sealed class RoomSnapshotRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider, ServerMetrics metrics)
{
    private readonly ConcurrentDictionary<Guid, SavedCheckpoint> _lastSaved = new();

    public async Task SaveIfDueAsync(BattleRoomSnapshot snapshot, CancellationToken cancellationToken = default)
    {
        var marker = RoomCheckpointPolicy.CreateCriticalMarker(snapshot);
        _lastSaved.TryGetValue(snapshot.RoomId, out var previous);
        if (!RoomCheckpointPolicy.ShouldSave(previous?.Revision, previous?.CriticalMarker, snapshot, marker))
            return;
        var json = JsonSerializer.Serialize(snapshot, SerializerOptions);
        var startedAt = timeProvider.GetTimestamp();
        await using var command = dataSource.CreateCommand(
            "INSERT INTO room_snapshots(room_id,revision,snapshot_json,rng_state_json,updated_at) VALUES($1,$2,$3,$4,$5) ON CONFLICT(room_id) DO UPDATE SET revision=EXCLUDED.revision,snapshot_json=EXCLUDED.snapshot_json,rng_state_json=EXCLUDED.rng_state_json,updated_at=EXCLUDED.updated_at WHERE room_snapshots.revision < EXCLUDED.revision");
        command.Parameters.AddWithValue(snapshot.RoomId);
        command.Parameters.AddWithValue(snapshot.Revision);
        command.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Jsonb, Value = json });
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Jsonb,
            Value = JsonSerializer.Serialize(new
            {
                roomRandomState = snapshot.RandomState,
                roomRandomStreams = snapshot.RandomStreams
            })
        });
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await command.ExecuteNonQueryAsync(cancellationToken);
        metrics.ObserveRoomSnapshotDuration(timeProvider.GetElapsedTime(startedAt));
        _lastSaved[snapshot.RoomId] = new(snapshot.Revision, marker);
    }

    public async Task<BattleRoomSnapshot?> GetAsync(Guid roomId, CancellationToken cancellationToken = default)
    {
        await using var command = dataSource.CreateCommand("SELECT snapshot_json::text FROM room_snapshots WHERE room_id=$1");
        command.Parameters.AddWithValue(roomId);
        var value = await command.ExecuteScalarAsync(cancellationToken);
        return value is string json
            ? JsonSerializer.Deserialize<BattleRoomSnapshot>(json, SerializerOptions)
            : null;
    }

    public async Task<IReadOnlyList<PersistedRoomSnapshot>> GetRunningAsync(CancellationToken cancellationToken = default)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT m.match_id,m.seed,s.snapshot_json::text,s.updated_at,
                COALESCE((
                    SELECT jsonb_object_agg(p.player_id::text,COALESCE(settlement.result,'Settled'))
                    FROM match_players p
                    LEFT JOIN match_settlements settlement ON settlement.match_id=p.match_id AND settlement.player_id=p.player_id
                    WHERE p.match_id=m.match_id AND (p.state='Settled' OR settlement.settlement_id IS NOT NULL)
                ),'{}'::jsonb)::text
            FROM matches m JOIN room_snapshots s ON s.room_id=m.room_id
            WHERE m.status='Running' ORDER BY s.updated_at,m.match_id
            """);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<PersistedRoomSnapshot>();
        while (await reader.ReadAsync(cancellationToken))
        {
            var snapshot = JsonSerializer.Deserialize<BattleRoomSnapshot>(reader.GetString(2), SerializerOptions)
                ?? throw new InvalidOperationException("A persisted room snapshot is invalid.");
            var settledPlayers = JsonSerializer.Deserialize<Dictionary<Guid, string>>(reader.GetString(4))
                ?? throw new InvalidOperationException("Persisted room settlement state is invalid.");
            result.Add(new(reader.GetGuid(0), reader.GetInt32(1), snapshot, reader.GetFieldValue<DateTimeOffset>(3), settledPlayers));
        }
        return result;
    }

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    private sealed record SavedCheckpoint(long Revision, string CriticalMarker);
}

public sealed record PersistedRoomSnapshot(
    Guid MatchId,
    int Seed,
    BattleRoomSnapshot Snapshot,
    DateTimeOffset SavedAt,
    IReadOnlyDictionary<Guid, string> SettledPlayers);

public static class RoomCheckpointPolicy
{
    public static bool ShouldSave(
        long? previousRevision,
        string? previousCriticalMarker,
        BattleRoomSnapshot snapshot,
        string? currentCriticalMarker = null) =>
        previousRevision is null ||
        snapshot.Revision - previousRevision >= 10 ||
        !string.Equals(
            previousCriticalMarker,
            currentCriticalMarker ?? CreateCriticalMarker(snapshot),
            StringComparison.Ordinal);

    public static string CreateCriticalMarker(BattleRoomSnapshot snapshot) => JsonSerializer.Serialize(new
    {
        mapInitialized = snapshot.Map is not null,
        players = snapshot.Players.OrderBy(player => player.PlayerId).Select(player => new
        {
            player.PlayerId,
            player.Phase,
            player.CurrentDuelId,
            player.Position,
            pveBattleId = player.Pve?.BattleId,
            extracting = player.ExtractionRemaining > TimeSpan.Zero,
            spring = player.SpringDrink is null ? null : new { player.SpringDrink.Position },
            disconnected = player.DisconnectedRemaining > TimeSpan.Zero,
            reward = player.RewardChoice is null ? null : new
            {
                player.RewardChoice.RefreshCount,
                optionIds = player.RewardChoice.Options.Select(option => option.OptionId).ToArray()
            },
            pendingReplacement = player.Inventory?.PendingReplacement?.Token,
            inventoryItems = player.Inventory?.Items.OrderBy(item => item.SlotIndex),
            safeSlots = player.Inventory?.SafeSlotIndexes,
            wornArmor = player.WornArmor?.OrderBy(item => item.ItemId),
            recycledEquipment = player.RecycledEquipment?.OrderBy(item => item.ItemId),
            clearedCells = player.ClearedCells?.OrderBy(position => position.Row).ThenBy(position => position.Column),
            consumedSprings = player.ConsumedSprings?.OrderBy(position => position.Row).ThenBy(position => position.Column)
        }),
        duels = snapshot.Duels.OrderBy(duel => duel.DuelId).Select(duel => new
        {
            duel.DuelId,
            leaveRequests = duel.LeaveRequests?.Order().ToArray(),
            escapingPlayer = duel.EscapeAttempt?.PlayerId
        }),
        relicPiles = snapshot.RelicPiles?.OrderBy(pile => pile.PileId).Select(pile => new
        {
            pile.PileId,
            pile.Version,
            itemIds = pile.Items.Select(item => item.ItemId).Order().ToArray()
        })
    });
}
