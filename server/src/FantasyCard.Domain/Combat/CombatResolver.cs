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

    public static CardResolutionDraft Resolve(
        IReadOnlyList<CombatCardDefinition> cards,
        PlayerCombatState attacker,
        Func<CardElement, double>? targetResistance = null)
    {
        ArgumentNullException.ThrowIfNull(cards);
        ArgumentNullException.ThrowIfNull(attacker);
        var elemental = cards
            .Where(card => card.Effect.ElementalDamage > 0 && card.Effect.Element != CardElement.None)
            .ToArray();
        var counts = elemental
            .GroupBy(card => card.Effect.Element)
            .ToDictionary(group => group.Key, group => group.Count());
        var bases = elemental.Select(card =>
        {
            var sameElementOthers = counts[card.Effect.Element] - 1;
            return card.Effect.ElementalDamage +
                card.Effect.SameElementBonus * Math.Max(0, sameElementOthers - 2);
        }).ToArray();

        CardElement? core = null;
        var coreCount = 0;
        var elementalDamage = 0;
        if (elemental.Length > 0)
        {
            coreCount = counts.Values.Max();
            core = elemental.First(card => counts[card.Effect.Element] == coreCount).Effect.Element;
            var coreBase = elemental
                .Select((card, index) => (card, index))
                .Where(value => value.card.Effect.Element == core)
                .Sum(value => bases[value.index]);
            var conflictPairCount = ConflictPairs.Sum(pair =>
                counts.TryGetValue(pair.Left, out var left) && counts.TryGetValue(pair.Right, out var right)
                    ? Math.Min(left, right)
                    : 0);
            if (conflictPairCount == 0)
            {
                var resonanceBonus = cards.Sum(card => card.Effect.ResonanceBonus);
                var resonance = Resonance(coreCount + resonanceBonus);
                if (resonanceBonus > 0)
                {
                    resonance = Math.Min(3.5, resonance);
                }
                var equipmentBonus = attacker.Equipment.DamageBonus(core.Value);
                var resistance = targetResistance?.Invoke(core.Value) ?? 0;
                elementalDamage = (int)Math.Floor(coreBase * resonance * (1 + equipmentBonus) * (1 - resistance));
            }
            else
            {
                var cancelBonus = cards.Sum(card => card.Effect.ConflictCancelBonus);
                var cancellation = Math.Min(0.65 + cancelBonus, 0.20 * conflictPairCount + cancelBonus);
                var equipmentBonus = attacker.Equipment.DamageBonus(core.Value);
                var resistance = targetResistance?.Invoke(core.Value) ?? 0;
                elementalDamage = (int)Math.Floor(
                    coreBase * Resonance(coreCount) * (1 + equipmentBonus) * (1 - resistance) * (1 - cancellation));
            }
        }

        var directDamage = cards.Sum(card => card.Effect.DirectDamage);
        var piercingDamage = cards.Select((card, index) =>
        {
            var elementalIndex = Array.IndexOf(elemental, card);
            var elementalBase = elementalIndex >= 0 ? bases[elementalIndex] : 0;
            var damageBase = elementalBase + card.Effect.DirectDamage;
            return (int)Math.Floor(damageBase * attacker.Equipment.PiercingBonus);
        }).Sum();
        var heal = cards.Sum(card => card.Effect.Heal);
        var shield = cards.Sum(card => card.Effect.Shield);
        var stunSeconds = cards.Max(card => card.Effect.StunSeconds);
        var blockSeconds = cards.Max(card => card.Effect.DrawBlockSeconds);
        var speedSeconds = cards.Max(card => card.Effect.DrawSpeedSeconds);
        var speedModifier = cards.Min(card => card.Effect.DrawSpeedModifier);
        return new CardResolutionDraft(
            elementalDamage + directDamage + piercingDamage,
            attacker.ResolveHeal(heal),
            attacker.ResolveShield(shield),
            attacker.ResolveControl(TimeSpan.FromSeconds(stunSeconds)),
            TimeSpan.FromSeconds(blockSeconds),
            cards.Sum(card => card.Effect.DrawCharge),
            cards.Sum(card => card.Effect.ImmediateDraw),
            TimeSpan.FromSeconds(speedSeconds),
            speedModifier,
            cards.Sum(card => card.Effect.HealthCost),
            core,
            coreCount);
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
