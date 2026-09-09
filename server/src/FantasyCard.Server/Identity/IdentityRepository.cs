using FantasyCard.Domain.Players;
using FantasyCard.Server.Progression;
using Npgsql;
using NpgsqlTypes;

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
    public async Task<PlayerProfile> SignInLocalAsync(
        string deviceId,
        string displayName,
        byte[] tokenHash,
        DateTimeOffset now,
        DateTimeOffset expiresAt,
        CancellationToken cancellationToken)
    {
        return await SignInExternalAsync(
            "local", deviceId, displayName, tokenHash, now, expiresAt, cancellationToken);
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

        await provisioningService.ProvisionAsync(
            connection,
            transaction,
            profile.UserId,
            now,
            cancellationToken);

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
            WHERE s.token_hash = $1
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
            await playerCommand.ExecuteNonQueryAsync(cancellationToken);
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
