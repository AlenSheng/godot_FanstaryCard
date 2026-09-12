using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class DeathReturnRulesTests
{
    [Fact]
    public void Empty_feet_and_no_inventory_shoes_requires_a_bound_white_pair()
    {
        Assert.True(DeathReturnRules.ShouldGrantBoundWhiteShoes(
            loadoutFeetEmpty: true,
            hasWearableInventoryShoes: false));
    }

    [Fact]
    public void Inventory_shoes_block_a_system_grant_even_when_the_loadout_slot_is_empty()
    {
        Assert.False(DeathReturnRules.ShouldGrantBoundWhiteShoes(
            loadoutFeetEmpty: true,
            hasWearableInventoryShoes: true));
    }

    [Fact]
    public void An_occupied_feet_slot_does_not_receive_another_pair()
    {
        Assert.False(DeathReturnRules.ShouldGrantBoundWhiteShoes(
            loadoutFeetEmpty: false,
            hasWearableInventoryShoes: false));
    }

    [Fact]
    public void Replacement_shoes_match_the_starter_bound_white_pair()
    {
        Assert.Equal("Feet", DeathReturnRules.ReplacementSlot);
        Assert.Equal("White", DeathReturnRules.ReplacementQuality);
        Assert.Equal(0, DeathReturnRules.ReplacementLevel);
        Assert.True(DeathReturnRules.ReplacementBound);
        Assert.Equal("Fire", DeathReturnRules.ReplacementElement);
        Assert.Equal("DrawInterval", DeathReturnRules.ReplacementSecondaryTrait);
    }
}
