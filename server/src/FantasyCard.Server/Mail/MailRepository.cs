using FantasyCard.Contracts.Http;
using FantasyCard.Server.ProtobufHttp;
using System.Text.Json;
using FantasyCard.Contracts.Mail;
using FantasyCard.Server.Common;
using Npgsql;

namespace FantasyCard.Server.Mail;

public sealed class MailRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider)
{
    public async Task<MailListResponse> GetAsync(Guid playerId, CancellationToken cancellationToken, int limit = 200, int offset = 0)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT mail_id,title,body,sender,sent_at,expires_at,read_at,claimed_at,attachments_json::text,title_en,body_en
            FROM mail_messages
            WHERE player_id=$1 AND (expires_at IS NULL OR expires_at > $2)
            ORDER BY sent_at DESC,mail_id DESC LIMIT $3 OFFSET $4
            """);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        command.Parameters.AddWithValue(limit);
        command.Parameters.AddWithValue(offset);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var items = new List<MailItemResponse>();
        while (await reader.ReadAsync(cancellationToken))
        {
            items.Add(new MailItemResponse(
                reader.GetGuid(0),
                reader.GetString(1),
                reader.GetString(2),
                reader.GetString(3),
                reader.GetFieldValue<DateTimeOffset>(4),
                reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5),
                !reader.IsDBNull(6),
                !reader.IsDBNull(7),
                ReadAttachments(reader.GetString(8)),
                reader.GetString(9),
                reader.GetString(10)));
        }

        await reader.DisposeAsync();
        await using var unread = dataSource.CreateCommand("SELECT COUNT(*) FROM mail_messages WHERE player_id=$1 AND read_at IS NULL AND (expires_at IS NULL OR expires_at > $2)");
        unread.Parameters.AddWithValue(playerId);
        unread.Parameters.AddWithValue(timeProvider.GetUtcNow());
        var unreadCount = checked((int)(long)(await unread.ExecuteScalarAsync(cancellationToken))!);
        return new MailListResponse(items, unreadCount);
    }

    public async Task<bool> MarkReadAsync(Guid playerId, Guid mailId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "UPDATE mail_messages SET read_at=COALESCE(read_at,$1),version=version+1 WHERE mail_id=$2 AND player_id=$3");
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        command.Parameters.AddWithValue(mailId);
        command.Parameters.AddWithValue(playerId);
        return await command.ExecuteNonQueryAsync(cancellationToken) != 0;
    }

    public async Task<int> MarkAllReadAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "UPDATE mail_messages SET read_at=$1,version=version+1 WHERE player_id=$2 AND read_at IS NULL");
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        command.Parameters.AddWithValue(playerId);
        return await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<MailClaimResponse?> ClaimAsync(Guid playerId, Guid mailId, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        var requestHash = PersistentIdempotency.Hash(new { mailId });
        var now = timeProvider.GetUtcNow();
        await using var query = new NpgsqlCommand(
            "SELECT attachments_json::text,claimed_at FROM mail_messages WHERE mail_id=$1 AND player_id=$2 AND (expires_at IS NULL OR expires_at > $3) FOR UPDATE",
            connection, transaction);
        query.Parameters.AddWithValue(mailId);
        query.Parameters.AddWithValue(playerId);
        query.Parameters.AddWithValue(now);
        await using var reader = await query.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        var payload = reader.GetString(0);
        var alreadyClaimed = !reader.IsDBNull(1);
        await reader.DisposeAsync();

        var replay = await PersistentIdempotency.ReadAsync<MailClaimResponse>(
            connection, transaction, playerId, "mail.claim", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            GameResponseBudget.EnsureFits("MailClaimResponse", replay);
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }

        if (alreadyClaimed)
        {
            await transaction.CommitAsync(cancellationToken);
            return new MailClaimResponse(mailId, true, Array.Empty<MailAttachmentResponse>());
        }

        var attachments = ReadAttachments(payload);
        var response = new MailClaimResponse(mailId, false, attachments);
        GameResponseBudget.EnsureFits("MailClaimResponse", response);
        foreach (var attachment in attachments)
            await GrantAsync(connection, transaction, playerId, attachment, requestId, cancellationToken);

        await using var update = new NpgsqlCommand(
            "UPDATE mail_messages SET claimed_at=$1,read_at=COALESCE(read_at,$1),version=version+1 WHERE mail_id=$2 AND player_id=$3",
            connection, transaction);
        update.Parameters.AddWithValue(now);
        update.Parameters.AddWithValue(mailId);
        update.Parameters.AddWithValue(playerId);
        await update.ExecuteNonQueryAsync(cancellationToken);
        await PersistentIdempotency.WriteAsync(
            connection, transaction, playerId, "mail.claim", requestId, requestHash, response, now, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return response;
    }

    public async Task<MailClaimAllResponse> ClaimAllAsync(Guid playerId, string requestId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        var now = timeProvider.GetUtcNow();
        await using (var playerLock = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction))
        {
            playerLock.Parameters.AddWithValue(playerId);
            if (await playerLock.ExecuteScalarAsync(cancellationToken) is null)
                throw new InvalidOperationException("Player is missing.");
        }

        var requestHash = PersistentIdempotency.Hash(new { operation = "claim-all" });
        var replay = await PersistentIdempotency.ReadAsync<MailClaimAllResponse>(
            connection, transaction, playerId, "mail.claim-all", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            GameResponseBudget.EnsureFits("MailClaimAllResponse", replay);
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }

        var pending = new List<(Guid Id, string Payload)>();
        await using (var query = new NpgsqlCommand(
            "SELECT mail_id,attachments_json::text FROM mail_messages WHERE player_id=$1 AND claimed_at IS NULL AND (expires_at IS NULL OR expires_at > $2) ORDER BY sent_at,mail_id LIMIT 4097 FOR UPDATE",
            connection, transaction))
        {
            query.Parameters.AddWithValue(playerId);
            query.Parameters.AddWithValue(now);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                pending.Add((reader.GetGuid(0), reader.GetString(1)));
        }

        if (pending.Count > HttpProtocolRegistry.MaximumCollectionItems)
            throw new BadHttpRequestException("Too many pending mails for one claim-all response. Claim individual mails first.", 413);
        var claims = pending.Select(mail => new MailClaimResponse(mail.Id, false, ReadAttachments(mail.Payload))).ToList();
        var attachmentCount = claims.Sum(claim => claim.Granted.Count);
        var response = new MailClaimAllResponse(pending.Count, attachmentCount, claims);
        GameResponseBudget.EnsureFits("MailClaimAllResponse", response);
        foreach (var claim in claims)
        {
            foreach (var attachment in claim.Granted)
                await GrantAsync(connection, transaction, playerId, attachment, requestId, cancellationToken);
            await using var update = new NpgsqlCommand(
                "UPDATE mail_messages SET claimed_at=$1,read_at=COALESCE(read_at,$1),version=version+1 WHERE mail_id=$2 AND player_id=$3",
                connection, transaction);
            update.Parameters.AddWithValue(now);
            update.Parameters.AddWithValue(claim.MailId);
            update.Parameters.AddWithValue(playerId);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }

        await PersistentIdempotency.WriteAsync(
            connection, transaction, playerId, "mail.claim-all", requestId, requestHash, response, now, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return response;
    }

    public async Task<bool> DeleteAsync(Guid playerId, Guid mailId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "DELETE FROM mail_messages WHERE mail_id=$1 AND player_id=$2 AND read_at IS NOT NULL AND (claimed_at IS NOT NULL OR attachments_json = '[]'::jsonb)");
        command.Parameters.AddWithValue(mailId);
        command.Parameters.AddWithValue(playerId);
        return await command.ExecuteNonQueryAsync(cancellationToken) != 0;
    }

    public async Task<int> DeleteReadAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "DELETE FROM mail_messages WHERE player_id=$1 AND read_at IS NOT NULL AND (claimed_at IS NOT NULL OR attachments_json = '[]'::jsonb)");
        command.Parameters.AddWithValue(playerId);
        return await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static List<MailAttachmentResponse> ReadAttachments(string json)
    {
        using var document = JsonDocument.Parse(json);
        if (document.RootElement.ValueKind != JsonValueKind.Array)
            throw new InvalidOperationException("Mail attachments must be an array.");
        var result = new List<MailAttachmentResponse>();
        foreach (var element in document.RootElement.EnumerateArray())
        {
            if (!element.TryGetProperty("kind", out var kindElement))
                throw new InvalidOperationException("Mail attachment kind is required.");
            var kind = kindElement.GetString();
            if (string.IsNullOrWhiteSpace(kind)) throw new InvalidOperationException("Mail attachment kind is invalid.");
            var amount = element.TryGetProperty("amount", out var amountElement) ? amountElement.GetInt64() : 1;
            if (amount <= 0) throw new InvalidOperationException("Mail attachment amount must be positive.");
            result.Add(new MailAttachmentResponse(
                kind,
                amount,
                element.TryGetProperty("itemId", out var item) ? item.GetString() : null,
                element.TryGetProperty("heroClass", out var hero) ? hero.GetString() : null,
                element.TryGetProperty("effectAffix", out var effectAffix) ? effectAffix.GetString() : null,
                element.TryGetProperty("secondaryTrait", out var secondaryTrait) ? secondaryTrait.GetString() : null));
        }
        return result;
    }

    private static async Task GrantAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        MailAttachmentResponse attachment,
        string requestId,
        CancellationToken cancellationToken)
    {
        var kind = attachment.Kind.Trim();
        if (kind is "Gold" or "Diamond")
        {
            var column = kind == "Gold" ? "gold" : "diamond";
            await using var wallet = new NpgsqlCommand($"UPDATE player_wallets SET {column}={column}+$1,version=version+1 WHERE player_id=$2", connection, transaction);
            wallet.Parameters.AddWithValue(attachment.Amount);
            wallet.Parameters.AddWithValue(playerId);
            if (await wallet.ExecuteNonQueryAsync(cancellationToken) != 1) throw new InvalidOperationException("Player wallet is missing.");
            return;
        }

        var materialColumn = kind switch
        {
            "WarriorSoul" => "warrior_soul",
            "PriestSoul" => "priest_soul",
            "MageSoul" => "mage_soul",
            "GuardianSoul" => "guardian_soul",
            "EquipmentFragments" => "equipment_fragments",
            _ => null
        };
        if (materialColumn is not null)
        {
            await using var materials = new NpgsqlCommand($"UPDATE player_materials SET {materialColumn}={materialColumn}+$1,version=version+1 WHERE player_id=$2", connection, transaction);
            materials.Parameters.AddWithValue(attachment.Amount);
            materials.Parameters.AddWithValue(playerId);
            if (await materials.ExecuteNonQueryAsync(cancellationToken) != 1) throw new InvalidOperationException("Player materials are missing.");
            return;
        }

        var consumableColumn = kind switch
        {
            "HealthPotion" => "health_potion_count",
            "AdvancedBag" => "advanced_bag_count",
            "TopBag" => "top_bag_count",
            _ => null
        };
        if (consumableColumn is not null)
        {
            await using var consumables = new NpgsqlCommand($"UPDATE player_consumables SET {consumableColumn}={consumableColumn}+$1,version=version+1 WHERE player_id=$2", connection, transaction);
            consumables.Parameters.AddWithValue(checked((int)attachment.Amount));
            consumables.Parameters.AddWithValue(playerId);
            if (await consumables.ExecuteNonQueryAsync(cancellationToken) != 1) throw new InvalidOperationException("Player consumables are missing.");
            return;
        }

        if (kind == "Card")
        {
            if (string.IsNullOrWhiteSpace(attachment.ItemId)) throw new InvalidOperationException("Card attachment itemId is required.");
            await using var card = new NpgsqlCommand("UPDATE player_cards SET copy_count=1,unlocked=true,version=version + CASE WHEN unlocked AND copy_count=1 THEN 0 ELSE 1 END WHERE player_id=$1 AND card_id=$2", connection, transaction);
            card.Parameters.AddWithValue(playerId);
            card.Parameters.AddWithValue(attachment.ItemId);
            if (await card.ExecuteNonQueryAsync(cancellationToken) != 1) throw new InvalidOperationException("Card attachment references an unavailable card.");
            return;
        }

        if (kind == "Equipment")
        {
            var parts = (attachment.ItemId ?? string.Empty).Split('|', 3, StringSplitOptions.TrimEntries);
            if (parts.Length != 3 || parts.Any(string.IsNullOrWhiteSpace))
                throw new InvalidOperationException("Equipment attachment itemId must be quality|element|slot.");
            if (attachment.EffectAffix is not (null or "Piercing" or "Bulwark" or "Vitality"))
                throw new InvalidOperationException("Equipment attachment effectAffix is invalid.");
            if (attachment.SecondaryTrait is not (null or "DrawInterval" or "ForcedEscape"))
                throw new InvalidOperationException("Equipment attachment secondaryTrait is invalid.");
            if (attachment.SecondaryTrait == "ForcedEscape" && parts[2] != "Feet")
                throw new InvalidOperationException("ForcedEscape is only valid for Feet equipment.");
            if (parts[0] is "White" or "Green" or "Blue" && attachment.EffectAffix is not null)
                throw new InvalidOperationException("Low-quality equipment cannot have an effectAffix.");
            var equipmentId = Guid.CreateVersion7();
            await using var equipment = new NpgsqlCommand(
                "INSERT INTO equipments(instance_id,owner_id,slot,quality,level,is_bound,location,version,created_at,element,effect_affix,secondary_trait) VALUES($1,$2,$3,$4,0,false,'Inventory',1,now(),$5,$6,$7)",
                connection, transaction);
            equipment.Parameters.AddWithValue(equipmentId);
            equipment.Parameters.AddWithValue(playerId);
            equipment.Parameters.AddWithValue(parts[2]);
            equipment.Parameters.AddWithValue(parts[0]);
            equipment.Parameters.AddWithValue(parts[1]);
            equipment.Parameters.AddWithValue((object?)attachment.EffectAffix ?? DBNull.Value);
            equipment.Parameters.AddWithValue((object?)attachment.SecondaryTrait ?? DBNull.Value);
            await equipment.ExecuteNonQueryAsync(cancellationToken);
            return;
        }

        throw new InvalidOperationException($"Unsupported mail attachment kind '{kind}'.");
    }
}
