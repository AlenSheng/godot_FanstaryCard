using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Seasons;
using System.Text.Json.Serialization;

namespace FantasyCard.Domain.Rooms;

public enum RewardChoiceKind : short { Equipment = 1, EquipmentFragments = 2, ImmediateHeal = 3 }

public sealed record EquipmentRewardData(
    string Slot,
    string Quality,
    string Element,
    string? EffectAffix,
    string SecondaryTrait,
    int Level = 0,
    bool IsBound = false,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] SeasonEquipmentOrigin? SeasonOrigin = null);

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
public sealed record RewardChoiceSnapshot(ChaosMapLayer Layer, IReadOnlyList<RewardChoiceOption> Options, int RefreshCount, bool IsBoss = false, bool IsTreasure = false,
    [property: JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] SeasonRewardContext? SeasonLoot = null);
public sealed record RewardRefreshReceiptSnapshot(string RequestId, RewardChoiceSnapshot Choice, long RoomRevision);

public sealed class RewardChoiceState
{
    private readonly List<RewardChoiceOption> _options;
    private readonly GameConfigCatalog _configuration;
    private SeasonRewardContext? _season;
    private RewardChoiceState(ChaosMapLayer layer, IReadOnlyList<RewardChoiceOption> options, int refreshCount, bool isBoss, bool isTreasure, GameConfigCatalog configuration, SeasonRewardContext? season)
    {
        if (refreshCount is < 0 or > 3)
            throw new DomainValidationException("Reward refresh count must be between zero and three.");
        if (options.Count != 3 || options.Select(o => o.Kind).Distinct().Count() != 3)
            throw new DomainValidationException("A reward choice must contain one equipment, one fragment, and one heal option.");
        if (isTreasure && (layer != ChaosMapLayer.Outer || isBoss))
            throw new DomainValidationException("Treasure encounters must use outer-layer rewards.");
        Layer = layer; IsBoss = isBoss; IsTreasure = isTreasure; _options = options.ToList(); RefreshCount = refreshCount;
        _configuration = configuration;
        _season = season;
        if(season is not null)
        {
            SeasonLootRules.RequireCatalog(season.Season,configuration);
            if(!Enum.IsDefined(season.Bias))throw new DomainValidationException("Unknown seasonal reward bias.");
            foreach(var option in options.Where(option=>option.Item?.Equipment is not null))
            {
                var item=option.Item!.Equipment!;
                if(item.SeasonOrigin is not { } origin || origin.LayerId!=SeasonLootConfig.Layer(layer,isBoss) ||
                    origin.Source!=(isTreasure?"Treasure":"NaturalChoice"))
                    throw new DomainValidationException("Seasonal reward choice is missing its original cell policy.");
                SeasonLootRules.RequireOrigin(item,season.Season,configuration);
            }
        }
    }
    public ChaosMapLayer Layer { get; }
    public bool IsBoss { get; }
    public bool IsTreasure { get; }
    public IReadOnlyList<RewardChoiceOption> Options => _options;
    public int RefreshCount { get; private set; }
    public static RewardChoiceState Create(ChaosMapLayer layer, Random random, bool isBoss = false, int refreshCount = 0, bool isTreasure = false, GameConfigCatalog? configuration = null, SeasonRewardContext? season = null)
    {
        var catalog = configuration ?? GameConfigCatalog.Current;
        return new(layer, CreateOptions(layer, random, isBoss, isTreasure, catalog,season), refreshCount, isBoss, isTreasure, catalog,season);
    }
    public static RewardChoiceState Restore(RewardChoiceSnapshot snapshot, GameConfigCatalog? configuration = null,SeasonContext? expectedSeason = null)
    {
        if(snapshot.SeasonLoot?.Season != expectedSeason)
            throw new DomainValidationException("Saved reward policy and room season differ.");
        return new(snapshot.Layer,snapshot.Options,snapshot.RefreshCount,snapshot.IsBoss,snapshot.IsTreasure,configuration??GameConfigCatalog.Current,snapshot.SeasonLoot);
    }
    public RewardChoiceSnapshot Capture() => new(Layer, _options.ToArray(), RefreshCount, IsBoss, IsTreasure,_season);
    public RewardChoiceOption Get(string optionId) => _options.SingleOrDefault(o => o.OptionId == optionId)
        ?? throw new DomainValidationException("The reward option is not available.");
    public void Refresh(Random random,SeasonRewardBias? bias = null)
    {
        if (RefreshCount >= 3) throw new DomainValidationException("The reward refresh limit has been reached.");
        var season=_season is null ? null : _season with {Bias=bias??_season.Bias};
        var options=CreateOptions(Layer,random,IsBoss,IsTreasure,_configuration,season);
        _options.Clear();_options.AddRange(options);_season=season;RefreshCount++;
    }
    private static IReadOnlyList<RewardChoiceOption> CreateOptions(ChaosMapLayer layer, Random random, bool isBoss, bool isTreasure, GameConfigCatalog configuration,SeasonRewardContext? season)
    {
        var loot = configuration.LootLayer(layer, isBoss);
        var quantity = random.Next(loot.FragmentMin, checked(loot.FragmentMax + 1));
        if(season is not null)
        {
            SeasonLootRules.RequireCatalog(season.Season,configuration);
            quantity=SeasonDifficultyConfig.Scale(checked(quantity*(season.Bias==SeasonRewardBias.Fragments?2:1)),configuration.SeasonDifficulty(season.Season.Difficulty).FragmentBasisPoints);
        }
        var heal = loot.HealPercentagePoints;
        var suffix = CreateDeterministicId(random).ToString("N");
        var equipment = CreateEquipment(loot, random, isTreasure, configuration,season);
        return [
            new($"equipment:{suffix}", RewardChoiceKind.Equipment, new ExplorationItem(CreateDeterministicId(random).ToString("D"), ExplorationItemKind.Equipment, Equipment: equipment, IsGenerated: true)),
            new($"fragments:{suffix}", RewardChoiceKind.EquipmentFragments, new ExplorationItem("equipment_fragments", ExplorationItemKind.EquipmentFragments, quantity)),
            new($"heal:{suffix}", RewardChoiceKind.ImmediateHeal, HealPercent: heal)];
    }

    private static EquipmentRewardData CreateEquipment(LootLayerConfig loot, Random random, bool isTreasure, GameConfigCatalog configuration,SeasonRewardContext? season)
    {
        string[] slots = ["Head", "Chest", "Hands", "Legs", "Feet"];
        string[] elements = ["Wood", "Fire", "Earth", "Metal", "Water"];
        string[] affixes = ["Piercing", "Bulwark", "Vitality"];
        SeasonEquipmentOrigin? origin=null;
        string quality;
        if(season is not null)
        {
            var rule=configuration.SeasonLoot(season.Season.Difficulty,loot.Layer=="Boss"?"boss":loot.Layer switch {"Outer"=>"outer","Middle"=>"middle",_=>"elite"});
            var original=rule.Roll(random.Next(SeasonLootConfig.ProbabilityBasis));
            var promote=(isTreasure || season.Bias==SeasonRewardBias.Equipment) && SeasonLootConfig.Rank(original)<rule.PromotionCap;
            quality=rule.ApplyCaps(original,promote,configuration.SeasonDifficulty(season.Season.Difficulty).QualityCap);
            origin=new(season.Season,isTreasure?"Treasure":"NaturalChoice",rule.RuleId,rule.LayerId,original,promote);
        }
        else
        {
            quality = loot.RollEquipmentQuality(random.Next(100));
            if (isTreasure)
                quality = quality switch { "White" => "Green", "Green" => "Blue", "Blue" => "Purple", _ => "Orange" };
        }
        var slot = slots[random.Next(slots.Length)];
        var affixRate = configuration.EquipmentQuality(quality).AffixDropRate;
        var hasAffix = affixRate >= 1 || affixRate > 0 && random.Next(100) < Math.Round(affixRate * 100);
        var effectAffix = hasAffix ? affixes[random.Next(affixes.Length)] : null;
        var secondaryTrait = slot == "Feet" && random.Next(2) == 1 ? "ForcedEscape" : "DrawInterval";
        return new(slot, quality, elements[random.Next(elements.Length)], effectAffix, secondaryTrait,SeasonOrigin:origin);
    }

    private static Guid CreateDeterministicId(Random random)
    {
        Span<byte> bytes = stackalloc byte[16];
        random.NextBytes(bytes);
        return new Guid(bytes);
    }
}
