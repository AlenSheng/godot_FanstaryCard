using FantasyCard.Domain.Configuration;

namespace FantasyCard.Domain.Matches;

public enum BackpackTier : short
{
    Free = 1,
    Advanced = 2,
    Top = 3
}

public static class PreparationRules
{
    public const int EquipmentSlotCount = 5;
    public const int MaximumPotionCount = 2;

    public static void Validate(
        IReadOnlyList<Guid?> equipmentIds,
        BackpackTier backpackTier,
        IReadOnlyList<int> safeSlotIndexes,
        int potionCount)
    {
        if (equipmentIds.Count != EquipmentSlotCount)
        {
            throw new Players.DomainValidationException(
                $"Equipment loadout must contain exactly {EquipmentSlotCount} positional slots.");
        }

        var duplicateEquipment = equipmentIds
            .Where(id => id.HasValue)
            .GroupBy(id => id!.Value)
            .Any(group => group.Count() > 1);
        if (duplicateEquipment)
        {
            throw new Players.DomainValidationException("The same equipment cannot occupy multiple slots.");
        }

        if (potionCount is < 0 or > MaximumPotionCount)
        {
            throw new Players.DomainValidationException(
                $"Potion count must be between 0 and {MaximumPotionCount}.");
        }

        if (!Enum.IsDefined(backpackTier))
            throw new Players.DomainValidationException("Unknown backpack tier.");
        var backpack = GameConfigCatalog.Current.Backpack(backpackTier.ToString());
        var capacity = backpack.Capacity;
        var safeSlotCount = backpack.SafeSlots;

        if (safeSlotIndexes.Count != safeSlotCount || safeSlotIndexes.Distinct().Count() != safeSlotCount)
        {
            throw new Players.DomainValidationException(
                $"{backpackTier} backpack requires exactly {safeSlotCount} distinct safe slot indexes.");
        }

        if (safeSlotIndexes.Any(index => index < 0 || index >= capacity))
        {
            throw new Players.DomainValidationException("Safe slot index is outside the backpack capacity.");
        }
    }
}
