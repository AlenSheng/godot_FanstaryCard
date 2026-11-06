using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Configuration;

public enum BlueprintKind { None, Blueprint, OrangeBlueprint }
public sealed record SeasonCraftingOffer(string Quality, int MinimumDifficulty, BlueprintKind MarkKind,
    int MarkCost, int ReforgeFragmentCost, int WishAttempts);
public sealed record SeasonMarkRule(int Difficulty, BlueprintKind Kind, int EliteMarks, int BossMarks, int MatchCap);
public sealed record BlueprintPayment(long Blueprints, long OrangeBlueprints);
public sealed record CraftingWishResult(string EffectAffix, int FailuresAfter, bool Guaranteed);
public sealed record PendingBlueprints(long Blueprints = 0, long OrangeBlueprints = 0);

/// <summary>Two typed blueprint currencies remain separate from legacy opaque ChallengeMarks.</summary>
public sealed record SeasonCraftingConfig(IReadOnlyList<SeasonCraftingOffer> Offers, IReadOnlyList<SeasonMarkRule> MarkRules)
{
    private static readonly string[] CraftedQualities = ["Orange","Purple"];
    public static IReadOnlyList<string> Effects { get; } = Array.AsReadOnly(new[] { "Piercing", "Bulwark", "Vitality" });

    public SeasonCraftingOffer Offer(string quality) => Offers.SingleOrDefault(row => row.Quality == quality)
        ?? throw new DomainValidationException("This quality cannot be crafted or rebuilt from a recipe.");

    public SeasonMarkRule Marks(int difficulty) => MarkRules.SingleOrDefault(row => row.Difficulty == difficulty)
        ?? throw new DomainValidationException("The original match blueprint rule is unavailable.");

    public void Validate()
    {
        if (Offers.Count != 2 || !Offers.Select(row => row.Quality).Order(StringComparer.Ordinal).SequenceEqual(CraftedQualities))
            throw new InvalidDataException("Season crafting must contain Purple and Orange only.");
        foreach (var row in Offers)
        {
            if (row.MinimumDifficulty < (row.Quality == "Purple" ? 1 : 2) || row.MinimumDifficulty > 5 ||
                row.MarkKind != (row.Quality == "Purple" ? BlueprintKind.Blueprint : BlueprintKind.OrangeBlueprint) ||
                row.MarkCost <= 0 || row.ReforgeFragmentCost <= 0 || row.WishAttempts is < 1 or > 3)
                throw new InvalidDataException("Invalid seasonal crafting offer.");
        }
        if (MarkRules.Count != 6 || !MarkRules.Select(row => row.Difficulty).Order().SequenceEqual(Enumerable.Range(0, 6)))
            throw new InvalidDataException("Blueprint rules require exactly D0 through D5.");
        foreach (var row in MarkRules)
        {
            var kind = row.Difficulty == 0 ? BlueprintKind.None : row.Difficulty == 1 ? BlueprintKind.Blueprint : BlueprintKind.OrangeBlueprint;
            if (row.Kind != kind || row.EliteMarks is < 0 or > 1 || row.BossMarks is < 0 or > 2 || row.MatchCap is < 0 or > 4 ||
                row.Difficulty == 0 && (row.EliteMarks != 0 || row.BossMarks != 0 || row.MatchCap != 0))
                throw new InvalidDataException("Invalid per-match blueprint source or cap.");
        }
    }

    public BlueprintPayment Payment(string quality, long blueprints, long orangeBlueprints)
    {
        if (blueprints < 0 || orangeBlueprints < 0) throw new DomainValidationException("Blueprint balances cannot be negative.");
        var offer = Offer(quality);
        var blue = offer.MarkKind == BlueprintKind.Blueprint ? Math.Min(blueprints, offer.MarkCost) : 0;
        var orange = offer.MarkCost - blue;
        if (orange > orangeBlueprints) throw new DomainValidationException("Not enough suitable blueprints.");
        return new(blue, orange);
    }

    public CraftingWishResult Wish(string quality, string selectedEffect, int previousFailures, int roll)
    {
        var offer = Offer(quality);
        if (!Effects.Contains(selectedEffect, StringComparer.Ordinal) || previousFailures < 0 || previousFailures >= offer.WishAttempts || roll is < 0 or >= 3)
            throw new DomainValidationException("The crafting wish or its saved progress is invalid.");
        var guaranteed = previousFailures == offer.WishAttempts - 1;
        var effect = guaranteed ? selectedEffect : Effects[roll];
        return new(effect, effect == selectedEffect ? 0 : previousFailures + 1, guaranteed);
    }

    public PendingBlueprints Pending(int difficulty, bool isBot, IEnumerable<ChaosMapCell> ownClearedCells)
    {
        var rule = Marks(difficulty);
        if (isBot || rule.Kind == BlueprintKind.None) return new();
        var amount = 0;
        foreach (var cell in ownClearedCells.DistinctBy(cell => cell.Position))
        {
            var boss = cell.IsBoss || cell.MonsterGroupId == "BOSS";
            if (boss) amount = Math.Min(rule.MatchCap, amount + rule.BossMarks);
            else if (cell.MonsterGroupId.StartsWith('E')) amount = Math.Min(rule.MatchCap, amount + rule.EliteMarks);
        }
        return rule.Kind == BlueprintKind.Blueprint ? new(amount, 0) : new(0, amount);
    }
}
