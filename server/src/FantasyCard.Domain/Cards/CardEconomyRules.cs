using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Cards;

public static class CardEconomyRules
{
    public static CardConfigDefinition GetCard(string cardId) =>
        GameConfigCatalog.Current.Cards.SingleOrDefault(card =>
            card.CardId == cardId && card.IsCodex && card.Enabled)
        ?? throw new DomainValidationException("Unknown collectible card.");

    public static string CurrencyKind(CardConfigDefinition card) => card.HeroClass switch
    {
        null => "WarriorSoul",
        HeroClass.Priest => "PriestSoul",
        HeroClass.Mage => "MageSoul",
        HeroClass.Guardian => "GuardianSoul",
        _ => throw new DomainValidationException("Unknown card hero class.")
    };

    public static long CraftCost(CardConfigDefinition card, bool owned) =>
        card.InitiallyUnlocked ? card.CopyCost : card.UnlockCost;

    public static CardLevelConfig Level(string cardId, int level)
    {
        if (level is < 0 or > 5)
            throw new DomainValidationException("Card level must be between zero and five.");
        return GameConfigCatalog.Current.CardLevels.SingleOrDefault(item => item.CardId == cardId && item.Level == level)
            ?? throw new DomainValidationException("Card level is not present in the active config.");
    }

    public static string? UpgradeBlockedReason(string cardId, bool unlocked, int copies, int level, int requiredCopies)
    {
        if (!unlocked || copies < 1) return "Card is not owned.";
        if (level >= 5) return "Card has reached maximum level.";
        _ = Level(cardId, level + 1);
        return null;
    }

    public static CombatCardEffect ApplyLevel(string cardId, CombatCardEffect effect, int level)
    {
        if (level == 0) return effect;
        var growth = Level(cardId, level);
        // Upgrade existing components only; costs, elements and combo structure remain unchanged.
        return effect with
        {
            ElementalDamage = effect.ElementalDamage > 0 ? checked(effect.ElementalDamage + growth.ValueBonus) : 0,
            SecondaryElementalDamage = effect.SecondaryElementalDamage > 0 ? checked(effect.SecondaryElementalDamage + growth.ValueBonus) : 0,
            DirectDamage = effect.DirectDamage > 0 ? checked(effect.DirectDamage + growth.ValueBonus) : 0,
            Heal = effect.Heal > 0 ? checked(effect.Heal + growth.ValueBonus) : 0,
            Shield = effect.Shield > 0 ? checked(effect.Shield + growth.ValueBonus) : 0,
            StunSeconds = effect.StunSeconds > 0 ? effect.StunSeconds + growth.DurationBonus : 0,
            DrawBlockSeconds = effect.DrawBlockSeconds > 0 ? effect.DrawBlockSeconds + growth.DurationBonus : 0,
            DrawSpeedSeconds = effect.DrawSpeedSeconds > 0 ? effect.DrawSpeedSeconds + growth.DurationBonus : 0
        };
    }

    public static IReadOnlyList<int> DeckLevels(IReadOnlyList<string> cardIds, IReadOnlyDictionary<string, int> ownedLevels)
    {
        var assigned = new HashSet<string>(StringComparer.Ordinal);
        return cardIds.Select(id => assigned.Add(id) ? ownedLevels.GetValueOrDefault(id) : 0).ToArray();
    }

    public static long UpgradeSoulSpent(string cardId, int level)
    {
        if (level is < 0 or > 5)
            throw new DomainValidationException("Card level must be between zero and five.");
        return GameConfigCatalog.Current.CardLevels
            .Where(item => item.CardId == cardId && item.Level > 0 && item.Level <= level)
            .Sum(item => (long)item.SoulCost);
    }

    public static long DismantleRefund(CardConfigDefinition card, int level) =>
        checked(CraftCost(card, owned: false) + UpgradeSoulSpent(card.CardId, level)) / 4;
}
