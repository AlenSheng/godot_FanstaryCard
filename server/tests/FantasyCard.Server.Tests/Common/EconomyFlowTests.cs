using System.Diagnostics.Metrics;
using System.Numerics;
using FantasyCard.Server.Common;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Common;

public sealed class EconomyFlowTests
{
    private static readonly string[] ExpectedQueryOutcomes=["success","invalid","timeout","failure"];
    [Fact]
    public void MarketGrossDebitAndSellerNetAreTransferLegsOnlyTaxChangesSupply()
    {
        var data=new[]{EconomyFlow.Ledger("Gold","s","market.purchase","General","-100",1),EconomyFlow.Ledger("Gold","s","market.sale","General","90",1),
            new EconomyFlowRow("Gold","Season","s",EconomyFlowKind.Transfer,"Market","90","0",1),
            new EconomyFlowRow("Gold","Season","s",EconomyFlowKind.SystemBurn,"MarketTax","10","0",0)};
        var total=Assert.Single(EconomyFlow.Summarize(data));Assert.Equal("0",total.SystemMint);Assert.Equal("10",total.SystemBurn);
        Assert.Equal("90",total.Transfer);Assert.Equal("-10",total.LedgerDelta);Assert.Equal("-10",total.RecognizedNetSupply);Assert.Equal("0",total.ReconciliationDifference);Assert.True(total.CoverageComplete);
        var sources=EconomyFlow.Breakdown(data);Assert.Equal("10",Assert.Single(sources,s=>s.Channel=="MarketTax").Quantity);
    }

    [Theory]
    [InlineData(false)] [InlineData(true)]
    public void AReservedCoinIsNotBurnedOrMintedUntilTheOutcome(bool refund)
    {
        var rows=new List<EconomyFlowRow>{EconomyFlow.Ledger("Gold","old","reward.choice.refresh.reserve",null,"-7",1)};
        var held=Assert.Single(EconomyFlow.Summarize(rows));Assert.Equal("0",held.SystemBurn);Assert.Equal("7",held.EscrowReserved);Assert.Equal("-7",held.LedgerDelta);Assert.Equal("0",held.ReconciliationDifference);
        if(refund)rows.Add(EconomyFlow.Ledger("Gold","old","reward.choice.refresh.refund",null,"7",1));
        else
        {
            rows.Add(new("Gold","Season","old",EconomyFlowKind.SystemBurn,"Refresh","7","0",1));
            rows.Add(new("Gold","Season","old",EconomyFlowKind.EscrowConsumed,"Refresh","7","0",0));
        }
        var resolved=Assert.Single(EconomyFlow.Summarize(rows));Assert.Equal(refund?"0":"7",resolved.SystemBurn);Assert.Equal("0",resolved.SystemMint);Assert.Equal("0",resolved.ReconciliationDifference);
    }

    [Fact]
    public void ConsumptionInAnotherWindowExplainsZeroNewAccountDebit()
    {
        var total=Assert.Single(EconomyFlow.Summarize(new[]{new EconomyFlowRow("Gold","Season","s",EconomyFlowKind.SystemBurn,"Refresh","7","0",1),
            new EconomyFlowRow("Gold","Season","s",EconomyFlowKind.EscrowConsumed,"Refresh","7","0",0)}));
        Assert.Equal("0",total.ExpectedLedgerDelta);Assert.Equal("-7",total.RecognizedNetSupply);Assert.True(total.CoverageComplete);
    }

    [Fact]
    public void PermanentSoulsAreNotTurnedIntoSeparateSeasonWalletsAndUnknownClassSoulIsNotGuessed()
    {
        var rows=new[]{EconomyFlow.Ledger("MageSoul","old","settlement.commit","MatchSettlement","4",1),EconomyFlow.Ledger("MageSoul","new","journey.claim","SeasonJourney","8",1)};
        var total=Assert.Single(EconomyFlow.Summarize(rows));Assert.Equal("Permanent",total.WalletScope);Assert.Null(total.WalletSeasonId);Assert.Equal("12",total.SystemMint);
        var unknown=EconomyFlow.Ledger("ClassSoul",null,"mail.claim","LegacyMail","3",1);Assert.False(unknown.Known);Assert.Equal(EconomyFlowKind.Unclassified,unknown.Kind);
    }

    [Fact]
    public void LargeIntegerSumsAndTheMinimumSignedDeltaNeverPassThroughFloatingPoint()
    {
        var total=Assert.Single(EconomyFlow.Summarize(new[]{EconomyFlow.Ledger("Gold",null,"shop.purchase",null,long.MinValue.ToString(System.Globalization.CultureInfo.InvariantCulture),1),
            EconomyFlow.Ledger("Gold",null,"shop.purchase",null,"-9223372036854775808",1)}));
        Assert.Equal("18446744073709551616",total.SystemBurn);Assert.Equal("-18446744073709551616",total.LedgerDelta);Assert.Equal("0",total.ReconciliationDifference);
        Assert.Throws<InvalidDataException>(()=>EconomyFlow.Parse("1.25"));
    }

    [Theory]
    [InlineData("Gold",0,null,true)] [InlineData("Gold",1,"0",true)] [InlineData("Gold",2,"0",false)]
    public void MinimumIntegerTaxCanLeaveNoSellerLedgerRow(string currency,long sellerRows,string? sellerDelta,bool expected)
    {
        Assert.Equal(expected,EconomyFlow.MarketLegsKnown(currency,1,0,1,"s",-BigInteger.One,sellerRows,"s",sellerDelta is null?null:EconomyFlow.Parse(sellerDelta)));
    }

    [Fact]
    public void MissingBuyerOrMismatchedSeasonCannotBeCoveredByTheOtherAccount()
    {
        Assert.False(EconomyFlow.MarketLegsKnown("Gold",100,90,0,null,null,1,"s",90));
        Assert.False(EconomyFlow.MarketLegsKnown("Gold",100,90,1,"a",-100,1,"b",90));
        Assert.True(EconomyFlow.MarketLegsKnown("Diamond",100,90,1,"a",-100,1,"b",90));
    }

    [Theory]
    [InlineData("settlement.commit","-5")] [InlineData("mystery.source","5")] [InlineData("equipment.enhance","5")]
    public void WrongSignOrUnrecognizedReasonRemainsUnclassified(string reason,string delta)
    {
        var total=Assert.Single(EconomyFlow.Summarize(new[]{EconomyFlow.Ledger("Gold",null,reason,null,delta,1)}));Assert.False(total.CoverageComplete);Assert.Equal("5",total.UnclassifiedMagnitude);Assert.Equal("0",total.RecognizedNetSupply);
    }

    [Fact]
    public void WindowsAreNonemptyAndBounded()
    {
        var at=DateTimeOffset.UnixEpoch;EconomyTelemetryRepository.ValidateWindow(at,at.AddDays(7));
        Assert.Throws<ArgumentException>(()=>EconomyTelemetryRepository.ValidateWindow(at,at));Assert.Throws<ArgumentException>(()=>EconomyTelemetryRepository.ValidateWindow(at,at.AddTicks(-1)));
        Assert.Throws<ArgumentException>(()=>EconomyTelemetryRepository.ValidateWindow(at,at.AddDays(7).AddTicks(1)));
    }

    [Fact]
    public void OperationalMeterHasOnlyOneBoundedOutcomeLabel()
    {
        var values=new List<string>();using var listener=new MeterListener();listener.InstrumentPublished=(instrument,l)=>{if(instrument.Meter.Name==ServerMetrics.MeterName&&instrument.Name=="fantasycard.telemetry.economy.query.duration")l.EnableMeasurementEvents(instrument);};
        listener.SetMeasurementEventCallback<double>((_,_,tags,_)=>{Assert.Equal(1,tags.Length);Assert.Equal("outcome",tags[0].Key);values.Add((string)tags[0].Value!);});listener.Start();
        using var metrics=new EconomyTelemetryMetrics();foreach(var value in new[]{TelemetryQueryOutcome.Success,TelemetryQueryOutcome.Invalid,TelemetryQueryOutcome.Timeout,(TelemetryQueryOutcome)999})metrics.Observe(TimeSpan.FromMilliseconds(2),value);
        Assert.Equal(ExpectedQueryOutcomes,values);
    }
}
