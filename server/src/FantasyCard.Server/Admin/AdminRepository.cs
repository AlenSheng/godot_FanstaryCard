using System.Text.Json;
using Npgsql;
using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Admin;

public sealed record AdminPlayer(Guid UserId, string DisplayName, short? SelectedClass, DateTimeOffset CreatedAt,
    string? Provider, string? Account, bool IsBanned, string? BanReason, long Gold, long Diamond,
    long WarriorSoul, long PriestSoul, long MageSoul, long GuardianSoul, long EquipmentFragments,
    int HealthPotion, int AdvancedBag, int TopBag, int EquipmentCount);

public sealed record AdminMailRequest(Guid PlayerId, string Title, string Body, IReadOnlyList<AdminAttachment> Attachments);
public sealed record AdminAttachment(string Kind, long Amount, string? ItemId);
public sealed record AdminRevokeRequest(Guid PlayerId, string Kind, long Amount, string? ItemId, string Reason);
public sealed record AdminBanRequest(Guid PlayerId, string Reason);
public sealed record AdminMessageRequest(Guid PlayerId, string Title, string Body);
public sealed record AdminEquipment(Guid InstanceId, string Slot, string Quality, string? Element, int Level);

public sealed class AdminRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider, ConnectionRegistry connections)
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private static readonly Dictionary<string, (string Table, string Column)> Balances = new(StringComparer.Ordinal)
    {
        ["Gold"] = ("player_wallets", "gold"), ["Diamond"] = ("player_wallets", "diamond"),
        ["WarriorSoul"] = ("player_materials", "warrior_soul"),
        ["PriestSoul"] = ("player_materials", "priest_soul"),
        ["MageSoul"] = ("player_materials", "mage_soul"),
        ["GuardianSoul"] = ("player_materials", "guardian_soul"),
        ["EquipmentFragments"] = ("player_materials", "equipment_fragments"),
        ["HealthPotion"] = ("player_consumables", "health_potion_count"),
        ["AdvancedBag"] = ("player_consumables", "advanced_bag_count"),
        ["TopBag"] = ("player_consumables", "top_bag_count")
    };

    public static bool ValidGrant(AdminAttachment item)
    {
        if (string.IsNullOrWhiteSpace(item.Kind)) return false;
        if (item.Amount is < 1 or > 1_000_000) return false;
        if (Balances.ContainsKey(item.Kind))
            return item.ItemId is null && (item.Kind is not ("HealthPotion" or "AdvancedBag" or "TopBag") || item.Amount <= 10000);
        if (item.Kind != "Equipment" || item.Amount != 1 || item.ItemId is null) return false;
        var parts = item.ItemId.Split('|');
        return parts.Length == 3 &&
            parts[0] is "White" or "Green" or "Blue" or "Purple" or "Orange" or "Red" &&
            parts[1] is "Fire" or "Water" or "Wood" or "Earth" or "Metal" &&
            parts[2] is "Head" or "Chest" or "Hands" or "Legs" or "Feet";
    }

    public async Task<IReadOnlyList<AdminPlayer>> FindPlayersAsync(string query, CancellationToken cancellationToken)
    {
        var isUid = Guid.TryParse(query, out var uid);
        await using var command = dataSource.CreateCommand(
            """
            SELECT p.user_id,p.display_name,p.selected_class,p.created_at,i.provider,i.external_subject,
                   b.reason,w.gold,w.diamond,m.warrior_soul,m.priest_soul,m.mage_soul,m.guardian_soul,
                   m.equipment_fragments,c.health_potion_count,c.advanced_bag_count,c.top_bag_count,
                   (SELECT count(*)::integer FROM equipments e WHERE e.owner_id=p.user_id AND e.location='Inventory')
            FROM players p
            LEFT JOIN external_identities i ON i.player_id=p.user_id
            LEFT JOIN player_bans b ON b.player_id=p.user_id
            JOIN player_wallets w ON w.player_id=p.user_id
            JOIN player_materials m ON m.player_id=p.user_id
            JOIN player_consumables c ON c.player_id=p.user_id
            WHERE ($1::uuid IS NOT NULL AND p.user_id=$1)
               OR (lower(p.display_name)=lower($2) OR i.external_subject=$2)
            ORDER BY p.created_at DESC LIMIT 20
            """);
        command.Parameters.AddWithValue((object?) (isUid ? uid : null) ?? DBNull.Value);
        command.Parameters.AddWithValue(query);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<AdminPlayer>();
        while (await reader.ReadAsync(cancellationToken))
            result.Add(new AdminPlayer(reader.GetGuid(0), reader.GetString(1), reader.IsDBNull(2) ? null : reader.GetInt16(2),
                reader.GetFieldValue<DateTimeOffset>(3), reader.IsDBNull(4) ? null : reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5), !reader.IsDBNull(6), reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.GetInt64(7), reader.GetInt64(8), reader.GetInt64(9), reader.GetInt64(10), reader.GetInt64(11),
                reader.GetInt64(12), reader.GetInt64(13), reader.GetInt32(14), reader.GetInt32(15), reader.GetInt32(16), reader.GetInt32(17)));
        return result;
    }

    public async Task<IReadOnlyList<AdminEquipment>> GetInventoryEquipmentAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT instance_id,slot,quality,element,level FROM equipments WHERE owner_id=$1 AND location='Inventory' ORDER BY created_at DESC LIMIT 100");
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<AdminEquipment>();
        while (await reader.ReadAsync(cancellationToken))
            result.Add(new AdminEquipment(reader.GetGuid(0), reader.GetString(1), reader.GetString(2),
                reader.IsDBNull(3) ? null : reader.GetString(3), reader.GetInt32(4)));
        return result;
    }

    public async Task<Guid?> SendMailAsync(AdminMailRequest request, string operation, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        if (!await LockPlayerAsync(connection, transaction, request.PlayerId, cancellationToken)) return null;
        if (await RequestExistsAsync(connection, transaction, requestId, cancellationToken)) throw new AdminConflictException();
        var mailId = await InsertMailAsync(connection, transaction, request.PlayerId, request.Title, request.Body,
            request.Attachments, cancellationToken);
        await AuditAsync(connection, transaction, operation, request.PlayerId, new { mailId, request.Title, request.Body, request.Attachments },
            requestId, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return mailId;
    }

    public async Task<bool?> SetBanAsync(Guid playerId, string? reason, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        if (!await LockPlayerAsync(connection, transaction, playerId, cancellationToken)) return null;
        if (await RequestExistsAsync(connection, transaction, requestId, cancellationToken)) throw new AdminConflictException();
        await using (var command = new NpgsqlCommand(reason is null
            ? "DELETE FROM player_bans WHERE player_id=$1"
            : "INSERT INTO player_bans(player_id,reason,banned_at,banned_by) VALUES($1,$2,$3,'admin-key') ON CONFLICT(player_id) DO UPDATE SET reason=excluded.reason,banned_at=excluded.banned_at,banned_by=excluded.banned_by",
            connection, transaction))
        {
            command.Parameters.AddWithValue(playerId);
            if (reason is not null)
            {
                command.Parameters.AddWithValue(reason);
                command.Parameters.AddWithValue(timeProvider.GetUtcNow());
            }
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
        if (reason is not null)
        {
            await using var sessions = new NpgsqlCommand("DELETE FROM player_sessions WHERE player_id=$1", connection, transaction);
            sessions.Parameters.AddWithValue(playerId);
            await sessions.ExecuteNonQueryAsync(cancellationToken);
        }
        await AuditAsync(connection, transaction, reason is null ? "unban" : "ban", playerId, new { reason }, requestId, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        if (reason is not null) connections.Disconnect(playerId);
        return true;
    }

    public async Task<bool?> RevokeAsync(AdminRevokeRequest request, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        if (!await LockPlayerAsync(connection, transaction, request.PlayerId, cancellationToken)) return null;
        if (await RequestExistsAsync(connection, transaction, requestId, cancellationToken)) throw new AdminConflictException();
        int changed;
        if (Balances.TryGetValue(request.Kind, out var balance))
        {
            await using var command = new NpgsqlCommand(
                $"UPDATE {balance.Table} SET {balance.Column}={balance.Column}-$1,version=version+1 WHERE player_id=$2 AND {balance.Column}>=$1 RETURNING {balance.Column}",
                connection, transaction);
            command.Parameters.AddWithValue(balance.Table == "player_consumables" ? checked((int)request.Amount) : request.Amount);
            command.Parameters.AddWithValue(request.PlayerId);
            var remaining = await command.ExecuteScalarAsync(cancellationToken);
            changed = remaining is null ? 0 : 1;
            if (remaining is not null && balance.Table != "player_consumables")
            {
                await using var ledger = new NpgsqlCommand(
                    "INSERT INTO economy_ledger(ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at) VALUES($1,$2,$3,$4,$5,$6,'admin_revoke',$7)",
                    connection, transaction);
                ledger.Parameters.AddWithValue(Guid.CreateVersion7());
                ledger.Parameters.AddWithValue(request.PlayerId);
                ledger.Parameters.AddWithValue(requestId);
                ledger.Parameters.AddWithValue(request.Kind is "PriestSoul" or "MageSoul" or "GuardianSoul" ? "ClassSoul" : request.Kind);
                ledger.Parameters.AddWithValue(-request.Amount);
                ledger.Parameters.AddWithValue((long)remaining);
                ledger.Parameters.AddWithValue(timeProvider.GetUtcNow());
                await ledger.ExecuteNonQueryAsync(cancellationToken);
            }
        }
        else if (request.Kind == "Equipment" && Guid.TryParse(request.ItemId, out var equipmentId))
        {
            await using var command = new NpgsqlCommand(
                "UPDATE equipments SET location='EnhanceMaterialConsumed',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='Inventory'", connection, transaction);
            command.Parameters.AddWithValue(equipmentId);
            command.Parameters.AddWithValue(request.PlayerId);
            changed = await command.ExecuteNonQueryAsync(cancellationToken);
            if (changed == 1)
            {
                await using var movement = new NpgsqlCommand(
                    "INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at) VALUES($1,$2,$3,'Inventory','EnhanceMaterialConsumed','admin_revoke',$4,$5)",
                    connection, transaction);
                movement.Parameters.AddWithValue(Guid.CreateVersion7());
                movement.Parameters.AddWithValue(request.PlayerId);
                movement.Parameters.AddWithValue(equipmentId);
                movement.Parameters.AddWithValue(requestId);
                movement.Parameters.AddWithValue(timeProvider.GetUtcNow());
                await movement.ExecuteNonQueryAsync(cancellationToken);
            }
        }
        else throw new ArgumentException("Unsupported item kind or item ID.");
        if (changed != 1) throw new AdminConflictException("Insufficient balance or equipment is unavailable in inventory.");
        await InsertMailAsync(connection, transaction, request.PlayerId, "道具收回通知",
            $"管理员收回：{request.Kind} × {request.Amount}。原因：{request.Reason}", [], cancellationToken);
        await AuditAsync(connection, transaction, "revoke", request.PlayerId, request, requestId, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return true;
    }

    private async Task<Guid> InsertMailAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId,
        string title, string body, IReadOnlyList<AdminAttachment> attachments, CancellationToken cancellationToken)
    {
        var id = Guid.CreateVersion7();
        await using var command = new NpgsqlCommand(
            "INSERT INTO mail_messages(mail_id,player_id,title,body,sender,attachments_json,sent_at) VALUES($1,$2,$3,$4,'Game Admin',$5::jsonb,$6)",
            connection, transaction);
        command.Parameters.AddWithValue(id);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(title);
        command.Parameters.AddWithValue(body);
        command.Parameters.AddWithValue(JsonSerializer.Serialize(attachments, Json));
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await command.ExecuteNonQueryAsync(cancellationToken);
        return id;
    }

    private static async Task<bool> LockPlayerAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("SELECT 1 FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction);
        command.Parameters.AddWithValue(playerId);
        return await command.ExecuteScalarAsync(cancellationToken) is not null;
    }

    private static async Task<bool> RequestExistsAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        string requestId, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("SELECT 1 FROM admin_audit WHERE request_id=$1", connection, transaction);
        command.Parameters.AddWithValue(requestId);
        return await command.ExecuteScalarAsync(cancellationToken) is not null;
    }

    private async Task AuditAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, string action, Guid playerId,
        object details, string requestId, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "INSERT INTO admin_audit(audit_id,actor,action,player_id,details_json,request_id,created_at) VALUES($1,'admin-key',$2,$3,$4::jsonb,$5,$6)",
            connection, transaction);
        command.Parameters.AddWithValue(Guid.CreateVersion7());
        command.Parameters.AddWithValue(action);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(JsonSerializer.Serialize(details, Json));
        command.Parameters.AddWithValue(requestId);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}

public sealed class AdminConflictException(string message = "Operation already applied or conflicts with current data.") : Exception(message);
