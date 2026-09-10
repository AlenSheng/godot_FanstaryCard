using FantasyCard.Contracts.Players;

namespace FantasyCard.Contracts.Progression;

public sealed record WalletResponse(long Gold, long Diamond);

public sealed record MaterialsResponse(
    long WarriorSoul,
    long PriestSoul,
    long MageSoul,
    long GuardianSoul,
    long EquipmentFragments);

public sealed record CardResponse(
    string CardId,
    HeroClassDto? HeroClass,
    string Rarity,
    bool Unlocked,
    int CopyCount,
    int Level,
    long Version,
    long CraftCost = 0,
    long UpgradeSoulSpent = 0,
    long DismantleRefund = 0,
    string CurrencyKind = "WarriorSoul",
    bool CanDismantle = false,
    string? BlockedReason = null,
    long UpgradeCost = 0,
    int UpgradeCopyCost = 0,
    bool CanUpgrade = false,
    string? UpgradeBlockedReason = null,
    CardEffectResponse? CurrentEffect = null,
    CardEffectResponse? NextEffect = null);

public sealed record CardEffectResponse(
    int ElementalDamage,
    string Element,
    int DirectDamage,
    int Heal,
    int Shield,
    double DrawCharge,
    int ImmediateDraw,
    double DrawSpeedModifier,
    double DrawSpeedSeconds,
    double StunSeconds,
    double DrawBlockSeconds,
    int HealthCost,
    int SameElementBonus,
    int ResonanceBonus,
    double ConflictCancelBonus,
    double ConflictHealCoefficient,
    bool IsClassReveal,
    int SecondaryElementalDamage = 0,
    string SecondaryElement = "None");

public sealed record CardMutationRequest(long ExpectedVersion);

public sealed record CardMutationResponse(
    CardResponse Card,
    MaterialsResponse Materials,
    string CurrencyKind,
    long SoulAmount,
    int ConsumedCopies = 0);

public sealed record DeckResponse(
    Guid DeckId,
    HeroClassDto HeroClass,
    IReadOnlyList<string> CardIds,
    long Version,
    DateTimeOffset UpdatedAt);

public sealed record UpdateDeckRequest(IReadOnlyList<string>? CardIds, long ExpectedVersion);

public sealed record ClassWeaponResponse(HeroClassDto HeroClass, int Level, long Version);

public sealed record EquipmentResponse(
    Guid InstanceId,
    string Slot,
    string Quality,
    int Level,
    bool IsBound,
    string Location,
    long Version,
    string? Element = null,
    string? EffectAffix = null,
    string? SecondaryTrait = null);

public sealed record LoadoutResponse(
    HeroClassDto HeroClass,
    IReadOnlyList<Guid?> EquipmentIds,
    long Version);

public sealed record InventorySummaryResponse(int Capacity, int EquipmentCount, int FreeSlots);

public sealed record InventoryConsumablesResponse(
    int HealthPotionCount,
    int AdvancedBagCount,
    int TopBagCount);

public sealed record InventoryResponse(
    InventorySummaryResponse Summary,
    IReadOnlyList<EquipmentResponse> Equipments,
    InventoryConsumablesResponse Consumables);

public sealed record UpdateLoadoutRequest(
    IReadOnlyList<Guid?>? EquipmentIds,
    long ExpectedVersion);

public sealed record EnhanceEquipmentRequest(
    long ExpectedVersion,
    Guid? MaterialEquipmentId = null);

public sealed record EnhancementQuoteResponse(
    string TargetKind,
    int CurrentLevel,
    int? NextLevel,
    long ExpectedVersion,
    long FragmentCost,
    int MaterialCount,
    string? MaterialQuality,
    long AvailableFragments,
    int AvailableMaterialCount,
    bool CanEnhance,
    string? BlockedReason);

public sealed record EnhanceResult(
    EquipmentResponse Equipment,
    long EquipmentFragments,
    Guid? ConsumedMaterialEquipmentId);
