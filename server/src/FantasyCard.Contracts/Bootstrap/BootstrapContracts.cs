using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Matchmaking;

namespace FantasyCard.Contracts.Bootstrap;

public sealed record UnfinishedMatchResponse(
    Guid MatchId,
    Guid RoomId,
    string Status,
    long? RoomRevision,
    string ConfigVersion);

public sealed record BootstrapResponse(
    DateTimeOffset ServerTime,
    string ConfigVersion,
    PlayerProfileResponse Player,
    WalletResponse Wallet,
    MaterialsResponse Materials,
    IReadOnlyList<ClassWeaponResponse> ClassWeapons,
    IReadOnlyList<LoadoutResponse> EquippedLoadouts,
    IReadOnlyList<DeckResponse> Decks,
    InventorySummaryResponse InventorySummary,
    UnfinishedMatchResponse? UnfinishedMatch,
    SettlementResponse? UnfinishedSettlement);
