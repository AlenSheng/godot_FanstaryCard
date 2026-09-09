using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RoomRandomStreamTests
{
    [Fact]
    public void Reward_refresh_advances_only_reward_stream_and_replays_after_restore()
    {
        var snapshot = CreateChoiceSnapshot();
        var first = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 101);
        var replay = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 101);
        var before = first.Capture().RandomStreams!;

        var firstReceipt = first.RefreshRewardChoice(
            snapshot.Players[0].PlayerId, first.Revision, requestId: "refresh-1");
        var replayReceipt = replay.RefreshRewardChoice(
            snapshot.Players[0].PlayerId, replay.Revision, requestId: "refresh-1");
        var after = first.Capture().RandomStreams!;

        Assert.NotEqual(before.Reward, after.Reward);
        Assert.Equal(before.PlayerSeed, after.PlayerSeed);
        Assert.Equal(before.Loot, after.Loot);
        Assert.Equal(before.Escape, after.Escape);
        Assert.Equal(before.Bot, after.Bot);
        Assert.Equal(before.Duel, after.Duel);
        Assert.Equivalent(firstReceipt, replayReceipt, strict: true);
        Assert.Equivalent(first.Capture().RandomStreams, replay.Capture().RandomStreams, strict: true);
    }

    [Fact]
    public void Legacy_single_random_state_remains_recoverable_until_snapshot_upgrade()
    {
        var snapshot = CreateChoiceSnapshot() with
        {
            RandomState = 0xA0761D6478BD642FUL,
            RandomStreams = null
        };
        var room = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 103);
        var before = room.Capture().RandomState;

        room.RefreshRewardChoice(snapshot.Players[0].PlayerId, room.Revision, requestId: "legacy-refresh");
        var after = room.Capture();

        Assert.NotNull(before);
        Assert.NotEqual(before, after.RandomState);
        Assert.Null(after.RandomStreams);
    }

    private static BattleRoomSnapshot CreateChoiceSnapshot()
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 101);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            null));
        room.GetPlayer(playerId).Inventory.TryAdd(new ExplorationItem("gold", ExplorationItemKind.Gold, 1000));
        var snapshot = room.Capture();
        return snapshot with
        {
            Players = snapshot.Players.Select(player => player with
            {
                Phase = RoomPlayerPhase.Choice,
                RewardChoice = RewardChoiceState.Create(ChaosMapLayer.Outer, new Random(17)).Capture()
            }).ToArray()
        };
    }
}
