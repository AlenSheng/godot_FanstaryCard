using FantasyCard.Server.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class RealtimeEventStoreTests
{
    [Fact]
    public void Create_AssignsMonotonicSequenceAndSupportsReplay()
    {
        var playerId = Guid.NewGuid();
        var store = new RealtimeEventStore(TimeProvider.System);

        var first = store.Create(playerId, "first", "trace", null);
        var second = store.Create(playerId, "second", "trace", null);
        var replay = store.ReadAfter(playerId, first.Sequence);

        Assert.Equal(1, first.Sequence);
        Assert.Equal(2, second.Sequence);
        Assert.False(replay.HasGap);
        Assert.Collection(replay.Events, item => Assert.Equal(second.EventId, item.EventId));
    }

    [Fact]
    public void Create_RemembersResponseByRequestId()
    {
        var playerId = Guid.NewGuid();
        var store = new RealtimeEventStore(TimeProvider.System);
        var created = store.Create(playerId, "ack", "trace", null, "request-0001");

        var found = store.TryGetResponse(playerId, "request-0001", out var cached);

        Assert.True(found);
        Assert.Equal(created.EventId, cached?.EventId);
    }

    [Fact]
    public void ReadAfter_ReportsGapWhenBufferRolledOver()
    {
        var playerId = Guid.NewGuid();
        var store = new RealtimeEventStore(TimeProvider.System);
        for (var index = 0; index < 260; index++)
        {
            store.Create(playerId, "event", "trace", new { index });
        }

        var replay = store.ReadAfter(playerId, 0);

        Assert.True(replay.HasGap);
        Assert.Empty(replay.Events);
    }

    [Fact]
    public void RemoveInactive_DropsOnlyStreamsOlderThanCutoff()
    {
        var time = new ManualTimeProvider(new DateTimeOffset(2026, 9, 6, 0, 0, 0, TimeSpan.Zero));
        var store = new RealtimeEventStore(time);
        var stalePlayer = Guid.NewGuid();
        var activePlayer = Guid.NewGuid();
        store.Create(stalePlayer, "old", "trace", null);
        time.Advance(TimeSpan.FromMinutes(61));
        store.Create(activePlayer, "new", "trace", null);

        var removed = store.RemoveInactive(time.GetUtcNow().AddMinutes(-60));

        Assert.Equal(1, removed);
        Assert.Empty(store.ReadAfter(stalePlayer, 0).Events);
        Assert.Single(store.ReadAfter(activePlayer, 0).Events);
    }

    [Fact]
    public void ReadAfter_RefreshesStreamActivity()
    {
        var time = new ManualTimeProvider(new DateTimeOffset(2026, 9, 6, 0, 0, 0, TimeSpan.Zero));
        var store = new RealtimeEventStore(time);
        var playerId = Guid.NewGuid();
        store.Create(playerId, "event", "trace", null);
        time.Advance(TimeSpan.FromMinutes(50));
        store.ReadAfter(playerId, 0);
        time.Advance(TimeSpan.FromMinutes(20));

        Assert.Equal(0, store.RemoveInactive(time.GetUtcNow().AddMinutes(-60)));
        Assert.Single(store.ReadAfter(playerId, 0).Events);
    }

    private sealed class ManualTimeProvider(DateTimeOffset now) : TimeProvider
    {
        private DateTimeOffset _now = now;

        public override DateTimeOffset GetUtcNow() => _now;

        public void Advance(TimeSpan duration) => _now += duration;
    }
}
