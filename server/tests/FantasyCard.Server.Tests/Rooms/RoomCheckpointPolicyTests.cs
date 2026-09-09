using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomCheckpointPolicyTests
{
    [Fact]
    public void Ordinary_combat_is_throttled_but_critical_state_changes_save_immediately()
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 47);
        var playerId = Guid.NewGuid();
        room.AddPlayer(new(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(Guid.NewGuid(), "monster-1",
                [new MonsterCombatState("monster-1", 100, 100, 0, TimeSpan.FromSeconds(5),
                    [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)])])));
        var initial = room.Capture();
        var marker = RoomCheckpointPolicy.CreateCriticalMarker(initial);

        room.GetPlayer(playerId).Combat.TakeDamage(1);
        var combatOnly = room.Capture() with { Revision = initial.Revision + 1 };
        Assert.False(RoomCheckpointPolicy.ShouldSave(initial.Revision, marker, combatOnly));

        var moved = combatOnly with
        {
            Players = combatOnly.Players.Select(player =>
                player.PlayerId == playerId ? player with { Position = new MapPosition(0, 1) } : player).ToArray()
        };
        Assert.True(RoomCheckpointPolicy.ShouldSave(initial.Revision, marker, moved));
        Assert.True(RoomCheckpointPolicy.ShouldSave(initial.Revision, marker, combatOnly with { Revision = initial.Revision + 10 }));
    }

    [Fact]
    public void Reward_relic_extraction_and_disconnect_markers_are_critical()
    {
        var playerId = Guid.NewGuid();
        var basePlayer = new RoomPlayerSnapshot(
            playerId,
            HeroClass.Priest,
            RoomPlayerPhase.ActionBar,
            null,
            CreateCombatSnapshot(),
            null,
            Inventory: new ExplorationInventory(20, 0).Capture());
        var baseline = new BattleRoomSnapshot(Guid.NewGuid(), "test", 1, TimeSpan.Zero, [basePlayer], []);
        var marker = RoomCheckpointPolicy.CreateCriticalMarker(baseline);

        AssertCritical(basePlayer with { ExtractionRemaining = TimeSpan.FromSeconds(3) });
        AssertCritical(basePlayer with { SpringDrink = new SpringDrinkSnapshot(new MapPosition(0, 0), TimeSpan.FromSeconds(1.2)) });
        AssertCritical(basePlayer with { ConsumedSprings = [new MapPosition(0, 0)] });
        AssertCritical(basePlayer with { DisconnectedRemaining = TimeSpan.FromSeconds(15) });
        AssertCritical(basePlayer with
        {
            Phase = RoomPlayerPhase.Choice,
            RewardChoice = RewardChoiceState.Create(ChaosMapLayer.Outer, new Random(3)).Capture()
        });

        var relic = baseline with
        {
            Revision = 2,
            RelicPiles = [new RelicPileSnapshot(Guid.NewGuid(), playerId.ToString("D"), new MapPosition(0, 0), 1,
                [new ExplorationItem("gold", ExplorationItemKind.Gold, 10)])]
        };
        Assert.True(RoomCheckpointPolicy.ShouldSave(1, marker, relic));

        void AssertCritical(RoomPlayerSnapshot player)
        {
            var changed = baseline with { Revision = 2, Players = [player] };
            Assert.True(RoomCheckpointPolicy.ShouldSave(1, marker, changed));
        }
    }

    private static PlayerCombatSnapshot CreateCombatSnapshot()
    {
        var combat = new PlayerCombatState(
            HeroClass.Priest,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new Random(5));
        return combat.Capture();
    }
}
