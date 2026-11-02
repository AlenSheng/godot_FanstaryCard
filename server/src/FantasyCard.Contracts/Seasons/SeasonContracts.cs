namespace FantasyCard.Contracts.Seasons;

public sealed record SeasonWalletResponse(
    string SeasonId, long Gold, long EquipmentFragments, long ChallengeMarks,
    long Version, DateTimeOffset? ArchivedAt, bool CanFundWeapon);

public sealed record SeasonSummaryResponse(
    string State, string? SeasonId, string? RulesetId, string? ConfigVersion, string? StatsVersion,
    DateTimeOffset? StartsAt, DateTimeOffset? EndsAt, int HighestOpenDifficulty,
    int HighestUnlockedDifficulty, int EffectiveLevelCap, long HistoricalEquipmentFragments,
    string? NextSeasonId, DateTimeOffset? NextStartsAt, SeasonWalletResponse? Wallet,
    IReadOnlyList<SeasonWalletResponse> FragmentWallets, bool HasJoined, string DifficultyId);
