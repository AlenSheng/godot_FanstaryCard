using FantasyCard.Contracts.Players;
using FantasyCard.Domain.Players;
using FantasyCard.Server.Common;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Players;

public enum UpdatePlayerResult
{
    Updated,
    VersionConflict,
    NotFound
}

public sealed record UpdatePlayerOutcome(
    UpdatePlayerResult Status,
    PlayerProfileResponse? Profile = null);

public sealed class PlayerRepository(NpgsqlDataSource dataSource)
{
    public async Task<UpdatePlayerOutcome> UpdateAsync(
        Guid playerId,
        UpdatePlayerProfileRequest request,
        string requestId,
        DateTimeOffset now,
        CancellationToken cancellationToken)
    {
        await using var connection = await dataSource.OpenConnectionAsync(cancellationToken);
        await using var transaction = await connection.BeginTransactionAsync(cancellationToken);
        PlayerProfile profile;
        await using (var read = new NpgsqlCommand(
            """
            SELECT user_id, display_name, selected_class, version, created_at, updated_at
            FROM players WHERE user_id = $1 FOR UPDATE
            """,
            connection,
            transaction))
        {
            read.Parameters.AddWithValue(playerId);
            await using var reader = await read.ExecuteReaderAsync(cancellationToken);
            if (!await reader.ReadAsync(cancellationToken))
                return new UpdatePlayerOutcome(UpdatePlayerResult.NotFound);
            profile = PlayerProfile.Rehydrate(
                reader.GetGuid(0),
                reader.GetString(1),
                reader.IsDBNull(2) ? null : (HeroClass?)reader.GetInt16(2),
                reader.GetInt64(3),
                reader.GetFieldValue<DateTimeOffset>(4),
                reader.GetFieldValue<DateTimeOffset>(5));
        }

        var requestHash = PersistentIdempotency.Hash(request);
        var replay = await PersistentIdempotency.ReadAsync<PlayerProfileResponse>(
            connection, transaction, playerId, "player.update", requestId, requestHash, cancellationToken);
        if (replay is not null)
        {
            await transaction.CommitAsync(cancellationToken);
            return new UpdatePlayerOutcome(UpdatePlayerResult.Updated, replay);
        }
        if (profile.Version != request.ExpectedVersion)
            return new UpdatePlayerOutcome(UpdatePlayerResult.VersionConflict);

        profile.Update(request.DisplayName, request.SelectedClass.ToDomain(), now);
        await using var command = new NpgsqlCommand(
            """
            UPDATE players
            SET display_name = $1, selected_class = $2, version = $3, updated_at = $4
            WHERE user_id = $5 AND version = $6
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(profile.DisplayName);
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Smallint,
            Value = profile.SelectedClass is null
                ? DBNull.Value
                : (short)profile.SelectedClass.Value
        });
        command.Parameters.AddWithValue(profile.Version);
        command.Parameters.AddWithValue(profile.UpdatedAt);
        command.Parameters.AddWithValue(profile.UserId);
        command.Parameters.AddWithValue(request.ExpectedVersion);

        var affected = await command.ExecuteNonQueryAsync(cancellationToken);
        if (affected != 1) return new UpdatePlayerOutcome(UpdatePlayerResult.VersionConflict);

        var response = profile.ToResponse();
        await PersistentIdempotency.WriteAsync(
            connection, transaction, playerId, "player.update", requestId, requestHash, response, now, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return new UpdatePlayerOutcome(UpdatePlayerResult.Updated, response);
    }
}
