using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class BattleTargetSelectionTests
{
    [Fact]
    public void Selecting_a_live_pve_target_updates_revision_and_survives_restore()
    {
        var playerId = Guid.NewGuid();
        var battleId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 73);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Mage,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(battleId, "monster-1",
            [
                Monster("monster-1", 100),
                Monster("monster-2", 100)
            ])));

        var revision = room.SelectPveTarget(playerId, battleId, "monster-2", room.Revision);

        Assert.Equal(1, revision);
        Assert.Equal("monster-2", room.CapturePlayer(playerId).Pve!.CurrentTargetId);
        var restored = BattleRoom.Restore(room.Capture(), CombatCardCatalog.CreatePrototype(), 73);
        Assert.Equal("monster-2", restored.CapturePlayer(playerId).Pve!.CurrentTargetId);
    }

    [Fact]
    public void Selecting_a_dead_or_foreign_target_is_rejected_without_mutation()
    {
        var playerId = Guid.NewGuid();
        var battleId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 79);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            HeroClass.Priest,
            Enumerable.Range(1, 20).Select(index => $"common-{index:D2}").ToArray(),
            new PveBattleState(battleId, "monster-live",
            [
                Monster("monster-live", 100),
                Monster("monster-dead", 0)
            ])));

        Assert.Throws<DomainValidationException>(() =>
            room.SelectPveTarget(playerId, battleId, "monster-dead", room.Revision));
        Assert.Throws<DomainValidationException>(() =>
            room.SelectPveTarget(playerId, battleId, "not-in-battle", room.Revision));
        Assert.Equal(0, room.Revision);
        Assert.Equal("monster-live", room.CapturePlayer(playerId).Pve!.CurrentTargetId);
    }

    private static MonsterCombatState Monster(string id, int hp) =>
        new(id, 100, hp, 0, TimeSpan.FromSeconds(5),
            [new MonsterIntentState(MonsterIntentKind.Attack, 1, CardElement.Fire)]);
}
