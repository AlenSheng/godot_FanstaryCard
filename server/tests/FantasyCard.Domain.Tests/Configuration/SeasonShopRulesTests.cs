using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Configuration;

public sealed class SeasonShopRulesTests
{
    [Fact]
    public void CurrentPolicyKeepsOriginalPricesAndOneSharedClassQuotaWhileBagPurchasesHaveNoDailyLimit()
    {
        var c=GameConfigCatalog.Current;var p=Assert.IsType<SeasonShopConfig>(c.SeasonShop);
        p.Validate(c.Cards,c.CardLevels,c.Economy,c.Backpacks,c.ShopCardPrices);
        Assert.Equal(9,p.Products.Count);Assert.Equal(1,p.ClassSoulDailyLimit);Assert.Equal(3,p.PaidBagCap);
        Assert.All(p.Products.Where(v=>v.Kind=="ClassSoul"),v=>Assert.Equal("class_soul",v.QuotaGroup));
        Assert.All(p.Products.Where(v=>v.Kind.EndsWith("Bag",StringComparison.Ordinal)),v=>Assert.Equal(0,v.DailyLimit));
        var path=Find("server/config/archive/season-v1-config-8/fantasycard.config.bytes");var old=GameConfigCatalog.Load(File.ReadAllBytes(path));
        Assert.Null(old.SeasonShop);Assert.NotNull(old.SeasonMarket);
    }

    [Fact]
    public void WeightedPackDrawsAllowDuplicatesAndNeverReplaceAnEmptyQualityPoolWithADifferentQuality()
    {
        var c=GameConfigCatalog.Current;var p=c.SeasonShop!;var counts=new Dictionary<string,int>();
        for(var roll=0;roll<100;roll++)
        {
            var calls=0;var card=p.Draw(c.Cards,_=>calls++==0?roll:0);counts[card.Quality!]=counts.GetValueOrDefault(card.Quality!)+1;
            Assert.True(SeasonShopConfig.PackEligible(card));Assert.False(card.Quality=="Purple"&&card.HeroClass is not null);
        }
        Assert.Equal(50,counts["White"]);Assert.Equal(30,counts["Green"]);Assert.Equal(15,counts["Blue"]);Assert.Equal(5,counts["Purple"]);
        var a=p.Draw(c.Cards,_=>0);Assert.Equal(a,p.Draw(c.Cards,_=>0));
        Assert.Throws<DomainValidationException>(()=>p.Draw(c.Cards.Where(v=>v.Quality!="Purple").ToArray(),_=>99));
    }

    [Fact]
    public void DailyOffersFreezeThreeDistinctEligibleCardsAndRejectAChangedPriceOrQuotaGroup()
    {
        var c=GameConfigCatalog.Current;var p=c.SeasonShop!;var offers=p.Offers(c,"2026-11-04:refresh:0");
        Assert.Equal(offers,p.Offers(c,"2026-11-04:refresh:0"));p.ValidateOffers(c,offers);
        Assert.Equal(3,offers.Where(v=>v.CardId is not null).Select(v=>v.CardId).Distinct().Count());
        Assert.Throws<DomainValidationException>(()=>p.ValidateOffers(c,offers.Select((v,i)=>i==0?v with {PriceGold=1}:v).ToArray()));
        Assert.Throws<DomainValidationException>(()=>p.ValidateOffers(c,offers.Select(v=>v.ProductId=="mage_soul"?v with {QuotaGroup="extra"}:v).ToArray()));
    }

    private static string Find(string relative)
    {
        var p=new DirectoryInfo(AppContext.BaseDirectory);
        while(p is not null){var candidate=Path.Combine(p.FullName,relative);if(File.Exists(candidate))return candidate;p=p.Parent;}
        throw new InvalidOperationException("The actual original config8 archive is required.");
    }
}
