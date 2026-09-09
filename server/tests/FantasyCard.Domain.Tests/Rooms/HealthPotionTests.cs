using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class HealthPotionTests
{
    [Theory]
    [InlineData(HeroClass.Priest, 16)]
    [InlineData(HeroClass.Mage, 14)]
    [InlineData(HeroClass.Guardian, 20)]
    public void Action_bar_use_consumes_one_potion_and_immediately_restores_twenty_percent(
        HeroClass heroClass,
        int expectedHeal)
    {
        var playerId = Guid.NewGuid();
        var room = CreateRoom(playerId, heroClass, actionBar: true);
        var player = room.GetPlayer(playerId);
        player.Inventory.TryAdd(new ExplorationItem("health_potion:1", ExplorationItemKind.HealthPotion));
        player.Combat.TakeDamage(40);
        var revision = room.Revision;

        var result = room.UsePotion(playerId);

        Assert.Equal("health_potion:1", result.ItemId);
        Assert.Equal(expectedHeal, result.Healed);
        Assert.Equal(player.Combat.MaximumHp - 40 + expectedHeal, player.Combat.Hp);
        Assert.DoesNotContain(player.Inventory.Items, item => item.Kind == ExplorationItemKind.HealthPotion);
        Assert.Equal(revision + 1, result.RoomRevision);
    }

    [Fact]
    public void Full_health_use_still_consumes_the_potion()
    {
        var playerId = Guid.NewGuid();
        var room = CreateRoom(playerId, HeroClass.Mage, actionBar: true);
        var player = room.GetPlayer(playerId);
        player.Inventory.TryAdd(new ExplorationItem("health_potion:1", ExplorationItemKind.HealthPotion));

        var result = room.UsePotion(playerId);

        Assert.Equal(0, result.Healed);
        Assert.Empty(player.Inventory.Items);
    }

    [Fact]
    public void Combat_use_is_rejected_without_consuming_the_potion()
    {
        var playerId = Guid.NewGuid();
        var room = CreateRoom(playerId, HeroClass.Mage, actionBar: false);
        var player = room.GetPlayer(playerId);
        player.Inventory.TryAdd(new ExplorationItem("health_potion:1", ExplorationItemKind.HealthPotion));

        Assert.Throws<DomainValidationException>(() => room.UsePotion(playerId));

        Assert.Contains(player.Inventory.Items, item => item.Kind == ExplorationItemKind.HealthPotion);
    }

    [Fact]
    public void Vitality_bonus_applies_after_base_rounding_and_heal_respects_effective_maximum()
    {
        var playerId = Guid.NewGuid();
        var equipment = new CombatEquipmentProfile(
            new ElementalEquipmentModifiers(),
            VitalityHealBonus: 0.25,
            VitalityOvercapBonus: 0.10);
        var room = CreateRoom(playerId, HeroClass.Mage, actionBar: true, equipment);
        var player = room.GetPlayer(playerId);
        player.Inventory.TryAdd(new ExplorationItem("health_potion:1", ExplorationItemKind.HealthPotion));
        player.Combat.TakeDamage(5);

        var result = room.UsePotion(playerId);

        Assert.Equal(12, result.Healed);
        Assert.Equal(player.Combat.EffectiveMaximumHp, player.Combat.Hp);
    }

    private static BattleRoom CreateRoom(
        Guid playerId,
        HeroClass heroClass,
        bool actionBar,
        CombatEquipmentProfile? equipment = null)
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "potion-test", catalog, 997);
        room.AddPlayer(new BattleRoomPlayerSetup(
            playerId,
            heroClass,
            Enumerable.Range(1, 20).Select(card => $"common-{card:D2}").ToArray(),
            null,
            Equipment: equipment));
        room.InitializeMap(ChaosMapGenerator.Generate(997, 1));
        if (!actionBar) return room;

        var snapshot = room.Capture();
        snapshot = snapshot with
        {
            Players = snapshot.Players.Select(player => player with
            {
                Phase = RoomPlayerPhase.ActionBar,
                Pve = null
            }).ToArray()
        };
        return BattleRoom.Restore(snapshot, catalog, 997);
    }
}
