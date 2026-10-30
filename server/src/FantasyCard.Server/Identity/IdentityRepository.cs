using FantasyCard.Domain.Players;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Players;
using FantasyCard.Server.Progression;
using Npgsql;
using NpgsqlTypes;
using System.Text.Json;

namespace FantasyCard.Server.Identity;

public sealed record SessionLookupResult(PlayerProfile? Player, bool IsExpired);

public sealed record ExpiredDataCleanupResult(
    int Sessions,
    int IdempotencyRecords,
    int RoomEvents,
    int Preparations,
    int MatchTickets);

public sealed class IdentityRepository(
    NpgsqlDataSource dataSource,
    PlayerProvisioningService provisioningService)
{
    private static readonly string[] TestEquipmentSlots = ["Head", "Chest", "Hands", "Legs", "Feet"];
    public async Task<PlayerProfile> SignInLocalAsync(
        string deviceId,
        string displayName,
        byte[] tokenHash,
        DateTimeOffset now,
        DateTimeOffset expiresAt,
        CancellationToken cancellationToken)
    {
        // Keep deviceId in the existing API for client compatibility; it no longer selects the account.
        return await SignInExternalAsync(
            "local-name", displayName, displayName, tokenHash, now, expiresAt, cancellationToken);
    }

    public async Task<PlayerProfile> SignInExternalAsync(
        string provider,
        string externalSubject,
        string displayName,
        byte[] tokenHash,
        DateTimeOffset now,
        DateTimeOffset expiresAt,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);

        if (string.Equals(provider, "local-name", StringComparison.Ordinal))
        {
            displayName = PlayerProfile.NormalizeDisplayName(displayName);
            // Use the database's normalization and casing rules for both the account key and its lock.
            await using var nameKeyCommand = new NpgsqlCommand(
                "SELECT lower(normalize(btrim($1), NFKC))",
                connection,
                transaction);
            nameKeyCommand.Parameters.AddWithValue(displayName);
            externalSubject = (string)(await nameKeyCommand.ExecuteScalarAsync(cancellationToken))!;
        }

        await using (var lockCommand = new NpgsqlCommand(
            "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))",
            connection,
            transaction))
        {
            lockCommand.Parameters.AddWithValue(provider + ":" + externalSubject);
            await lockCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        var profile = await FindByExternalIdentityAsync(connection, transaction, provider, externalSubject, cancellationToken);
        var created = profile is null;
        if (profile is null)
        {
            profile = PlayerProfile.Create(Guid.CreateVersion7(), displayName, now);
            await InsertPlayerAsync(connection, transaction, profile, provider, externalSubject, cancellationToken);
        }

        await using (var ban = new NpgsqlCommand("SELECT 1 FROM player_bans WHERE player_id=$1", connection, transaction))
        {
            ban.Parameters.AddWithValue(profile.UserId);
            if (await ban.ExecuteScalarAsync(cancellationToken) is not null)
                throw new PlayerBannedException();
        }

        if (created || !await provisioningService.IsProvisionedAsync(
                connection, transaction, profile.UserId, cancellationToken))
        {
            await provisioningService.ProvisionAsync(
                connection, transaction, profile.UserId, now, cancellationToken);
        }

        if (string.Equals(provider, "local-name", StringComparison.Ordinal))
        {
            if (externalSubject.StartsWith("test2_", StringComparison.OrdinalIgnoreCase))
                await SeedTestMailAsync(connection, transaction, profile.UserId, now, true, cancellationToken);
            else if (externalSubject.StartsWith("test_", StringComparison.OrdinalIgnoreCase))
                await SeedTestMailAsync(connection, transaction, profile.UserId, now, false, cancellationToken);
        }

        await using (var sessionCommand = new NpgsqlCommand(
            """
            INSERT INTO player_sessions(session_id, player_id, token_hash, expires_at, created_at)
            VALUES ($1, $2, $3, $4, $5)
            """,
            connection,
            transaction))
        {
            sessionCommand.Parameters.AddWithValue(Guid.CreateVersion7());
            sessionCommand.Parameters.AddWithValue(profile.UserId);
            sessionCommand.Parameters.Add(new NpgsqlParameter
            {
                NpgsqlDbType = NpgsqlDbType.Bytea,
                Value = tokenHash
            });
            sessionCommand.Parameters.AddWithValue(expiresAt);
            sessionCommand.Parameters.AddWithValue(now);
            await sessionCommand.ExecuteNonQueryAsync(cancellationToken);
        }

        await transaction.CommitAsync(cancellationToken);
        return profile;
    }

    private static async Task SeedTestMailAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        DateTimeOffset now,
        bool advancedEquipmentSet,
        CancellationToken cancellationToken)
    {
        var mails = advancedEquipmentSet
            ? new List<(string TemplateId, object Attachments)>
            {
                ("seed2_mixed_set", MixedEquipmentSet("Orange", "Purple", "Metal", "Bulwark", "DrawInterval")),
                ("seed2_fragments", new[] { new { kind = "EquipmentFragments", amount = 100000L } })
            }
            : new List<(string TemplateId, object Attachments)>
        {
            ("seed_gold", new[] { new { kind = "Gold", amount = 100000L } }),
            ("seed_souls", new object[] {
                new { kind = "WarriorSoul", amount = 100000L }, new { kind = "PriestSoul", amount = 100000L },
                new { kind = "MageSoul", amount = 100000L }, new { kind = "GuardianSoul", amount = 100000L } }),
            ("seed_white_fire", EquipmentSet("White", "Fire")),
            ("seed_green_water", EquipmentSet("Green", "Water")),
            ("seed_blue_earth", EquipmentSet("Blue", "Earth")),
            ("seed_purple_wood", EquipmentSet("Purple", "Wood")),
            ("seed_orange_metal", EquipmentSet("Orange", "Metal"))
        };
        var catalog = SystemMailCatalog.Current;
        var sender = catalog.Sender("system");
        foreach (var (templateId, attachments) in mails)
        {
            var mail = catalog.Render(templateId);
            var attachmentsJson = JsonSerializer.Serialize(attachments);
            await using var command = new NpgsqlCommand(
                "INSERT INTO mail_messages(mail_id,player_id,title,body,title_en,body_en,sender,attachments_json,sent_at,template_id,template_args,sender_role) SELECT $1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,'{}'::jsonb,'system' WHERE NOT EXISTS (SELECT 1 FROM mail_messages WHERE player_id=$2 AND (template_id=$10 OR title=$3))",
                connection, transaction);
            command.Parameters.AddWithValue(Guid.CreateVersion7());
            command.Parameters.AddWithValue(playerId);
            command.Parameters.AddWithValue(mail.Title);
            command.Parameters.AddWithValue(mail.Body);
            command.Parameters.AddWithValue(mail.TitleEn);
            command.Parameters.AddWithValue(mail.BodyEn);
            command.Parameters.AddWithValue(sender);
            command.Parameters.AddWithValue(attachmentsJson);
            command.Parameters.AddWithValue(now);
            command.Parameters.AddWithValue(templateId);
            await command.ExecuteNonQueryAsync(cancellationToken);

            // Repair only deterministic seed mail, never similarly titled admin prose.
            // Preserve mail identity, claim/read timestamps and the existing reward behavior.
            await using var repair = new NpgsqlCommand(
                "UPDATE mail_messages SET attachments_json=$1::jsonb,body=$2,title_en=$3,body_en=$4,template_id=$7,template_args='{}'::jsonb,sender_role='system',version=version+1 WHERE player_id=$5 AND (template_id=$7 OR (template_id='' AND title=$6)) AND (sender_role='system' OR (sender_role='' AND sender=$8)) AND (attachments_json IS DISTINCT FROM $1::jsonb OR body IS DISTINCT FROM $2 OR title_en IS DISTINCT FROM $3 OR body_en IS DISTINCT FROM $4 OR template_id IS DISTINCT FROM $7 OR template_args IS DISTINCT FROM '{}'::jsonb OR sender_role IS DISTINCT FROM 'system')",
                connection, transaction);
            repair.Parameters.AddWithValue(attachmentsJson);
            repair.Parameters.AddWithValue(mail.Body);
            repair.Parameters.AddWithValue(mail.TitleEn);
            repair.Parameters.AddWithValue(mail.BodyEn);
            repair.Parameters.AddWithValue(playerId);
            repair.Parameters.AddWithValue(mail.Title);
            repair.Parameters.AddWithValue(templateId);
            repair.Parameters.AddWithValue(sender);
            await repair.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    private static object[] EquipmentSet(string quality, string element, string? effectAffix = null, string? secondaryTrait = null) =>
        TestEquipmentSlots
            .Select(slot => (object)new
            {
                kind = "Equipment",
                amount = 1L,
                itemId = $"{quality}|{element}|{slot}",
                effectAffix,
                secondaryTrait
            })
            .ToArray();

    private static object[] MixedEquipmentSet(
        string firstQuality,
        string otherQuality,
        string element,
        string? effectAffix = null,
        string? secondaryTrait = null) =>
        TestEquipmentSlots
            .Select((slot, index) => (object)new
            {
                kind = "Equipment",
                amount = 1L,
                itemId = $"{(index == 0 ? firstQuality : otherQuality)}|{element}|{slot}",
                effectAffix,
                secondaryTrait
            })
            .ToArray();

    public async Task<SessionLookupResult> FindByTokenHashAsync(
        byte[] tokenHash,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var command = dataSource.CreateCommand(
            """
            SELECT p.user_id, p.display_name, p.selected_class, p.version, p.created_at, p.updated_at, s.expires_at
            FROM player_sessions s
            JOIN players p ON p.user_id = s.player_id
            WHERE s.token_hash = $1 AND NOT EXISTS (SELECT 1 FROM player_bans b WHERE b.player_id=p.user_id)
            """);
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Bytea,
            Value = tokenHash
        });
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            return new SessionLookupResult(null, false);
        var expiresAt = reader.GetFieldValue<DateTimeOffset>(6);
        return expiresAt <= now
            ? new SessionLookupResult(null, true)
            : new SessionLookupResult(ReadProfile(reader), false);
    }

    public async Task StoreRealtimeTicketAsync(
        Guid playerId,
        byte[] ticketHash,
        DateTimeOffset now,
        DateTimeOffset expiresAt,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "INSERT INTO realtime_tickets(ticket_hash,player_id,expires_at,created_at) VALUES ($1,$2,$3,$4)",
            connection);
        command.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Bytea, Value = ticketHash });
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(expiresAt);
        command.Parameters.AddWithValue(now);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    public async Task<PlayerProfile?> ConsumeRealtimeTicketAsync(
        byte[] ticketHash,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var consume = new NpgsqlCommand(
            "UPDATE realtime_tickets SET used_at=$1 WHERE ticket_hash=$2 AND used_at IS NULL AND expires_at > $1 RETURNING player_id",
            connection, transaction);
        consume.Parameters.AddWithValue(now);
        consume.Parameters.Add(new NpgsqlParameter { NpgsqlDbType = NpgsqlDbType.Bytea, Value = ticketHash });
        var playerId = await consume.ExecuteScalarAsync(cancellationToken);
        if (playerId is not Guid id)
        {
            await transaction.RollbackAsync(cancellationToken);
            return null;
        }

        await using var profileCommand = new NpgsqlCommand(
            "SELECT p.user_id,p.display_name,p.selected_class,p.version,p.created_at,p.updated_at FROM players p WHERE p.user_id=$1 AND NOT EXISTS (SELECT 1 FROM player_bans b WHERE b.player_id=p.user_id)",
            connection, transaction);
        profileCommand.Parameters.AddWithValue(id);
        await using var reader = await profileCommand.ExecuteReaderAsync(cancellationToken);
        var profile = await reader.ReadAsync(cancellationToken) ? ReadProfile(reader) : null;
        await reader.CloseAsync();
        await transaction.CommitAsync(cancellationToken);
        return profile;
    }

    public async Task<ExpiredDataCleanupResult> CleanupExpiredDataAsync(
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        var tickets = await ExecuteCleanupAsync(
            connection,
            transaction,
            "UPDATE match_tickets AS t SET status='Cancelled' FROM preparations AS p WHERE t.preparation_id=p.preparation_id AND t.status='Queued' AND p.status='Queued' AND p.expires_at <= $1",
            now,
            cancellationToken);
        var preparations = await ExecuteCleanupAsync(
            connection,
            transaction,
            "UPDATE preparations SET status='Expired' WHERE status IN ('Active','Queued') AND expires_at <= $1",
            now,
            cancellationToken);
        var sessions = await ExecuteCleanupAsync(
            connection, transaction, "DELETE FROM player_sessions WHERE expires_at <= $1", now, cancellationToken);
        _ = await ExecuteCleanupAsync(
            connection, transaction, "DELETE FROM realtime_tickets WHERE expires_at <= $1 OR used_at IS NOT NULL", now, cancellationToken);
        var idempotencyRecords = await ExecuteCleanupAsync(
            connection, transaction, "DELETE FROM idempotency_records WHERE expires_at <= $1", now, cancellationToken);
        var roomEvents = await ExecuteCleanupAsync(
            connection, transaction, "DELETE FROM room_event_buffers WHERE expires_at <= $1", now, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return new ExpiredDataCleanupResult(sessions, idempotencyRecords, roomEvents, preparations, tickets);
    }

    private static async Task<int> ExecuteCleanupAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        string sql,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue(now);
        return await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static async Task<PlayerProfile?> FindByExternalIdentityAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        string provider,
        string externalSubject,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(
            """
            SELECT p.user_id, p.display_name, p.selected_class, p.version, p.created_at, p.updated_at
            FROM external_identities i
            JOIN players p ON p.user_id = i.player_id
            WHERE i.provider = $1 AND i.external_subject = $2
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(provider);
        command.Parameters.AddWithValue(externalSubject);

        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? ReadProfile(reader) : null;
    }

    private static async Task InsertPlayerAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        PlayerProfile profile,
        string provider,
        string externalSubject,
        CancellationToken cancellationToken)
    {
        // 注意：Npgsql 在命令携带参数时走扩展协议（prepared statement），
        // PostgreSQL 不允许一条 prepared statement 含多条 SQL（42601），必须拆成两条命令。
        await using (var playerCommand = new NpgsqlCommand(
            """
            INSERT INTO players(user_id, display_name, selected_class, version, created_at, updated_at)
            VALUES ($1, $2, NULL, $3, $4, $5)
            """,
            connection,
            transaction))
        {
            playerCommand.Parameters.AddWithValue(profile.UserId);
            playerCommand.Parameters.AddWithValue(profile.DisplayName);
            playerCommand.Parameters.AddWithValue(profile.Version);
            playerCommand.Parameters.AddWithValue(profile.CreatedAt);
            playerCommand.Parameters.AddWithValue(profile.UpdatedAt);
            try
            {
                await playerCommand.ExecuteNonQueryAsync(cancellationToken);
            }
            catch (PostgresException exception) when (
                exception.SqlState == PostgresErrorCodes.UniqueViolation &&
                exception.ConstraintName == PlayerNameConflictException.UniqueIndexName)
            {
                throw new PlayerNameConflictException("Display name is already in use. Choose a different name.", exception);
            }
        }

        await using (var identityCommand = new NpgsqlCommand(
            """
            INSERT INTO external_identities(provider, external_subject, player_id, created_at)
            VALUES ($1, $2, $3, $4)
            """,
            connection,
            transaction))
        {
            identityCommand.Parameters.AddWithValue(provider);
            identityCommand.Parameters.AddWithValue(externalSubject);
            identityCommand.Parameters.AddWithValue(profile.UserId);
            identityCommand.Parameters.AddWithValue(profile.CreatedAt);
            await identityCommand.ExecuteNonQueryAsync(cancellationToken);
        }
    }

    internal static PlayerProfile ReadProfile(NpgsqlDataReader reader)
    {
        var selectedClass = reader.IsDBNull(2)
            ? null
            : (HeroClass?)reader.GetInt16(2);

        return PlayerProfile.Rehydrate(
            reader.GetGuid(0),
            reader.GetString(1),
            selectedClass,
            reader.GetInt64(3),
            reader.GetFieldValue<DateTimeOffset>(4),
            reader.GetFieldValue<DateTimeOffset>(5));
    }
}
