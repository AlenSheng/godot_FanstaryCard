using System.Text.Json.Serialization;

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

public sealed record CreateMarketListingRequest(Guid EquipmentId,long PriceGold,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? Currency=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] long? Price=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? SeasonId=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] long? ExpectedEquipmentVersion=null);

public sealed record RelistMarketListingRequest(string Currency,long Price,long ExpectedVersion,string? SeasonId=null);
public sealed record ClaimMarketReturnRequest(long ExpectedEquipmentVersion,string? SeasonId=null);

public sealed record MarketListingResponse(
    Guid ListingId,
    Guid SellerId,
    Guid EquipmentId,
    long PriceGold,
    string Status,
    long Version,
    DateTimeOffset CreatedAt,
    DateTimeOffset ExpiresAt,
    EquipmentResponse? Equipment = null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? Currency=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] long? Price=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? SeasonId=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? ConfigVersion=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] DateTimeOffset? SeasonEndsAt=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] long? Fee=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] long? SellerNet=null);

public sealed record MarketCurrencyResponse(string Currency,long OrangePriceCap,long RedPriceCap);
public sealed record MarketPolicyResponse(string State,string? SeasonId,string? ConfigVersion,DateTimeOffset? SeasonEndsAt,
    int SharedSlots,int ListingHours,int TaxBasisPoints,long MinimumFee,bool CanTrade,WalletResponse Wallet,
    IReadOnlyList<MarketCurrencyResponse> Currencies);
public sealed record MarketReturnResponse(Guid ReturnId,Guid ListingId,EquipmentResponse Equipment,DateTimeOffset HeldAt,bool CanClaim=true);
public sealed record MarketReturnsResponse(IReadOnlyList<MarketReturnResponse> Items,int? NextOffset=null);

public sealed record MarketInventoryContextResponse(
    IReadOnlyList<MarketListingResponse> Listings,
    InventoryResponse Inventory,
    MarketPolicyResponse? Policy=null,
    IReadOnlyList<MarketListingResponse>? OwnListings=null,
    IReadOnlyList<MarketReturnResponse>? Returns=null,
    int? ReturnsNextOffset=null);

public sealed record EconomyContextResponse(
    ShopResponse Shop,
    IReadOnlyList<MarketListingResponse> Market,
    InventoryResponse Inventory);

public sealed record MarketPurchaseResponse(
    MarketListingResponse Listing,
    long BuyerGoldAfter,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] WalletResponse? Wallet=null,
    [property:JsonIgnore(Condition=JsonIgnoreCondition.WhenWritingNull)] string? SeasonId=null);
