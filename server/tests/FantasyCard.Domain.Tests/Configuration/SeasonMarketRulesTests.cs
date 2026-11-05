using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Tests.Configuration;

public sealed class SeasonMarketRulesTests
{
    private static SeasonMarketConfig Policy()=>new(1000,1,48,8,[new("Gold",99999,99999),new("Diamond",2000,8000)]);

    [Fact]
    public void PublishedCandidateEnablesBothCurrenciesAndTheActualVersionSevenArchiveKeepsThemDisabled()
    {
        var current=GameConfigCatalog.Current;Assert.NotNull(current.SeasonMarket);current.SeasonMarket.Validate();
        var directory=new DirectoryInfo(AppContext.BaseDirectory);string? path=null;
        while(directory is not null)
        {
            var candidate=Path.Combine(directory.FullName,"server/config/archive/season-v1-config-7/fantasycard.config.bytes");
            if(File.Exists(candidate)){path=candidate;break;}directory=directory.Parent;
        }
        Assert.NotNull(path);var old=GameConfigCatalog.Load(File.ReadAllBytes(path));Assert.Equal("season-v1-config-7",old.Version);
        Assert.Null(old.SeasonMarket);Assert.NotNull(old.SeasonRed);
    }

    [Theory]
    [InlineData(1,1,0)] [InlineData(9,1,8)] [InlineData(10,1,9)] [InlineData(19,1,18)]
    [InlineData(2000,200,1800)] [InlineData(8000,800,7200)] [InlineData(99999,9999,90000)]
    public void SellerTaxFloorsOnceHasAMinimumAndDoesNotAddABuyerSurcharge(long price,long fee,long sellerNet)
    {
        var policy=Policy();policy.Validate();Assert.Equal(fee,policy.Fee(price));Assert.Equal(sellerNet,price-policy.Fee(price));
        Assert.Equal(price,fee+sellerNet);
    }

    [Theory]
    [InlineData("White")] [InlineData("Green")] [InlineData("Blue")] [InlineData("Purple")]
    public void OrdinaryQualitiesOnlyUseTheGoldMarket(string quality)
    {
        var policy=Policy();policy.RequirePrice("Gold",quality,99999);
        Assert.Throws<DomainValidationException>(()=>policy.RequirePrice("Gold",quality,100000));
        Assert.Throws<DomainValidationException>(()=>policy.RequirePrice("Diamond",quality,1));
    }

    [Theory]
    [InlineData("Orange",2000)] [InlineData("Red",8000)]
    public void DiamondCapsAreQualitySpecificAndGoldIsASeparatePrice(string quality,long cap)
    {
        var policy=Policy();policy.RequirePrice("Diamond",quality,cap);policy.RequirePrice("Gold",quality,99999);
        Assert.Throws<DomainValidationException>(()=>policy.RequirePrice("Diamond",quality,cap+1));
        Assert.Throws<DomainValidationException>(()=>policy.RequirePrice("Diamond",quality,0));
        Assert.Throws<DomainValidationException>(()=>policy.RequirePrice("Mixed",quality,1));
    }

    [Fact]
    public void BothCurrenciesUseOneEightSlotFortyEightHourPolicy()
    {
        var policy=Policy();policy.Validate();Assert.Equal(8,policy.SharedSlots);Assert.Equal(48,policy.ListingHours);
        Assert.Throws<InvalidDataException>(()=>(policy with {SharedSlots=16}).Validate());
        Assert.Throws<InvalidDataException>(()=>(policy with {TaxBasisPoints=999}).Validate());
        Assert.Throws<InvalidDataException>(()=>(policy with {Currencies=[new("Gold",99999,99999),new("Gold",99999,99999)]}).Validate());
    }
}
