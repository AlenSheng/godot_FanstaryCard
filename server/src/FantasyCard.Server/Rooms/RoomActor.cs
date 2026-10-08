using System.Diagnostics;
using System.Threading.Channels;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;

namespace FantasyCard.Server.Rooms;

public sealed class RoomActor : IAsyncDisposable
{
    public static readonly TimeSpan TickInterval = TimeSpan.FromMilliseconds(100);
    private const int CommandQueueCapacity = 256;
    private readonly Channel<ICommandWorkItem> _commands;
    private readonly CancellationTokenSource _shutdown = new();
    private readonly Task _reader;
    private Task? _ticker;
    private readonly TimeProvider _timeProvider;
    private readonly object _tickerGate = new();
    private readonly ServerMetrics? _metrics;
    private readonly Func<BattleRoomSnapshot, Task>? _snapshotObserver;
    private readonly Func<BattleRoomSnapshot, IReadOnlyList<CombatFeedbackResolution>, Task>? _combatObserver;
    private readonly object _observerGate = new();
    private readonly Queue<ObserverBatch> _observerBatches = new();
    private Task _observerTail = Task.CompletedTask;
    private bool _observerWorkerRunning;
    private long _queuedCommands;

    public RoomActor(
        BattleRoom room,
        TimeProvider timeProvider,
        bool startTicker = true,
        Func<BattleRoomSnapshot, Task>? snapshotObserver = null,
        ServerMetrics? metrics = null,
        Func<BattleRoomSnapshot, IReadOnlyList<CombatFeedbackResolution>, Task>? combatObserver = null)
    {
        RoomId = room?.RoomId ?? throw new ArgumentNullException(nameof(room));
        ArgumentNullException.ThrowIfNull(timeProvider);
        _timeProvider = timeProvider;
        _metrics = metrics;
        _snapshotObserver = snapshotObserver;
        _combatObserver = combatObserver;
        _commands = Channel.CreateBounded<ICommandWorkItem>(new BoundedChannelOptions(CommandQueueCapacity)
        {
            SingleReader = true,
            SingleWriter = false,
            FullMode = BoundedChannelFullMode.Wait,
            AllowSynchronousContinuations = false
        });
        _reader = RunReaderAsync(room, snapshotObserver, combatObserver);
        if (startTicker)
        {
            StartTicker();
        }
    }

    public Guid RoomId { get; }

    internal void StartTicker()
    {
        lock (_tickerGate)
        {
            ObjectDisposedException.ThrowIf(_shutdown.IsCancellationRequested, this);
            _ticker ??= RunTickerAsync(_timeProvider, _shutdown.Token);
        }
    }

    public ValueTask<TResult> ExecuteAsync<TResult>(
        IRoomCommand<TResult> command, long expectedRevision, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(command);
        return ExecuteAsync(new RevisionCheckedCommand<TResult>(command, expectedRevision), cancellationToken);
    }

    private sealed record RevisionCheckedCommand<TResult>(IRoomCommand<TResult> Inner, long ExpectedRevision) : IRoomCommand<TResult>
    {
        public bool NotifyObservers => Inner.NotifyObservers;

        public TResult Execute(BattleRoom room)
        {
            if (ExpectedRevision > room.Revision)
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
            throw new InvalidOperationException("The room actor command queue is full or closed.");
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
        }
        catch (OperationCanceledException)
        {
        }
        if (_ticker is not null)
        {
            try { await _ticker; }
            catch (OperationCanceledException) { }
        }
        Task observerTail;
        lock (_observerGate) observerTail = _observerTail;
        await observerTail;
        _shutdown.Dispose();
    }

    private async Task RunReaderAsync(BattleRoom room, Func<BattleRoomSnapshot, Task>? snapshotObserver,
        Func<BattleRoomSnapshot, IReadOnlyList<CombatFeedbackResolution>, Task>? combatObserver)
    {
        await foreach (var command in _commands.Reader.ReadAllAsync())
        {
            _metrics?.ObserveRoomActorQueueLength(Interlocked.Decrement(ref _queuedCommands));
            _metrics?.ObserveRoomActorCommandWait(
                command.CommandName,
                Stopwatch.GetElapsedTime(command.EnqueuedAt));
            BattleRoomSnapshot? snapshot;
            using (RuntimeTiming.Measure(_metrics, RuntimePhase.ActorExecute, command.EnqueueContext, room: RoomId.ToString("D")))
                snapshot = command.Execute(room);
            var feedback = room.DrainCombatFeedback();
            if (command.NotifyObservers)
            {
                snapshot ??= room.Capture();
                EnqueueObservers(snapshot, feedback);
            }
            else if (feedback.Count > 0)
            {
                EnqueueObservers(snapshot ?? room.Capture(), feedback);
            }
        }
    }

    private void EnqueueObservers(
        BattleRoomSnapshot snapshot,
        IReadOnlyList<CombatFeedbackResolution> feedback)
    {
        if (_combatObserver is null && _snapshotObserver is null) return;
        lock (_observerGate)
        {
            var hasCombat = _combatObserver is not null && feedback.Count > 0;
            if (hasCombat || _snapshotObserver is null)
            {
                var persistenceSnapshot = _snapshotObserver is null ? null : snapshot;
                _observerBatches.Enqueue(new ObserverBatch(
                    hasCombat ? feedback : null,
                    persistenceSnapshot,
                    hasCombat ? snapshot : null));
            }
            else if (_observerBatches.LastOrDefault() is { Combat: null } pending)
            {
                // Consecutive persistence snapshots are interchangeable; keep
                // only the newest one while preserving any queued combat
                // presentation batches in front of it.
                pending.Snapshot = snapshot;
            }
            else
            {
                _observerBatches.Enqueue(new ObserverBatch(null, snapshot, null));
            }

            if (_observerWorkerRunning) return;
            _observerWorkerRunning = true;
            _observerTail = _observerTail
                .ContinueWith(_ => DrainObservers(), CancellationToken.None,
                    TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default)
                .Unwrap();
        }
    }

    private async Task DrainObservers()
    {
        while (true)
        {
            ObserverBatch? batch;
            lock (_observerGate)
            {
                if (_observerBatches.Count == 0)
                {
                    _observerWorkerRunning = false;
                    return;
                }
                batch = _observerBatches.Dequeue();
            }
            if (batch.Combat is not null)
                await ObserveSafely(() => _combatObserver!(batch.CombatSnapshot!, batch.Combat));
            if (batch.Snapshot is not null)
                await ObserveSafely(() => _snapshotObserver!(batch.Snapshot));
        }
    }

    private sealed class ObserverBatch(
        IReadOnlyList<CombatFeedbackResolution>? combat,
        BattleRoomSnapshot? snapshot,
        BattleRoomSnapshot? combatSnapshot)
    {
        public IReadOnlyList<CombatFeedbackResolution>? Combat { get; } = combat;
        public BattleRoomSnapshot? CombatSnapshot { get; } = combatSnapshot;
        public BattleRoomSnapshot? Snapshot { get; set; } = snapshot;
    }

    private static async Task ObserveSafely(Func<Task> work)
    {
        try { await work(); }
        catch { /* Presentation and persistence must not stop authoritative room processing. */ }
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
            if (!await _commands.Writer.WaitToWriteAsync(cancellationToken))
            {
                return;
            }
            var workItem = new CommandWorkItem<BattleRoomSnapshot>(command, cancellationToken);
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
        long EnqueuedAt { get; }
        string CommandName { get; }
        ActivityContext EnqueueContext { get; }
        bool NotifyObservers { get; }
        BattleRoomSnapshot? Execute(BattleRoom room);
    }

    private sealed class CommandWorkItem<TResult>(
        IRoomCommand<TResult> command,
        CancellationToken cancellationToken) : ICommandWorkItem
    {
        private readonly TaskCompletionSource<TResult> _completion =
            new(TaskCreationOptions.RunContinuationsAsynchronously);

        public Task<TResult> Task => _completion.Task;

        public long EnqueuedAt { get; } = Stopwatch.GetTimestamp();
        public ActivityContext EnqueueContext { get; } = Activity.Current?.Context ?? default;
        public string CommandName => command.GetType().Name;
        public bool NotifyObservers => command.NotifyObservers;

        public BattleRoomSnapshot? Execute(BattleRoom room)
        {
            if (cancellationToken.IsCancellationRequested)
            {
                _completion.TrySetCanceled(cancellationToken);
                return null;
            }
            try
            {
                var result = command.Execute(room);
                _completion.TrySetResult(result);
                return result switch
                {
                    BattleRoomSnapshot snapshot => snapshot,
                    RoomClientState state => state.Snapshot,
                    IRoomCommandSnapshotResult snapshotResult => snapshotResult.Snapshot,
                    _ => null
                };
            }
            catch (Exception exception)
            {
                _completion.TrySetException(exception);
                return null;
            }
        }
    }
}
