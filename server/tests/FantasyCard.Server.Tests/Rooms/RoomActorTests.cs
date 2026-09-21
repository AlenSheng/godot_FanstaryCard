using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomActorTests
{
    [Fact]
    public async Task Revision_check_rejects_future_versions_after_prior_writes()
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 1);
        await using var actor = new RoomActor(room, TimeProvider.System, startTicker: false);
        var token = TestContext.Current.CancellationToken;
        var first = actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100)), 0, token).AsTask();
        var stale = actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(10)), 2, token).AsTask();
        await first;
        await Assert.ThrowsAsync<DomainValidationException>(() => stale);
        var snapshot = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), token);
        Assert.Equal(1, snapshot.Revision);
        Assert.Equal(TimeSpan.FromMilliseconds(100), snapshot.Elapsed);
        await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100)), 1, token);
        Assert.Equal(2, (await actor.ExecuteAsync(new GetRoomSnapshotCommand(), token)).Revision);
    }

    [Fact]
    public async Task Concurrent_commands_are_serialized_by_single_reader()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(
            Guid.NewGuid(),
            "test-config",
            CombatCardCatalog.CreatePrototype(),
            seed: 42);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(
                Guid.NewGuid(),
                "monster",
                [
                    new MonsterCombatState(
                        "monster",
                        500,
                        500,
                        0,
                        TimeSpan.FromSeconds(100),
                        [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)])
                ])));
        await using var actor = new RoomActor(room, TimeProvider.System, startTicker: false);

        var commands = Enumerable.Range(0, 100)
            .Select(_ => actor.ExecuteAsync(
                new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100)),
                TestContext.Current.CancellationToken).AsTask())
            .ToArray();
        await Task.WhenAll(commands);
        var snapshot = await actor.ExecuteAsync(
            new GetRoomSnapshotCommand(),
            TestContext.Current.CancellationToken);

        Assert.Equal(TimeSpan.FromSeconds(10), snapshot.Elapsed);
        Assert.Equal(100, snapshot.Revision);
    }

    [Fact]
    public async Task Recovery_downtime_replays_the_same_authoritative_ticks()
    {
        var playerId = Guid.NewGuid();
        var original = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 42);
        original.AddPlayer(CreatePlayer(playerId, HeroClass.Mage));
        var checkpoint = original.Capture();
        var expectedRoom = BattleRoom.Restore(checkpoint, CombatCardCatalog.CreatePrototype(), 42);
        var recoveredRoom = BattleRoom.Restore(checkpoint, CombatCardCatalog.CreatePrototype(), 42);
        await using var expectedActor = new RoomActor(expectedRoom, TimeProvider.System, startTicker: false);
        await using var recoveredActor = new RoomActor(recoveredRoom, TimeProvider.System, startTicker: false);
        var recoveredAt = new DateTimeOffset(2026, 9, 7, 6, 0, 2, TimeSpan.Zero);

        for (var tick = 0; tick < 20; tick++)
            await expectedActor.ExecuteAsync(
                new AdvanceRoomTimeCommand(RoomActor.TickInterval, recoveredAt - TimeSpan.FromSeconds(2) + RoomActor.TickInterval * (tick + 1)),
                TestContext.Current.CancellationToken);
        var expected = await expectedActor.ExecuteAsync(
            new GetRoomSnapshotCommand(), TestContext.Current.CancellationToken);

        var recovered = await recoveredActor.ExecuteAsync(
            new RecoverRoomDowntimeCommand(TimeSpan.FromSeconds(2), recoveredAt),
            TestContext.Current.CancellationToken);

        Assert.Equivalent(expected, recovered, strict: true);
    }

    [Fact]
    public async Task Actor_round_trips_complete_duel_snapshot()
    {
        var firstId = Guid.NewGuid();
        var lateId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 1);
        room.AddPlayer(CreatePlayer(firstId, HeroClass.Priest));
        room.AddPlayer(CreatePlayer(lateId, HeroClass.Mage));
        var before = room.CapturePlayer(firstId);
        await using var actor = new RoomActor(room, TimeProvider.System, startTicker: false);

        var duel = await actor.ExecuteAsync(
            new StartRoomDuelCommand(firstId, lateId, DateTimeOffset.UnixEpoch),
            TestContext.Current.CancellationToken);
        await actor.ExecuteAsync(
            new AdvanceRoomTimeCommand(TimeSpan.FromSeconds(3)),
            TestContext.Current.CancellationToken);
        await actor.ExecuteAsync(new EndRoomDuelSurvivedCommand(
            duel.DuelId,
            DuelEndReason.MutualLeave),
            TestContext.Current.CancellationToken);
        var snapshot = await actor.ExecuteAsync(
            new GetRoomSnapshotCommand(),
            TestContext.Current.CancellationToken);

        Assert.Equivalent(before, snapshot.Players.Single(player => player.PlayerId == firstId), strict: true);
    }

    [Fact]
    public async Task Dispose_drains_commands_that_were_already_accepted()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 7);
        room.AddPlayer(CreatePlayer(playerId, HeroClass.Guardian));
        var actor = new RoomActor(room, TimeProvider.System, startTicker: false);

        var commands = Enumerable.Range(0, 20)
            .Select(_ => actor.ExecuteAsync(
                new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100))).AsTask())
            .ToArray();

        await actor.DisposeAsync();
        var results = await Task.WhenAll(commands).WaitAsync(
            TimeSpan.FromSeconds(2),
            TestContext.Current.CancellationToken);

        Assert.All(commands, command => Assert.True(command.IsCompletedSuccessfully));
        Assert.Equal(TimeSpan.FromSeconds(2), results[^1].Elapsed);
    }

    [Fact]
    public async Task Slow_observers_do_not_block_authoritative_commands_and_snapshots_coalesce()
    {
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var observed = new List<long>();
        var observedGate = new object();
        var room = new BattleRoom(Guid.NewGuid(), "test-config", CombatCardCatalog.CreatePrototype(), 9);
        var actor = new RoomActor(
            room,
            TimeProvider.System,
            startTicker: false,
            snapshotObserver: async snapshot =>
            {
                lock (observedGate) observed.Add(snapshot.Revision);
                started.TrySetResult();
                await release.Task;
            });

        await actor.ExecuteAsync(new AdvanceRoomTimeCommand(RoomActor.TickInterval),
            TestContext.Current.CancellationToken);
        await started.Task.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);

        // The first observer is intentionally blocked.  The actor must still
        // accept and apply the next command, retaining only its newest
        // snapshot for the observer queue.
        var second = actor.ExecuteAsync(new AdvanceRoomTimeCommand(RoomActor.TickInterval),
            TestContext.Current.CancellationToken).AsTask();
        await second.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        var third = actor.ExecuteAsync(new AdvanceRoomTimeCommand(RoomActor.TickInterval),
            TestContext.Current.CancellationToken).AsTask();
        await third.WaitAsync(TimeSpan.FromSeconds(2), TestContext.Current.CancellationToken);
        var current = await actor.ExecuteAsync(new GetRoomSnapshotCommand(),
            TestContext.Current.CancellationToken);
        Assert.Equal(3, current.Revision);

        release.TrySetResult();
        await actor.DisposeAsync();
        lock (observedGate)
        {
            Assert.Equal([1L, 3L], observed);
        }
    }

    private static BattleRoomPlayerSetup CreatePlayer(Guid playerId, HeroClass heroClass) =>
        new(
            playerId,
            heroClass,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(
                Guid.NewGuid(),
                "monster",
                [
                    new MonsterCombatState(
                        "monster",
                        80,
                        80,
                        0,
                        TimeSpan.FromSeconds(4),
                        [new MonsterIntentState(MonsterIntentKind.Attack, 3, CardElement.Fire)])
                ]));
}
