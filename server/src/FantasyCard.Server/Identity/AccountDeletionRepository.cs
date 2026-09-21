using Npgsql;

namespace FantasyCard.Server.Identity;

public sealed record AccountDeletionStatus(
    Guid RequestId,
    string Status,
    DateTimeOffset RequestedAt,
    DateTimeOffset ScheduledFor,
    DateTimeOffset? CompletedAt,
    DateTimeOffset? CancelledAt);

public sealed class AccountDeletionRepository(NpgsqlDataSource dataSource)
{
    public async Task<AccountDeletionStatus> RequestAsync(
        Guid playerId,
        DateTimeOffset now,
        int coolingPeriodDays,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using (var lockCommand = new NpgsqlCommand(
            "SELECT 1 FROM players WHERE user_id=$1 FOR UPDATE", connection, transaction))
        {
            lockCommand.Parameters.AddWithValue(playerId);
            if (await lockCommand.ExecuteScalarAsync(cancellationToken) is null)
                throw new InvalidOperationException("Player does not exist.");
        }

        await using (var existing = new NpgsqlCommand(
            "SELECT request_id,status,requested_at,scheduled_for,completed_at,cancelled_at FROM account_deletion_requests WHERE player_id=$1 AND status='Requested' ORDER BY requested_at DESC LIMIT 1",
            connection, transaction))
        {
            existing.Parameters.AddWithValue(playerId);
            await using var reader = await existing.ExecuteReaderAsync(cancellationToken);
            if (await reader.ReadAsync(cancellationToken))
            {
                var result = Read(reader);
                await transaction.CommitAsync(cancellationToken);
                return result;
            }
        }

        var requestId = Guid.CreateVersion7();
        var scheduledFor = now.AddDays(coolingPeriodDays);
        await using (var insert = new NpgsqlCommand(
            "INSERT INTO account_deletion_requests(request_id,player_id,status,requested_at,scheduled_for) VALUES ($1,$2,'Requested',$3,$4)",
            connection, transaction))
        {
            insert.Parameters.AddWithValue(requestId);
            insert.Parameters.AddWithValue(playerId);
            insert.Parameters.AddWithValue(now);
            insert.Parameters.AddWithValue(scheduledFor);
            await insert.ExecuteNonQueryAsync(cancellationToken);
        }
        await transaction.CommitAsync(cancellationToken);
        return new AccountDeletionStatus(requestId, "Requested", now, scheduledFor, null, null);
    }

    public async Task<AccountDeletionStatus?> GetAsync(Guid playerId, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "SELECT request_id,status,requested_at,scheduled_for,completed_at,cancelled_at FROM account_deletion_requests WHERE player_id=$1 ORDER BY requested_at DESC LIMIT 1",
            connection);
        command.Parameters.AddWithValue(playerId);
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        return await reader.ReadAsync(cancellationToken) ? Read(reader) : null;
    }

    public async Task<bool> CancelAsync(Guid playerId, DateTimeOffset now, CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var command = new NpgsqlCommand(
            "UPDATE account_deletion_requests SET status='Cancelled',cancelled_at=$1 WHERE player_id=$2 AND status='Requested'",
            connection);
        command.Parameters.AddWithValue(now);
        command.Parameters.AddWithValue(playerId);
        return await command.ExecuteNonQueryAsync(cancellationToken) == 1;
    }

    public async Task<int> CompleteDueAsync(DateTimeOffset now, CancellationToken cancellationToken)
    {
        var completed = 0;
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        await using var due = new NpgsqlCommand(
            "SELECT request_id,player_id FROM account_deletion_requests WHERE status='Requested' AND scheduled_for <= $1 AND player_id IS NOT NULL ORDER BY scheduled_for FOR UPDATE SKIP LOCKED LIMIT 20",
            connection, transaction);
        due.Parameters.AddWithValue(now);
        await using var reader = await due.ExecuteReaderAsync(cancellationToken);
        var requests = new List<(Guid RequestId, Guid PlayerId)>();
        while (await reader.ReadAsync(cancellationToken))
            requests.Add((reader.GetGuid(0), reader.GetGuid(1)));
        await reader.CloseAsync();

        foreach (var request in requests)
        {
            await ExecuteAsync(connection, transaction, "DELETE FROM match_tickets WHERE player_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "DELETE FROM match_players WHERE player_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "DELETE FROM settlement_asset_holds WHERE player_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "DELETE FROM match_settlements WHERE player_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "DELETE FROM market_transactions WHERE buyer_id=$1 OR seller_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "DELETE FROM red_equipment_weekly_quotas WHERE player_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "UPDATE relic_piles SET dead_player_id='00000000-0000-0000-0000-000000000000' WHERE dead_player_id=$1", request.PlayerId, cancellationToken);
            await ExecuteAsync(connection, transaction, "DELETE FROM players WHERE user_id=$1", request.PlayerId, cancellationToken);
            await using var complete = new NpgsqlCommand(
                "UPDATE account_deletion_requests SET status='Completed',completed_at=$1 WHERE request_id=$2",
                connection, transaction);
            complete.Parameters.AddWithValue(now);
            complete.Parameters.AddWithValue(request.RequestId);
            await complete.ExecuteNonQueryAsync(cancellationToken);
            completed++;
        }

        await transaction.CommitAsync(cancellationToken);
        return completed;
    }

    private static async Task ExecuteAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        string sql,
        Guid playerId,
        CancellationToken cancellationToken)
    {
        await using var command = new NpgsqlCommand(sql, connection, transaction);
        command.Parameters.AddWithValue(playerId);
        await command.ExecuteNonQueryAsync(cancellationToken);
    }

    private static AccountDeletionStatus Read(NpgsqlDataReader reader) => new(
        reader.GetGuid(0), reader.GetString(1), reader.GetFieldValue<DateTimeOffset>(2),
        reader.GetFieldValue<DateTimeOffset>(3), reader.IsDBNull(4) ? null : reader.GetFieldValue<DateTimeOffset>(4),
        reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5));
}
