using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomObservationCoalescingTests
{
    [Fact]
    public async Task CoalescedSnapshotsKeepBothPlayersEventsWithoutBlockingAuthoritativeCommands()
    {
        var first=Guid.NewGuid();var second=Guid.NewGuid();var room=new BattleRoom(Guid.NewGuid(),"observer-fixture",CombatCardCatalog.CreatePrototype(),73);
        var deck=Enumerable.Range(1,20).Select(i=>$"common-{i:D2}").ToArray();
        room.AddPlayer(new(first,HeroClass.Mage,deck,null));room.AddPlayer(new(second,HeroClass.Priest,deck,null));
        room.InitializeMap(ChaosMapGenerator.Generate(73,2),DateTimeOffset.UnixEpoch);
        var blocked=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);var release=new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var observed=new List<BattleRoomSnapshot>();var gate=new object();var ct=TestContext.Current.CancellationToken;
        var actor=new RoomActor(room,TimeProvider.System,startTicker:false,snapshotObserver:async snapshot=>
        {
            lock(gate)observed.Add(snapshot);blocked.TrySetResult();await release.Task;
        });
        try
        {
            await actor.ExecuteAsync(new AdvanceRoomTimeCommand(TimeSpan.FromMilliseconds(100),DateTimeOffset.UnixEpoch.AddMilliseconds(100)),ct);
            await blocked.Task.WaitAsync(TimeSpan.FromSeconds(2),ct);
            await actor.ExecuteAsync(new AbandonBattleCommand(first),ct).AsTask().WaitAsync(TimeSpan.FromSeconds(2),ct);
            await actor.ExecuteAsync(new AbandonBattleCommand(second),ct).AsTask().WaitAsync(TimeSpan.FromSeconds(2),ct);
        }
        finally{release.TrySetResult();await actor.DisposeAsync();}
        lock(gate)
        {
            Assert.Equal(2,observed.Count);Assert.Empty(observed[0].Observations!.Events);var events=observed[1].Observations!.Events;
            Assert.Equal(4,events.Count);Assert.Equal(2,events.Select(e=>e.PlayerId).Distinct().Count());Assert.Equal(new long[]{1,2,3,4},events.Select(e=>e.Sequence));
        }
    }
}
