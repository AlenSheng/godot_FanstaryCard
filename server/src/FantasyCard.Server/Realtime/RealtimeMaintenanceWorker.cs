using FantasyCard.Server.Common;
using Microsoft.Extensions.Options;

namespace FantasyCard.Server.Realtime;

public sealed partial class RealtimeMaintenanceWorker(
    RealtimeEventStore eventStore,
    TimeProvider timeProvider,
    IOptions<RealtimeOptions> options,
    ServerMetrics metrics,
    ILogger<RealtimeMaintenanceWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        var settings = options.Value;
        using var timer = new PeriodicTimer(
            TimeSpan.FromMinutes(settings.CleanupIntervalMinutes), timeProvider);
        do
        {
            var cutoff = timeProvider.GetUtcNow()
                .AddMinutes(-settings.EventStreamIdleRetentionMinutes);
            var removed = eventStore.RemoveInactive(cutoff);
            if (removed > 0)
            {
                metrics.RealtimeStreamsExpired(removed);
                StreamsExpired(logger, removed);
            }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }

    [LoggerMessage(EventId = 4201, Level = LogLevel.Information, Message = "Removed {Count} inactive realtime event stream(s).")]
    private static partial void StreamsExpired(ILogger logger, int count);
}
