using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Cards;

/// <summary>Isolated one-card experiment guard; does not change published decks.</summary>
public static class PairedDeckBudget
{
    public static void Validate(GameConfigCatalog config, HeroClass hero,
        IReadOnlyList<string> baseline, IReadOnlyList<string> candidate,
        IReadOnlyList<int>? baselineLevels = null, IReadOnlyList<int>? candidateLevels = null)
    {
        if (baseline.Count!=20 || candidate.Count!=20 || baseline.Distinct().Count()!=20 || candidate.Distinct().Count()!=20)
            throw new DomainValidationException("A paired deck must retain exactly twenty unique owned card definitions.");
        var removed=baseline.Except(candidate).ToArray();var added=candidate.Except(baseline).ToArray();
        if (removed.Length!=1 || added.Length!=1)throw new DomainValidationException("A paired deck experiment must replace exactly one card.");
        var a=config.Cards.SingleOrDefault(c=>c.CardId==removed[0]);var b=config.Cards.SingleOrDefault(c=>c.CardId==added[0]);
        if (a is null || b is null || a.Rarity!=b.Rarity || a.UnlockCost!=b.UnlockCost)
            throw new DomainValidationException("Replacement rarity and unlock cost must match.");
        foreach (var id in baseline.Concat(candidate))
        {
            var card=config.Cards.SingleOrDefault(c=>c.CardId==id);
            if (card is null || !card.Enabled || !card.IsCodex || card.MonsterType is not null || card.HeroClass is { } own && own!=hero)
                throw new DomainValidationException("Paired decks require enabled owned codex cards for this class.");
        }
        var al=baselineLevels??Enumerable.Repeat(0,20).ToArray();var bl=candidateLevels??Enumerable.Repeat(0,20).ToArray();
        if (al.Count!=20 || bl.Count!=20 || al.Any(l=>l is <0 or >5) || bl.Any(l=>l is <0 or >5))throw new DomainValidationException("A complete valid card-level budget is required.");
        var levels=baseline.Select((id,i)=>(id,level:al[i])).ToDictionary(row=>row.id,row=>row.level);
        for (var i=0;i<20;i++)
            if (bl[i]!=(candidate[i]==added[0]?levels[removed[0]]:levels[candidate[i]]))
                throw new DomainValidationException("Paired card levels must match, including the replacement.");
    }
}
