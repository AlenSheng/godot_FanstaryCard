using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using Npgsql;

namespace FantasyCard.Server.Progression;

public enum SaveDeckStatus
{
    Updated,
    VersionConflict,
    NotFound
}

public sealed record SaveDeckResult(SaveDeckStatus Status, DeckResponse? Deck = null);

public enum SaveLoadoutStatus { Updated, VersionConflict, NotFound, AssetUnavailable }
public sealed record SaveLoadoutResult(SaveLoadoutStatus Status, LoadoutResponse? Loadout = null, string? Detail = null);

public sealed partial class ProgressionRepository(NpgsqlDataSource dataSource)
{
    private static readonly string[] EquipmentSlots = ["Head", "Chest", "Hands", "Legs", "Feet"];

    public async Task<InventoryResponse> GetInventoryAsync(Guid playerId, CancellationToken cancellationToken)
    {
        var items = new List<EquipmentResponse>();
        await using (var command = dataSource.CreateCommand(
            """
            SELECT instance_id, slot, quality, level, is_bound, location, version,
                   element, effect_affix, secondary_trait
            FROM equipments
            WHERE owner_id = $1 AND location IN ('Inventory', 'Equipped')
            ORDER BY CASE location WHEN 'Equipped' THEN 0 ELSE 1 END, created_at, instance_id
            """))
        {
            command.Parameters.AddWithValue(playerId);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                items.Add(ReadEquipment(reader));
        }

        InventoryConsumablesResponse consumables;
        await using (var command = dataSource.CreateCommand(
            """
            SELECT health_potion_count, advanced_bag_count, top_bag_count
            FROM player_consumables WHERE player_id = $1
            """))
        {
            command.Parameters.AddWithValue(playerId);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
                throw new InvalidOperationException("The player consumables aggregate is missing.");
            consumables = new InventoryConsumablesResponse(
                reader.GetInt32(0), reader.GetInt32(1), reader.GetInt32(2));
        }

        var inventoryEquipmentCount = items.Count(item => item.Location == "Inventory");
        return new InventoryResponse(
            new InventorySummaryResponse(50, inventoryEquipmentCount, Math.Max(0, 50 - inventoryEquipmentCount)),
            items,
            consumables);
    }

    public async Task<LoadoutResponse?> GetLoadoutAsync(
        Guid playerId,
        HeroClass heroClass,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT head_id, chest_id, hands_id, legs_id, feet_id, version
            FROM player_loadouts
            WHERE player_id = $1 AND hero_class = $2
            """);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue((short)heroClass);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        return new LoadoutResponse(
            (HeroClassDto)(short)heroClass,
            Enumerable.Range(0, 5)
                .Select(index => reader.IsDBNull(index) ? null : (Guid?)reader.GetGuid(index))
                .ToArray(),
            reader.GetInt64(5));
    }

    public async Task<SaveLoadoutResult> SaveLoadoutAsync(
        Guid playerId, HeroClass heroClass, IReadOnlyList<Guid?> equipmentIds,
        string requestId, long expectedVersion, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var lockPlayer = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id = $1 FOR UPDATE", connection, transaction);
        lockPlayer.Parameters.AddWithValue(playerId);
        if (await lockPlayer.ExecuteScalarAsync(cancellationToken) is null) return new(SaveLoadoutStatus.NotFound);
        var requestHash = HashIdempotentRequest(heroClass, new { equipmentIds, expectedVersion });
        var replay = await ReadIdempotentResultAsync<SaveLoadoutResult>(
            connection, transaction, playerId, "loadout.save", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }

        long version;
        await using (var current = new NpgsqlCommand(
            "SELECT version FROM player_loadouts WHERE player_id = $1 AND hero_class = $2 FOR UPDATE", connection, transaction))
        {
            current.Parameters.AddWithValue(playerId); current.Parameters.AddWithValue((short)heroClass);
            var value = await current.ExecuteScalarAsync(cancellationToken);
            if (value is null) return new(SaveLoadoutStatus.NotFound);
            version = (long)value;
        }
        if (version != expectedVersion) return new(SaveLoadoutStatus.VersionConflict);

        var selected = equipmentIds.Where(id => id.HasValue).Select(id => id!.Value).ToArray();
        if (selected.Distinct().Count() != selected.Length)
            throw new DomainValidationException("An equipment item cannot occupy multiple slots.");
        var highQualityCount = 0;
        for (var index = 0; index < equipmentIds.Count; index++)
        {
            if (equipmentIds[index] is not { } id) continue;
            await using var item = new NpgsqlCommand(
                "SELECT slot, location, is_bound, quality FROM equipments WHERE instance_id = $1 AND owner_id = $2 FOR UPDATE", connection, transaction);
            item.Parameters.AddWithValue(id); item.Parameters.AddWithValue(playerId);
            await using var reader = await item.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken)) return new(SaveLoadoutStatus.AssetUnavailable, Detail: "Equipment is not owned.");
            var slot = reader.GetString(0); var location = reader.GetString(1);
            if (!string.Equals(slot, EquipmentSlots[index], StringComparison.Ordinal) ||
                location is not ("Inventory" or "Equipped"))
                return new(SaveLoadoutStatus.AssetUnavailable, Detail: "Equipment is in the wrong slot or unavailable.");
            if (reader.GetString(3) is "Orange" or "Red") highQualityCount++;
        }
        if (highQualityCount > 1)
            return new(SaveLoadoutStatus.AssetUnavailable, Detail: "A loadout can contain at most one Orange or Red armor item.");

        var currentlyEquipped = new HashSet<Guid>();
        await using (var currentEquipment = new NpgsqlCommand(
            "SELECT instance_id FROM equipments WHERE owner_id=$1 AND location='Equipped' FOR UPDATE",
            connection,
            transaction))
        {
            currentEquipment.Parameters.AddWithValue(playerId);
            await using var reader = await currentEquipment.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken)) currentlyEquipped.Add(reader.GetGuid(0));
        }
        var selectedSet = selected.ToHashSet();
        foreach (var id in currentlyEquipped.Except(selectedSet))
        {
            await using var unequip = new NpgsqlCommand(
                "UPDATE equipments SET location='Inventory',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='Equipped'",
                connection,
                transaction);
            unequip.Parameters.AddWithValue(id);
            unequip.Parameters.AddWithValue(playerId);
            if (await unequip.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("Equipped item changed while saving the loadout.");
            await WriteInventoryMovementAsync(
                connection, transaction, playerId, id, "Equipped", "Inventory", "loadout.save", cancellationToken);
        }
        foreach (var id in selectedSet.Except(currentlyEquipped))
        {
            await using var equip = new NpgsqlCommand(
                "UPDATE equipments SET location='Equipped',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='Inventory'",
                connection,
                transaction);
            equip.Parameters.AddWithValue(id);
            equip.Parameters.AddWithValue(playerId);
            if (await equip.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException("Inventory item changed while saving the loadout.");
            await WriteInventoryMovementAsync(
                connection, transaction, playerId, id, "Inventory", "Equipped", "loadout.save", cancellationToken);
        }
        var newVersion = version + 1;
        await using (var update = new NpgsqlCommand(
            "UPDATE player_loadouts SET head_id=$1, chest_id=$2, hands_id=$3, legs_id=$4, feet_id=$5, version=$6 WHERE player_id=$7 AND hero_class=$8", connection, transaction))
        {
            for (var index = 0; index < 5; index++) update.Parameters.AddWithValue(equipmentIds[index] ?? (object)DBNull.Value);
            update.Parameters.AddWithValue(newVersion); update.Parameters.AddWithValue(playerId); update.Parameters.AddWithValue((short)heroClass);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }
        var result = new SaveLoadoutResult(
            SaveLoadoutStatus.Updated,
            new LoadoutResponse((HeroClassDto)(short)heroClass, equipmentIds, newVersion));
        await WriteIdempotentResultAsync(
            connection, transaction, playerId, "loadout.save", requestId, requestHash, result, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result;
    }

    public async Task<EnhanceResult> EnhanceEquipmentAsync(Guid playerId, Guid equipmentId, string requestId, EnhanceEquipmentRequest request, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var requestHash = HashIdempotentRequest(equipmentId, request);
        var replay = await ReadIdempotentResultAsync<EnhanceResult>(connection, transaction, playerId, "equipment.enhance", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }
        await using var command = new NpgsqlCommand(
            "SELECT slot, quality, level, is_bound, location, version, element, effect_affix, secondary_trait FROM equipments WHERE instance_id=$1 AND owner_id=$2 FOR UPDATE", connection, transaction);
        command.Parameters.AddWithValue(equipmentId); command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) throw new DomainValidationException("Equipment was not found.");
        var slot = reader.GetString(0); var quality = reader.GetString(1); var level = reader.GetInt32(2);
        var bound = reader.GetBoolean(3); var location = reader.GetString(4); var version = reader.GetInt64(5);
        var element = reader.IsDBNull(6) ? null : reader.GetString(6);
        var effectAffix = reader.IsDBNull(7) ? null : reader.GetString(7);
        var secondaryTrait = reader.IsDBNull(8) ? null : reader.GetString(8);
        if (location is not ("Inventory" or "Equipped") || level >= 5) throw new DomainValidationException("Equipment cannot be enhanced in its current state.");
        if (version != request.ExpectedVersion) throw new DomainValidationException("Equipment changed. Reload and retry.");
        var cost = FragmentCost(quality, level + 1);
        var materialId = request.MaterialEquipmentId;
        if (level < 3 && materialId is not null)
            throw new DomainValidationException("This enhancement does not consume a material equipment item.");
        await reader.DisposeAsync();
        if (level >= 3)
        {
            var required = quality;
            if (materialId is null || materialId == equipmentId) throw new DomainValidationException("A valid enhancement material is required.");
            await using var material = new NpgsqlCommand(
                "SELECT quality, location FROM equipments WHERE instance_id=$1 AND owner_id=$2 FOR UPDATE", connection, transaction);
            material.Parameters.AddWithValue(materialId.Value); material.Parameters.AddWithValue(playerId);
            await using var materialReader = await material.ExecuteReaderAsync(cancellationToken);
            if (!await materialReader.ReadAsync(cancellationToken) || materialReader.GetString(0) != required || materialReader.GetString(1) != "Inventory")
                throw new DomainValidationException("The enhancement material is invalid.");
        }
        var fragments = await SpendFragmentsAsync(connection, transaction, playerId, cost, cancellationToken);
        await using (var update = new NpgsqlCommand("UPDATE equipments SET level=level+1, version=version+1 WHERE instance_id=$1", connection, transaction))
        { update.Parameters.AddWithValue(equipmentId); await update.ExecuteNonQueryAsync(cancellationToken); }
        if (materialId is not null)
        {
            await using var consume = new NpgsqlCommand("UPDATE equipments SET location='EnhanceMaterialConsumed', version=version+1 WHERE instance_id=$1", connection, transaction);
            consume.Parameters.AddWithValue(materialId.Value); await consume.ExecuteNonQueryAsync(cancellationToken);
            await WriteInventoryMovementAsync(connection, transaction, playerId, materialId.Value, "Inventory", "EnhanceMaterialConsumed", "equipment.enhance", cancellationToken, requestId);
        }
        await WriteEconomyLedgerAsync(connection, transaction, playerId, -cost, fragments, "EquipmentFragments", "equipment.enhance", cancellationToken, requestId);
        var result = new EnhanceResult(new EquipmentResponse(equipmentId, slot, quality, level + 1, bound, location, version + 1, element, effectAffix, secondaryTrait), fragments, materialId);
        await WriteIdempotentResultAsync(connection, transaction, playerId, "equipment.enhance", requestId, requestHash, result, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result;
    }

    public async Task<EnhanceResult> EnhanceWeaponAsync(Guid playerId, HeroClass heroClass, string requestId, long expectedVersion, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var requestHash = HashIdempotentRequest(heroClass, expectedVersion);
        var replay = await ReadIdempotentResultAsync<EnhanceResult>(connection, transaction, playerId, "class_weapon.enhance", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }
        await using var command = new NpgsqlCommand("SELECT level, version FROM class_weapons WHERE player_id=$1 AND hero_class=$2 FOR UPDATE", connection, transaction);
        command.Parameters.AddWithValue(playerId); command.Parameters.AddWithValue((short)heroClass);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) throw new DomainValidationException("Class weapon was not found.");
        var level = reader.GetInt32(0); var version = reader.GetInt64(1);
        await reader.DisposeAsync();
        if (version != expectedVersion) throw new DomainValidationException("Class weapon changed. Reload and retry.");
        if (level >= 5) throw new DomainValidationException("Class weapon is already at maximum level.");
        var fragments = await SpendFragmentsAsync(connection, transaction, playerId, FragmentCost("White", level + 1), cancellationToken);
        await using var update = new NpgsqlCommand("UPDATE class_weapons SET level=level+1, version=version+1 WHERE player_id=$1 AND hero_class=$2", connection, transaction);
        update.Parameters.AddWithValue(playerId); update.Parameters.AddWithValue((short)heroClass); await update.ExecuteNonQueryAsync(cancellationToken);
        await WriteEconomyLedgerAsync(connection, transaction, playerId, -FragmentCost("White", level + 1), fragments, "EquipmentFragments", "class_weapon.enhance", cancellationToken, requestId);
        var result = new EnhanceResult(new EquipmentResponse(Guid.Empty, "ClassWeapon", heroClass.ToString(), level + 1, true, "Equipped", version + 1), fragments, null);
        await WriteIdempotentResultAsync(connection, transaction, playerId, "class_weapon.enhance", requestId, requestHash, result, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result;
    }

    private static async Task LockPlayerAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction);
        command.Parameters.AddWithValue(playerId);
        if (await command.ExecuteScalarAsync(cancellationToken) is null)
            throw new DomainValidationException("Player was not found.");
    }

    private static string HashIdempotentRequest<TTarget, TRequest>(TTarget target, TRequest request) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            JsonSerializer.Serialize(new { target, request })))).ToLowerInvariant();

    private static async Task<TResponse?> ReadIdempotentResultAsync<TResponse>(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string scope,
        string requestId,
        string requestHash,
        CancellationToken cancellationToken)
        where TResponse : class
    {
        await using var command = new NpgsqlCommand(
            "SELECT request_hash,response_json::text FROM idempotency_records WHERE player_id=$1 AND scope=$2 AND request_id=$3",
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(scope);
        command.Parameters.AddWithValue(requestId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken)) return null;
        if (!string.Equals(reader.GetString(0), requestHash, StringComparison.Ordinal))
            throw new IdempotencyConflictException();
        if (reader.IsDBNull(1))
            throw new InvalidOperationException("Completed idempotency record has no response.");
        return JsonSerializer.Deserialize<TResponse>(reader.GetString(1))
            ?? throw new InvalidOperationException("Stored idempotency response is invalid.");
    }

    private static async Task WriteIdempotentResultAsync<TResponse>(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string scope,
        string requestId,
        string requestHash,
        TResponse result,
        CancellationToken cancellationToken)
        where TResponse : class
    {
        var now = DateTimeOffset.UtcNow;
        await using var command = new NpgsqlCommand(
            "INSERT INTO idempotency_records(player_id,scope,request_id,request_hash,response_json,created_at,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7)",
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(scope);
        command.Parameters.AddWithValue(requestId);
        command.Parameters.AddWithValue(requestHash);
        command.Parameters.Add(new Npgsql.NpgsqlParameter { NpgsqlDbType = NpgsqlTypes.NpgsqlDbType.Jsonb, Value = JsonSerializer.Serialize(result) });
        command.Parameters.AddWithValue(now);
        command.Parameters.AddWithValue(now.AddDays(7));
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static EquipmentResponse ReadEquipment(NpgsqlDataReader reader) => new(
        reader.GetGuid(0), reader.GetString(1), reader.GetString(2), reader.GetInt32(3),
        reader.GetBoolean(4), reader.GetString(5), reader.GetInt64(6),
        reader.IsDBNull(7) ? null : reader.GetString(7),
        reader.IsDBNull(8) ? null : reader.GetString(8),
        reader.IsDBNull(9) ? null : reader.GetString(9));

    private static long FragmentCost(string quality, int targetLevel) =>
        GameConfigCatalog.Current.EquipmentQuality(quality).EnhancementCost(targetLevel);

    private static async Task<long> SpendFragmentsAsync(
        NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId, long cost, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "UPDATE player_materials SET equipment_fragments = equipment_fragments - $1, version = version + 1 WHERE player_id = $2 AND equipment_fragments >= $1 RETURNING equipment_fragments",
            connection, transaction);
        command.Parameters.AddWithValue(cost); command.Parameters.AddWithValue(playerId);
        var remaining = await command.ExecuteScalarAsync(cancellationToken);
        if (remaining is null) throw new DomainValidationException("Not enough equipment fragments.");
        return (long)remaining;
    }

    private static async Task WriteEconomyLedgerAsync(
        NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId, long delta,
        long balanceAfter, string currency, string reason, CancellationToken cancellationToken,
        string? requestId = null)
    {
        await using var command = new NpgsqlCommand(
            "INSERT INTO economy_ledger(ledger_id, player_id, request_id, currency, delta, balance_after, reason, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            connection, transaction);
        command.Parameters.AddWithValue(Guid.CreateVersion7()); command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue((object?)requestId ?? DBNull.Value); command.Parameters.AddWithValue(currency);
        command.Parameters.AddWithValue(delta); command.Parameters.AddWithValue(balanceAfter);
        command.Parameters.AddWithValue(reason); command.Parameters.AddWithValue(DateTimeOffset.UtcNow);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task WriteInventoryMovementAsync(
        NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId, Guid itemId,
        string from, string to, string reason, CancellationToken cancellationToken,
        string? requestId = null)
    {
        await using var command = new NpgsqlCommand(
            "INSERT INTO inventory_movements(movement_id, player_id, item_id, from_location, to_location, reason, request_id, created_at) VALUES ($1,$2,$3,$4,$5,$6,$7,$8)",
            connection, transaction);
        command.Parameters.AddWithValue(Guid.CreateVersion7()); command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(itemId); command.Parameters.AddWithValue(from); command.Parameters.AddWithValue(to);
        command.Parameters.AddWithValue(reason); command.Parameters.AddWithValue((object?)requestId ?? DBNull.Value);
        command.Parameters.AddWithValue(DateTimeOffset.UtcNow);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<IReadOnlyList<CardResponse>> GetCardsAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT c.card_id, c.hero_class, c.rarity, c.unlocked, c.copy_count, c.level, c.version,
                   COALESCE((SELECT max(copies) FROM (
                       SELECT count(*) AS copies FROM player_deck_cards dc
                       JOIN player_decks d ON d.deck_id=dc.deck_id
                       WHERE d.player_id=c.player_id AND dc.card_id=c.card_id
                       GROUP BY d.deck_id) required), 0)::integer
            FROM player_cards c
            WHERE c.player_id = $1
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var owned = new Dictionary<string, CardResponse>(StringComparer.Ordinal);
        while (await reader.ReadAsync(cancellationToken))
        {
            var card = new CardResponse(
                reader.GetString(0),
                reader.IsDBNull(1) ? null : (HeroClassDto?)reader.GetInt16(1),
                ((CardRarity)reader.GetInt16(2)).ToString(),
                reader.GetBoolean(3),
                reader.GetInt32(4),
                reader.GetInt32(5),
                reader.GetInt64(6));
            var definition = GameConfigCatalog.Current.Cards.SingleOrDefault(item =>
                item.CardId == card.CardId && item.IsCodex && item.Enabled);
            if (definition is not null)
                owned.Add(card.CardId, QuoteCard(definition, card, reader.GetInt32(7)));
        }

        return GameConfigCatalog.Current.Cards.Where(card => card.IsCodex && card.Enabled)
            .Select(card => owned.GetValueOrDefault(card.CardId) ?? QuoteCard(card, EmptyCard(card), 0))
            .ToArray();
    }

    public async Task<IReadOnlyList<DeckResponse>> GetDecksAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT d.deck_id, d.hero_class, d.version, d.updated_at,
                   COALESCE(array_agg(dc.card_id ORDER BY dc.slot_index)
                       FILTER (WHERE dc.card_id IS NOT NULL), ARRAY[]::varchar[]) AS card_ids
            FROM player_decks d
            LEFT JOIN player_deck_cards dc ON dc.deck_id = d.deck_id
            WHERE d.player_id = $1
            GROUP BY d.deck_id, d.hero_class, d.version, d.updated_at
            ORDER BY d.hero_class
            """);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new List<DeckResponse>();
        while (await reader.ReadAsync(cancellationToken))
        {
            result.Add(ReadDeck(reader));
        }

        return result;
    }

    public async Task<SaveDeckResult> SaveDeckAsync(
        Guid playerId,
        HeroClass heroClass,
        IReadOnlyList<string> cardIds,
        string requestId,
        long expectedVersion,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var requestHash = HashIdempotentRequest(heroClass, new { cardIds, expectedVersion });
        var replay = await ReadIdempotentResultAsync<SaveDeckResult>(
            connection, transaction, playerId, "deck.save", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return replay;
        }

        Guid deckId;
        long currentVersion;
        await using (var deckCommand = new NpgsqlCommand(
            """
            SELECT deck_id, version
            FROM player_decks
            WHERE player_id = $1 AND hero_class = $2
            FOR UPDATE
            """,
            connection,
            transaction))
        {
            deckCommand.Parameters.AddWithValue(playerId);
            deckCommand.Parameters.AddWithValue((short)heroClass);
            await using var reader = await deckCommand.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
            {
                return new SaveDeckResult(SaveDeckStatus.NotFound);
            }

            deckId = reader.GetGuid(0);
            currentVersion = reader.GetInt64(1);
        }

        if (currentVersion != expectedVersion)
        {
            return new SaveDeckResult(SaveDeckStatus.VersionConflict);
        }

        var ownedCards = await LoadOwnedCardsAsync(connection, transaction, playerId, cancellationToken);
        DeckRules.Validate(heroClass, cardIds, ownedCards);

        await using (var deleteCommand = new NpgsqlCommand(
            "DELETE FROM player_deck_cards WHERE deck_id = $1",
            connection,
            transaction))
        {
            deleteCommand.Parameters.AddWithValue(deckId);
            await deleteCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        for (var index = 0; index < cardIds.Count; index++)
        {
            await using var insertCommand = new NpgsqlCommand(
                """
                INSERT INTO player_deck_cards(deck_id, slot_index, card_id)
                VALUES ($1, $2, $3)
                """,
                connection,
                transaction);
            insertCommand.Parameters.AddWithValue(deckId);
            insertCommand.Parameters.AddWithValue(index);
            insertCommand.Parameters.AddWithValue(cardIds[index]);
            await insertCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        var newVersion = currentVersion + 1;
        await using (var updateCommand = new NpgsqlCommand(
            """
            UPDATE player_decks SET version = $1, updated_at = $2 WHERE deck_id = $3
            """,
            connection,
            transaction))
        {
            updateCommand.Parameters.AddWithValue(newVersion);
            updateCommand.Parameters.AddWithValue(now);
            updateCommand.Parameters.AddWithValue(deckId);
            await updateCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        var result = new SaveDeckResult(
            SaveDeckStatus.Updated,
            new DeckResponse(deckId, (HeroClassDto)(short)heroClass, cardIds, newVersion, now));
        await WriteIdempotentResultAsync(
            connection, transaction, playerId, "deck.save", requestId, requestHash, result, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result;
    }

    private static async Task<IReadOnlyDictionary<string, OwnedCard>> LoadOwnedCardsAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT card_id, hero_class, rarity, copy_count, is_monster
            FROM player_cards
            WHERE player_id = $1 AND unlocked
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        var result = new Dictionary<string, OwnedCard>(StringComparer.Ordinal);
        while (await reader.ReadAsync(cancellationToken))
        {
            var card = new OwnedCard(
                reader.GetString(0),
                reader.IsDBNull(1) ? null : (HeroClass?)reader.GetInt16(1),
                (CardRarity)reader.GetInt16(2),
                reader.GetInt32(3),
                reader.GetBoolean(4));
            result.Add(card.CardId, card);
        }

        return result;
    }

    private static DeckResponse ReadDeck(NpgsqlDataReader reader) => new(
        reader.GetGuid(0),
        (HeroClassDto)reader.GetInt16(1),
        reader.GetFieldValue<string[]>(4),
        reader.GetInt64(2),
        reader.GetFieldValue<DateTimeOffset>(3));
}
