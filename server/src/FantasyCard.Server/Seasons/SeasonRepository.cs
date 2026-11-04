using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Serialization;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using FantasyCard.Domain.Configuration;
using Npgsql;

namespace FantasyCard.Server.Seasons;

public enum SeasonWalletPurpose { General = 1, PermanentWeaponEnhancement = 2, LateSettlement = 3 }
public sealed record SeasonWalletSnapshot(
    Guid PlayerId, string SeasonId, long Gold, long EquipmentFragments,
    long ChallengeMarks, long Version, DateTimeOffset? ArchivedAt,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)] long BlueprintMarks = 0,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingDefault)] long OrangeBlueprintMarks = 0);
public sealed record SeasonWalletListEntry(SeasonWalletSnapshot Wallet, bool CanFundWeapon);

public sealed class SeasonRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider)
{
    private const long PublicationLock = 6_202_611_020_000_001;

    /// <summary>Persist only an already compiled configuration snapshot; never mutate a published season.</summary>
    public async Task<bool> PublishAsync(SeasonDefinition definition,string configSha256,CancellationToken cancellationToken,
        GameConfigCatalog? configuration=null)
    {
        ArgumentNullException.ThrowIfNull(definition);
        if (configSha256.Length != 64 || configSha256.Any(character => !char.IsAsciiHexDigitLower(character)))
            throw new DomainValidationException("The season configuration hash is invalid.");
        configuration??=GameConfigCatalog.Current;
        if(configuration.Version==definition.ConfigVersion && configuration.ContentHash!=configSha256)
            throw new DomainValidationException("The season configuration hash differs from its compiled bundle.");
        var cardRule=configuration.Version==definition.ConfigVersion&&configuration.SeasonShop is not null
            ?SeasonShopConfig.Version:null;
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var gate = new NpgsqlCommand("SELECT pg_advisory_xact_lock($1)", connection, transaction))
        {
            gate.Parameters.AddWithValue(PublicationLock);
            await gate.ExecuteNonQueryAsync(cancellationToken);
        }
        var existing = await ReadDefinitionAsync(connection, transaction, definition.SeasonId, cancellationToken);
        if (existing is not null)
        {
            if (existing.Value.Definition != definition || existing.Value.Hash != configSha256)
                throw new DomainValidationException("A published season cannot change its rules, dates or configuration.");
            if(cardRule is not null)
            {
                await using var policy=new NpgsqlCommand("UPDATE season_definitions SET permanent_card_rule=$1 WHERE season_id=$2 AND permanent_card_rule IS NULL",connection,transaction);
                policy.Parameters.AddWithValue(cardRule);policy.Parameters.AddWithValue(definition.SeasonId);await policy.ExecuteNonQueryAsync(cancellationToken);
            }
            await transaction.CommitAsync(cancellationToken);
            return false;
        }
        await using var insert = new NpgsqlCommand("""
            INSERT INTO season_definitions
                (season_id,ruleset_id,config_version,config_sha256,stats_version,starts_at,ends_at,
                 duration_days,highest_open_difficulty,published_at,permanent_card_rule)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """, connection, transaction);
        insert.Parameters.AddWithValue(definition.SeasonId);
        insert.Parameters.AddWithValue(definition.RulesetId);
        insert.Parameters.AddWithValue(definition.ConfigVersion);
        insert.Parameters.AddWithValue(configSha256);
        insert.Parameters.AddWithValue(definition.StatsVersion);
        insert.Parameters.AddWithValue(definition.StartsAtUtc);
        insert.Parameters.AddWithValue(definition.EndsAtUtc);
        insert.Parameters.AddWithValue(definition.DurationDays);
        insert.Parameters.AddWithValue((short)definition.HighestOpenDifficulty);
        insert.Parameters.AddWithValue(timeProvider.GetUtcNow());
        insert.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.Varchar,(object?)cardRule??DBNull.Value);
        try { await insert.ExecuteNonQueryAsync(cancellationToken); }
        catch (PostgresException exception) when (exception.SqlState == PostgresErrorCodes.ExclusionViolation)
        {
            throw new DomainValidationException("Season calendar periods cannot overlap.");
        }
        await transaction.CommitAsync(cancellationToken);
        return true;
    }

    public async Task<SeasonDefinition?> GetActiveAsync(CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand("""
            SELECT season_id,ruleset_id,config_version,stats_version,starts_at,ends_at,highest_open_difficulty
            FROM season_definitions WHERE ruleset_id='season-v1' AND starts_at <= $1 AND ends_at > $1
            """);
        command.Parameters.AddWithValue(timeProvider.GetUtcNow());
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? ReadDefinition(reader) : null;
    }

    public Task<SeasonScheduleSnapshot> GetScheduleAsync(CancellationToken cancellationToken) =>
        GetScheduleAtAsync(timeProvider.GetUtcNow(), cancellationToken);

    public async Task<SeasonScheduleSnapshot> GetScheduleAtAsync(DateTimeOffset snapshotTime, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand("""
            SELECT season_id,ruleset_id,config_version,stats_version,starts_at,ends_at,highest_open_difficulty
            FROM season_definitions WHERE ruleset_id='season-v1' ORDER BY starts_at
            """);
        var definitions = new List<SeasonDefinition>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken)) definitions.Add(ReadDefinition(reader));
        return SeasonSchedule.Resolve(definitions, snapshotTime);
    }

    public async Task<IReadOnlyList<SeasonWalletListEntry>> GetWalletsAsync(
        Guid playerId, DateTimeOffset snapshotTime, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand("""
            SELECT w.season_id,w.gold,w.equipment_fragments,w.challenge_marks,w.version,w.archived_at,
                   d.ruleset_id='season-v1' AND d.starts_at <= $2 AS can_fund_weapon,
                   w.blueprint_marks,w.orange_blueprint_marks
            FROM player_season_wallets w JOIN season_definitions d ON d.season_id=w.season_id
            WHERE w.player_id=$1 ORDER BY d.starts_at DESC NULLS LAST,w.season_id
            """);
        command.Parameters.AddWithValue(playerId); command.Parameters.AddWithValue(snapshotTime);
        var wallets = new List<SeasonWalletListEntry>();
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
            wallets.Add(new(new(playerId, reader.GetString(0), reader.GetInt64(1), reader.GetInt64(2),
                reader.GetInt64(3), reader.GetInt64(4), reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5),
                reader.GetInt64(7),reader.GetInt64(8)), reader.GetBoolean(6)));
        return wallets;
    }

    public async Task<int> GetUnlockedDifficultyAsync(Guid playerId, string seasonId, CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            "SELECT highest_unlocked_difficulty FROM player_season_state WHERE player_id=$1 AND season_id=$2");
        command.Parameters.AddWithValue(playerId); command.Parameters.AddWithValue(seasonId);
        return await command.ExecuteScalarAsync(cancellationToken) is short value ? value
            : throw new DomainValidationException("The player has not joined the selected season.");
    }

    /// <summary>Membership creates zeroed seasonal balances and never resets the permanent aggregate.</summary>
    public async Task EnsurePlayerAsync(Guid playerId, SeasonContext context, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await EnsurePlayerWithinTransactionAsync(connection, transaction, playerId, context, timeProvider.GetUtcNow(), cancellationToken);
        await transaction.CommitAsync(cancellationToken);
    }

    public static async Task EnsurePlayerWithinTransactionAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        Guid playerId, SeasonContext context, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var definition = await ValidateContextAsync(connection, transaction, context, cancellationToken);
        if (!definition.Contains(now))
            throw new DomainValidationException("The selected season is not accepting new entries.");
        await using (var state = new NpgsqlCommand("""
            INSERT INTO player_season_state (player_id,season_id,joined_at) VALUES ($1,$2,$3)
            ON CONFLICT (player_id,season_id) DO NOTHING
            """, connection, transaction))
        {
            state.Parameters.AddWithValue(playerId); state.Parameters.AddWithValue(context.SeasonId);
            state.Parameters.AddWithValue(now);
            await state.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var wallet = new NpgsqlCommand("""
            INSERT INTO player_season_wallets (player_id,season_id) VALUES ($1,$2)
            ON CONFLICT (player_id,season_id) DO NOTHING
            """, connection, transaction))
        {
            wallet.Parameters.AddWithValue(playerId); wallet.Parameters.AddWithValue(context.SeasonId);
            await wallet.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var state = new NpgsqlCommand(
            "SELECT archived_at IS NOT NULL FROM player_season_state WHERE player_id=$1 AND season_id=$2", connection, transaction))
        {
            state.Parameters.AddWithValue(playerId); state.Parameters.AddWithValue(context.SeasonId);
            if ((bool)(await state.ExecuteScalarAsync(cancellationToken))!)
                throw new DomainValidationException("The player's season has been archived.");
        }
    }

    public async Task<SeasonWalletSnapshot?> GetWalletAsync(Guid playerId, SeasonContext context, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await ValidateContextAsync(connection, null, context, cancellationToken);
        return await ReadWalletAsync(connection, null, playerId, context.SeasonId, false, cancellationToken);
    }

    /// <summary>Economy actions use D0 as their context; no battle difficulty is inferred from a wallet ID.</summary>
    public async Task<SeasonContext> GetWeaponFragmentSourceAsync(Guid playerId, string seasonId, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(seasonId) || seasonId.Length > 80 ||
            seasonId.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not '-' and not '_' and not '.'))
            throw new DomainValidationException("The selected fragment wallet season is invalid.");
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        var published = await ReadDefinitionAsync(connection, null, seasonId, cancellationToken)
            ?? throw new DomainValidationException("The selected fragment wallet season was not found.");
        if (timeProvider.GetUtcNow() < published.Definition.StartsAtUtc)
            throw new DomainValidationException("The selected season has not started.");
        if (await ReadWalletAsync(connection, null, playerId, seasonId, false, cancellationToken) is null)
            throw new DomainValidationException("The player has not joined the selected season.");
        return published.Definition.ContextFor(0);
    }

    public async Task<SeasonWalletSnapshot> ApplyAsync(
        Guid playerId, SeasonContext context, long goldDelta, long fragmentDelta, long markDelta,
        string reason, string requestId, SeasonWalletPurpose purpose, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        ArgumentNullException.ThrowIfNull(context);
        var businessHash = WalletRequestHash(context, goldDelta, fragmentDelta, markDelta, reason, purpose, "wallet-only");
        var result = await ApplyWithinTransactionAsync(connection, transaction, playerId, context,
            goldDelta, fragmentDelta, markDelta, reason, requestId, purpose, timeProvider.GetUtcNow(), businessHash, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return result;
    }

    /// <summary>Item grants and their idempotency record must share this caller-owned transaction.</summary>
    public static async Task<SeasonWalletSnapshot> ApplyWithinTransactionAsync(
        NpgsqlConnection connection, NpgsqlTransaction transaction, Guid playerId, SeasonContext context,
        long goldDelta, long fragmentDelta, long markDelta, string reason, string requestId,
        SeasonWalletPurpose purpose, DateTimeOffset now, string businessRequestHash, CancellationToken cancellationToken,
        long blueprintDelta = 0, long orangeBlueprintDelta = 0)
    {
        if (!Enum.IsDefined(purpose) || (goldDelta == 0 && fragmentDelta == 0 && markDelta == 0 && blueprintDelta == 0 && orangeBlueprintDelta == 0))
            throw new DomainValidationException("The season wallet operation is invalid.");
        if (string.IsNullOrWhiteSpace(reason) || reason.Length > 80 ||
            reason.Any(character => !char.IsAsciiLetterOrDigit(character) && character is not '.' and not '_' and not '-') ||
            string.IsNullOrWhiteSpace(requestId) || requestId.Length > 80 || requestId.Any(char.IsControl))
            throw new DomainValidationException("The season wallet request identity is invalid.");
        if (businessRequestHash.Length != 64 || businessRequestHash.Any(character => !char.IsAsciiHexDigitLower(character)))
            throw new DomainValidationException("The season wallet business request hash is invalid.");
        await LockPlayerAsync(connection, transaction, playerId, cancellationToken);
        var definition = await ValidateContextAsync(connection, transaction, context, cancellationToken);
        var hash = WalletRequestHash(context, goldDelta, fragmentDelta, markDelta, reason, purpose, businessRequestHash,blueprintDelta,orangeBlueprintDelta);
        await using (var replay = new NpgsqlCommand("""
            SELECT request_hash,gold_after,fragments_after,marks_after,wallet_version,archived_at,blueprints_after,orange_blueprints_after
            FROM season_wallet_operations WHERE player_id=$1 AND season_id=$2 AND reason=$3 AND request_id=$4
            """, connection, transaction))
        {
            replay.Parameters.AddWithValue(playerId); replay.Parameters.AddWithValue(context.SeasonId);
            replay.Parameters.AddWithValue(reason); replay.Parameters.AddWithValue(requestId);
            await using var reader = await replay.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                if (reader.GetString(0) != hash)
                    throw new DomainValidationException("The season wallet request was reused with different parameters.");
                return new(playerId, context.SeasonId, reader.GetInt64(1), reader.GetInt64(2), reader.GetInt64(3),
                    reader.GetInt64(4), reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5),reader.GetInt64(6),reader.GetInt64(7));
            }
        }
        var wallet = await ReadWalletAsync(connection, transaction, playerId, context.SeasonId, true, cancellationToken)
            ?? throw new DomainValidationException("The player has not joined the selected season.");
        if (now < definition.StartsAtUtc)
            throw new DomainValidationException("The selected season has not started.");
        switch (purpose)
        {
            case SeasonWalletPurpose.General when wallet.ArchivedAt is not null || !definition.Contains(now):
                throw new DomainValidationException("The selected season wallet is closed for new actions.");
            case SeasonWalletPurpose.PermanentWeaponEnhancement when goldDelta != 0 || markDelta != 0 || fragmentDelta >= 0 || blueprintDelta != 0 || orangeBlueprintDelta != 0:
                throw new DomainValidationException("Only fragments may fund a permanent weapon upgrade.");
            case SeasonWalletPurpose.LateSettlement when goldDelta < 0 || fragmentDelta < 0 || markDelta < 0 || blueprintDelta < 0 || orangeBlueprintDelta < 0:
                throw new DomainValidationException("Late settlement may only credit its original season.");
        }
        long gold, fragments, marks, version, blueprints, orangeBlueprints;
        try
        {
            gold = checked(wallet.Gold + goldDelta);
            fragments = checked(wallet.EquipmentFragments + fragmentDelta);
            marks = checked(wallet.ChallengeMarks + markDelta);
            version = checked(wallet.Version + 1);
            blueprints = checked(wallet.BlueprintMarks + blueprintDelta);
            orangeBlueprints = checked(wallet.OrangeBlueprintMarks + orangeBlueprintDelta);
        }
        catch (OverflowException) { throw new DomainValidationException("The season wallet amount exceeds the supported range."); }
        if (gold < 0 || fragments < 0 || marks < 0 || blueprints < 0 || orangeBlueprints < 0)
            throw new DomainValidationException("The season wallet balance is insufficient.");
        await using (var update = new NpgsqlCommand("""
            UPDATE player_season_wallets SET gold=$3,equipment_fragments=$4,challenge_marks=$5,version=$6,
                blueprint_marks=$7,orange_blueprint_marks=$8
            WHERE player_id=$1 AND season_id=$2
            """, connection, transaction))
        {
            update.Parameters.AddWithValue(playerId); update.Parameters.AddWithValue(context.SeasonId);
            update.Parameters.AddWithValue(gold); update.Parameters.AddWithValue(fragments);
            update.Parameters.AddWithValue(marks); update.Parameters.AddWithValue(version);
            update.Parameters.AddWithValue(blueprints);update.Parameters.AddWithValue(orangeBlueprints);
            await update.ExecuteNonQueryAsync(cancellationToken);
        }
        foreach (var (currency, delta, balance) in new[] { ("Gold", goldDelta, gold),
                     ("EquipmentFragments", fragmentDelta, fragments), ("ChallengeMarks", markDelta, marks),
                     ("BlueprintMarks",blueprintDelta,blueprints),("OrangeBlueprintMarks",orangeBlueprintDelta,orangeBlueprints) })
        {
            if (delta == 0) continue;
            await using var ledger = new NpgsqlCommand("""
                INSERT INTO economy_ledger
                    (ledger_id,player_id,request_id,currency,delta,balance_after,reason,created_at,season_id,source_kind,
                     difficulty_id,ruleset_id,config_version,stats_version)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
                """, connection, transaction);
            ledger.Parameters.AddWithValue(Guid.NewGuid()); ledger.Parameters.AddWithValue(playerId);
            ledger.Parameters.AddWithValue(requestId); ledger.Parameters.AddWithValue(currency);
            ledger.Parameters.AddWithValue(delta); ledger.Parameters.AddWithValue(balance);
            ledger.Parameters.AddWithValue(reason); ledger.Parameters.AddWithValue(now);
            ledger.Parameters.AddWithValue(context.SeasonId); ledger.Parameters.AddWithValue(purpose.ToString());
            ledger.Parameters.AddWithValue(context.DifficultyId); ledger.Parameters.AddWithValue(context.RulesetId);
            ledger.Parameters.AddWithValue(context.ConfigVersion); ledger.Parameters.AddWithValue(context.StatsVersion);
            await ledger.ExecuteNonQueryAsync(cancellationToken);
        }
        await using (var operation = new NpgsqlCommand("""
            INSERT INTO season_wallet_operations
                (player_id,season_id,reason,request_id,request_hash,gold_after,fragments_after,marks_after,wallet_version,archived_at,created_at,blueprints_after,orange_blueprints_after)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
            """, connection, transaction))
        {
            operation.Parameters.AddWithValue(playerId); operation.Parameters.AddWithValue(context.SeasonId);
            operation.Parameters.AddWithValue(reason); operation.Parameters.AddWithValue(requestId);
            operation.Parameters.AddWithValue(hash); operation.Parameters.AddWithValue(gold);
            operation.Parameters.AddWithValue(fragments); operation.Parameters.AddWithValue(marks);
            operation.Parameters.AddWithValue(version);
            operation.Parameters.AddWithValue(NpgsqlTypes.NpgsqlDbType.TimestampTz, (object?)wallet.ArchivedAt ?? DBNull.Value);
            operation.Parameters.AddWithValue(now);
            operation.Parameters.AddWithValue(blueprints);operation.Parameters.AddWithValue(orangeBlueprints);
            await operation.ExecuteNonQueryAsync(cancellationToken);
        }
        return wallet with { Gold = gold, EquipmentFragments = fragments, ChallengeMarks = marks, Version = version,
            BlueprintMarks=blueprints,OrangeBlueprintMarks=orangeBlueprints };
    }

    private static string WalletRequestHash(SeasonContext context, long gold, long fragments, long marks,
        string reason, SeasonWalletPurpose purpose, string businessHash,long blueprints=0,long orangeBlueprints=0)
    {
        var parts = new[] { "v2", context.SeasonId, context.DifficultyId, context.RulesetId, context.ConfigVersion,
            context.StatsVersion, gold.ToString(CultureInfo.InvariantCulture), fragments.ToString(CultureInfo.InvariantCulture),
            marks.ToString(CultureInfo.InvariantCulture), reason, purpose.ToString(), businessHash };
        if(blueprints!=0 || orangeBlueprints!=0)
            parts=["v3-blueprints",..parts,blueprints.ToString(CultureInfo.InvariantCulture),orangeBlueprints.ToString(CultureInfo.InvariantCulture)];
        return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', parts))));
    }

    private static async Task LockPlayerAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        Guid playerId, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("SELECT user_id FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction);
        command.Parameters.AddWithValue(playerId);
        if (await command.ExecuteScalarAsync(cancellationToken) is null)
            throw new DomainValidationException("The player was not found.");
    }

    private static async Task<SeasonDefinition> ValidateContextAsync(NpgsqlConnection connection,
        NpgsqlTransaction? transaction, SeasonContext context, CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(context);
        var published = await ReadDefinitionAsync(connection, transaction, context.SeasonId, cancellationToken)
            ?? throw new DomainValidationException("The season configuration has not been published.");
        published.Definition.ContextFor(context.Difficulty).RequireSameDomain(context);
        return published.Definition;
    }

    private static async Task<(SeasonDefinition Definition, string Hash)?> ReadDefinitionAsync(
        NpgsqlConnection connection, NpgsqlTransaction? transaction, string seasonId, CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand("""
            SELECT season_id,ruleset_id,config_version,stats_version,starts_at,ends_at,highest_open_difficulty,config_sha256
            FROM season_definitions WHERE season_id=$1 AND ruleset_id='season-v1'
            """, connection, transaction);
        command.Parameters.AddWithValue(seasonId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? (ReadDefinition(reader), reader.GetString(7)) : null;
    }

    private static SeasonDefinition ReadDefinition(NpgsqlDataReader reader) => new(
        reader.GetString(0), reader.GetString(1), reader.GetString(2), reader.GetString(3),
        reader.GetFieldValue<DateTimeOffset>(4), reader.GetFieldValue<DateTimeOffset>(5), reader.GetInt16(6));

    private static async Task<SeasonWalletSnapshot?> ReadWalletAsync(NpgsqlConnection connection,
        NpgsqlTransaction? transaction, Guid playerId, string seasonId, bool lockRow, CancellationToken cancellationToken)
    {
        var sql = "SELECT gold,equipment_fragments,challenge_marks,version,archived_at,blueprint_marks,orange_blueprint_marks FROM player_season_wallets WHERE player_id=$1 AND season_id=$2";
        if (lockRow) sql += " FOR UPDATE";
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue(playerId); command.Parameters.AddWithValue(seasonId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken)
            ? new(playerId, seasonId, reader.GetInt64(0), reader.GetInt64(1), reader.GetInt64(2), reader.GetInt64(3),
                reader.IsDBNull(4) ? null : reader.GetFieldValue<DateTimeOffset>(4),reader.GetInt64(5),reader.GetInt64(6))
            : null;
    }
}
