using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Configuration;

public sealed record SeasonMarketCurrencyConfig(string Currency,long OrangePriceCap,long RedPriceCap)
{
    public long MaximumPrice(string quality) => (Currency,quality) switch
    {
        ("Gold","White" or "Green" or "Blue" or "Purple" or "Orange" or "Red")=>OrangePriceCap,
        ("Diamond","Orange")=>OrangePriceCap,
        ("Diamond","Red")=>RedPriceCap,
        _=>throw new DomainValidationException("The selected quality cannot be listed in this currency.")
    };
}

public sealed record SeasonMarketConfig(int TaxBasisPoints,long MinimumFee,int ListingHours,int SharedSlots,
    IReadOnlyList<SeasonMarketCurrencyConfig> Currencies)
{
    public const string RuleVersion="season-market-v1";

    public void Validate()
    {
        if(TaxBasisPoints!=1000 || MinimumFee!=1 || ListingHours!=48 || SharedSlots!=8 || Currencies.Count!=2 ||
            Currencies.Count(value=>value.Currency=="Gold")!=1 || Currencies.Count(value=>value.Currency=="Diamond")!=1 ||
            Currencies.SingleOrDefault(value=>value.Currency=="Gold") is not {OrangePriceCap:99999,RedPriceCap:99999} ||
            Currencies.SingleOrDefault(value=>value.Currency=="Diamond") is not {OrangePriceCap:2000,RedPriceCap:8000})
            throw new InvalidDataException("Season market terms differ from the shared dual-currency contract.");
    }

    public SeasonMarketCurrencyConfig Currency(string currency) => Currencies.SingleOrDefault(value=>value.Currency==currency)
        ??throw new DomainValidationException("The market currency is unavailable.");

    public long Fee(long price)
    {
        if(price<1)throw new DomainValidationException("Market price must be positive.");
        return Math.Max(MinimumFee,decimal.ToInt64(decimal.Floor((decimal)price*TaxBasisPoints/10000)));
    }

    public void RequirePrice(string currency,string quality,long price)
    {
        if(price<1 || price>Currency(currency).MaximumPrice(quality))
            throw new DomainValidationException("Market price exceeds the selected currency and quality limit.");
    }
}
