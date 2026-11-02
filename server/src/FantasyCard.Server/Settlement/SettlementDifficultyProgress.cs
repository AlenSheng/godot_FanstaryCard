using System.Text.Json;
using Npgsql;

namespace FantasyCard.Server.Settlement;

public sealed partial class SettlementRepository
{
    private static async Task CreditDifficultyProgressAsync(NpgsqlConnection connection,NpgsqlTransaction transaction,
        SettlementContext context,Guid playerId,Guid settlementId,string result,JsonElement details,DateTimeOffset now,CancellationToken ct)
    {
        // Older persisted settlement details did not include authoritative cleared-cell proof.
        if (context.Season is not { } season || result != "Extracted" || details.ValueKind != JsonValueKind.Object || !details.TryGetProperty("difficultyProgress",out var progress)) return;
        if (progress.ValueKind != JsonValueKind.Object || !details.TryGetProperty("roomId",out var room) ||
            !room.TryGetGuid(out var roomId) || roomId != context.RoomId ||
            !progress.TryGetProperty("eliteCleared",out var elite) || elite.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
            !progress.TryGetProperty("bossCleared",out var boss) || boss.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
            throw new InvalidDataException("Difficulty completion requires authoritative room and cleared-cell proof.");
        int unlocked;
        await using (var state = new NpgsqlCommand("SELECT highest_unlocked_difficulty FROM player_season_state WHERE player_id=$1 AND season_id=$2 FOR UPDATE",connection,transaction))
        {
            state.Parameters.AddWithValue(playerId);state.Parameters.AddWithValue(season.SeasonId);
            unlocked = await state.ExecuteScalarAsync(ct) is short current ? current
                : throw new InvalidOperationException("Difficulty completion has no original seasonal membership.");
        }
        if (season.Difficulty > unlocked) throw new InvalidOperationException("The completed difficulty was not unlocked for this player.");
        await using (var insert = new NpgsqlCommand("""
            INSERT INTO season_difficulty_completions(match_id,player_id,settlement_id,season_id,difficulty_id,ruleset_id,config_version,stats_version,elite_cleared,boss_cleared,completed_at)
            VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11) ON CONFLICT(match_id,player_id) DO NOTHING
            """,connection,transaction))
        {
            insert.Parameters.AddWithValue(context.MatchId);insert.Parameters.AddWithValue(playerId);insert.Parameters.AddWithValue(settlementId);
            insert.Parameters.AddWithValue(season.SeasonId);insert.Parameters.AddWithValue(season.DifficultyId);insert.Parameters.AddWithValue(season.RulesetId);
            insert.Parameters.AddWithValue(season.ConfigVersion);insert.Parameters.AddWithValue(season.StatsVersion);
            insert.Parameters.AddWithValue(elite.GetBoolean());insert.Parameters.AddWithValue(boss.GetBoolean());insert.Parameters.AddWithValue(now);
            if (await insert.ExecuteNonQueryAsync(ct)==0) return;
        }
        var counts = new Dictionary<string,(long All,long Elite,long Boss)>(StringComparer.Ordinal);
        await using (var count = new NpgsqlCommand("""
            SELECT difficulty_id,count(*),count(*) FILTER(WHERE elite_cleared),count(*) FILTER(WHERE boss_cleared)
            FROM season_difficulty_completions WHERE player_id=$1 AND season_id=$2 GROUP BY difficulty_id
            """,connection,transaction))
        {
            count.Parameters.AddWithValue(playerId);count.Parameters.AddWithValue(season.SeasonId);
            await using var reader = await count.ExecuteReaderAsync(ct);
            while (await reader.ReadAsync(ct)) counts[reader.GetString(0)] = (reader.GetInt64(1),reader.GetInt64(2),reader.GetInt64(3));
        }
        while (unlocked < 5)
        {
            var previous = counts.GetValueOrDefault($"D{unlocked}");
            var qualifies = unlocked switch {0 => previous.All>=2,1 => previous.Elite>=1,2 => previous.Boss>=1,_ => previous.Boss>=2};
            if (!qualifies) break;
            unlocked++;
        }
        await using var update = new NpgsqlCommand("UPDATE player_season_state SET highest_unlocked_difficulty=GREATEST(highest_unlocked_difficulty,$3),version=version+1 WHERE player_id=$1 AND season_id=$2",connection,transaction);
        update.Parameters.AddWithValue(playerId);update.Parameters.AddWithValue(season.SeasonId);update.Parameters.AddWithValue((short)unlocked);
        await update.ExecuteNonQueryAsync(ct);
    }
}
