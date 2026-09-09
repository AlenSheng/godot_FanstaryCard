using System.Diagnostics.Metrics;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Common;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomLifecycleMetricsTrackerTests
{
    [Fact]
    public void Pve_duration_counts_active_time_but_excludes_pvp_freeze()
    {
        var room = CreateRoomWithPlayers(1);
        using var capture = new MetricCapture("fantasycard.combat.pve.duration");
        using var metrics = new ServerMetrics();
        var initial = room.Capture();
        var tracker = new RoomLifecycleMetricsTracker(initial, metrics, TimeProvider.System);
        var player = initial.Players[0];

        tracker.Observe(WithPvePhase(initial, player, TimeSpan.FromSeconds(5), PveBattlePhase.Active));
        tracker.Observe(WithPvePhase(initial, player, TimeSpan.FromSeconds(10), PveBattlePhase.Frozen));
        tracker.Observe(WithPvePhase(initial, player, TimeSpan.FromSeconds(20), PveBattlePhase.Active));
        tracker.Observe(WithPvePhase(initial, player, TimeSpan.FromSeconds(25), PveBattlePhase.Cleared));

        Assert.Contains(15, capture.Values);
    }

    [Fact]
    public void Pvp_duration_uses_authoritative_duel_start_time()
    {
        var time = new ManualTimeProvider(new DateTimeOffset(2026, 9, 6, 0, 0, 0, TimeSpan.Zero));
        var room = CreateRoomWithPlayers(2);
        using var capture = new MetricCapture("fantasycard.combat.pvp.duration");
        using var metrics = new ServerMetrics();
        var tracker = new RoomLifecycleMetricsTracker(room.Capture(), metrics, time);
        var players = room.Capture().Players;
        var duel = room.StartDuel(players[0].PlayerId, players[1].PlayerId, time.GetUtcNow());
        tracker.Observe(room.Capture());

        time.Advance(TimeSpan.FromSeconds(8));
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);
        tracker.Observe(room.Capture());

        Assert.Contains(8, capture.Values);
    }

    private static BattleRoomSnapshot WithPvePhase(
        BattleRoomSnapshot baseline,
        RoomPlayerSnapshot player,
        TimeSpan elapsed,
        PveBattlePhase phase) =>
        baseline with
        {
            Elapsed = elapsed,
            Players =
            [
                player with
                {
                    Phase = phase == PveBattlePhase.Cleared ? RoomPlayerPhase.Choice : RoomPlayerPhase.Pve,
                    Pve = player.Pve! with { Phase = phase }
                }
            ]
        };

    private static BattleRoom CreateRoomWithPlayers(int count)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 7);
        for (var index = 0; index < count; index++)
        {
            room.AddPlayer(new BattleRoomPlayerSetup(
                Guid.NewGuid(),
                index % 2 == 0 ? HeroClass.Mage : HeroClass.Priest,
                Enumerable.Range(1, 20).Select(card => $"common-{card:D2}").ToArray(),
                new PveBattleState(
                    Guid.NewGuid(),
                    "monster",
                    [
                        new MonsterCombatState(
                            "monster",
                            100,
                            100,
                            0,
                            TimeSpan.FromSeconds(10),
                            [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)])
                    ])));
        }
        return room;
    }

    private sealed class MetricCapture : IDisposable
    {
        private readonly string _instrumentName;
        private readonly MeterListener _listener = new();

        public MetricCapture(string instrumentName)
        {
            _instrumentName = instrumentName;
            _listener.InstrumentPublished = (instrument, listener) =>
            {
                if (instrument.Meter.Name == ServerMetrics.MeterName && instrument.Name == _instrumentName)
                    listener.EnableMeasurementEvents(instrument);
            };
            _listener.SetMeasurementEventCallback<double>((_, value, _, _) => Values.Add(value));
            _listener.Start();
        }

        public List<double> Values { get; } = [];

        public void Dispose() => _listener.Dispose();
    }

    private sealed class ManualTimeProvider(DateTimeOffset now) : TimeProvider
    {
        private DateTimeOffset _now = now;

        public override DateTimeOffset GetUtcNow() => _now;

        public void Advance(TimeSpan duration) => _now += duration;
    }
}
