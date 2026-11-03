using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Seasons;

public enum SeasonRewardBias { None, Equipment, Fragments }

public sealed record SeasonRewardContext(SeasonContext Season, SeasonRewardBias Bias,
    [property: System.Text.Json.Serialization.JsonIgnore(Condition=System.Text.Json.Serialization.JsonIgnoreCondition.WhenWritingNull)] string? LootPreferenceElement = null);

/// <summary>Original mint context follows a generated item through swaps, piles and settlement.</summary>
public sealed record SeasonEquipmentOrigin(SeasonContext Season,string Source,string LootRuleId,string LayerId,
    string BaseQuality,bool Promoted);

public static class SeasonLootRules
{
    public static ChaosMapLayer RewardLayer(ChaosMapCell cell) => cell.IsBoss || cell.MonsterGroupId=="BOSS" || cell.MonsterGroupId.StartsWith('E')
        ? ChaosMapLayer.Core : cell.Layer;

    public static SeasonRewardBias Bias(int hp,int baseMaximumHp,ChaosMapLayer layer,
        IEnumerable<ExplorationItem> worn,IEnumerable<ExplorationItem> inventory)
    {
        if (baseMaximumHp<=0 || hp<0) throw new DomainValidationException("Invalid reward health input.");
        if ((long)hp*100<=(long)baseMaximumHp*60) return SeasonRewardBias.None;
        var value=Value(worn.Concat(inventory));
        var threshold=layer switch {ChaosMapLayer.Outer=>8,ChaosMapLayer.Middle=>16,ChaosMapLayer.Core=>24,_=>throw new DomainValidationException("Unknown reward layer.")};
        return value>=threshold ? SeasonRewardBias.Fragments : SeasonRewardBias.Equipment;
    }

    public static long Value(IEnumerable<ExplorationItem> items)
    {
        long value=0;
        var material=new Dictionary<ExplorationItemKind,long>();
        foreach(var item in items)
        {
            if(item.Kind==ExplorationItemKind.Equipment && item.Equipment is { } equipment)
            {
                var score=SeasonLootConfig.Rank(equipment.Quality) switch {0=>1,1=>2,2=>4,3=>7,4=>12,_=>24};
                if(equipment.Level is <0 or >5) throw new DomainValidationException("Invalid reward valuation level.");
                value=checked(value+(long)score*(5+equipment.Level)/5);
            }
            else if(item.Kind is ExplorationItemKind.Gold or ExplorationItemKind.WarriorSoul or ExplorationItemKind.ClassSoul or ExplorationItemKind.EquipmentFragments)
                material[item.Kind]=checked(material.GetValueOrDefault(item.Kind)+item.Quantity);
        }
        foreach(var entry in material) value=checked(value+entry.Value/(entry.Key==ExplorationItemKind.Gold?80:10));
        return value;
    }

    public static void RequireCatalog(SeasonContext context,GameConfigCatalog configuration)
    {
        if(context.ConfigVersion!=configuration.Version) throw new DomainValidationException("Seasonal loot configuration differs from its frozen context.");
        _=configuration.ResolveSeasonEquipment(context.StatsVersion);
    }

    public static void RequireGeneratedQuality(SeasonContext context,string quality,GameConfigCatalog configuration)
    {
        RequireCatalog(context,configuration);
        if(SeasonLootConfig.Rank(quality)>configuration.SeasonDifficulty(context.Difficulty).QualityCap)
            throw new DomainValidationException("Generated equipment exceeds the difficulty's ordinary quality cap.");
    }

    public static void RequireEntry(SeasonContext context,IEnumerable<EquipmentRewardData> equipment,GameConfigCatalog configuration)
    {
        RequireCatalog(context,configuration);
        var armor=equipment.ToArray();var cap=configuration.SeasonDifficulty(context.Difficulty).EntryQualityCap;
        if(armor.Any(item=>SeasonLootConfig.Rank(item.Quality)>cap) || armor.Count(item=>item.Quality is "Orange" or "Red")>1)
            throw new DomainValidationException("Armor exceeds the selected difficulty's entry quality or combined orange/red limit.");
    }

    public static void RequireOrigin(EquipmentRewardData item,SeasonContext context,GameConfigCatalog configuration)
    {
        if(item.StatsVersion is not null && item.StatsVersion!=context.StatsVersion)
            throw new DomainValidationException("The generated item's stats version differs from its original season.");
        RequireGeneratedQuality(context,item.Quality,configuration);
        if(item.SeasonOrigin is not { } origin) throw new DomainValidationException("New seasonal equipment is missing its original source policy.");
        context.RequireSameDomain(origin.Season);
        if(origin.Source=="BotBudget")
        {
            if(origin.LootRuleId!="bot-budget-v1" || origin.LayerId!="outer" || origin.BaseQuality!=item.Quality ||
                origin.Promoted || item.Quality is not ("White" or "Green") || item.Level!=0)
                throw new DomainValidationException("Generated bot reward exceeds its original loot policy.");
            return;
        }
        var rule=configuration.SeasonLoot(context.Difficulty,origin.LayerId);
        var baseRank=SeasonLootConfig.Rank(origin.BaseQuality);
        if(baseRank>4 || rule.Weights[baseRank]==0 || origin.Promoted && baseRank>=rule.PromotionCap ||
            origin.Source is not ("NaturalChoice" or "Treasure") || origin.LootRuleId!=rule.RuleId ||
            origin.Source=="Treasure" && origin.LayerId!="outer" ||
            rule.ApplyCaps(origin.BaseQuality,origin.Promoted,configuration.SeasonDifficulty(context.Difficulty).QualityCap)!=item.Quality)
            throw new DomainValidationException("Generated equipment differs from its original loot policy.");
    }
}
