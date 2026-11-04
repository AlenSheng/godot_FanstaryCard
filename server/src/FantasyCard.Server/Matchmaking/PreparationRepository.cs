using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Cards;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Matches;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Contracts.Seasons;
using FantasyCard.Server.Bootstrap;
using FantasyCard.Server.Common;
using FantasyCard.Server.Seasons;
using FantasyCard.Server.Rooms;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Matchmaking;

public enum CreatePreparationStatus
{
    Created,
    Replayed,
    RequestConflict,
    ActivePreparationExists,
    DeckVersionConflict,
    AssetUnavailable
}

public sealed record CreatePreparationResult(
    CreatePreparationStatus Status,
    PreparationResponse? Preparation = null,
    string? Detail = null);

public enum CancelPreparationStatus
{
    Cancelled,
    NotFound,
    StateConflict
}

public sealed class PreparationRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider,
    PublishedConfigCatalogs? configurations = null)
{
    private readonly PublishedConfigCatalogs _configurations = configurations ?? new(GameConfigCatalog.Current);
    private static readonly string[] EquipmentSlots = ["Head", "Chest", "Hands", "Legs", "Feet"];
    private static readonly JsonSerializerOptions SerializerOptions = CreateSerializerOptions();

    public async Task<PreparationResponse?> GetActiveAsync(
        Guid playerId,
        CancellationToken cancellationToken)
    {
        var now = timeProvider.GetUtcNow();
        await using var command = dataSource.CreateCommand(
            """
            SELECT preparation_id, status, snapshot_json::text, created_at, expires_at
            FROM preparations
            WHERE player_id = $1
              AND status IN ('Active', 'Queued', 'Matched')
              AND (status = 'Matched' OR expires_at > $2)
            ORDER BY created_at DESC
            LIMIT 1
            """);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(now);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? ReadPreparation(reader) : null;
    }

    public async Task<CreatePreparationResult> CreateAsync(
        Guid playerId,
        string requestId,
        CreatePreparationRequest request,
        CancellationToken cancellationToken)
    {
        var equipmentIds = request.EquipmentIds?.ToArray() ?? [];
        var safeSlotIndexes = request.SafeSlotIndexes?.ToArray() ?? [];
        var backpackTier = (BackpackTier)(int)request.BackpackTier;
        PreparationRules.Validate(equipmentIds, backpackTier, safeSlotIndexes, request.PotionCount);

        if (!Enum.IsDefined(request.HeroClass))
        {
            throw new DomainValidationException("Unknown hero class.");
        }

        var requestHash = ComputeHash(request);
        var now = timeProvider.GetUtcNow();
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        now = timeProvider.GetUtcNow();
        await ExpireStaleAsync(connection, transaction, playerId, now, cancellationToken);
        var replay = await FindByRequestIdAsync(
            connection,
            transaction,
            playerId,
            requestId,
            cancellationToken);
        if (replay is not null)
        {
            var result = string.Equals(replay.Value.RequestHash, requestHash, StringComparison.Ordinal)
                ? new CreatePreparationResult(CreatePreparationStatus.Replayed, replay.Value.Preparation)
                : new CreatePreparationResult(
                    CreatePreparationStatus.RequestConflict,
                    Detail: "The Idempotency-Key was already used with a different request body.");
            await transaction.CommitAsync(cancellationToken);
            return result;
        }

        if (await HasActivePreparationAsync(connection, transaction, playerId, cancellationToken))
        {
            await transaction.CommitAsync(cancellationToken);
            return new CreatePreparationResult(
                CreatePreparationStatus.ActivePreparationExists,
                Detail: "Cancel the existing preparation before creating another one.");
        }

        var schedule = await new SeasonRepository(dataSource, timeProvider).GetScheduleAtAsync(now, cancellationToken);
        SeasonContext? season = null;
        var configuration = GameConfigCatalog.Current;
        if (schedule.Current is { } definition)
        {
            if (request.SeasonId is not null && request.SeasonId != definition.SeasonId)
                throw new DomainValidationException("The requested season is not the current season.");
            configuration = await ResolveOriginalConfigurationAsync(connection, transaction, definition, cancellationToken);
            var token = request.Difficulty ?? "D0";
            var difficulty = string.Equals(token, "Standard", StringComparison.OrdinalIgnoreCase) ? 0
                : token.Length == 2 && (token[0] is 'D' or 'd') && token[1] is >= '0' and <= '5' ? token[1] - '0'
                : throw new DomainValidationException("Season difficulty must be D0 through D5.");
            season = definition.ContextFor(difficulty);
            _=configuration.ResolveSeasonEquipment(season.StatsVersion);
            await using var unlocked = new NpgsqlCommand("SELECT highest_unlocked_difficulty FROM player_season_state WHERE player_id=$1 AND season_id=$2 AND archived_at IS NULL", connection, transaction);
            unlocked.Parameters.AddWithValue(playerId);unlocked.Parameters.AddWithValue(season.SeasonId);
            var unlockedValue = await unlocked.ExecuteScalarAsync(cancellationToken);
            if ((unlockedValue is short value ? value : 0) < difficulty)
                throw new DomainValidationException("The selected season difficulty has not been unlocked.");
        }
        else
        {
            if (!schedule.LegacyAllowed || request.SeasonId is not null)
                throw new DomainValidationException("No active season is accepting preparations.");
            if (!string.Equals(request.Difficulty, "Standard", StringComparison.OrdinalIgnoreCase))
                throw new DomainValidationException("Only Standard difficulty is available in the prototype.");
        }

        var heroClass = (HeroClass)(int)request.HeroClass;
        if (request.UseBorrowedDeck && season is null)
            throw new DomainValidationException("Borrowed templates are available only in an active season.");
        var borrowed = request.UseBorrowedDeck ? configuration.BorrowedDeck(heroClass) : null;
        var deck = borrowed is null ? await LoadDeckAsync(connection, transaction, playerId, heroClass, cancellationToken) : null;
        if (borrowed is null && (deck is null || deck.Value.Version != request.DeckVersion))
        {
            await transaction.CommitAsync(cancellationToken);
            return new CreatePreparationResult(
                CreatePreparationStatus.DeckVersionConflict,
                Detail: "Reload the deck and create the preparation with its latest version.");
        }

        var equipmentValidation = await ValidateEquipmentAsync(
            connection,
            transaction,
            playerId,
            equipmentIds,
            season,
            configuration,
            cancellationToken);
        if (equipmentValidation.Error is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return new CreatePreparationResult(CreatePreparationStatus.AssetUnavailable, Detail: equipmentValidation.Error);
        }

        var consumables = await LoadConsumablesAsync(connection, transaction, playerId, cancellationToken);
        if (request.PotionCount > consumables.HealthPotions ||
            (backpackTier == BackpackTier.Advanced && consumables.AdvancedBags < 1) ||
            (backpackTier == BackpackTier.Top && consumables.TopBags < 1))
        {
            await transaction.CommitAsync(cancellationToken);
            return new CreatePreparationResult(
                CreatePreparationStatus.AssetUnavailable,
                Detail: "The requested backpack or potion quantity is unavailable.");
        }

        var weaponLevel = await LoadClassWeaponLevelAsync(
            connection,
            transaction,
            playerId,
            heroClass,
            cancellationToken);
        var cardIds = borrowed?.CardIds ?? deck!.Value.CardIds;
        var actualCardLevels = borrowed is null
            ? await LoadCardLevelsAsync(connection, transaction, playerId, heroClass, cardIds, configuration, cancellationToken)
            : await LoadBorrowedActualLevelsAsync(connection,transaction,playerId,cardIds,cancellationToken);
        if (schedule.Current is { } currentSeason && !currentSeason.Contains(timeProvider.GetUtcNow()) ||
            schedule.Current is null && schedule.Next is { } nextSeason && timeProvider.GetUtcNow() >= nextSeason.StartsAtUtc)
            throw new DomainValidationException("The season changed while creating the preparation. Reload and retry.");
        if (season is not null)
            await SeasonRepository.EnsurePlayerWithinTransactionAsync(connection, transaction, playerId, season,
                timeProvider.GetUtcNow(), cancellationToken);
        var preferencePolicy=season is null ? null : configuration.SeasonLootPreference;
        if(preferencePolicy is null && request.LootPreferenceElement is not null)
            throw new DomainValidationException("This preparation has no seasonal loot preference policy.");
        var lootPreference=preferencePolicy?.Resolve(request.LootPreferenceElement);
        var snapshot = new PreparationSnapshotResponse(
            request.HeroClass,
            MaximumHp(heroClass),
            cardIds,
            equipmentIds,
            borrowed is null ? season?.ProjectPermanentLevel(weaponLevel) ?? weaponLevel : season!.Difficulty,
            request.BackpackTier,
            configuration.Backpack(backpackTier.ToString()).Capacity,
            safeSlotIndexes,
            request.PotionCount,
            season?.DifficultyId ?? "Standard",
            season?.ConfigVersion ?? BootstrapRepository.CurrentConfigVersion,
            equipmentValidation.Items,
            borrowed is null ? actualCardLevels.Select(level => season?.ProjectPermanentLevel(level) ?? level).ToArray()
                : Enumerable.Repeat(season!.Difficulty,cardIds.Count).ToArray(),
            season is null ? null : new SeasonContextResponse(season.SeasonId, season.DifficultyId, season.RulesetId, season.ConfigVersion, season.StatsVersion),
            season is null ? null : actualCardLevels,
            season is null ? null : weaponLevel,
            borrowed?.TemplateId, lootPreference);
        var preparation = new PreparationResponse(
            Guid.CreateVersion7(),
            "Active",
            snapshot,
            now,
            schedule.Current is { } active && active.EndsAtUtc < now.AddMinutes(30) ? active.EndsAtUtc : now.AddMinutes(30));

        await InsertPreparationAsync(
            connection,
            transaction,
            playerId,
            requestId,
            requestHash,
            preparation,
            cancellationToken);
        await InsertReservedAssetsAsync(
            connection,
            transaction,
            preparation.PreparationId,
            request,
            cancellationToken);
        await LockEquipmentAsync(
            connection,
            transaction,
            preparation.PreparationId,
            playerId,
            requestId,
            equipmentIds,
            cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return new CreatePreparationResult(CreatePreparationStatus.Created, preparation);
    }

    public async Task<CancelPreparationStatus> CancelAsync(
        Guid playerId,
        Guid preparationId,
        string requestId,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        // CreateAsync uses the same player-row lock. Serializing both operations
        // makes cancellation release the preparation lock atomically with the
        // state transition, so a concurrent create cannot observe a half-cancelled
        // preparation.
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var now = timeProvider.GetUtcNow();
        var requestHash = PersistentIdempotency.Hash(new { preparationId });
        var replay = await PersistentIdempotency.ReadAsync<IdempotencyAcknowledgement>(
            connection, transaction, playerId, "preparation.cancel", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return CancelPreparationStatus.Cancelled;
        }

        await using var command = new NpgsqlCommand(
            """
            UPDATE preparations
            SET status = 'Cancelled'
            WHERE preparation_id = $1 AND player_id = $2 AND status = 'Active'
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(preparationId);
        command.Parameters.AddWithValue(playerId);
        if (await command.ExecuteNonQueryAsync(cancellationToken) == 1)
        {
            await ReleaseEquipmentAsync(
                connection, transaction, preparationId, requestId, cancellationToken);
            await PersistentIdempotency.WriteAsync(
                connection, transaction, playerId, "preparation.cancel", requestId, requestHash,
                new IdempotencyAcknowledgement(), now, cancellationToken);
            await transaction.CommitAsync(cancellationToken);
            return CancelPreparationStatus.Cancelled;
        }

        await using var existsCommand = new NpgsqlCommand(
            "SELECT status FROM preparations WHERE preparation_id = $1 AND player_id = $2",
            connection,
            transaction);
        existsCommand.Parameters.AddWithValue(preparationId);
        existsCommand.Parameters.AddWithValue(playerId);
        var status = await existsCommand.ExecuteScalarAsync(cancellationToken);
        if (status is "Cancelled")
        {
            await PersistentIdempotency.WriteAsync(
                connection, transaction, playerId, "preparation.cancel", requestId, requestHash,
                new IdempotencyAcknowledgement(), now, cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
        return status switch
        {
            null => CancelPreparationStatus.NotFound,
            "Cancelled" => CancelPreparationStatus.Cancelled,
            _ => CancelPreparationStatus.StateConflict
        };
    }

    private static async Task LockPlayerAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "SELECT user_id FROM players WHERE user_id = $1 FOR UPDATE",
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        if (await command.ExecuteScalarAsync(cancellationToken) is null)
        {
            throw new InvalidOperationException("Authenticated player no longer exists.");
        }
    }

    internal static async Task<int> ExpireStaleAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        var expiring = new List<Guid>();
        await using (var query = new NpgsqlCommand(
            "SELECT preparation_id FROM preparations WHERE player_id=$1 AND status IN ('Active','Queued') AND expires_at <= $2 FOR UPDATE",
            connection, transaction))
        {
            query.Parameters.AddWithValue(playerId);
            query.Parameters.AddWithValue(now);
            await using var reader = await query.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken)) expiring.Add(reader.GetGuid(0));
        }
        foreach (var preparationId in expiring)
            await ReleaseEquipmentAsync(connection, transaction, preparationId, null, cancellationToken);

        await using (var tickets = new NpgsqlCommand(
            """
            UPDATE match_tickets AS t
            SET status = 'Cancelled'
            FROM preparations AS p
            WHERE t.preparation_id = p.preparation_id
              AND t.player_id = $1
              AND t.status = 'Queued'
              AND p.status = 'Queued'
              AND p.expires_at <= $2
            """,
            connection,
            transaction))
        {
            tickets.Parameters.AddWithValue(playerId);
            tickets.Parameters.AddWithValue(now);
            await tickets.ExecuteNonQueryAsync(cancellationToken);
        }

        await using var preparations = new NpgsqlCommand(
            """
            UPDATE preparations
            SET status = 'Expired'
            WHERE player_id = $1
              AND status IN ('Active', 'Queued')
              AND expires_at <= $2
            """,
            connection,
            transaction);
        preparations.Parameters.AddWithValue(playerId);
        preparations.Parameters.AddWithValue(now);
        return await preparations.ExecuteNonQueryAsync(cancellationToken);
    }

    internal static async Task ReleaseEquipmentAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid preparationId,
        string? requestId,
        CancellationToken cancellationToken)
    {
        var released = new List<(Guid EquipmentId, Guid PlayerId)>();
        await using (var command = new NpgsqlCommand(
            """
            UPDATE equipments e
            SET location='Equipped',version=e.version+1
            FROM preparation_assets pa,preparations p
            WHERE pa.preparation_id=$1
              AND pa.asset_type='Equipment'
              AND e.instance_id=pa.asset_id::uuid
              AND p.preparation_id=pa.preparation_id
              AND e.owner_id=p.player_id
              AND e.location='PreparationLocked'
            RETURNING e.instance_id,e.owner_id
            """, connection, transaction))
        {
            command.Parameters.AddWithValue(preparationId);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            while (await reader.ReadAsync(cancellationToken))
                released.Add((reader.GetGuid(0), reader.GetGuid(1)));
        }
        foreach (var item in released)
        {
            await using var movement = new NpgsqlCommand(
                """
                INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at,season_id,difficulty_id,ruleset_id,config_version,stats_version)
                SELECT $1,$2,$3,'PreparationLocked','Equipped','preparation.release',$4,CURRENT_TIMESTAMP,p.season_id,
                    CASE WHEN p.season_id IS NULL THEN 'Standard' ELSE 'D'||p.difficulty_id::text END,p.ruleset_id,p.config_version,p.stats_version
                FROM equipments e CROSS JOIN preparations p WHERE e.instance_id=$3 AND e.owner_id=$2 AND p.preparation_id=$5
                """,
                connection, transaction);
            movement.Parameters.AddWithValue(Guid.CreateVersion7());
            movement.Parameters.AddWithValue(item.PlayerId);
            movement.Parameters.AddWithValue(item.EquipmentId);
            movement.Parameters.AddWithValue(requestId ?? (object)DBNull.Value);
            movement.Parameters.AddWithValue(preparationId);
            await movement.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static async Task<(string RequestHash, PreparationResponse Preparation)?> FindByRequestIdAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string requestId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT request_hash, preparation_id, status, snapshot_json::text, created_at, expires_at
            FROM preparations WHERE player_id = $1 AND request_id = $2
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(requestId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            return null;
        }

        return (reader.GetString(0), ReadPreparation(reader, 1));
    }

    private static async Task<bool> HasActivePreparationAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT EXISTS(
                SELECT 1 FROM preparations
                WHERE player_id = $1 AND status IN ('Active', 'Queued', 'Matched')
            )
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        return (bool)(await command.ExecuteScalarAsync(cancellationToken) ?? false);
    }

    private static async Task<(long Version, string[] CardIds)?> LoadDeckAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        HeroClass heroClass,
        CancellationToken cancellationToken)
    {
        Guid deckId;
        long version;
        await using (var deckCommand = new NpgsqlCommand(
            """
            SELECT deck_id, version
            FROM player_decks
            WHERE player_id = $1 AND hero_class = $2
            FOR SHARE
            """,
            connection,
            transaction))
        {
            deckCommand.Parameters.AddWithValue(playerId);
            deckCommand.Parameters.AddWithValue((short)heroClass);
            await using var reader = await deckCommand.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
            {
                return null;
            }

            deckId = reader.GetGuid(0);
            version = reader.GetInt64(1);
        }

        await using var command = new NpgsqlCommand(
            """
            SELECT COALESCE(array_agg(card_id ORDER BY slot_index), ARRAY[]::varchar[])
            FROM player_deck_cards
            WHERE deck_id = $1
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(deckId);
        var cardIds = (string[])(await command.ExecuteScalarAsync(cancellationToken) ?? Array.Empty<string>());
        return (version, cardIds);
    }

    private async Task<GameConfigCatalog> ResolveOriginalConfigurationAsync(NpgsqlConnection connection,
        NpgsqlTransaction transaction, SeasonDefinition season, CancellationToken ct)
    {
        GameConfigCatalog configuration;
        try { configuration = _configurations.Resolve(season.ConfigVersion); }
        catch (Exception e) when (e is IOException or InvalidDataException)
        {
            throw new DomainValidationException("The active season's original published configuration is unavailable.");
        }
        await using var hash = new NpgsqlCommand("SELECT config_sha256 FROM season_definitions WHERE season_id=$1 AND config_version=$2", connection, transaction);
        hash.Parameters.AddWithValue(season.SeasonId);hash.Parameters.AddWithValue(season.ConfigVersion);
        if (await hash.ExecuteScalarAsync(ct) is not string expected || expected != configuration.ContentHash)
            throw new DomainValidationException("The original preparation configuration hash differs from its published season.");
        return configuration;
    }

    private static async Task<IReadOnlyList<int>> LoadCardLevelsAsync(
        NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId, HeroClass heroClass,
        IReadOnlyList<string> cardIds, GameConfigCatalog configuration, CancellationToken cancellationToken)
    {
        var levels = new Dictionary<string, int>(StringComparer.Ordinal);
        var definitions = configuration.Cards.Where(card=>card.IsCodex).ToDictionary(card=>card.CardId,StringComparer.Ordinal);
        var owned = new Dictionary<string,OwnedCard>(StringComparer.Ordinal);
        await using var command = new NpgsqlCommand(
            "SELECT card_id,level,copy_count FROM player_cards WHERE player_id=$1 AND unlocked=true AND card_id=ANY($2) FOR SHARE",
            connection, transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(cardIds.ToArray());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            var id=reader.GetString(0);
            if (!definitions.TryGetValue(id,out var definition))
                throw new DomainValidationException("A prepared card is unavailable in the original published configuration.");
            levels.Add(id, reader.GetInt32(1));
            owned.Add(id,new(id,definition.HeroClass,(CardRarity)definition.Rarity,reader.GetInt32(2),false));
        }
        DeckRules.Validate(heroClass,cardIds,owned);
        return CardEconomyRules.DeckLevels(cardIds, levels);
    }

    private static async Task<int[]> LoadBorrowedActualLevelsAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        Guid playerId,IReadOnlyList<string> cards,CancellationToken ct)
    {
        await using var command = new NpgsqlCommand("SELECT card_id,level FROM player_cards WHERE player_id=$1 AND card_id=ANY($2) FOR SHARE",connection,transaction);
        command.Parameters.AddWithValue(playerId);command.Parameters.AddWithValue(cards.ToArray());
        var levels = new Dictionary<string,int>(StringComparer.Ordinal);
        await using var reader = await command.ExecuteReaderAsync(ct);
        while (await reader.ReadAsync(ct)) levels[reader.GetString(0)] = reader.GetInt32(1);
        return cards.Select(id => levels.GetValueOrDefault(id)).ToArray();
    }

    private static async Task<(string? Error, IReadOnlyList<PreparationEquipmentSnapshotResponse> Items)> ValidateEquipmentAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        Guid?[] equipmentIds,
        SeasonContext? season,
        GameConfigCatalog configuration,
        CancellationToken cancellationToken)
    {
        var snapshots = new List<PreparationEquipmentSnapshotResponse>();
        for (var index = 0; index < equipmentIds.Length; index++)
        {
            if (equipmentIds[index] is not { } equipmentId)
            {
                continue;
            }

            await using var command = new NpgsqlCommand(
                """
                SELECT slot, location, quality, level, element, effect_affix, secondary_trait,season_id,asset_scope,stats_version,source_kind,unique_affix,unique_element FROM equipments
                WHERE instance_id = $1 AND owner_id = $2
                FOR SHARE
                """,
                connection,
                transaction);
            command.Parameters.AddWithValue(equipmentId);
            command.Parameters.AddWithValue(playerId);
            await using var reader = await command.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
            {
                return ($"Equipment '{equipmentId}' is not owned by the player.", []);
            }

            var sameDomain = season is null ? reader.IsDBNull(7) && reader.IsDBNull(8)
                : !reader.IsDBNull(7) && reader.GetString(7) == season.SeasonId &&
                  !reader.IsDBNull(8) && reader.GetString(8) == "ActiveSeason" &&
                  !reader.IsDBNull(9) && reader.GetString(9) == season.StatsVersion;
            if (!sameDomain) return ("Prepared equipment belongs to another season, archive or stats version.", []);
            if (season is not null)
            {
                var rank = SeasonLootConfig.Rank(reader.GetString(2));
                var entryCap = configuration.SeasonDifficulty(season.Difficulty).EntryQualityCap;
                if (rank > entryCap) return ("Equipment quality exceeds the selected difficulty entry cap.", []);
                if (reader.GetString(10) is "BotProjection" or "Borrowed" or "ActivityMaterial")
                    return ("Projected, borrowed or material-only equipment cannot enter a preparation.", []);
            }

            if (!string.Equals(reader.GetString(0), EquipmentSlots[index], StringComparison.Ordinal) ||
                !string.Equals(reader.GetString(1), "Equipped", StringComparison.Ordinal))
            {
                return ($"Equipment '{equipmentId}' is in the wrong slot or is currently locked.", []);
            }
            if (reader.IsDBNull(4))
            {
                return ($"Equipment '{equipmentId}' has no combat element.", []);
            }
            snapshots.Add(new PreparationEquipmentSnapshotResponse(
                equipmentId,
                reader.GetString(0),
                reader.GetString(2),
                reader.GetInt32(3),
                reader.GetString(4),
                reader.IsDBNull(5) ? null : reader.GetString(5),
                reader.IsDBNull(6) ? null : reader.GetString(6),
                reader.IsDBNull(11)?null:reader.GetString(11),reader.IsDBNull(12)?null:reader.GetString(12),
                reader.IsDBNull(9)?null:reader.GetString(9)));
        }

        if (snapshots.Count(item => item.Quality is "Orange" or "Red") > 1)
        {
            return ("A loadout can contain at most one Orange or Red armor item.", []);
        }

        return (null, snapshots);
    }

    private static async Task<(int HealthPotions, int AdvancedBags, int TopBags)> LoadConsumablesAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT health_potion_count, advanced_bag_count, top_bag_count
            FROM player_consumables WHERE player_id = $1 FOR UPDATE
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
        {
            throw new InvalidOperationException("Player consumables were not provisioned.");
        }

        return (reader.GetInt32(0), reader.GetInt32(1), reader.GetInt32(2));
    }

    private static async Task<int> LoadClassWeaponLevelAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        HeroClass heroClass,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            "SELECT level FROM class_weapons WHERE player_id = $1 AND hero_class = $2",
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue((short)heroClass);
        return (int)(await command.ExecuteScalarAsync(cancellationToken)
            ?? throw new InvalidOperationException("Class weapon was not provisioned."));
    }

    private static async Task InsertPreparationAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string requestId,
        string requestHash,
        PreparationResponse preparation,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            INSERT INTO preparations(
                preparation_id, player_id, request_id, request_hash, snapshot_json,
                status, config_version, created_at, expires_at,season_id,difficulty_id,ruleset_id,stats_version)
            VALUES ($1, $2, $3, $4, $5, 'Active', $6, $7, $8,$9,$10,$11,$12)
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(preparation.PreparationId);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(requestId);
        command.Parameters.AddWithValue(requestHash);
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Jsonb,
            Value = JsonSerializer.Serialize(preparation.Snapshot, SerializerOptions)
        });
        command.Parameters.AddWithValue(preparation.Snapshot.ConfigVersion);
        command.Parameters.AddWithValue(preparation.CreatedAt);
        command.Parameters.AddWithValue(preparation.ExpiresAt);
        var season = preparation.Snapshot.Season;
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)season?.SeasonId ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlDbType.Smallint, season is null ? DBNull.Value : (short)(season.DifficultyId[1] - '0'));
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)season?.RulesetId ?? DBNull.Value);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)season?.StatsVersion ?? DBNull.Value);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task InsertReservedAssetsAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid preparationId,
        CreatePreparationRequest request,
        CancellationToken cancellationToken)
    {
        var assets = new List<(string Type, string Id, int Quantity)>();
        if (request.PotionCount > 0)
        {
            assets.Add(("Consumable", "health_potion", request.PotionCount));
        }

        if (request.BackpackTier != BackpackTierDto.Free)
        {
            assets.Add(("Backpack", request.BackpackTier.ToString(), 1));
        }

        assets.AddRange((request.EquipmentIds ?? [])
            .Where(id => id.HasValue)
            .Select(id => ("Equipment", id!.Value.ToString("D"), 1)));

        foreach (var asset in assets)
        {
            await using var command = new NpgsqlCommand(
                """
                INSERT INTO preparation_assets(preparation_id, asset_type, asset_id, quantity)
                VALUES ($1, $2, $3, $4)
                """,
                connection,
                transaction);
            command.Parameters.AddWithValue(preparationId);
            command.Parameters.AddWithValue(asset.Type);
            command.Parameters.AddWithValue(asset.Id);
            command.Parameters.AddWithValue(asset.Quantity);
            await command.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static async Task LockEquipmentAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid preparationId,
        Guid playerId,
        string requestId,
        IReadOnlyList<Guid?> equipmentIds,
        CancellationToken cancellationToken)
    {
        foreach (var equipmentId in equipmentIds.Where(id => id.HasValue).Select(id => id!.Value))
        {
            await using var equipment = new NpgsqlCommand(
                "UPDATE equipments SET location='PreparationLocked',version=version+1 WHERE instance_id=$1 AND owner_id=$2 AND location='Equipped'",
                connection, transaction);
            equipment.Parameters.AddWithValue(equipmentId);
            equipment.Parameters.AddWithValue(playerId);
            if (await equipment.ExecuteNonQueryAsync(cancellationToken) != 1)
                throw new InvalidOperationException($"Preparation '{preparationId}' could not lock its equipment.");
            await using var movement = new NpgsqlCommand(
                """
                INSERT INTO inventory_movements(movement_id,player_id,item_id,from_location,to_location,reason,request_id,created_at,season_id,difficulty_id,ruleset_id,config_version,stats_version)
                SELECT $1,$2,$3,'Equipped','PreparationLocked','preparation.lock',$4,CURRENT_TIMESTAMP,p.season_id,
                    CASE WHEN p.season_id IS NULL THEN 'Standard' ELSE 'D'||p.difficulty_id::text END,p.ruleset_id,p.config_version,p.stats_version
                FROM equipments e CROSS JOIN preparations p WHERE e.instance_id=$3 AND e.owner_id=$2 AND p.preparation_id=$5
                """,
                connection, transaction);
            movement.Parameters.AddWithValue(Guid.CreateVersion7());
            movement.Parameters.AddWithValue(playerId);
            movement.Parameters.AddWithValue(equipmentId);
            movement.Parameters.AddWithValue(requestId);
            movement.Parameters.AddWithValue(preparationId);
            await movement.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static PreparationResponse ReadPreparation(NpgsqlDataReader reader, int offset = 0)
    {
        var snapshot = JsonSerializer.Deserialize<PreparationSnapshotResponse>(
            reader.GetString(offset + 2),
            SerializerOptions) ?? throw new InvalidOperationException("Preparation snapshot is invalid.");
        return new PreparationResponse(
            reader.GetGuid(offset),
            reader.GetString(offset + 1),
            snapshot,
            reader.GetFieldValue<DateTimeOffset>(offset + 3),
            reader.GetFieldValue<DateTimeOffset>(offset + 4));
    }

    private static string ComputeHash(CreatePreparationRequest request)
    {
        var json = JsonSerializer.Serialize(request, SerializerOptions);
        return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(json))).ToLowerInvariant();
    }

    private static int MaximumHp(HeroClass heroClass) => heroClass switch
    {
        HeroClass.Priest => 80,
        HeroClass.Mage => 70,
        HeroClass.Guardian => 100,
        _ => throw new ArgumentOutOfRangeException(nameof(heroClass))
    };

    private static JsonSerializerOptions CreateSerializerOptions()
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        options.Converters.Add(new JsonStringEnumConverter());
        return options;
    }
}
