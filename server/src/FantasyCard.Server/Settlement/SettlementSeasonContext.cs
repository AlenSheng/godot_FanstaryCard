using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using FantasyCard.Contracts.Seasons;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Seasons;
using Npgsql;
using NpgsqlTypes;

namespace FantasyCard.Server.Settlement;

public sealed partial class SettlementRepository
{
    private sealed record SettlementContext(Guid MatchId, Guid RoomId, string ConfigVersion, SeasonContext? Season, string Status);
    private sealed record CommitRealm(SettlementContext Context, bool Active, DateTimeOffset Now, Guid PlayerId, bool RestoreLoadout);

    private static async Task<SettlementContext> ReadMatchContextAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        Guid matchId, CancellationToken ct)
    {
        await using var command = new NpgsqlCommand("SELECT room_id,config_version,season_id,difficulty,ruleset_id,stats_version,status FROM matches WHERE match_id=$1", connection, transaction);
        command.Parameters.AddWithValue(matchId);
        await using var reader = await command.ExecuteReaderAsync(ct);
        if (!await reader.ReadAsync(ct)) throw new InvalidOperationException("The settlement match is missing.");
        return new(matchId, reader.GetGuid(0), reader.GetString(1), ReadSeason(reader, 1), reader.GetString(6));
    }

    // Columns are config_version,season_id,difficulty_id,ruleset_id,stats_version.
    private static SeasonContext? ReadSeason(NpgsqlDataReader reader, int index) => reader.IsDBNull(index + 1) ? null
        : new SeasonContext(reader.GetString(index + 1), reader.GetString(index + 2)[1] - '0', reader.GetString(index + 3),
            reader.GetString(index), reader.GetString(index + 4));

    private static void AddContextParameters(NpgsqlCommand command, SettlementContext context)
    {
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)context.Season?.SeasonId ?? DBNull.Value);
        command.Parameters.AddWithValue(context.Season?.DifficultyId ?? "Standard");
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)context.Season?.RulesetId ?? DBNull.Value);
        command.Parameters.AddWithValue(context.ConfigVersion);
        command.Parameters.AddWithValue(NpgsqlDbType.Varchar, (object?)context.Season?.StatsVersion ?? DBNull.Value);
    }

    private static void RequireStoredContext(SeasonContext? stored, string? config, SettlementContext expected)
    {
        if (stored != expected.Season || config is not null && config != expected.ConfigVersion)
            throw new InvalidOperationException("The settlement context differs from its durable match.");
    }

    private async Task<CommitRealm> ReadCommitRealmAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        Guid settlementId, CancellationToken ct)
    {
        Guid matchId; Guid playerId; SeasonContext? stored; string? config;
        await using (var command = new NpgsqlCommand("SELECT match_id,player_id,config_version,season_id,difficulty_id,ruleset_id,stats_version FROM match_settlements WHERE settlement_id=$1", connection, transaction))
        {
            command.Parameters.AddWithValue(settlementId);
            await using var reader = await command.ExecuteReaderAsync(ct);
            if (!await reader.ReadAsync(ct)) throw new InvalidOperationException("The settlement record is missing.");
            matchId = reader.GetGuid(0); playerId = reader.GetGuid(1);
            config = reader.IsDBNull(2) ? null : reader.GetString(2); stored = ReadSeason(reader, 2);
        }
        var context = await ReadMatchContextAsync(connection, transaction, matchId, ct);
        RequireStoredContext(stored, config, context);
        var now = timeProvider.GetUtcNow();
        bool canRestore;
        await using (var preparation = new NpgsqlCommand("""
            SELECT NOT EXISTS (
                SELECT 1 FROM preparations p WHERE p.player_id=$1 AND p.status IN ('Active','Queued','Matched')
                AND p.preparation_id IS DISTINCT FROM (SELECT preparation_id FROM match_players WHERE match_id=$2 AND player_id=$1))
            """, connection, transaction))
        {
            preparation.Parameters.AddWithValue(playerId); preparation.Parameters.AddWithValue(matchId);
            canRestore = (bool)(await preparation.ExecuteScalarAsync(ct))!;
        }
        if (context.Season is null)
        {
            await using var legacy = new NpgsqlCommand("SELECT NOT EXISTS(SELECT 1 FROM season_definitions WHERE ruleset_id='season-v1' AND starts_at <= $1)", connection, transaction);
            legacy.Parameters.AddWithValue(now);
            var activeLegacy = (bool)(await legacy.ExecuteScalarAsync(ct))!;
            return new(context, activeLegacy, now, playerId, activeLegacy && canRestore);
        }
        await using var state = new NpgsqlCommand("""
            SELECT d.starts_at <= $3 AND d.ends_at > $3 AND w.archived_at IS NULL AND p.archived_at IS NULL
            FROM season_definitions d JOIN player_season_state p ON p.season_id=d.season_id AND p.player_id=$1
            JOIN player_season_wallets w ON w.player_id=p.player_id AND w.season_id=p.season_id
            WHERE d.season_id=$2
            """, connection, transaction);
        state.Parameters.AddWithValue(playerId); state.Parameters.AddWithValue(context.Season.SeasonId); state.Parameters.AddWithValue(now);
        var active = await state.ExecuteScalarAsync(ct);
        if (active is not bool value) throw new InvalidOperationException("The settlement player's original season membership is missing.");
        return new(context, value, now, playerId, value && canRestore);
    }

    private static async Task CreditSeasonWalletAsync(NpgsqlConnection connection, NpgsqlTransaction transaction,
        SettlementHoldRecord hold, CommitRealm realm, long gold, long fragments, CancellationToken ct)
    {
        var business = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
            JsonSerializer.Serialize(new { hold.SettlementId, hold.HoldId, realm.Context.MatchId, hold.AssetSnapshot }))));
        await SeasonRepository.ApplyWithinTransactionAsync(connection, transaction, hold.PlayerId, realm.Context.Season!,
            gold, fragments, 0, "settlement.commit", hold.HoldId.ToString("D"), SeasonWalletPurpose.LateSettlement,
            realm.Now, business, ct);
    }

    private static SeasonContextResponse? ToResponse(SeasonContext? season) => season is null ? null
        : new(season.SeasonId, season.DifficultyId, season.RulesetId, season.ConfigVersion, season.StatsVersion);
}
