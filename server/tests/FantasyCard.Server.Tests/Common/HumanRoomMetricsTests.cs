using System.Diagnostics.Metrics;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Common;

public sealed class HumanRoomMetricsTests
{
    [Fact]
    public async Task Human_routes_exclude_bots_and_ignore_old_terminal_snapshot_after_rejoin()
    {
        using var metrics = new ServerMetrics();
        var deltas = new List<long>();
        using var listener = new MeterListener();
        listener.InstrumentPublished = (instrument, current) =>
        {
            if (ReferenceEquals(instrument.Meter, metrics.SourceMeter) && instrument.Name == "fantasycard.rooms.humans.active")
                current.EnableMeasurementEvents(instrument);
        };
        listener.SetMeasurementEventCallback<long>((_, value, _, _) => deltas.Add(value));
        listener.Start();
        await using var registry = new RoomRegistry(TimeProvider.System, metrics: metrics);
        var catalog = CombatCardCatalog.CreatePrototype();
        var first = new BattleRoom(Guid.NewGuid(), "metrics", catalog, 1);
        var human = Guid.NewGuid();
        first.AddPlayer(new(human, HeroClass.Mage, Enumerable.Repeat("C01", 20).ToArray(), null));
        first.AddPlayer(new(Guid.NewGuid(), HeroClass.Priest, Enumerable.Repeat("C01", 20).ToArray(), null));
        first.AddPlayer(new(Guid.NewGuid(), HeroClass.Guardian, Enumerable.Repeat("C01", 20).ToArray(), null, IsBot: true));
        registry.Register(first, startTicker: false);
        var oldTerminal = first.Capture() with { Players = first.Capture().Players.Select(p =>
            p.PlayerId == human ? p with { Phase = RoomPlayerPhase.Dead } : p).ToArray() };
        registry.ReleaseTerminalPlayers(oldTerminal);
        registry.ReleaseTerminalPlayers(oldTerminal);
        var second = new BattleRoom(Guid.NewGuid(), "metrics", catalog, 2);
        second.AddPlayer(new(human, HeroClass.Mage, Enumerable.Repeat("C01", 20).ToArray(), null));
        registry.Register(second, startTicker: false);
        registry.ReleaseTerminalPlayers(oldTerminal);
        Assert.True(registry.TryGetForPlayer(human, out _));
        await registry.RemoveAsync(first.RoomId);
        await registry.RemoveAsync(second.RoomId);
        Assert.Equal(new long[] { 2, -1, 1, -1, -1 }, deltas);
        Assert.Equal(0, deltas.Sum());
    }
}
