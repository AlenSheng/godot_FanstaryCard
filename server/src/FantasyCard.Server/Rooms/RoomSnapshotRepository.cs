using System.Collections.Concurrent;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Common;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Rooms;

public sealed class RoomSnapshotRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider, ServerMetrics metrics)
{
    private readonly ConcurrentDictionary<Guid, SavedCheckpoint> _lastSaved = new();
    private const string PreparedPolicySql = "COALESCE((SELECT jsonb_object_agg(mp.player_id::text,jsonb_build_object('borrowedTemplateId',p.snapshot_json->'borrowedTemplateId','lootPreferenceElement',p.snapshot_json->'lootPreferenceElement')) FROM match_players mp JOIN preparations p ON p.preparation_id=mp.preparation_id WHERE mp.match_id=m.match_id AND NOT mp.is_bot),'{}'::jsonb)::text";

    public async Task SaveIfDueAsync(BattleRoomSnapshot snapshot, CancellationToken cancellationToken = default)
    {
        var marker = RoomCheckpointPolicy.CreateCriticalMarker(snapshot);
        _lastSaved.TryGetValue(snapshot.RoomId, out var previous);
        if (!RoomCheckpointPolicy.ShouldSave(previous?.Revision, previous?.CriticalMarker, snapshot, marker))
            return;
        await ValidateOwnerAsync(snapshot, cancellationToken);
        var json = JsonSerializer.Serialize(snapshot, SerializerOptions);
        var startedAt = timeProvider.GetTimestamp();
        await using var command = dataSource.CreateCommand(
            """
            INSERT INTO room_snapshots(room_id,revision,snapshot_json,rng_state_json,updated_at) VALUES($1,$2,$3,$4,$5)
            ON CONFLICT(room_id) DO UPDATE SET revision=EXCLUDED.revision,snapshot_json=EXCLUDED.snapshot_json,
                rng_state_json=EXCLUDED.rng_state_json,updated_at=EXCLUDED.updated_at
            WHERE room_snapshots.revision < EXCLUDED.revision
              AND room_snapshots.snapshot_json->>'configVersion'=EXCLUDED.snapshot_json->>'configVersion'
              AND COALESCE(room_snapshots.snapshot_json->'season','null'::jsonb)=COALESCE(EXCLUDED.snapshot_json->'season','null'::jsonb)
            """);
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
        if (await command.ExecuteNonQueryAsync(cancellationToken) == 0)
        {
            var saved = await GetAsync(snapshot.RoomId, cancellationToken)
                ?? throw new InvalidOperationException("The existing room checkpoint disappeared.");
            RequireMatchContext(snapshot, saved.RoomId, saved.ConfigVersion, saved.Season);
        }
        metrics.ObserveRoomSnapshotDuration(timeProvider.GetElapsedTime(startedAt));
        _lastSaved[snapshot.RoomId] = new(snapshot.Revision, marker);
    }

    public async Task<BattleRoomSnapshot?> GetAsync(Guid roomId, CancellationToken cancellationToken = default)
    {
        await using var command = dataSource.CreateCommand($"""
            SELECT s.snapshot_json::text,m.config_version,m.season_id,m.difficulty,m.ruleset_id,m.stats_version,{PreparedPolicySql}
            FROM room_snapshots s LEFT JOIN matches m ON m.room_id=s.room_id WHERE s.room_id=$1
            """);
        command.Parameters.AddWithValue(roomId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        var snapshot = Deserialize(reader.GetString(0));
        if (!reader.IsDBNull(1)) RequireMatchContext(snapshot, roomId, reader.GetString(1), ReadMatchSeason(reader, 1));
        else throw new InvalidOperationException("A room checkpoint requires an owning match.");
        if (snapshot.RoomId != roomId) throw new InvalidOperationException("The checkpoint has another room ID.");
        RequirePreparedSources(snapshot,reader.GetString(6));
        return snapshot;
    }

    public async Task<OwnedTerminalCheckpoint?> GetOwnedTerminalAsync(
        Guid playerId, Guid roomId, Guid matchId, CancellationToken cancellationToken = default)
    {
        // A caller-supplied room ID is never sufficient authority. Match membership
        // and committed terminal state must be established in the same query.
        await using var command = dataSource.CreateCommand(
            $"""
            SELECT m.seed,s.snapshot_json::text,m.config_version,m.season_id,m.difficulty,m.ruleset_id,m.stats_version,{PreparedPolicySql}
            FROM matches m
            JOIN match_players p ON p.match_id=m.match_id AND p.player_id=$1 AND NOT p.is_bot
            JOIN room_snapshots s ON s.room_id=m.room_id
            WHERE m.room_id=$2 AND m.match_id=$3 AND p.state='Settled'
            """);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(roomId);
        command.Parameters.AddWithValue(matchId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        var snapshot = Deserialize(reader.GetString(1));
        RequireMatchContext(snapshot, roomId, reader.GetString(2), ReadMatchSeason(reader, 2));
        RequirePreparedSources(snapshot,reader.GetString(7));
        var player = snapshot.Players.SingleOrDefault(value => value.PlayerId == playerId);
        if (snapshot.RoomId != roomId || player is null || player.IsBot ||
            player.Phase is not (RoomPlayerPhase.Dead or RoomPlayerPhase.Extracted))
            return null;
        return new(snapshot, reader.GetInt32(0));
    }

    public async Task<IReadOnlyList<PersistedRoomSnapshot>> GetRunningAsync(CancellationToken cancellationToken = default)
    {
        await using var command = dataSource.CreateCommand(
            $"""
            SELECT m.match_id,m.seed,s.snapshot_json::text,s.updated_at,
                COALESCE((
                    SELECT jsonb_object_agg(p.player_id::text,COALESCE(settlement.result,'Settled'))
                    FROM match_players p
                    LEFT JOIN match_settlements settlement ON settlement.match_id=p.match_id AND settlement.player_id=p.player_id
                    WHERE p.match_id=m.match_id AND (p.state='Settled' OR settlement.settlement_id IS NOT NULL)
                ),jsonb_build_object())::text,m.room_id,m.config_version,m.season_id,m.difficulty,m.ruleset_id,m.stats_version,{PreparedPolicySql}
            FROM matches m JOIN room_snapshots s ON s.room_id=m.room_id
            WHERE m.status='Running' ORDER BY s.updated_at,m.match_id
            """);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<PersistedRoomSnapshot>();
        while (await reader.ReadAsync(cancellationToken))
        {
            BattleRoomSnapshot? snapshot = null;
            string? readError = null;
            try
            {
                snapshot = Deserialize(reader.GetString(2));
                RequirePreparedSources(snapshot,reader.GetString(11));
            }
            catch (Exception exception) when (exception is JsonException or DomainValidationException or ArgumentException or InvalidOperationException)
            {
                snapshot = null;
                readError = "The persisted room checkpoint could not be read: " + exception.Message;
            }
            var settledPlayers = JsonSerializer.Deserialize<Dictionary<Guid, string>>(reader.GetString(4))
                ?? throw new InvalidOperationException("Persisted room settlement state is invalid.");
            result.Add(new(reader.GetGuid(0), reader.GetInt32(1), snapshot, reader.GetFieldValue<DateTimeOffset>(3), settledPlayers,
                reader.GetString(6), ReadMatchSeason(reader, 6), reader.GetGuid(5), readError));
        }
        return result;
    }

    internal static void RequireMatchContext(BattleRoomSnapshot snapshot, Guid roomId, string configVersion, SeasonContext? season)
    {
        if (snapshot.RoomId != roomId || snapshot.ConfigVersion != configVersion || snapshot.Season != season ||
            snapshot.Season is { } actual && actual.ConfigVersion != snapshot.ConfigVersion)
            throw new InvalidOperationException("Room checkpoint and durable match contexts differ.");
    }

    private async Task ValidateOwnerAsync(BattleRoomSnapshot snapshot, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand($"SELECT config_version,season_id,difficulty,ruleset_id,stats_version,{PreparedPolicySql} FROM matches m WHERE room_id=$1");
        command.Parameters.AddWithValue(snapshot.RoomId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (await reader.ReadAsync(cancellationToken))
        {
            RequireMatchContext(snapshot, snapshot.RoomId, reader.GetString(0), ReadMatchSeason(reader, 0));
            RequirePreparedSources(snapshot,reader.GetString(5));
        }
        else throw new InvalidOperationException("A room checkpoint requires an owning match.");
    }

    private sealed record PreparedSource(string? BorrowedTemplateId, string? LootPreferenceElement);

    private static void RequirePreparedSources(BattleRoomSnapshot snapshot,string json)
    {
        var expected = JsonSerializer.Deserialize<Dictionary<Guid,PreparedSource>>(json,SerializerOptions)
            ?? throw new InvalidOperationException("The durable preparation policy is invalid.");
        foreach (var player in snapshot.Players.Where(player=>!player.IsBot))
        {
            if (expected.GetValueOrDefault(player.PlayerId)?.BorrowedTemplateId != player.BorrowedTemplateId)
                throw new InvalidOperationException("Saved borrowed source differs from the original preparation.");
            if(expected.GetValueOrDefault(player.PlayerId)?.LootPreferenceElement != player.LootPreferenceElement)
                throw new InvalidOperationException("Saved loot preference differs from the original preparation.");
        }
        if (expected.Any(entry=>(entry.Value.BorrowedTemplateId is not null || entry.Value.LootPreferenceElement is not null) && !snapshot.Players.Any(player=>player.PlayerId==entry.Key && !player.IsBot)))
            throw new InvalidOperationException("A participant with a frozen preparation policy is missing from its checkpoint.");
    }

    // Columns are config_version,season_id,difficulty,ruleset_id,stats_version in every owning-match query.
    private static SeasonContext? ReadMatchSeason(NpgsqlDataReader reader, int configIndex) => reader.IsDBNull(configIndex + 1) ? null
        : new SeasonContext(reader.GetString(configIndex + 1), reader.GetString(configIndex + 2)[1] - '0',
            reader.GetString(configIndex + 3), reader.GetString(configIndex), reader.GetString(configIndex + 4));

    private static BattleRoomSnapshot Deserialize(string json) => JsonSerializer.Deserialize<BattleRoomSnapshot>(json, SerializerOptions)
        ?? throw new InvalidOperationException("The room checkpoint is invalid.");

    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        Converters = { new JsonStringEnumConverter() }
    };

    private sealed record SavedCheckpoint(long Revision, string CriticalMarker);
}

public sealed record OwnedTerminalCheckpoint(BattleRoomSnapshot Snapshot, int Seed);

public sealed record PersistedRoomSnapshot(
    Guid MatchId,
    int Seed,
    BattleRoomSnapshot? Snapshot,
    DateTimeOffset SavedAt,
    IReadOnlyDictionary<Guid, string> SettledPlayers,
    string? MatchConfigVersion = null,
    SeasonContext? MatchSeason = null,
    Guid StoredRoomId = default,
    string? ReadError = null)
{
    public Guid RoomId => StoredRoomId != Guid.Empty ? StoredRoomId : Snapshot!.RoomId;
}

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
        snapshot.ConfigVersion,
        snapshot.Season,
        mapInitialized = snapshot.Map is not null,
        players = snapshot.Players.OrderBy(player => player.PlayerId).Select(player => new
        {
            player.PlayerId,
            player.BorrowedTemplateId,
            player.LootPreferenceElement,
            player.BotVictoryReward,
            player.PendingRedEvaluation,player.RedReward,player.PendingRedItem,
            player.Phase,
            player.LastCombatActionSequence,
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
