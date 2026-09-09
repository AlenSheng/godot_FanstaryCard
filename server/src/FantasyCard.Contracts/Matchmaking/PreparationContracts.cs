using FantasyCard.Contracts.Players;

namespace FantasyCard.Contracts.Matchmaking;

public enum BackpackTierDto
{
    Free = 1,
    Advanced = 2,
    Top = 3
}

public sealed record CreatePreparationRequest(
    HeroClassDto HeroClass,
    long DeckVersion,
    IReadOnlyList<Guid?>? EquipmentIds,
    BackpackTierDto BackpackTier,
    IReadOnlyList<int>? SafeSlotIndexes,
    int PotionCount,
    string? Difficulty);

public sealed record PreparationSnapshotResponse(
    HeroClassDto HeroClass,
    int MaximumHp,
    IReadOnlyList<string> CardIds,
    IReadOnlyList<Guid?> EquipmentIds,
    int ClassWeaponLevel,
    BackpackTierDto BackpackTier,
    int BackpackCapacity,
    IReadOnlyList<int> SafeSlotIndexes,
    int PotionCount,
    string Difficulty,
    string ConfigVersion,
    IReadOnlyList<PreparationEquipmentSnapshotResponse>? EquipmentSnapshots = null);

public sealed record PreparationEquipmentSnapshotResponse(
    Guid InstanceId,
    string Slot,
    string Quality,
    int Level,
    string Element,
    string? EffectAffix,
    string? SecondaryTrait);

public sealed record PreparationResponse(
    Guid PreparationId,
    string Status,
    PreparationSnapshotResponse Snapshot,
    DateTimeOffset CreatedAt,
    DateTimeOffset ExpiresAt);
