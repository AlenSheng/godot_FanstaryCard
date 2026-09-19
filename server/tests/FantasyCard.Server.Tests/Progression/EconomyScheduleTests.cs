using FantasyCard.Server.Progression;
using System.Globalization;

namespace FantasyCard.Server.Tests.Progression;

public sealed class EconomyScheduleTests
{
    [Theory]
    [InlineData("2026-09-04T19:59:59Z", "2026-09-04")]
    [InlineData("2026-09-04T20:00:00Z", "2026-09-05")]
    [InlineData("2026-12-31T19:59:59Z", "2026-12-31")]
    [InlineData("2026-12-31T20:00:00Z", "2027-01-01")]
    public void Daily_reset_occurs_at_0400_china_time(string timestamp, string expected)
    {
        Assert.Equal(expected, EconomySchedule.GetDailyResetKey(
            DateTimeOffset.Parse(timestamp, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal)));
    }

    [Theory]
    [InlineData("2026-09-06T19:59:59Z", "2026-08-31")]
    [InlineData("2026-09-06T20:00:00Z", "2026-09-07")]
    [InlineData("2026-09-13T19:59:59Z", "2026-09-07")]
    [InlineData("2026-09-13T20:00:00Z", "2026-09-14")]
    public void Weekly_quota_resets_on_monday_at_0400_china_time(string timestamp, string expected)
    {
        Assert.Equal(expected, RedEquipmentQuotaSchedule.GetWeekKey(
            DateTimeOffset.Parse(timestamp, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal)));
    }

    [Theory]
    [InlineData("2026-09-19T23:59:59Z", "2026-09-19")]
    [InlineData("2026-09-20T00:00:00Z", "2026-09-20")]
    public void Shop_refresh_quota_resets_at_server_utc_midnight(string timestamp, string expected)
    {
        Assert.Equal(expected, EconomySchedule.GetServerDayKey(
            DateTimeOffset.Parse(timestamp, CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal)));
    }
}
