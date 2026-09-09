namespace FantasyCard.Server.Matchmaking;

public sealed partial class MatchmakerWorker(
    MatchmakingRepository repository,
    RoomReadyCoordinator readyCoordinator,
    ILogger<MatchmakerWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                var assignment = await repository.TryCreateMatchAsync(stoppingToken);
                if (assignment is not null)
                {
                    await readyCoordinator.NotifyRequiredAsync(assignment, stoppingToken);
                }
                else
                {
                    await Task.Delay(TimeSpan.FromMilliseconds(500), stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                LogIterationFailed(logger, exception);
                await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken);
            }
        }
    }

    [LoggerMessage(EventId = 3001, Level = LogLevel.Error, Message = "Matchmaker iteration failed.")]
    private static partial void LogIterationFailed(ILogger logger, Exception exception);
}
