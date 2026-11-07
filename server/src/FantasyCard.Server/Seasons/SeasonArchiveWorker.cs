using Npgsql;

namespace FantasyCard.Server.Seasons;

public sealed partial class SeasonArchiveWorker(SeasonRepository seasons,TimeProvider clock,ILogger<SeasonArchiveWorker> logger):BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        using var timer=new PeriodicTimer(TimeSpan.FromSeconds(5),clock);
        do
        {
            try
            {
                foreach(var work in await seasons.GetArchiveWorkAsync(32,stoppingToken))
                {
                    try { await seasons.AdvanceArchivePageAsync(work.PlayerId,work.SeasonId,32,stoppingToken); }
                    catch(OperationCanceledException) when(stoppingToken.IsCancellationRequested) { return; }
                    catch(Exception exception)
                    {
                        var code=exception is PostgresException pg?"postgres."+pg.SqlState:"archive.page.failed";
                        PageFailed(logger,work.PlayerId,work.SeasonId,code);
                        await seasons.MarkArchiveFailureAsync(work,code,stoppingToken);
                    }
                }
            }
            catch(OperationCanceledException) when(stoppingToken.IsCancellationRequested) { return; }
            catch(Exception exception) { ScanFailed(logger,exception); }
        }
        while(await timer.WaitForNextTickAsync(stoppingToken));
    }

    [LoggerMessage(EventId=4811,Level=LogLevel.Error,Message="Season archive page failed for {PlayerId}/{SeasonId}: {ErrorCode}.")]
    private static partial void PageFailed(ILogger logger,Guid playerId,string seasonId,string errorCode);
    [LoggerMessage(EventId=4812,Level=LogLevel.Error,Message="Season archive scan failed.")]
    private static partial void ScanFailed(ILogger logger,Exception exception);
}
