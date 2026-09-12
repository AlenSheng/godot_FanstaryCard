namespace FantasyCard.Domain.Rooms;

/// <summary>
/// GDD 2.5.2: after a death return, grant one bound white pair of shoes when a
/// class loadout has an empty Feet slot and the development bag has no wearable shoes.
/// </summary>
public static class DeathReturnRules
{
    public const string ReplacementSlot = "Feet";
    public const string ReplacementQuality = "White";
    public const int ReplacementLevel = 0;
    public const bool ReplacementBound = true;
    public const string ReplacementElement = "Fire";
    public const string ReplacementSecondaryTrait = "DrawInterval";
    public const string MovementSource = "SystemGrant";
    public const string MovementReason = "settlement.death.replacement_shoes";

    public static bool ShouldGrantBoundWhiteShoes(
        bool loadoutFeetEmpty,
        bool hasWearableInventoryShoes) =>
        loadoutFeetEmpty && !hasWearableInventoryShoes;
}
