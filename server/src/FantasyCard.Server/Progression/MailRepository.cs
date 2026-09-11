using System.Text.Json;
using Npgsql;

namespace FantasyCard.Server.Progression;

public sealed class MailRepository(NpgsqlDataSource dataSource)
{
    public async Task<IReadOnlyList<object>> ListAsync(Guid playerId, CancellationToken ct)
    {
        var result = new List<object>();
        await using var command = dataSource.CreateCommand("SELECT mail_id,title,body,attachments,is_read,claimed_at,created_at FROM player_mail WHERE player_id=$1 AND (expires_at IS NULL OR expires_at>now()) ORDER BY created_at DESC");
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(ct);
        while (await reader.ReadAsync(ct)) result.Add(new { mailId=reader.GetGuid(0), title=reader.GetString(1), body=reader.GetString(2), attachments=reader.GetFieldValue<JsonDocument>(3), isRead=reader.GetBoolean(4), claimed= !reader.IsDBNull(5), createdAt=reader.GetDateTime(6) });
        return result;
    }
    public async Task<bool> ClaimAsync(Guid playerId, Guid mailId, CancellationToken ct)
    {
        await using var connection = await dataSource.OpenConnectionAsync(ct);
        await using var transaction = await connection.BeginTransactionAsync(ct);
        await using var read = new NpgsqlCommand("SELECT attachments FROM player_mail WHERE mail_id=$1 AND player_id=$2 AND claimed_at IS NULL FOR UPDATE", connection, transaction);
        read.Parameters.AddWithValue(mailId); read.Parameters.AddWithValue(playerId);
        var raw = await read.ExecuteScalarAsync(ct);
        if (raw is null) return false;
        var attachments = JsonDocument.Parse(raw.ToString()!);
        await using var wallet = new NpgsqlCommand("UPDATE player_wallets SET gold=gold+$1, diamond=diamond+$2, version=version+1 WHERE player_id=$3", connection, transaction);
        wallet.Parameters.AddWithValue(attachments.RootElement.TryGetProperty("gold", out var gold) ? gold.GetInt64() : 0L);
        wallet.Parameters.AddWithValue(attachments.RootElement.TryGetProperty("diamond", out var diamond) ? diamond.GetInt64() : 0L); wallet.Parameters.AddWithValue(playerId); await wallet.ExecuteNonQueryAsync(ct);
        await using var materials = new NpgsqlCommand("UPDATE player_materials SET warrior_soul=warrior_soul+$1, priest_soul=priest_soul+$2, mage_soul=mage_soul+$3, guardian_soul=guardian_soul+$4, equipment_fragments=equipment_fragments+$5, version=version+1 WHERE player_id=$6", connection, transaction);
        var names = new[] { "warriorSoul", "priestSoul", "mageSoul", "guardianSoul", "equipmentFragments" }; for (var i=0;i<names.Length;i++) materials.Parameters.AddWithValue(attachments.RootElement.TryGetProperty(names[i], out var value) ? value.GetInt64() : 0L); materials.Parameters.AddWithValue(playerId); await materials.ExecuteNonQueryAsync(ct);
        if (attachments.RootElement.TryGetProperty("equipmentQualities", out var qualities)) { var slots = new[] { "Head", "Chest", "Hands", "Legs", "Feet" }; var index = 0; foreach (var quality in qualities.EnumerateArray())
        { await using var equipment = new NpgsqlCommand("INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at) VALUES ($1,$2,$3,$4,0,true,'Inventory',1,now())", connection, transaction); equipment.Parameters.AddWithValue(Guid.NewGuid()); equipment.Parameters.AddWithValue(playerId); equipment.Parameters.AddWithValue(slots[index++ % slots.Length]); equipment.Parameters.AddWithValue(quality.GetString()!); await equipment.ExecuteNonQueryAsync(ct); } }
        await using var claim = new NpgsqlCommand("UPDATE player_mail SET is_read=true,claimed_at=now() WHERE mail_id=$1 AND player_id=$2", connection, transaction); claim.Parameters.AddWithValue(mailId); claim.Parameters.AddWithValue(playerId); await claim.ExecuteNonQueryAsync(ct); await transaction.CommitAsync(ct); return true;
    }
}
