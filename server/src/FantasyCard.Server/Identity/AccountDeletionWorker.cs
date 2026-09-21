namespace FantasyCard.Server.Identity;

public sealed partial class AccountDeletionWorker(
    AccountDeletionRepository repository,
    TimeProvider timeProvider,
    ILogger<AccountDeletionWorker> logger) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(15), timeProvider);
        do
        {
            try
            {
                var completed = await repository.CompleteDueAsync(timeProvider.GetUtcNow(), stoppingToken);
                if (completed > 0)
                    Completed(logger, completed);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                return;
            }
            catch (Exception exception)
            {
                Failed(logger, exception);
            }
        }
        while (await timer.WaitForNextTickAsync(stoppingToken));
    }

    [LoggerMessage(EventId = 4010, Level = LogLevel.Information, Message = "Completed {AccountDeletionCount} account deletion request(s).")]
    private static partial void Completed(ILogger logger, int accountDeletionCount);

    [LoggerMessage(EventId = 4011, Level = LogLevel.Error, Message = "Account deletion processing failed.")]
    private static partial void Failed(ILogger logger, Exception exception);
}
