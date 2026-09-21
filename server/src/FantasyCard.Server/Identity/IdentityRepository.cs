using FantasyCard.Domain.Players;
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

        await provisioningService.ProvisionAsync(
            connection,
            transaction,
            profile.UserId,
            profile.DisplayName,
            now,
            cancellationToken);

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
            ? new List<(string Title, string Body, object Attachments)>
            {
                ("测试邮件2：橙紫双词缀套装", "test2 测试账号奖励：头部橙色、其余紫色的同词缀套装，每件带效果词缀和第二词缀。", MixedEquipmentSet("Orange", "Purple", "Metal", "Bulwark", "DrawInterval")),
                ("测试邮件2：装备碎片", "test2 测试账号奖励：装备碎片 100000。", new[] { new { kind = "EquipmentFragments", amount = 100000L } })
            }
            : new List<(string Title, string Body, object Attachments)>
        {
            ("测试邮件：金币", "测试账号奖励：金币 100000。", new[] { new { kind = "Gold", amount = 100000L } }),
            ("测试邮件：魂晶", "测试账号奖励：各类魂晶各 100000。", new object[] {
                new { kind = "WarriorSoul", amount = 100000L }, new { kind = "PriestSoul", amount = 100000L },
                new { kind = "MageSoul", amount = 100000L }, new { kind = "GuardianSoul", amount = 100000L } }),
            ("测试邮件：白色火系装备", "测试账号奖励：白色火系装备一套。", EquipmentSet("White", "Fire")),
            ("测试邮件：绿色水系装备", "测试账号奖励：绿色水系装备一套。", EquipmentSet("Green", "Water")),
            ("测试邮件：蓝色土系装备", "测试账号奖励：蓝色土系装备一套。", EquipmentSet("Blue", "Earth")),
            ("测试邮件：紫色木系装备", "测试账号奖励：紫色木系装备一套。", EquipmentSet("Purple", "Wood")),
            ("测试邮件：橙色金系装备", "测试账号奖励：橙色金系装备一套。", EquipmentSet("Orange", "Metal"))
        };
        foreach (var mail in mails)
        {
            await using var command = new NpgsqlCommand("INSERT INTO mail_messages(mail_id,player_id,title,body,sender,attachments_json,sent_at) SELECT $1,$2,$3,$4,'System',$5::jsonb,$6 WHERE NOT EXISTS (SELECT 1 FROM mail_messages WHERE player_id=$2 AND title=$3)", connection, transaction);
            command.Parameters.AddWithValue(Guid.CreateVersion7());
            command.Parameters.AddWithValue(playerId);
            command.Parameters.AddWithValue(mail.Title);
            command.Parameters.AddWithValue(mail.Body);
            command.Parameters.AddWithValue(JsonSerializer.Serialize(mail.Attachments));
            command.Parameters.AddWithValue(now);
            await command.ExecuteNonQueryAsync(cancellationToken);

            // Test accounts may already have a mail created by an older build.
            // Refresh only its deterministic display payload; claimed_at is left
            // untouched, so this never grants the reward a second time.
            await using var repair = new NpgsqlCommand(
                "UPDATE mail_messages SET attachments_json=$1::jsonb,body=$2,version=version+1 WHERE player_id=$3 AND title=$4 AND (attachments_json IS DISTINCT FROM $1::jsonb OR body IS DISTINCT FROM $2)",
                connection, transaction);
            repair.Parameters.AddWithValue(JsonSerializer.Serialize(mail.Attachments));
            repair.Parameters.AddWithValue(mail.Body);
            repair.Parameters.AddWithValue(playerId);
            repair.Parameters.AddWithValue(mail.Title);
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
