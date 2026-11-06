using FantasyCard.Contracts.Seasons;

namespace FantasyCard.Contracts.Progression;

public sealed record CraftingOfferResponse(string Quality, int MinimumDifficulty, string MarkKind,
    int MarkCost, int ReforgeFragmentCost, int WishAttempts);
public sealed record CraftingWishResponse(string Quality, string Slot, string Element, string WishedEffect,
    int Failures, int AttemptsUntilGuaranteed);
public sealed record SeasonRecipeResponse(Guid RecipeId, string SeasonId, string Quality, string Slot, string Element,
    string? EffectAffix, string SecondaryTrait, string StatsVersion, Guid SourceItemId);
public sealed record SeasonCraftingResponse(SeasonContextResponse Season, SeasonWalletResponse? Wallet, int MaximumDifficulty,
    IReadOnlyList<CraftingOfferResponse> Offers, IReadOnlyList<CraftingWishResponse> Wishes, IReadOnlyList<SeasonRecipeResponse> Recipes);
public sealed record CraftEquipmentRequest(string SeasonId, string Quality, string Slot, string Element,
    string WishedEffect, long ExpectedWalletVersion);
public sealed record CraftEquipmentResponse(EquipmentResponse Equipment, SeasonWalletResponse Wallet, CraftingWishResponse Wish,
    long BlueprintsSpent, long OrangeBlueprintsSpent);
public sealed record LearnSeasonRecipeRequest(string SeasonId, Guid EquipmentId, long ExpectedVersion);
public sealed record LearnSeasonRecipeResponse(SeasonRecipeResponse Recipe, EquipmentResponse Equipment, bool AlreadyLearned);
public sealed record ReforgeEquipmentRequest(string SeasonId, Guid RecipeId, Guid BodyEquipmentId,
    long ExpectedBodyVersion, long ExpectedWalletVersion);
public sealed record ReforgeQuoteResponse(SeasonRecipeResponse Recipe, EquipmentResponse Before, EquipmentResponse After,
    long FragmentCost, long AvailableFragments, long ExpectedWalletVersion, bool CanReforge, string? BlockedReason);
public sealed record ReforgeEquipmentResponse(EquipmentResponse Equipment, SeasonWalletResponse Wallet);
