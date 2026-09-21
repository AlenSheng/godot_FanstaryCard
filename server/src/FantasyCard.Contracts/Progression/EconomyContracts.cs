namespace FantasyCard.Contracts.Progression;

public sealed record ShopProductResponse(
    string ProductId,
    string Kind,
    long PriceGold,
    int Limit,
    int Purchased,
    string Payload,
    bool AlreadyOwned = false);

public sealed record ShopResponse(
    string ResetKey,
    IReadOnlyList<ShopProductResponse> Products,
    int RefreshesUsed = 0,
    int RefreshLimit = 0);

public sealed record ShopInventoryContextResponse(
    ShopResponse Shop,
    InventoryResponse Inventory);

public sealed record PurchaseShopRequest(string ProductId, int Quantity = 1);

public sealed record ShopPurchaseResponse(
    string ProductId,
    int Quantity,
    long GoldAfter,
    string Granted);

public sealed record CreateMarketListingRequest(Guid EquipmentId, long PriceGold);

public sealed record MarketListingResponse(
    Guid ListingId,
    Guid SellerId,
    Guid EquipmentId,
    long PriceGold,
    string Status,
    long Version,
    DateTimeOffset CreatedAt,
    DateTimeOffset ExpiresAt,
    EquipmentResponse? Equipment = null);

public sealed record MarketInventoryContextResponse(
    IReadOnlyList<MarketListingResponse> Listings,
    InventoryResponse Inventory);

public sealed record EconomyContextResponse(
    ShopResponse Shop,
    IReadOnlyList<MarketListingResponse> Market,
    InventoryResponse Inventory);

public sealed record MarketPurchaseResponse(
    MarketListingResponse Listing,
    long BuyerGoldAfter);
