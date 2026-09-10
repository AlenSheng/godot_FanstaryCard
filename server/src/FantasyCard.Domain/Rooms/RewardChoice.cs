using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public enum RewardChoiceKind : short { Equipment = 1, EquipmentFragments = 2, ImmediateHeal = 3 }

public sealed record EquipmentRewardData(
    string Slot,
    string Quality,
    string Element,
    string? EffectAffix,
    string SecondaryTrait,
    int Level = 0,
    bool IsBound = false);

public static class EquipmentRewardRules
{
    public static bool IsValid(EquipmentRewardData equipment) =>
        (equipment.Slot is "Head" or "Chest" or "Hands" or "Legs" or "Feet") &&
        equipment.Level is >= 0 and <= 5 &&
        (equipment.Quality is "White" or "Green" or "Blue" or "Purple" or "Orange") &&
        (equipment.Element is "Wood" or "Fire" or "Earth" or "Metal" or "Water") &&
        (equipment.EffectAffix is null or "Piercing" or "Bulwark" or "Vitality") &&
        (equipment.SecondaryTrait is "DrawInterval" or "ForcedEscape") &&
        (equipment.SecondaryTrait != "ForcedEscape" || equipment.Slot == "Feet") &&
        (equipment.Quality is "Purple" or "Orange" || equipment.EffectAffix is null) &&
        (equipment.Quality != "Orange" || equipment.EffectAffix is not null);
}

public sealed record RewardChoiceOption(string OptionId, RewardChoiceKind Kind, ExplorationItem? Item = null, int HealPercent = 0);
public sealed record RewardChoiceSnapshot(ChaosMapLayer Layer, IReadOnlyList<RewardChoiceOption> Options, int RefreshCount, bool IsBoss = false, bool IsTreasure = false);
public sealed record RewardRefreshReceiptSnapshot(string RequestId, RewardChoiceSnapshot Choice, long RoomRevision);

public sealed class RewardChoiceState
{
    private readonly List<RewardChoiceOption> _options;
    private RewardChoiceState(ChaosMapLayer layer, IReadOnlyList<RewardChoiceOption> options, int refreshCount, bool isBoss, bool isTreasure)
    {
        if (refreshCount is < 0 or > 3)
            throw new DomainValidationException("Reward refresh count must be between zero and three.");
        if (options.Count != 3 || options.Select(o => o.Kind).Distinct().Count() != 3)
            throw new DomainValidationException("A reward choice must contain one equipment, one fragment, and one heal option.");
        if (isTreasure && (layer != ChaosMapLayer.Outer || isBoss))
            throw new DomainValidationException("Treasure encounters must use outer-layer rewards.");
        Layer = layer; IsBoss = isBoss; IsTreasure = isTreasure; _options = options.ToList(); RefreshCount = refreshCount;
    }
    public ChaosMapLayer Layer { get; }
    public bool IsBoss { get; }
    public bool IsTreasure { get; }
    public IReadOnlyList<RewardChoiceOption> Options => _options;
    public int RefreshCount { get; private set; }
    public static RewardChoiceState Create(ChaosMapLayer layer, Random random, bool isBoss = false, int refreshCount = 0, bool isTreasure = false) => new(layer, CreateOptions(layer, random, isBoss, isTreasure), refreshCount, isBoss, isTreasure);
    public static RewardChoiceState Restore(RewardChoiceSnapshot snapshot) => new(snapshot.Layer, snapshot.Options, snapshot.RefreshCount, snapshot.IsBoss, snapshot.IsTreasure);
    public RewardChoiceSnapshot Capture() => new(Layer, _options.ToArray(), RefreshCount, IsBoss, IsTreasure);
    public RewardChoiceOption Get(string optionId) => _options.SingleOrDefault(o => o.OptionId == optionId)
        ?? throw new DomainValidationException("The reward option is not available.");
    public void Refresh(Random random)
    {
        if (RefreshCount >= 3) throw new DomainValidationException("The reward refresh limit has been reached.");
        _options.Clear(); _options.AddRange(CreateOptions(Layer, random, IsBoss, IsTreasure)); RefreshCount++;
    }
    private static IReadOnlyList<RewardChoiceOption> CreateOptions(ChaosMapLayer layer, Random random, bool isBoss, bool isTreasure)
    {
        var loot = GameConfigCatalog.Current.LootLayer(layer, isBoss);
        var quantity = random.Next(loot.FragmentMin, checked(loot.FragmentMax + 1));
        var heal = loot.HealPercentagePoints;
        var suffix = CreateDeterministicId(random).ToString("N");
        var equipment = CreateEquipment(loot, random, isTreasure);
        return [
            new($"equipment:{suffix}", RewardChoiceKind.Equipment, new ExplorationItem(CreateDeterministicId(random).ToString("D"), ExplorationItemKind.Equipment, Equipment: equipment, IsGenerated: true)),
            new($"fragments:{suffix}", RewardChoiceKind.EquipmentFragments, new ExplorationItem("equipment_fragments", ExplorationItemKind.EquipmentFragments, quantity)),
            new($"heal:{suffix}", RewardChoiceKind.ImmediateHeal, HealPercent: heal)];
    }

    private static EquipmentRewardData CreateEquipment(LootLayerConfig loot, Random random, bool isTreasure)
    {
        string[] slots = ["Head", "Chest", "Hands", "Legs", "Feet"];
        string[] elements = ["Wood", "Fire", "Earth", "Metal", "Water"];
        string[] affixes = ["Piercing", "Bulwark", "Vitality"];
        var quality = loot.RollEquipmentQuality(random.Next(100));
        if (isTreasure)
            quality = quality switch { "White" => "Green", "Green" => "Blue", "Blue" => "Purple", _ => "Orange" };
        var slot = slots[random.Next(slots.Length)];
        var affixRate = GameConfigCatalog.Current.EquipmentQuality(quality).AffixDropRate;
        var hasAffix = affixRate >= 1 || affixRate > 0 && random.Next(100) < Math.Round(affixRate * 100);
        var effectAffix = hasAffix ? affixes[random.Next(affixes.Length)] : null;
        var secondaryTrait = slot == "Feet" && random.Next(2) == 1 ? "ForcedEscape" : "DrawInterval";
        return new(slot, quality, elements[random.Next(elements.Length)], effectAffix, secondaryTrait);
    }

    private static Guid CreateDeterministicId(Random random)
    {
        Span<byte> bytes = stackalloc byte[16];
        random.NextBytes(bytes);
        return new Guid(bytes);
    }
}
