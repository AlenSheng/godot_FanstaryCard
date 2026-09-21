using System.Text.Json;
using System.Globalization;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Domain.Bots;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Common;
using FantasyCard.Server.Persistence;
using Npgsql;

namespace FantasyCard.Server.Matchmaking;

public sealed record MatchAssignment(Guid MatchId, Guid RoomId, int Seed, IReadOnlyList<MatchPlayerAssignment> Players);
public sealed record PendingMatch(Guid MatchId, Guid RoomId, DateTimeOffset ReadyDeadline, IReadOnlyList<Guid> PlayerIds);
public sealed record ReadyLobbyView(Guid MatchId, Guid RoomId, DateTimeOffset ReadyDeadline, int ReadyPlayers, int RequiredPlayers, bool IsReady);
public sealed record ReadyMatchLaunch(MatchAssignment Assignment, IReadOnlyList<Guid> HumanPlayerIds, IReadOnlyList<Guid> RemovedPlayerIds);

public sealed class MatchReadyException(string code, string message) : InvalidOperationException(message)
{
    public string Code { get; } = code;
}
public sealed record MatchPlayerAssignment(
    Guid PlayerId,
    bool IsBot,
    HeroClass HeroClass,
    IReadOnlyList<string> CardIds,
    int InventoryCapacity = 20,
    int SafeSlots = 0,
    int PotionCount = 0,
    IReadOnlyList<Guid>? EquipmentIds = null,
    int WeaponLevel = 0,
    IReadOnlyList<CombatEquipmentItem>? Equipment = null,
    IReadOnlyList<int>? CardLevels = null,
    IReadOnlyList<int>? SafeSlotIndexes = null,
    string? DisplayName = null);

public sealed class MatchmakingRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider, ServerMetrics metrics, IConfiguration? configuration = null)
{
    private readonly TimeSpan botFillDelay = TimeSpan.FromSeconds(Math.Max(0,
        configuration?.GetValue<int?>("Matchmaking:BotFillDelaySeconds") ?? 30));
    private static readonly JsonSerializerOptions SnapshotSerializerOptions = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public async Task<MatchTicketResponse> GetTicketAsync(Guid playerId, Guid ticketId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT t.ticket_id,t.preparation_id,t.status,t.queued_at,mp.match_id FROM match_tickets t LEFT JOIN match_players mp ON mp.player_id=t.player_id AND mp.preparation_id=t.preparation_id WHERE t.ticket_id=$1 AND t.player_id=$2");
        command.Parameters.AddWithValue(ticketId);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            throw new InvalidOperationException("Match ticket was not found.");
        return new MatchTicketResponse(
            reader.GetGuid(0), reader.GetGuid(1), reader.GetString(2),
            reader.GetFieldValue<DateTimeOffset>(3), reader.IsDBNull(4) ? null : reader.GetGuid(4));
    }

    public async Task<MatchTicketResponse> EnqueueAsync(Guid playerId, string requestId, EnqueueMatchRequest request, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var now = timeProvider.GetUtcNow();
        await PreparationRepository.ExpireStaleAsync(
            connection, transaction, playerId, now, cancellationToken);
        await using (var replay = new NpgsqlCommand("SELECT ticket_id,preparation_id,status,queued_at,(SELECT match_id FROM match_players WHERE player_id=$1 LIMIT 1) FROM match_tickets WHERE player_id=$1 AND request_id=$2", connection, transaction))
        {
            replay.Parameters.AddWithValue(playerId); replay.Parameters.AddWithValue(requestId);
            await using var reader = await replay.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                if (reader.GetGuid(1) != request.PreparationId)
                    throw new IdempotencyConflictException();
                var result = new MatchTicketResponse(reader.GetGuid(0), reader.GetGuid(1), reader.GetString(2), reader.GetFieldValue<DateTimeOffset>(3), reader.IsDBNull(4) ? null : reader.GetGuid(4));
                await reader.DisposeAsync(); await transaction.CommitAsync(cancellationToken); return result;
            }
        }
        await using (var preparation = new NpgsqlCommand("SELECT status FROM preparations WHERE preparation_id=$1 AND player_id=$2 FOR UPDATE", connection, transaction))
        {
            preparation.Parameters.AddWithValue(request.PreparationId); preparation.Parameters.AddWithValue(playerId);
            var status = (string?)await preparation.ExecuteScalarAsync(cancellationToken);
            if (status != "Active")
            {
                await transaction.CommitAsync(cancellationToken);
                throw new InvalidOperationException("Only an Active preparation can enter matchmaking.");
            }
        }
        var ticketId = Guid.CreateVersion7();
        await using (var insert = new NpgsqlCommand("INSERT INTO match_tickets(ticket_id,player_id,preparation_id,request_id,status,queued_at) VALUES($1,$2,$3,$4,'Queued',$5)", connection, transaction))
        { insert.Parameters.AddWithValue(ticketId); insert.Parameters.AddWithValue(playerId); insert.Parameters.AddWithValue(request.PreparationId); insert.Parameters.AddWithValue(requestId); insert.Parameters.AddWithValue(now); await insert.ExecuteNonQueryAsync(cancellationToken); }
        await using (var update = new NpgsqlCommand("UPDATE preparations SET status='Queued' WHERE preparation_id=$1", connection, transaction)) { update.Parameters.AddWithValue(request.PreparationId); await update.ExecuteNonQueryAsync(cancellationToken); }
        await transaction.CommitAsync(cancellationToken);
        return new MatchTicketResponse(ticketId, request.PreparationId, "Queued", now, null);
    }

    public async Task CancelAsync(Guid playerId, Guid ticketId, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var now = timeProvider.GetUtcNow();
        var requestHash = PersistentIdempotency.Hash(new { ticketId });
        var replay = await PersistentIdempotency.ReadAsync<IdempotencyAcknowledgement>(
            connection, transaction, playerId, "matchmaking.cancel", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return;
        }
        await using var update = new NpgsqlCommand("UPDATE match_tickets SET status='Cancelled' WHERE ticket_id=$1 AND player_id=$2 AND status IN ('Queued','Cancelled') RETURNING preparation_id", connection, transaction);
        update.Parameters.AddWithValue(ticketId); update.Parameters.AddWithValue(playerId);
        var preparation = await update.ExecuteScalarAsync(cancellationToken);
        if (preparation is null) throw new InvalidOperationException("Match ticket is not queued or does not belong to the player.");
        await using var prep = new NpgsqlCommand("UPDATE preparations SET status='Cancelled' WHERE preparation_id=$1 AND player_id=$2 AND status='Queued'", connection, transaction);
        prep.Parameters.AddWithValue((Guid)preparation); prep.Parameters.AddWithValue(playerId); await prep.ExecuteNonQueryAsync(cancellationToken);
        await PreparationRepository.ReleaseEquipmentAsync(
            connection, transaction, (Guid)preparation, requestId, cancellationToken);
        await PersistentIdempotency.WriteAsync(
            connection, transaction, playerId, "matchmaking.cancel", requestId, requestHash,
            new IdempotencyAcknowledgement(), now, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public async Task<PendingMatch?> TryCreateMatchAsync(CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        var now = timeProvider.GetUtcNow();
        await ExpireQueuedPreparationsAsync(connection, transaction, now, cancellationToken);
        var tickets = new List<(Guid Ticket, Guid Player, Guid Preparation, DateTimeOffset Queued, HeroClass HeroClass, string[] Cards, int Capacity, int SafeSlots, int Potions, Guid[] EquipmentIds, int WeaponLevel, CombatEquipmentItem[] Equipment)>();
        await using (var query = new NpgsqlCommand("SELECT t.ticket_id,t.player_id,t.preparation_id,t.queued_at,p.snapshot_json->>'heroClass',p.snapshot_json->'cardIds',p.snapshot_json->>'backpackCapacity',jsonb_array_length(p.snapshot_json->'safeSlotIndexes'),p.snapshot_json->>'potionCount',p.snapshot_json->'equipmentIds',p.snapshot_json->>'classWeaponLevel',p.snapshot_json->'equipmentSnapshots' FROM match_tickets t JOIN preparations p ON p.preparation_id=t.preparation_id WHERE t.status='Queued' ORDER BY t.queued_at LIMIT 4 FOR UPDATE OF t SKIP LOCKED", connection, transaction))
        {
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
            {
                if (!Enum.TryParse<HeroClass>(reader.GetString(4), true, out var heroClass)) continue;
                var cards = JsonSerializer.Deserialize<string[]>(reader.GetString(5)) ?? [];
                var equipmentIds = JsonSerializer.Deserialize<Guid?[]>(reader.GetString(9))?.Where(id => id.HasValue).Select(id => id!.Value).ToArray() ?? [];
                var equipmentSnapshots = reader.IsDBNull(11)
                    ? []
                    : JsonSerializer.Deserialize<PreparationEquipmentSnapshotResponse[]>(reader.GetString(11), SnapshotSerializerOptions) ?? [];
                var equipment = equipmentSnapshots.Select(item => new CombatEquipmentItem(
                    item.InstanceId,
                    item.Slot,
                    item.Quality,
                    item.Level,
                    Enum.Parse<CardElement>(item.Element, true),
                    item.EffectAffix,
                    item.SecondaryTrait)).ToArray();
                tickets.Add((reader.GetGuid(0), reader.GetGuid(1), reader.GetGuid(2), reader.GetFieldValue<DateTimeOffset>(3), heroClass, cards, int.Parse(reader.GetString(6), CultureInfo.InvariantCulture), reader.GetInt32(7), int.Parse(reader.GetString(8), CultureInfo.InvariantCulture), equipmentIds, int.Parse(reader.GetString(10), CultureInfo.InvariantCulture), equipment));
            }
        }
        if (tickets.Count == 0 || (tickets.Count < 4 && now - tickets[0].Queued < botFillDelay))
        {
            await transaction.CommitAsync(cancellationToken);
            return null;
        }
        var matchId = Guid.CreateVersion7(); var roomId = Guid.CreateVersion7(); var seed = Random.Shared.Next();
        var readyDeadline = now.AddSeconds(15);
        await using (var insert = new NpgsqlCommand("INSERT INTO matches(match_id,room_id,mode,difficulty,seed,config_version,status,created_at,ready_deadline) VALUES($1,$2,'ChaosRealm','Standard',$3,$4,'Starting',$5,$6)", connection, transaction))
        { insert.Parameters.AddWithValue(matchId); insert.Parameters.AddWithValue(roomId); insert.Parameters.AddWithValue(seed); insert.Parameters.AddWithValue(BootstrapRepository.CurrentConfigVersion); insert.Parameters.AddWithValue(now); insert.Parameters.AddWithValue(readyDeadline); await insert.ExecuteNonQueryAsync(cancellationToken); }
        foreach (var ticket in tickets)
        {
            await using (var player = new NpgsqlCommand("INSERT INTO match_players(match_id,player_id,preparation_id,is_bot) VALUES($1,$2,$3,false)", connection, transaction))
            { player.Parameters.AddWithValue(matchId); player.Parameters.AddWithValue(ticket.Player); player.Parameters.AddWithValue(ticket.Preparation); await player.ExecuteNonQueryAsync(cancellationToken); }
            await using (var ticketUpdate = new NpgsqlCommand("UPDATE match_tickets SET status='Matched',matched_at=$1 WHERE ticket_id=$2", connection, transaction))
            { ticketUpdate.Parameters.AddWithValue(now); ticketUpdate.Parameters.AddWithValue(ticket.Ticket); await ticketUpdate.ExecuteNonQueryAsync(cancellationToken); }
            await using (var preparationUpdate = new NpgsqlCommand("UPDATE preparations SET status='Matched' WHERE preparation_id=$1", connection, transaction))
            { preparationUpdate.Parameters.AddWithValue(ticket.Preparation); await preparationUpdate.ExecuteNonQueryAsync(cancellationToken); }
        }
        await transaction.CommitAsync(cancellationToken);
        foreach (var ticket in tickets)
            metrics.ObserveMatchmakingQueueDuration(now - ticket.Queued);
        return new PendingMatch(matchId, roomId, readyDeadline, tickets.Select(ticket => ticket.Player).ToArray());
    }

    public async Task<ReadyLobbyView?> GetReadyLobbyAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT m.match_id,m.room_id,m.ready_deadline,
                   count(*) FILTER (WHERE p.state='Ready'),count(*),mine.state
            FROM matches m
            JOIN match_players mine ON mine.match_id=m.match_id AND mine.player_id=$1 AND mine.is_bot=false
            JOIN match_players p ON p.match_id=m.match_id AND p.is_bot=false AND p.state IN ('Assigned','Ready')
            WHERE m.status='Starting'
            GROUP BY m.match_id,m.room_id,m.ready_deadline,m.created_at,mine.state
            ORDER BY m.created_at DESC
            LIMIT 1
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        var matchId = reader.GetGuid(0);
        var roomId = reader.GetGuid(1);
        var deadline = reader.GetFieldValue<DateTimeOffset>(2);
        var ready = checked((int)reader.GetInt64(3));
        var required = checked((int)reader.GetInt64(4));
        return new(matchId, roomId, deadline, ready, required, reader.GetString(5) == "Ready");
    }

    public async Task<ReadyLobbyView> MarkReadyAsync(Guid playerId, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        Guid matchId;
        Guid roomId;
        DateTimeOffset deadline;
        string playerState;
        await using (var query = new NpgsqlCommand(
            """
            SELECT m.match_id,m.room_id,m.ready_deadline,mp.state
            FROM matches m JOIN match_players mp ON mp.match_id=m.match_id
            WHERE mp.player_id=$1 AND mp.is_bot=false AND m.status='Starting'
            ORDER BY m.created_at DESC LIMIT 1 FOR UPDATE OF m,mp
            """, connection, transaction))
        {
            query.Parameters.AddWithValue(playerId);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
                throw new MatchReadyException("READY_NOT_FOUND", "The player has no pending ready lobby.");
            matchId = reader.GetGuid(0); roomId = reader.GetGuid(1);
            deadline = reader.GetFieldValue<DateTimeOffset>(2); playerState = reader.GetString(3);
        }
        if (now >= deadline || playerState == "Removed")
            throw new MatchReadyException("READY_TIMEOUT", "The ready deadline has passed.");
        if (playerState == "Assigned")
        {
            await using var update = new NpgsqlCommand("UPDATE match_players SET state='Ready' WHERE match_id=$1 AND player_id=$2 AND state='Assigned'", connection, transaction);
            update.Parameters.AddWithValue(matchId); update.Parameters.AddWithValue(playerId);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }
        await using var count = new NpgsqlCommand("SELECT count(*) FILTER (WHERE state='Ready'),count(*) FROM match_players WHERE match_id=$1 AND is_bot=false AND state IN ('Assigned','Ready')", connection, transaction);
        count.Parameters.AddWithValue(matchId);
        await using var counts = await count.ExecuteReaderAsync(cancellationToken);
        await counts.ReadAsync(cancellationToken);
        var ready = checked((int)counts.GetInt64(0)); var required = checked((int)counts.GetInt64(1));
        await counts.DisposeAsync();
        await transaction.CommitAsync(cancellationToken);
        return new(matchId, roomId, deadline, ready, required, true);
    }

    public async Task<ReadyMatchLaunch?> ClaimReadyMatchAsync(DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        Guid matchId = Guid.Empty; Guid roomId = Guid.Empty; int seed = 0; bool firstClaim = false;
        var hasRow = false;
        await using (var query = new NpgsqlCommand(
            """
            SELECT m.match_id,m.room_id,m.seed,m.status
            FROM matches m
            WHERE m.status='Launching' OR (m.status='Starting' AND
                (m.ready_deadline <= $1 OR NOT EXISTS (
                    SELECT 1 FROM match_players p WHERE p.match_id=m.match_id AND p.is_bot=false AND p.state='Assigned')))
            ORDER BY m.created_at LIMIT 1 FOR UPDATE SKIP LOCKED
            """, connection, transaction))
        {
            query.Parameters.AddWithValue(now);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            hasRow = await reader.ReadAsync(cancellationToken);
            if (hasRow)
            {
                matchId = reader.GetGuid(0); roomId = reader.GetGuid(1); seed = reader.GetInt32(2);
                firstClaim = reader.GetString(3) == "Starting";
            }
        }

        // 空结果路径：reader 必须先释放再提交事务（Npgsql 在打开的 reader 上提交会抛
        // "A command is already in progress"，毒化连接池并阻塞整个 ready 协调器——2026-09-08 遭遇战联调发现）
        if (!hasRow)
        {
            await transaction.CommitAsync(cancellationToken);
            return null;
        }

        Guid[] removed = [];
        Guid[] removedPreparations = [];
        if (firstClaim)
        {
            await using (var removedQuery = new NpgsqlCommand("SELECT player_id,preparation_id FROM match_players WHERE match_id=$1 AND is_bot=false AND state='Assigned'", connection, transaction))
            {
                removedQuery.Parameters.AddWithValue(matchId);
                await using var reader = await removedQuery.ExecuteReaderAsync(cancellationToken);
                var ids = new List<Guid>(); var preparationIds = new List<Guid>();
                while (await reader.ReadAsync(cancellationToken))
                {
                    ids.Add(reader.GetGuid(0));
                    if (!reader.IsDBNull(1)) preparationIds.Add(reader.GetGuid(1));
                }
                removed = [.. ids];
                removedPreparations = [.. preparationIds];
            }
            await using (var cancel = new NpgsqlCommand("UPDATE preparations p SET status='Cancelled' FROM match_players mp WHERE mp.match_id=$1 AND mp.player_id=p.player_id AND mp.preparation_id=p.preparation_id AND mp.is_bot=false AND mp.state='Assigned' AND p.status='Matched'", connection, transaction))
            { cancel.Parameters.AddWithValue(matchId); await cancel.ExecuteNonQueryAsync(cancellationToken); }
            foreach (var preparationId in removedPreparations)
                await PreparationRepository.ReleaseEquipmentAsync(
                    connection, transaction, preparationId, null, cancellationToken);
            await using (var states = new NpgsqlCommand("UPDATE match_players SET state=CASE WHEN state='Ready' THEN 'Active' ELSE 'Removed' END WHERE match_id=$1 AND is_bot=false AND state IN ('Assigned','Ready')", connection, transaction))
            { states.Parameters.AddWithValue(matchId); await states.ExecuteNonQueryAsync(cancellationToken); }
        }

        var humans = await ReadActiveHumansAsync(connection, transaction, matchId, cancellationToken);
        if (firstClaim)
            await ReserveMatchAssetsAsync(connection, transaction, matchId, cancellationToken);
        var botIds = new List<Guid>();
        await using (var existingBots = new NpgsqlCommand("SELECT player_id FROM match_players WHERE match_id=$1 AND is_bot=true ORDER BY player_id", connection, transaction))
        {
            existingBots.Parameters.AddWithValue(matchId);
            await using var reader = await existingBots.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken)) botIds.Add(reader.GetGuid(0));
        }
        while (humans.Count + botIds.Count < 4) botIds.Add(Guid.CreateVersion7());
        botIds.Sort();
        if (firstClaim)
        {
            foreach (var botId in botIds)
            {
                await using var insertBot = new NpgsqlCommand("INSERT INTO match_players(match_id,player_id,is_bot,state) VALUES($1,$2,true,'Active') ON CONFLICT DO NOTHING", connection, transaction);
                insertBot.Parameters.AddWithValue(matchId); insertBot.Parameters.AddWithValue(botId);
                await insertBot.ExecuteNonQueryAsync(cancellationToken);
            }
            await using var launching = new NpgsqlCommand("UPDATE matches SET status='Launching' WHERE match_id=$1 AND status='Starting'", connection, transaction);
            launching.Parameters.AddWithValue(matchId); await launching.ExecuteNonQueryAsync(cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
        var players = CompleteWithBots(humans, botIds, seed);
        return new(new(matchId, roomId, seed, players), humans.Select(player => player.PlayerId).ToArray(), removed);
    }

    public async Task MarkRunningAsync(Guid matchId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand("UPDATE matches SET status='Running' WHERE match_id=$1 AND status='Launching'");
        command.Parameters.AddWithValue(matchId);
        if (await command.ExecuteNonQueryAsync(cancellationToken) != 1)
            throw new InvalidOperationException("The launching match could not transition to Running.");
    }

    private static async Task<List<MatchPlayerAssignment>> ReadActiveHumansAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, Guid matchId, CancellationToken cancellationToken)
    {
        var result = new List<MatchPlayerAssignment>();
        await using var command = new NpgsqlCommand("SELECT mp.player_id,p.snapshot_json->>'heroClass',p.snapshot_json->'cardIds',p.snapshot_json->>'backpackCapacity',jsonb_array_length(p.snapshot_json->'safeSlotIndexes'),p.snapshot_json->>'potionCount',p.snapshot_json->'equipmentIds',p.snapshot_json->>'classWeaponLevel',p.snapshot_json->'equipmentSnapshots',p.snapshot_json->'cardLevels',p.snapshot_json->'safeSlotIndexes',u.display_name FROM match_players mp JOIN preparations p ON p.preparation_id=mp.preparation_id JOIN players u ON u.user_id=mp.player_id WHERE mp.match_id=$1 AND mp.is_bot=false AND mp.state='Active' ORDER BY mp.player_id", connection, transaction);
        command.Parameters.AddWithValue(matchId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var heroClass = Enum.Parse<HeroClass>(reader.GetString(1), true);
            var equipmentIds = JsonSerializer.Deserialize<Guid?[]>(reader.GetString(6))?.Where(id => id.HasValue).Select(id => id!.Value).ToArray() ?? [];
            var equipmentSnapshots = reader.IsDBNull(8) ? [] : JsonSerializer.Deserialize<PreparationEquipmentSnapshotResponse[]>(reader.GetString(8), SnapshotSerializerOptions) ?? [];
            var equipment = equipmentSnapshots.Select(item => new CombatEquipmentItem(item.InstanceId, item.Slot, item.Quality, item.Level, Enum.Parse<CardElement>(item.Element, true), item.EffectAffix, item.SecondaryTrait)).ToArray();
            var cardLevels = reader.IsDBNull(9) ? null : JsonSerializer.Deserialize<int[]>(reader.GetString(9));
            var safeSlotIndexes = JsonSerializer.Deserialize<int[]>(reader.GetString(10));
            result.Add(new(reader.GetGuid(0), false, heroClass, JsonSerializer.Deserialize<string[]>(reader.GetString(2)) ?? [], int.Parse(reader.GetString(3), CultureInfo.InvariantCulture), reader.GetInt32(4), int.Parse(reader.GetString(5), CultureInfo.InvariantCulture), equipmentIds, int.Parse(reader.GetString(7), CultureInfo.InvariantCulture), equipment, cardLevels, safeSlotIndexes, reader.GetString(11)));
        }
        return result;
    }

    private static async Task ReserveMatchAssetsAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid matchId,
        CancellationToken cancellationToken)
    {
        var assets = new List<(Guid PlayerId, string Type, string Id, int Quantity)>();
        await using (var command = new NpgsqlCommand(
            """
            SELECT mp.player_id,pa.asset_type,pa.asset_id,pa.quantity
            FROM match_players mp
            JOIN preparation_assets pa ON pa.preparation_id=mp.preparation_id
            WHERE mp.match_id=$1 AND mp.is_bot=false AND mp.state='Active'
            ORDER BY mp.player_id,pa.asset_type,pa.asset_id
            """, connection, transaction))
        {
            command.Parameters.AddWithValue(matchId);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                assets.Add((reader.GetGuid(0), reader.GetString(1), reader.GetString(2), reader.GetInt32(3)));
        }

        foreach (var playerId in assets.Select(asset => asset.PlayerId).Distinct().Order())
        {
            await using var playerLock = new NpgsqlCommand(
                "SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction);
            playerLock.Parameters.AddWithValue(playerId);
            if (await playerLock.ExecuteScalarAsync(cancellationToken) is null)
                throw new InvalidOperationException("The matched player is missing.");
        }

        foreach (var asset in assets)
        {
            if (asset.Type == "Equipment")
            {
                if (!Guid.TryParse(asset.Id, out var equipmentId))
                    throw new InvalidOperationException("Preparation equipment id is invalid.");
                await using var equipment = new NpgsqlCommand(
                    "UPDATE equipments SET location='InMatchEquipped',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='PreparationLocked'",
                    connection, transaction);
                equipment.Parameters.AddWithValue(equipmentId);
                equipment.Parameters.AddWithValue(asset.PlayerId);
                if (await equipment.ExecuteNonQueryAsync(cancellationToken) != 1)
                    throw new InvalidOperationException("Prepared equipment is no longer available for the match.");
                await using var movement = new NpgsqlCommand(
                    "INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at) VALUES($1,$2,$3,'PreparationLocked','InMatchEquipped','match.start',$4,CURRENT_TIMESTAMP)",
                    connection, transaction);
                movement.Parameters.AddWithValue(Guid.CreateVersion7());
                movement.Parameters.AddWithValue(asset.PlayerId);
                movement.Parameters.AddWithValue(equipmentId);
                movement.Parameters.AddWithValue(matchId.ToString("D"));
                await movement.ExecuteNonQueryAsync(cancellationToken);
                continue;
            }

            if (asset.Type == "Backpack" && asset.Id is "Advanced" or "Top")
                continue;
            var column = asset.Type == "Consumable" && asset.Id == "health_potion"
                ? "health_potion_count"
                : throw new InvalidOperationException("Preparation contains an unsupported reserved asset.");
            await using var consumable = new NpgsqlCommand(
                $"UPDATE player_consumables SET {column}={column}-$1,version=version+1 WHERE player_id=$2 AND {column}>=$1",
                connection, transaction);
            consumable.Parameters.AddWithValue(asset.Quantity);
            consumable.Parameters.AddWithValue(asset.PlayerId);
            if (await consumable.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("Prepared consumables are no longer available for the match.");
        }
    }

    internal static IReadOnlyList<MatchPlayerAssignment> CompleteWithBots(IReadOnlyList<MatchPlayerAssignment> humans, IReadOnlyList<Guid> botIds, int seed)
    {
        var assignments = humans.ToList();
        var random = new Random(seed);
        var averageWeaponLevel = BotRules.AverageWeaponEnhance(new PartyWearSnapshot([], humans.Select(player => player.WeaponLevel).ToArray()));
        foreach (var botId in botIds)
        {
            var represented = Enum.GetValues<HeroClass>().Select(heroClass => (HeroClass: heroClass, Count: assignments.Count(player => player.HeroClass == heroClass))).GroupBy(value => value.Count).OrderBy(group => group.Key).First().Select(value => value.HeroClass).OrderBy(_ => random.Next()).First();
            var displayName = BotRules.PickDisplayName(assignments.Select(player => player.DisplayName).OfType<string>().ToArray(), random.Next());
            assignments.Add(new(botId, true, represented, DefaultCards(represented), PotionCount: BotRules.StartingPotions, WeaponLevel: averageWeaponLevel, DisplayName: displayName));
        }
        if (assignments.Count != 4) throw new InvalidOperationException("A ready match must launch with exactly four players.");
        return assignments;
    }

    private static string[] DefaultCards(HeroClass heroClass) => Enumerable.Range(1, 13).Select(i => $"common-{i:D2}").Concat(Enumerable.Range(1, 7).Select(i => $"{heroClass.ToString().ToLowerInvariant()}-{i:D2}")).ToArray();
    private static async Task ExpireQueuedPreparationsAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, DateTimeOffset now, CancellationToken cancellationToken)
    {
        var expiring = new List<Guid>();
        await using (var query = new NpgsqlCommand(
            "SELECT preparation_id FROM preparations WHERE status='Queued' AND expires_at <= $1 FOR UPDATE",
            connection, transaction))
        {
            query.Parameters.AddWithValue(now);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken)) expiring.Add(reader.GetGuid(0));
        }
        foreach (var preparationId in expiring)
            await PreparationRepository.ReleaseEquipmentAsync(
                connection, transaction, preparationId, null, cancellationToken);
        await using (var tickets = new NpgsqlCommand("UPDATE match_tickets AS t SET status='Cancelled' FROM preparations AS p WHERE t.preparation_id=p.preparation_id AND t.status='Queued' AND p.status='Queued' AND p.expires_at <= $1", connection, transaction))
        {
            tickets.Parameters.AddWithValue(now);
            await tickets.ExecuteNonQueryAsync(cancellationToken);
        }
        await using var preparations = new NpgsqlCommand("UPDATE preparations SET status='Expired' WHERE status='Queued' AND expires_at <= $1", connection, transaction);
        preparations.Parameters.AddWithValue(now);
        await preparations.ExecuteNonQueryAsync(cancellationToken);
    }
    private static async Task LockPlayerAsync(NpgsqlConnection c, NpgsqlTransaction t, Guid id, CancellationToken ct) { await using var cmd = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", c, t); cmd.Parameters.AddWithValue(id); if (await cmd.ExecuteScalarAsync(ct) is null) throw new InvalidOperationException("Player was not found."); }
}
