using System.Globalization;
using Npgsql;

namespace FantasyCard.Server.Progression;

public enum RedEquipmentDropSource
{
    ChaosBoss,
    ShopChest
}

public sealed record RedEquipmentQuotaSnapshot(
    string WeekKey,
    bool IsClaimed,
    RedEquipmentDropSource? Source,
    Guid? PlayerId,
    Guid? MatchId,
    Guid? EquipmentId,
    DateTimeOffset? ClaimedAt);

public static class RedEquipmentQuotaSchedule
{
    private static readonly TimeSpan ChinaOffset = TimeSpan.FromHours(8);

    public static string GetWeekKey(DateTimeOffset utc)
    {
        var businessDate = utc.ToOffset(ChinaOffset).AddHours(-4).Date;
        var daysSinceMonday = ((int)businessDate.DayOfWeek + 6) % 7;
        return DateOnly.FromDateTime(businessDate.AddDays(-daysSinceMonday))
            .ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
    }
}

public sealed class RedEquipmentQuotaRepository(NpgsqlDataSource dataSource, TimeProvider timeProvider)
{
    public async Task<RedEquipmentQuotaSnapshot> GetCurrentAsync(CancellationToken cancellationToken)
    {
        var weekKey = RedEquipmentQuotaSchedule.GetWeekKey(timeProvider.GetUtcNow());
        await using var command = dataSource.CreateCommand(
            "SELECT red_dropped_this_week,source,player_id,match_id,equipment_id,claimed_at FROM red_equipment_weekly_quotas WHERE week_key=$1");
        command.Parameters.AddWithValue(DateOnly.ParseExact(weekKey, "yyyy-MM-dd", CultureInfo.InvariantCulture));
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        if (!await reader.ReadAsync(cancellationToken))
            return new(weekKey, false, null, null, null, null, null);
        return new(
            weekKey,
            reader.GetInt16(0) == 1,
            reader.IsDBNull(1) ? null : Enum.Parse<RedEquipmentDropSource>(reader.GetString(1)),
            reader.IsDBNull(2) ? null : reader.GetGuid(2),
            reader.IsDBNull(3) ? null : reader.GetGuid(3),
            reader.IsDBNull(4) ? null : reader.GetGuid(4),
            reader.IsDBNull(5) ? null : reader.GetFieldValue<DateTimeOffset>(5));
    }

    public static async Task<bool> TryClaimAsync(
        NpgsqlConnection connection,
        NpgsqlTransaction transaction,
        DateTimeOffset now,
        RedEquipmentDropSource source,
        Guid playerId,
        Guid? matchId,
        Guid equipmentId,
        CancellationToken cancellationToken)
    {
        var weekKey = DateOnly.ParseExact(
            RedEquipmentQuotaSchedule.GetWeekKey(now), "yyyy-MM-dd", CultureInfo.InvariantCulture);
        await using var command = new NpgsqlCommand(
            """
            INSERT INTO red_equipment_weekly_quotas(
                week_key,red_dropped_this_week,source,player_id,match_id,equipment_id,claimed_at)
            VALUES($1,1,$2,$3,$4,$5,$6)
            ON CONFLICT (week_key) DO UPDATE SET
                red_dropped_this_week=1,source=EXCLUDED.source,player_id=EXCLUDED.player_id,
                match_id=EXCLUDED.match_id,equipment_id=EXCLUDED.equipment_id,claimed_at=EXCLUDED.claimed_at
            WHERE red_equipment_weekly_quotas.red_dropped_this_week=0
            RETURNING week_key
            """,
            connection,
            transaction);
        command.Parameters.AddWithValue(weekKey);
        command.Parameters.AddWithValue(source.ToString());
        command.Parameters.AddWithValue(playerId);
        command.Parameters.AddWithValue((object?)matchId ?? DBNull.Value);
        command.Parameters.AddWithValue(equipmentId);
        command.Parameters.AddWithValue(now);
        return await command.ExecuteScalarAsync(cancellationToken) is not null;
    }
}

