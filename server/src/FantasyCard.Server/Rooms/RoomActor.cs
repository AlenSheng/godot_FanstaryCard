using System.Threading.Channels;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Rooms;

public sealed class RoomActor : IAsyncDisposable
{
    public static readonly TimeSpan TickInterval = TimeSpan.FromMilliseconds(100);
    private readonly Channel<ICommandWorkItem> _commands;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _reader;
    private readonly Task? _ticker;
    private readonly ServerMetrics? _metrics;
    private long _queuedCommands;

    public RoomActor(
        BattleRoom room,
        TimeProvider timeProvider,
        bool startTicker = true,
        Func<BattleRoomSnapshot, Task>? snapshotObserver = null,
        ServerMetrics? metrics = null)
    {
        RoomId = room?.RoomId ?? throw new ArgumentNullException(nameof(room));
        ArgumentNullException.ThrowIfNull(timeProvider);
        _metrics = metrics;
        _commands = Channel.CreateUnbounded<ICommandWorkItem>(new UnboundedChannelOptions
        {
            SingleReader = true,
            SingleWriter = false,
            AllowSynchronousContinuations = false
        });
        _reader = RunReaderAsync(room, snapshotObserver);
        if (startTicker)
        {
            _ticker = RunTickerAsync(timeProvider, _shutdown.Token);
        }
    }

    public Guid RoomId { get; }

    public ValueTask<TResult> ExecuteAsync<TResult>(
        IRoomCommand<TResult> command, long expectedRevision, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(command);
        return ExecuteAsync(new RevisionCheckedCommand<TResult>(command, expectedRevision), cancellationToken);
    }

    private sealed record RevisionCheckedCommand<TResult>(IRoomCommand<TResult> Inner, long ExpectedRevision) : IRoomCommand<TResult>
    {
        public TResult Execute(BattleRoom room)
        {
            if (room.Revision != ExpectedRevision)
                throw new FantasyCard.Domain.Players.DomainValidationException(
                    $"Room revision conflict. Expected {ExpectedRevision}, current {room.Revision}.");
            return Inner.Execute(room);
        }
    }

    public ValueTask<TResult> ExecuteAsync<TResult>(
        IRoomCommand<TResult> command,
        CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(command);
        cancellationToken.ThrowIfCancellationRequested();
        var workItem = new CommandWorkItem<TResult>(command, cancellationToken);
        _metrics?.ObserveRoomActorQueueLength(Interlocked.Increment(ref _queuedCommands));
        if (!_commands.Writer.TryWrite(workItem))
        {
            _metrics?.ObserveRoomActorQueueLength(Interlocked.Decrement(ref _queuedCommands));
            throw new InvalidOperationException("The room actor no longer accepts commands.");
        }
        return new ValueTask<TResult>(workItem.Task);
    }

    public async ValueTask DisposeAsync()
    {
        await _shutdown.CancelAsync();
        _commands.Writer.TryComplete();
        try
        {
            await _reader;
            if (_ticker is not null)
            {
                await _ticker;
            }
        }
        catch (OperationCanceledException)
        {
        }
        _shutdown.Dispose();
    }

    private async Task RunReaderAsync(BattleRoom room, Func<BattleRoomSnapshot, Task>? snapshotObserver)
    {
        await foreach (var command in _commands.Reader.ReadAllAsync())
        {
            _metrics?.ObserveRoomActorQueueLength(Interlocked.Decrement(ref _queuedCommands));
            command.Execute(room);
            if (snapshotObserver is not null)
            {
                try
                {
                    await snapshotObserver(room.Capture());
                }
                catch
                {
                    // Persistence is retried by the settlement worker; a transient store failure must not stop the room actor.
                }
            }
        }
    }

    private async Task RunTickerAsync(TimeProvider timeProvider, CancellationToken cancellationToken)
    {
        using var timer = new PeriodicTimer(TickInterval, timeProvider);
        var nextTickAt = timeProvider.GetUtcNow() + TickInterval;
        while (await timer.WaitForNextTickAsync(cancellationToken))
        {
            var now = timeProvider.GetUtcNow();
            _metrics?.ObserveRoomActorTickDelay(now - nextTickAt);
            nextTickAt = now + TickInterval;
            var command = new AdvanceRoomTimeCommand(TickInterval, now);
            var workItem = new CommandWorkItem<BattleRoomSnapshot>(command, cancellationToken);
            if (!await _commands.Writer.WaitToWriteAsync(cancellationToken))
            {
                return;
            }
            _metrics?.ObserveRoomActorQueueLength(Interlocked.Increment(ref _queuedCommands));
            if (!_commands.Writer.TryWrite(workItem))
            {
                _metrics?.ObserveRoomActorQueueLength(Interlocked.Decrement(ref _queuedCommands));
                return;
            }
            await workItem.Task;
        }
    }

    private interface ICommandWorkItem
    {
        void Execute(BattleRoom room);
    }

    private sealed class CommandWorkItem<TResult>(
        IRoomCommand<TResult> command,
        CancellationToken cancellationToken) : ICommandWorkItem
    {
        private readonly TaskCompletionSource<TResult> _completion =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task<TResult> Task => _completion.Task;

        public void Execute(BattleRoom room)
        {
            if (cancellationToken.IsCancellationRequested)
            {
                _completion.TrySetCanceled(cancellationToken);
                return;
            }
            try
            {
                _completion.TrySetResult(command.Execute(room));
            }
            catch (Exception exception)
            {
                _completion.TrySetException(exception);
            }
        }
    }
}
