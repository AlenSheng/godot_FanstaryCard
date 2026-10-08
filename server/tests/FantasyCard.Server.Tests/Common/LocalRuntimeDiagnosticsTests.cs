using System.Text.Json;
using FantasyCard.Server.Common;
using Microsoft.Extensions.Logging.Abstractions;

namespace FantasyCard.Server.Tests.Common;

public sealed class LocalRuntimeDiagnosticsTests
{
    [Fact]
    public void Native_metric_windows_keep_real_waits_bounded_and_no_business_labels()
    {
        using var metrics = new ServerMetrics();
        using var collector = new LocalRuntimeDiagnostics(metrics, Path.GetFullPath("unused-owned-metrics.jsonl"),
            NullLogger<LocalRuntimeDiagnostics>.Instance);
        metrics.RoomOpened(4); metrics.RoomHumanPlayersChanged(2);
        for (var i = 1; i <= 100; i++)
            metrics.ObserveRoomActorCommandWait("business-request-" + i, TimeSpan.FromMilliseconds(i));
        metrics.ObserveRuntimePhase(RuntimePhase.SqlExecution, TimeSpan.FromMilliseconds(19));
        using var first = JsonDocument.Parse(JsonSerializer.Serialize(collector.DrainWindow()));
        var wait = first.RootElement.GetProperty("durations").GetProperty("fantasycard.room_actor.command.wait");
        Assert.Equal(100, wait.GetProperty("count").GetInt32()); Assert.Equal(95, wait.GetProperty("p95_ms").GetDouble());
        Assert.DoesNotContain("business-request", first.RootElement.ToString());
        Assert.Equal(2, first.RootElement.GetProperty("counters").GetProperty("fantasycard.rooms.humans.active").GetInt64());
        using var second = JsonDocument.Parse(JsonSerializer.Serialize(collector.DrainWindow()));
        Assert.Empty(second.RootElement.GetProperty("durations").EnumerateObject());
        Assert.Equal("no_actor_wait_observation_in_this_window", second.RootElement.GetProperty("actor_wait_missing_reason").GetString());
        for (var i = 0; i < 32769; i++) metrics.ObserveRoomActorTickDelay(TimeSpan.FromMilliseconds(1));
        using var bounded = JsonDocument.Parse(JsonSerializer.Serialize(collector.DrainWindow()));
        Assert.Equal(1, bounded.RootElement.GetProperty("dropped_observations").GetInt64());
        Assert.Equal(32768, bounded.RootElement.GetProperty("durations").GetProperty("fantasycard.room_actor.tick.delay").GetProperty("count").GetInt32());
    }

    [Fact]
    public async Task Native_process_receipt_records_rss_allocations_and_never_overwrites_prior_process()
    {
        var file = Path.Combine(Path.GetTempPath(), "pr13-own-metric-" + Guid.NewGuid().ToString("N") + ".jsonl");
        try
        {
            using var metrics = new ServerMetrics();
            using (var collector = new LocalRuntimeDiagnostics(metrics, file, NullLogger<LocalRuntimeDiagnostics>.Instance))
            {
                await collector.StartAsync(TestContext.Current.CancellationToken);
                using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
                while (!File.Exists(file) || new FileInfo(file).Length == 0) await Task.Delay(20, deadline.Token);
                await collector.StopAsync(deadline.Token);
            }
            var bytes = await File.ReadAllBytesAsync(file, TestContext.Current.CancellationToken);
            using var row = JsonDocument.Parse(System.Text.Encoding.UTF8.GetString(bytes).Split('\n', StringSplitOptions.RemoveEmptyEntries)[0]);
            Assert.Equal(Environment.ProcessId, row.RootElement.GetProperty("pid").GetInt32());
            Assert.True(row.RootElement.GetProperty("rss_bytes").GetInt64() > 0);
            Assert.True(row.RootElement.GetProperty("managed_allocated_bytes_total").GetInt64() > 0);
            using var second = new LocalRuntimeDiagnostics(metrics, file, NullLogger<LocalRuntimeDiagnostics>.Instance);
            await second.StartAsync(TestContext.Current.CancellationToken);
            await second.StopAsync(TestContext.Current.CancellationToken);
            Assert.Equal(bytes, await File.ReadAllBytesAsync(file, TestContext.Current.CancellationToken));
        }
        finally { if (File.Exists(file)) File.Delete(file); }
    }
}
