using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Common;

public sealed class IdempotencyConflictException : Exception;

public static class PersistentIdempotency
{
    public static string Hash<T>(T request) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            JsonSerializer.Serialize(request)))).ToLowerInvariant();

    public static async Task<TResponse?> ReadAsync<TResponse>(
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

    public static async Task WriteAsync<TResponse>(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        Guid playerId,
        string scope,
        string requestId,
        string requestHash,
        TResponse response,
        DateTimeOffset now,
        CancellationToken cancellationToken)
        where TResponse : class
    {
        await using var command = new NpgsqlCommand(
            "INSERT INTO idempotency_records(player_id,scope,request_id,request_hash,response_json,created_at,expires_at) VALUES($1,$2,$3,$4,$5,$6,$7)",
            connection,
            transaction);
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue(scope);
        command.Parameters.AddWithValue(requestId);
        command.Parameters.AddWithValue(requestHash);
        command.Parameters.Add(new NpgsqlParameter
        {
            NpgsqlDbType = NpgsqlDbType.Jsonb,
            Value = JsonSerializer.Serialize(response)
        });
        command.Parameters.AddWithValue(now);
        command.Parameters.AddWithValue(now.AddDays(7));
        await command.ExecuteNonQueryAsync(cancellationToken);
    }
}

public sealed record IdempotencyAcknowledgement(bool Succeeded = true);
