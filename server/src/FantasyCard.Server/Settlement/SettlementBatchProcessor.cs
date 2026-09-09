namespace FantasyCard.Server.Settlement;

public static class SettlementBatchProcessor
{
    public static async Task ProcessAsync(
        IEnumerable<Guid> settlementIds,
        Func<Guid, CancellationToken, Task<int>> commit,
        Action<Guid, int> committed,
        Action<Guid, Exception> failed,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(settlementIds);
        ArgumentNullException.ThrowIfNull(commit);
        ArgumentNullException.ThrowIfNull(committed);
        ArgumentNullException.ThrowIfNull(failed);
        foreach (var settlementId in settlementIds.Distinct())
        {
            cancellationToken.ThrowIfCancellationRequested();
            try
            {
                committed(settlementId, await commit(settlementId, cancellationToken));
            }
            catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
            {
                throw;
            }
            catch (Exception exception)
            {
                failed(settlementId, exception);
            }
        }
    }
}
