using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Combat;

public static class CombatResolver
{
    private static readonly HashSet<(CardElement Left, CardElement Right)> ConflictPairs =
    [
        Pair(CardElement.Wood, CardElement.Earth),
        Pair(CardElement.Earth, CardElement.Water),
        Pair(CardElement.Water, CardElement.Fire),
        Pair(CardElement.Fire, CardElement.Metal),
        Pair(CardElement.Metal, CardElement.Wood)
    ];

    private static bool IsConflict(CardElement left, CardElement right) =>
        left != right && ConflictPairs.Contains(Pair(left, right));

    public static CardResolutionDraft Resolve(
        IReadOnlyList<CombatCardDefinition> cards,
        PlayerCombatState attacker,
        Func<CardElement, double>? targetResistance = null)
    {
        ArgumentNullException.ThrowIfNull(cards);
        ArgumentNullException.ThrowIfNull(attacker);
        if (cards.Count == 0) throw new DomainValidationException("At least one card is required for combat resolution.");
        var elemental = cards
            .Where(card => card.Effect.ElementalDamage > 0 && card.Effect.Element != CardElement.None &&
                card.Effect.SecondaryElementalDamage == 0)
            .ToArray();
        var counts = elemental
            .GroupBy(card => card.Effect.Element)
            .ToDictionary(group => group.Key, group => group.Count());
        var revealElement = attacker.HeroClass switch
        {
            Players.HeroClass.Mage => CardElement.Fire,
            Players.HeroClass.Priest => CardElement.Water,
            _ => CardElement.Earth
        };
        var reveal = cards.Any(card => card.Effect.IsClassReveal);
        var bases = cards.Select(card =>
        {
            var sameElementOthers = counts.GetValueOrDefault(card.Effect.Element) - 1;
            var value = card.Effect.ElementalDamage +
                card.Effect.SameElementBonus * Math.Max(0, sameElementOthers - 2);
            return reveal && card.Effect.Element == revealElement ? (int)Math.Floor(value * 1.3) : value;
        }).ToArray();

        CardElement? core = null;
        var coreCount = 0;
        var elementalDamage = 0;
        var conflictPairCount = 0;
        var conflictHeal = 0;
        var resonanceMultiplier = 1d;
        var conflictCancellation = 0d;
        var segments = new List<CombatDamageSegment>();
        if (elemental.Length > 0)
        {
            // The first ordinary elemental card establishes the core. Direct
            // damage cards do not consume this position.
            core = elemental[0].Effect.Element;
            coreCount = elemental.Count(card => card.Effect.Element == core);
            conflictPairCount = elemental.Count(card =>
                card.Effect.Element != core && !card.Effect.IsElementTuning && IsConflict(core.Value, card.Effect.Element));
            var resonanceBonus = cards.Any(card => card.Effect.ResonanceBonus > 0) ? 1 : 0;
            // The first core card is the unmodified baseline. M is the number
            // of later core cards left after counter cards consume their
            // advantage. This keeps the first card at its printed value.
            var mainCoreStacks = Math.Max(0, coreCount - 1 + resonanceBonus - conflictPairCount);
            resonanceMultiplier = 1 + .20 * mainCoreStacks;
            var equipmentBonus = attacker.Equipment.DamageBonus(core.Value);
            var resistance = targetResistance?.Invoke(core.Value) ?? 0;
            var sharedMultiplier = (1 + equipmentBonus) * (1 - resistance);
            var cancelBonus = cards.Max(card => card.Effect.ConflictCancelBonus);
            conflictCancellation = conflictPairCount == 0
                ? 0
                : Math.Min(0.80, 0.20 * conflictPairCount + cancelBonus);
            var coreBase = cards
                .Select((card, index) => (card, index))
                .Where(value => value.card.Effect.Element == core && value.card.Effect.SecondaryElementalDamage == 0 && !value.card.Effect.IsElementTuning)
                .Sum(value => bases[value.index]);
            var beforeConflict = coreBase * sharedMultiplier * resonanceMultiplier;
            if (conflictPairCount > 0)
            {
                var healCoefficient = Math.Max(0.50, cards.Max(card => card.Effect.ConflictHealCoefficient));
                conflictHeal = attacker.ResolveRecovery((int)Math.Floor(beforeConflict * conflictCancellation * healCoefficient) + 2 * conflictPairCount);
            }

            foreach (var (card, index) in cards.Select((card, index) => (card, index))
                         .Where(value => value.card.Effect.ElementalDamage > 0 && value.card.Effect.Element != CardElement.None && value.card.Effect.SecondaryElementalDamage == 0))
            {
                var branchMultiplier = card.Effect.Element == core
                    ? resonanceMultiplier
                    : IsConflict(core.Value, card.Effect.Element) && !card.Effect.IsElementTuning
                        ? 1 - conflictCancellation
                        : 1;
                var damage = Math.Max(0, (int)Math.Floor(bases[index] * sharedMultiplier * branchMultiplier));
                if (damage > 0) segments.Add(new(card.Effect.Element.ToString(), damage));
                elementalDamage += damage;
            }
        }

        // The boss card resolves its two printed elements independently, outside resonance and conflict.
        foreach (var (card, index) in cards.Select((card, index) => (card, index))
                     .Where(value => value.card.Effect.SecondaryElementalDamage > 0))
        {
            var secondary = card.Effect.SecondaryElementalDamage;
            if (reveal && card.Effect.SecondaryElement == revealElement) secondary = (int)Math.Floor(secondary * 1.3);
            foreach (var (element, value) in new[] { (card.Effect.Element, bases[index]), (card.Effect.SecondaryElement, secondary) })
            {
                var damageMultiplier = core is CardElement coreElement
                    ? (1 + attacker.Equipment.DamageBonus(coreElement)) * (1 - (targetResistance?.Invoke(coreElement) ?? 0))
                    : (1 + attacker.Equipment.DamageBonus(element)) * (1 - (targetResistance?.Invoke(element) ?? 0));
                var damage = Math.Max(0, (int)Math.Floor(value * damageMultiplier));
                if (damage > 0) segments.Add(new(element.ToString(), damage));
                elementalDamage += damage;
            }
        }

        var directDamage = cards.Sum(card => card.Effect.DirectDamage);
        var piercingDamage = cards.Select((card, index) =>
        {
            var secondary = card.Effect.SecondaryElementalDamage;
            if (reveal && card.Effect.SecondaryElement == revealElement) secondary = (int)Math.Floor(secondary * 1.3);
            var damageBase = bases[index] + secondary + card.Effect.DirectDamage;
            return (int)Math.Floor(damageBase * attacker.Equipment.PiercingBonus);
        }).Sum();
        if (directDamage + piercingDamage > 0) segments.Add(new("Direct", directDamage + piercingDamage));
        var heal = cards.Sum(card => card.Effect.Heal) * (1 + .25 * conflictPairCount);
        var shield = cards.Sum(card => card.Effect.Shield);
        var healthCost = cards.Sum(card => card.Effect.HealthCost);
        var shieldDraft = attacker.PreviewShield(shield, healthCost);
        var stunSeconds = cards.Max(card => card.Effect.StunSeconds);
        var blockSeconds = cards.Max(card => card.Effect.DrawBlockSeconds);
        var speedSeconds = cards.Max(card => card.Effect.DrawSpeedSeconds);
        var speedModifier = cards.Min(card => card.Effect.DrawSpeedModifier);
        return new CardResolutionDraft(
            elementalDamage + directDamage + piercingDamage,
            attacker.ResolveHeal(heal) + conflictHeal,
            shieldDraft.Shield,
            attacker.ResolveControl(TimeSpan.FromSeconds(stunSeconds)),
            attacker.ResolveControl(TimeSpan.FromSeconds(blockSeconds)),
            cards.Sum(card => card.Effect.DrawCharge),
            cards.Sum(card => card.Effect.ImmediateDraw),
            TimeSpan.FromSeconds(speedSeconds),
            speedModifier,
            healthCost,
            core,
            coreCount,
            segments.GroupBy(segment => segment.Kind, StringComparer.Ordinal)
                .Select(group => new CombatDamageSegment(group.Key, group.Sum(segment => segment.Amount))).ToArray(),
            resonanceMultiplier, conflictPairCount, conflictCancellation,
            shieldDraft.RemainderTenthsAfter);
    }

    public static IReadOnlyList<CombatDamageSegment> ResolveDamageSegments(
        IReadOnlyList<CombatDamageSegment> segments, int actualDamage, double multiplier = 1)
    {
        ArgumentNullException.ThrowIfNull(segments);
        if (actualDamage <= 0) return [];
        if (multiplier < 0 || multiplier > 1) throw new ArgumentOutOfRangeException(nameof(multiplier));
        var grouped = segments.Where(segment => segment.Amount > 0)
            .GroupBy(segment => segment.Kind, StringComparer.Ordinal)
            .Select(group => new CombatDamageSegment(group.Key, group.Sum(segment => segment.Amount)))
            .ToArray();
        if (grouped.Length == 0) return [new("Direct", actualDamage)];
        var reduced = grouped.Select(segment => segment with { Amount = (int)Math.Floor(segment.Amount * multiplier) }).ToArray();
        var expected = (int)Math.Floor(grouped.Sum(segment => segment.Amount) * multiplier);
        var largest = Array.FindIndex(grouped, segment => segment.Amount == grouped.Max(value => value.Amount));
        reduced[largest] = reduced[largest] with { Amount = reduced[largest].Amount + expected - reduced.Sum(segment => segment.Amount) };
        if (expected != actualDamage)
        {
            // Overkill cannot create visible damage beyond the shield and HP actually removed.
            var scale = expected == 0 ? 0 : (double)actualDamage / expected;
            reduced = reduced.Select(segment => segment with { Amount = (int)Math.Floor(segment.Amount * scale) }).ToArray();
            reduced[largest] = reduced[largest] with { Amount = reduced[largest].Amount + actualDamage - reduced.Sum(segment => segment.Amount) };
        }
        return reduced.Where(segment => segment.Amount > 0).ToArray();
    }

    private static double Resonance(int count) => count switch
    {
        <= 1 => 1,
        2 => 1.2,
        3 => 1.5,
        4 => 2,
        _ => 3
    };

    private static (CardElement, CardElement) Pair(CardElement left, CardElement right) =>
        left < right ? (left, right) : (right, left);
}
