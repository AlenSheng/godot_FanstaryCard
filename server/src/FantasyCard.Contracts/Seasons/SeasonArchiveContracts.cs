using FantasyCard.Contracts.Progression;

namespace FantasyCard.Contracts.Seasons;

public sealed record SeasonArchiveSummaryResponse(
    string SeasonId, string RulesetId, string? ConfigVersion, string? ConfigSha256, string? StatsVersion,
    DateTimeOffset? StartsAt, DateTimeOffset? EndsAt, DateTimeOffset? ArchivedAt,
    string Status, string? Phase, SeasonWalletResponse? Wallet,
    long EquipmentCount, long RecipeCount, long WishCount, long LoadoutCount);
public sealed record SeasonArchivesResponse(IReadOnlyList<SeasonArchiveSummaryResponse> Items, int? NextOffset);
public sealed record ArchivedCraftingWishResponse(string Quality, string Slot, string Element, string WishedEffect, int Failures);
public sealed record SeasonArchiveSectionResponse(
    SeasonArchiveSummaryResponse Season, string Section, bool ReadOnly,
    IReadOnlyList<EquipmentResponse> Equipments, IReadOnlyList<SeasonRecipeResponse> Recipes,
    IReadOnlyList<ArchivedCraftingWishResponse> Wishes, IReadOnlyList<LoadoutResponse> Loadouts,
    int? NextOffset, IReadOnlyList<EquipmentResponse>? ReferencedEquipments = null);
