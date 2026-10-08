using System.Collections.Concurrent;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Net.WebSockets;
using System.Security.Cryptography;
using System.Text.Json;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Identity;
using FantasyCard.Server.Matchmaking;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Tests.Persistence;
using Npgsql;

namespace FantasyCard.Server.Tests.Common;

public sealed class RuntimeTimingTests(ITestOutputHelper output)
{
    public static bool HasTestDatabase => PostgresRuntimeIntegrationTests.HasTestDatabase;

    [Fact(Skip = "Set FANTASYCARD_TEST_POSTGRES to an isolated PostgreSQL test database.", SkipUnless = nameof(HasTestDatabase))]
    [Trait("Category", "PostgresIntegration")]
    public async Task Actual_pool_acquisition_wait_is_separate_from_replay_SQL_execution()
    {
        await using var database = await PostgresTestSchema.CreateAsync(migrate: true);
        var ct = TestContext.Current.CancellationToken;
        var player = await new IdentityRepository(database.DataSource, new PlayerProvisioningService())
            .SignInLocalAsync("timing-" + Guid.NewGuid().ToString("N"), "Pool timing", RandomNumberGenerator.GetBytes(32), DateTimeOffset.UtcNow, DateTimeOffset.UtcNow.AddHours(1), ct);
        using var metrics = new ServerMetrics();
        using var capture = new Capture(metrics);
        using var root = new Activity("actual-pool-replay-request").Start();
        var settings = new NpgsqlConnectionStringBuilder(database.ConnectionString) { MaxPoolSize = 1, MinPoolSize = 0 };
        await using var limited = NpgsqlDataSource.Create(settings.ConnectionString);
        await using var held = await limited.OpenConnectionAsync(ct);
        var repository = new MatchmakingRepository(limited, TimeProvider.System, metrics);
        var request = Guid.NewGuid().ToString("D");
        var pending = repository.EnqueueAsync(player.UserId, request, new(Guid.NewGuid()), ct);
        await Task.Delay(150, ct);
        Assert.False(pending.IsCompleted);
        await held.DisposeAsync();
        await Assert.ThrowsAsync<InvalidOperationException>(() => pending);
        var spans = capture.Spans.Where(a => a.TraceId == root.TraceId).ToArray();
        var acquire = Assert.Single(spans, a => a.GetTagItem("runtime.phase")?.ToString() == nameof(RuntimePhase.DatabaseAcquire));
        var sql = Assert.Single(spans, a => a.GetTagItem("runtime.phase")?.ToString() == nameof(RuntimePhase.SqlExecution));
        Assert.True(acquire.Duration.TotalMilliseconds >= 100);
        Assert.True(sql.StartTimeUtc >= acquire.StartTimeUtc + acquire.Duration);
        Assert.Equal(request, acquire.GetTagItem("request.id"));
        Assert.Equal(request, sql.GetTagItem("request.id"));
        output.WriteLine("PR13_RUNTIME " + JsonSerializer.Serialize(new { acquisitionMs = acquire.Duration.TotalMilliseconds, sqlExecutionMs = sql.Duration.TotalMilliseconds,
            nonoverlapping = true, sameRequestTrace = true, dbInternalLockWaitMs = (double?)null, reason = "PlayerLockRoundTrip includes the lock query round trip; internal DB wait is not isolated." }));
    }

    [Fact]
    public async Task Blocked_socket_send_keeps_actor_execution_separate_in_the_same_request_trace()
    {
        using var metrics = new ServerMetrics();
        using var capture = new Capture(metrics);
        using var root = new Activity("actual-socket-and-actor-request").Start();
        using var socket = new GateSocket();
        await using var connection = new RealtimeConnection(socket, metrics);
        var room = new BattleRoom(Guid.NewGuid(), "timing", CombatCardCatalog.CreatePrototype(), 71);
        await using var actor = new RoomActor(room, TimeProvider.System, startTicker: false, metrics: metrics);
        var send = connection.SendAsync(new ServerEvent("pong", "timing", new PongEventPayload(DateTimeOffset.UtcNow), "timing-event", 1, DateTimeOffset.UtcNow, "timing-request"), TestContext.Current.CancellationToken);
        await socket.Entered.Task.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        try
        {
            await actor.ExecuteAsync(new GetRoomSnapshotCommand()).AsTask().WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
            Assert.False(send.IsCompleted);
            Assert.Contains(capture.Spans, a => a.TraceId == root.TraceId && a.GetTagItem("runtime.phase")?.ToString() == nameof(RuntimePhase.ActorExecute));
            Assert.DoesNotContain(capture.Spans, a => a.TraceId == root.TraceId && a.GetTagItem("runtime.phase")?.ToString() == nameof(RuntimePhase.SocketSend));
        }
        finally { socket.Release.TrySetResult(); }
        await send;
        var actorSpan = Assert.Single(capture.Spans, a => a.TraceId == root.TraceId && a.GetTagItem("runtime.phase")?.ToString() == nameof(RuntimePhase.ActorExecute));
        var sendSpan = Assert.Single(capture.Spans, a => a.TraceId == root.TraceId && a.GetTagItem("runtime.phase")?.ToString() == nameof(RuntimePhase.SocketSend));
        Assert.Equal(room.RoomId.ToString("D"), actorSpan.GetTagItem("room.id"));
        Assert.Equal("timing-request", sendSpan.GetTagItem("request.id"));
        output.WriteLine("PR13_RUNTIME " + JsonSerializer.Serialize(new { actorExecutionMs = actorSpan.Duration.TotalMilliseconds, socketSendMs = sendSpan.Duration.TotalMilliseconds,
            actorCompletedWhileSendBlocked = true, sharedInitiatingTrace = true }));
    }

    [Fact]
    public void Thousands_of_business_ids_never_create_metric_identity_labels()
    {
        using var metrics = new ServerMetrics();
        using var capture = new Capture(metrics);
        foreach (var phase in Enum.GetValues<RuntimePhase>())
            for (var i = 0; i < 1000; i++)
                using (RuntimeTiming.Measure(metrics, phase, room: Guid.NewGuid().ToString("D"), player: Guid.NewGuid().ToString("D"), request: Guid.NewGuid().ToString("D"))) { }
        Assert.Equal(6000, capture.MetricTags.Count);
        Assert.All(capture.MetricTags, tags => Assert.Equal("phase", Assert.Single(tags).Key));
        Assert.Equal(6, capture.MetricTags.Select(tags => tags[0].Value!.ToString()).Distinct().Count());
        output.WriteLine("PR13_RUNTIME " + JsonSerializer.Serialize(new { measurements = 6000, differentRoomIdentities = 6000, labelNames = new[] { "phase" }, labelValues = 6, businessIdsOnlyInTrace = true }));
    }

    private sealed class Capture : IDisposable
    {
        private readonly ActivityListener _activities;
        private readonly MeterListener _metrics = new();
        public ConcurrentQueue<Activity> Spans { get; } = new();
        public ConcurrentQueue<KeyValuePair<string, object?>[]> MetricTags { get; } = new();
        public Capture(ServerMetrics metrics)
        {
            _activities = new ActivityListener
            {
                ShouldListenTo = source => source.Name == ServerMetrics.MeterName,
                Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
                ActivityStopped = activity => Spans.Enqueue(activity)
            };
            ActivitySource.AddActivityListener(_activities);
            _metrics.InstrumentPublished = (instrument, listener) =>
            {
                if (ReferenceEquals(instrument.Meter, metrics.SourceMeter) && instrument.Name == "fantasycard.runtime.phase.duration") listener.EnableMeasurementEvents(instrument);
            };
            _metrics.SetMeasurementEventCallback<double>((_, _, tags, _) => MetricTags.Enqueue(tags.ToArray()));
            _metrics.Start();
        }
        public void Dispose() { _activities.Dispose(); _metrics.Dispose(); }
    }

    private sealed class GateSocket : WebSocket
    {
        private WebSocketState _state = WebSocketState.Open;
        public TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public TaskCompletionSource Release { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);
        public override WebSocketCloseStatus? CloseStatus => null;
        public override string? CloseStatusDescription => null;
        public override WebSocketState State => _state;
        public override string? SubProtocol => null;
        public override void Abort() => _state = WebSocketState.Aborted;
        public override void Dispose() => _state = WebSocketState.Closed;
        public override Task CloseAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) => Task.CompletedTask;
        public override Task CloseOutputAsync(WebSocketCloseStatus status, string? description, CancellationToken ct) => Task.CompletedTask;
        public override Task<WebSocketReceiveResult> ReceiveAsync(ArraySegment<byte> buffer, CancellationToken ct) => throw new NotSupportedException();
        public override async Task SendAsync(ArraySegment<byte> buffer, WebSocketMessageType type, bool end, CancellationToken ct) { Entered.TrySetResult(); await Release.Task.WaitAsync(ct); }
    }
}
