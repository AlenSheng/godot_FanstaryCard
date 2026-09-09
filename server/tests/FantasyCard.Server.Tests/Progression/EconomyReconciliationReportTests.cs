using FantasyCard.Server.Progression;

namespace FantasyCard.Server.Tests.Progression;

public sealed class EconomyReconciliationReportTests
{
    [Fact]
    public void Empty_report_is_healthy()
    {
        var report = new EconomyReconciliationReport(0, 0, 0, 0, 0, 0);

        Assert.True(report.IsHealthy);
        Assert.Equal(0, report.TotalViolationCount);
    }

    [Fact]
    public void Report_aggregates_all_violation_categories()
    {
        var report = new EconomyReconciliationReport(1, 2, 3, 4, 5, 6);

        Assert.False(report.IsHealthy);
        Assert.Equal(21, report.TotalViolationCount);
    }
}
