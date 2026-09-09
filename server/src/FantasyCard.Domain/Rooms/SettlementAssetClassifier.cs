namespace FantasyCard.Domain.Rooms;

public sealed record SettlementAsset(
    string AssetKind,
    string AssetId,
    bool IsSafe,
    long Quantity = 1,
    EquipmentRewardData? Equipment = null,
    string? Destination = null);

public sealed record DeathAssetDisposition(
    IReadOnlyList<SettlementAsset> ReturnToPlayer,
    IReadOnlyList<SettlementAsset> ToRelicPile,
    IReadOnlyList<SettlementAsset> ExcludedFromRelicPile);

public static class SettlementAssetClassifier
{
    public static DeathAssetDisposition ClassifyDeath(
        IReadOnlyList<ExplorationItem> inventory,
        IReadOnlyList<SettlementAsset> wornArmor,
        SettlementAsset classWeapon)
    {
        ArgumentNullException.ThrowIfNull(inventory);
        ArgumentNullException.ThrowIfNull(wornArmor);
        ArgumentNullException.ThrowIfNull(classWeapon);
        if (!string.Equals(classWeapon.AssetKind, "ClassWeapon", StringComparison.Ordinal))
            throw new ArgumentException("The excluded asset must be the class weapon.", nameof(classWeapon));

        var safe = inventory.Where(item => item.IsSafe)
            .Select(ToAsset)
            .ToArray();
        var unsafeItems = inventory.Where(item => !item.IsSafe)
            .Select(ToAsset)
            .Concat(wornArmor)
            .ToArray();
        return new DeathAssetDisposition(safe, unsafeItems, [classWeapon]);
    }

    private static SettlementAsset ToAsset(ExplorationItem item) =>
        new(item.Kind.ToString(), item.ItemId, item.IsSafe, item.Quantity, item.Equipment);
}
