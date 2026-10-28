using FantasyCard.Contracts.Players;
using FantasyCard.Contracts.Progression;
using FantasyCard.Contracts.Matchmaking;
using FantasyCard.Contracts.Mail;

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
    IReadOnlyList<CardResponse> Cards,
    InventorySummaryResponse InventorySummary,
    UnfinishedMatchResponse? UnfinishedMatch,
    SettlementResponse? UnfinishedSettlement)
{
    // Optional fields keep older bootstrap consumers compatible while giving
    // the client a complete account snapshot in one response.
    public InventoryResponse? Inventory { get; init; }
    public ShopResponse? Shop { get; init; }
    public IReadOnlyList<MarketListingResponse>? Market { get; init; }
    public MailListResponse? Mail { get; init; }
    public PreparationResponse? ActivePreparation { get; init; }
}

// Opt-in recovery projection of the existing BootstrapResponse wire contract.
public sealed record BootstrapSettlementProjection(
    DateTimeOffset ServerTime,
    string ConfigVersion,
    SettlementResponse? UnfinishedSettlement);
