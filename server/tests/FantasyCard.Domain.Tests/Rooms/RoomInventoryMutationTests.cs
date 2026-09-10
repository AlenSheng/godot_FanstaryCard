using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RoomInventoryMutationTests
{
    private static readonly CombatCardCatalog Catalog = CombatCardCatalog.CreatePrototype();

    [Fact]
    public void Moving_between_safe_and_normal_slots_swaps_the_contents_and_survives_restore()
    {
        var room = CreateRoom(capacity: 28, safeSlots: 1, safeIndexes: [4]);
        var player = room.Capture().Players.Single().PlayerId;
        var inventory = room.GetPlayer(player).Inventory;
        inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 25));
        inventory.TryAdd(new("potion", ExplorationItemKind.HealthPotion, SlotIndex: 4));

        room.MoveInventoryItem(player, "gold", 4);

        Assert.True(inventory.Items.Single(item => item.ItemId == "gold").IsSafe);
        Assert.False(inventory.Items.Single(item => item.ItemId == "potion").IsSafe);
        Assert.Equal(0, inventory.Items.Single(item => item.ItemId == "potion").SlotIndex);
        var restored = BattleRoom.Restore(room.Capture(), Catalog, 11);
        Assert.Equivalent(room.Capture(), restored.Capture(), strict: true);
    }

    [Fact]
    public void A_full_backpack_can_swap_armor_and_breaking_vitality_clamps_health_without_healing()
    {
        var armor = new[] { Armor("Head", "Purple", "Vitality"), Armor("Chest", "Purple", "Vitality"), Armor("Feet", "Purple", "Vitality") };
        var room = CreateRoom(armor, 28, 1);
        var player = room.GetPlayer(room.Capture().Players.Single().PlayerId);
        player.Combat.Heal(100);
        Assert.True(player.Combat.Hp > player.Combat.MaximumHp);
        var replacement = Armor("Head");
        player.Inventory.TryAdd(replacement with { SlotIndex = 27 });
        Fill(player.Inventory);

        room.EquipInventoryItem(player.PlayerId, replacement.ItemId);

        Assert.Equal(player.Combat.MaximumHp, player.Combat.Hp);
        Assert.Equal(0, player.Combat.Equipment.VitalityOvercapBonus);
        Assert.Equal(28, player.Inventory.Items.Count);
        var returned = player.Inventory.Items.Single(item => item.ItemId == armor[0].ItemId);
        Assert.True(returned.IsSafe);
        Assert.Equal(27, returned.SlotIndex);
        Assert.DoesNotContain(player.Inventory.Items, item => item.ItemId == replacement.ItemId);
        Assert.False(player.WornArmor.Single(item => item.ItemId == replacement.ItemId).IsSafe);
        Assert.Equivalent(room.Capture(), BattleRoom.Restore(room.Capture(), Catalog, 11).Capture(), strict: true);
    }

    [Fact]
    public void Second_orange_armor_and_unequip_into_full_backpack_are_atomic_rejections()
    {
        var room = CreateRoom([Armor("Head", "Orange", "Piercing")]);
        var player = room.GetPlayer(room.Capture().Players.Single().PlayerId);
        var orange = Armor("Chest", "Orange", "Vitality");
        player.Inventory.TryAdd(orange);
        Fill(player.Inventory);
        var before = room.Capture();

        Assert.Throws<DomainValidationException>(() => room.EquipInventoryItem(player.PlayerId, orange.ItemId));
        Assert.Throws<DomainValidationException>(() => room.UnequipArmor(player.PlayerId, "Head"));
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Fact]
    public void Inventory_and_relic_reads_are_locked_during_pvp()
    {
        var room = CreateRoom([Armor("Head")]);
        var player = room.GetPlayer(room.Capture().Players.Single().PlayerId);
        player.Inventory.TryAdd(new("gold", ExplorationItemKind.Gold, 1));
        var other = Guid.NewGuid();
        room.AddPlayer(new(other, HeroClass.Priest, Enumerable.Repeat("common-01", 20).ToArray(), null));
        room.StartDuel(player.PlayerId, other, DateTimeOffset.UnixEpoch);
        var before = room.Capture();

        Assert.Throws<DomainValidationException>(() => room.MoveInventoryItem(player.PlayerId, "gold", 1));
        Assert.Throws<DomainValidationException>(() => room.UnequipArmor(player.PlayerId, "Head"));
        Assert.Throws<DomainValidationException>(() => room.GetAvailableRelicPiles(player.PlayerId));
        Assert.Equivalent(before, room.Capture(), strict: true);
    }

    [Fact]
    public void Direct_reward_equip_recycles_selected_removed_armor_when_full_and_records_it_for_settlement()
    {
        var previous = Armor("Head", level: 3);
        var reward = Armor("Head", "Blue") with { IsGenerated = true };
        var room = CreateRoom([previous]);
        var playerId = room.Capture().Players.Single().PlayerId;
        Fill(room.GetPlayer(playerId).Inventory);
        room = WithReward(room, reward);
        var before = room.Capture();
        Assert.Throws<DomainValidationException>(() => room.ClaimReward(playerId, "equipment", equip: true));
        Assert.Equivalent(before, room.Capture(), strict: true);

        room.ClaimReward(playerId, "equipment", previous.ItemId, equip: true);

        var player = room.Capture().Players.Single();
        Assert.Equal(reward.ItemId, Assert.Single(player.WornArmor!).ItemId);
        Assert.Equal(previous.ItemId, Assert.Single(player.RecycledEquipment!).ItemId);
        Assert.Equal(20, player.Inventory!.Items.Count);
        Assert.Null(player.RewardChoice);
        Assert.Empty(room.Capture().RelicPiles!);
        Assert.Equivalent(room.Capture(), BattleRoom.Restore(room.Capture(), Catalog, 11).Capture(), strict: true);
    }

    [Fact]
    public void Direct_reward_equip_can_return_old_armor_into_the_recycled_inventory_slot()
    {
        var previous = Armor("Head");
        var reward = Armor("Head", "Green") with { IsGenerated = true };
        var room = CreateRoom([previous], 28, 1);
        var playerId = room.Capture().Players.Single().PlayerId;
        Fill(room.GetPlayer(playerId).Inventory);
        var discarded = room.GetPlayer(playerId).Inventory.Items.Single(item => item.SlotIndex == 27);
        room = WithReward(room, reward);

        room.ClaimReward(playerId, "equipment", discarded.ItemId, equip: true);

        var returned = room.GetPlayer(playerId).Inventory.Items.Single(item => item.ItemId == previous.ItemId);
        Assert.Equal(27, returned.SlotIndex);
        Assert.True(returned.IsSafe);
        Assert.DoesNotContain(room.GetPlayer(playerId).Inventory.Items, item => item.ItemId == discarded.ItemId);
    }

    [Fact]
    public void Failed_relic_replacement_leaves_the_pile_and_inventory_versions_unchanged()
    {
        var inventory = new ExplorationInventory(20, 0);
        Fill(inventory);
        var pile = new RelicPile(Guid.NewGuid(), Guid.NewGuid().ToString("D"), new(1, 1), "Explorer");
        pile.Add(Armor("Feet"));
        var before = pile.Capture();
        var beforeInventory = inventory.Capture();

        Assert.False(pile.TakeToInventory(inventory, before.Items[0].ItemId, before.Version, "missing"));
        Assert.False(pile.TakeToInventory(inventory, before.Items[0].ItemId, before.Version));
        Assert.Equivalent(before, pile.Capture(), strict: true);
        Assert.Equivalent(beforeInventory, inventory.Capture(), strict: true);
        Assert.Equal("Explorer", RelicPile.Restore(before).VictimName);
    }

    [Fact]
    public void Legacy_inventory_flags_get_valid_slots_and_cannot_exceed_the_safe_capacity()
    {
        var restored = ExplorationInventory.Restore(new(28, 1,
            [new("gold", ExplorationItemKind.Gold, 12, true), new("potion", ExplorationItemKind.HealthPotion)]));
        Assert.Equal(27, restored.Items.Single(item => item.ItemId == "gold").SlotIndex);
        Assert.Equal(0, restored.Items.Single(item => item.ItemId == "potion").SlotIndex);
        Assert.False(new ExplorationInventory(20, 0).TryAdd(new("gold", ExplorationItemKind.Gold, 1, true)));
    }

    [Fact]
    public void Unequipping_armor_keeps_its_level_and_bound_identity_in_the_backpack()
    {
        var armor = Armor("Feet", level: 4) with { Equipment = new("Feet", "White", "Fire", null, "DrawInterval", 4, true) };
        var room = CreateRoom([armor]);
        var id = room.Capture().Players.Single().PlayerId;

        room.UnequipArmor(id, "Feet");

        var returned = Assert.Single(room.GetPlayer(id).Inventory.Items);
        Assert.Equal(armor.ItemId, returned.ItemId);
        Assert.Equal(4, returned.Equipment!.Level);
        Assert.True(returned.Equipment.IsBound);
        Assert.False(returned.IsGenerated);
        Assert.Empty(room.GetPlayer(id).WornArmor);
    }

    private static BattleRoom CreateRoom(IReadOnlyList<ExplorationItem>? armor = null, int capacity = 20,
        int safeSlots = 0, IReadOnlyList<int>? safeIndexes = null)
    {
        armor ??= [];
        var profile = EquipmentCombatRules.Calculate(armor.Select(item => new CombatEquipmentItem(
            Guid.Parse(item.ItemId), item.Equipment!.Slot, item.Equipment.Quality, item.Equipment.Level,
            CardElement.Fire, item.Equipment.EffectAffix, item.Equipment.SecondaryTrait)).ToArray());
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog, 11);
        room.AddPlayer(new(Guid.NewGuid(), HeroClass.Mage, Enumerable.Repeat("common-01", 20).ToArray(), null,
            InventoryCapacity: capacity, SafeSlots: safeSlots, WornArmor: armor, Equipment: profile,
            SafeSlotIndexes: safeIndexes, DisplayName: "Explorer"));
        return room;
    }

    private static BattleRoom WithReward(BattleRoom room, ExplorationItem equipment)
    {
        var snapshot = room.Capture();
        var player = snapshot.Players.Single();
        return BattleRoom.Restore(snapshot with { Players = [player with
        {
            Phase = RoomPlayerPhase.Choice,
            RewardChoice = new(ChaosMapLayer.Outer,
                [new("equipment", RewardChoiceKind.Equipment, equipment),
                 new("fragments", RewardChoiceKind.EquipmentFragments, new("equipment_fragments", ExplorationItemKind.EquipmentFragments, 2)),
                 new("heal", RewardChoiceKind.ImmediateHeal, HealPercent: 14)], 0)
        }] }, Catalog, 11);
    }

    private static ExplorationItem Armor(string slot, string quality = "White", string? affix = null, int level = 0) =>
        new(Guid.NewGuid().ToString("D"), ExplorationItemKind.Equipment,
            Equipment: new(slot, quality, "Fire", affix, "DrawInterval", level), IsGenerated: false);

    private static void Fill(ExplorationInventory inventory)
    {
        while (inventory.FreeSlots > 0)
            Assert.True(inventory.TryAdd(new(Guid.NewGuid().ToString("D"), ExplorationItemKind.HealthPotion)));
    }
}
