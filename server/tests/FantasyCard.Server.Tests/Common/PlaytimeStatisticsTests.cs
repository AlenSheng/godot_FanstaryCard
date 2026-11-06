using System.Numerics;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Common;

public sealed class PlaytimeStatisticsTests
{
    private static readonly DateTimeOffset Epoch=DateTimeOffset.UnixEpoch;
    [Fact]
    public void AClockWhollyOutsideTheRequestedWindowDoesNotCreateAnUnknownDurationInsideIt()
    {
        var id=Guid.NewGuid();var rows=new[]{new PlaytimeInterval(id,"Human","Mage",Epoch.AddDays(-2),TimeSpan.FromHours(1),null,true),
            new PlaytimeInterval(id,"Human","Mage",Epoch.AddDays(2),TimeSpan.FromHours(1),null,true)};
        var projection=PlaytimeStatistics.Project(rows,Epoch,Epoch.AddHours(1),new Dictionary<Guid,BigInteger>());
        Assert.Empty(projection.Samples);Assert.Equal(0,projection.UnknownTerminalClocks);
    }
    [Fact]
    public void WalletScopeIsExplicitAndPermanentCurrenciesCannotBeSplitByTheirOriginSeason()
    {
        Assert.Equal("Season",PlaytimeTelemetryRepository.ValidateScope("Gold","s",false));
        Assert.Equal("LegacyUnspecified",PlaytimeTelemetryRepository.ValidateScope("Gold",null,true));
        Assert.Equal("Permanent",PlaytimeTelemetryRepository.ValidateScope("MageSoul",null,false));
        Assert.Throws<ArgumentException>(()=>PlaytimeTelemetryRepository.ValidateScope("Gold",null,false));
        Assert.Throws<ArgumentException>(()=>PlaytimeTelemetryRepository.ValidateScope("MageSoul","s",false));
        Assert.Throws<ArgumentException>(()=>PlaytimeTelemetryRepository.ValidateScope("ChallengeMarks",null,true));
    }
    [Fact]
    public void DeadZeroIncomeAndNegativeNetSamplesRemainInThePercentiles()
    {
        var rows=Enumerable.Range(0,10).Select(i=>new PlaytimeRateSample(Guid.NewGuid(),"Human","Mage",TimeSpan.TicksPerHour,i-5)).ToArray();
        var value=Assert.Single(PlaytimeStatistics.Distributions(rows));Assert.Equal(10,value.Players);Assert.Equal(1,value.ZeroNetPlayers);Assert.Equal(5,value.NegativeNetPlayers);
        Assert.Equal("-5.000000",value.P10.DecimalDisplay);Assert.Equal("-1.000000",value.P50.DecimalDisplay);Assert.Equal("3.000000",value.P90.DecimalDisplay);Assert.Equal("-0.500000",value.WeightedNetPerHour.DecimalDisplay);
    }
    [Fact]
    public void IntervalClippingAndUnionPreventDoubleCountingOnePlayerAcrossRooms()
    {
        var player=Guid.NewGuid();var rows=new[]{new PlaytimeInterval(player,"Human","Mage",Epoch,TimeSpan.FromHours(3),TimeSpan.FromHours(1),true),
            new PlaytimeInterval(player,"Human","Priest",Epoch.AddMinutes(30),TimeSpan.FromHours(1),TimeSpan.FromHours(1),true)};
        var result=PlaytimeStatistics.Project(rows,Epoch.AddMinutes(15),Epoch.AddMinutes(75),new Dictionary<Guid,BigInteger>{{player,9}});var sample=Assert.Single(result.Samples);
        Assert.Equal(TimeSpan.TicksPerHour,sample.KnownTicks);Assert.Equal("Mixed",sample.Hero);Assert.Equal(9,sample.Net);
    }
    [Fact]
    public void UnknownTerminalTimeIsNeverReplacedWithTheLatestRoomElapsed()
    {
        var id=Guid.NewGuid();var rows=new[]{new PlaytimeInterval(id,"Human","Mage",Epoch,TimeSpan.FromHours(4),null,true)};
        var result=PlaytimeStatistics.Project(rows,Epoch,Epoch.AddDays(1),new Dictionary<Guid,BigInteger>());Assert.Empty(result.Samples);Assert.Equal(1,result.UnknownTerminalClocks);
    }
    [Fact]
    public void ActivePartialTimeIsRecordedAsRightCensoredAndNeverExtrapolated()
    {
        var id=Guid.NewGuid();var result=PlaytimeStatistics.Project([new(id,"Human","Guardian",Epoch,TimeSpan.FromMinutes(10),null,false)],Epoch,Epoch.AddHours(1),new Dictionary<Guid,BigInteger>());
        Assert.Equal(TimeSpan.FromMinutes(10).Ticks,Assert.Single(result.Samples).KnownTicks);Assert.Equal(1,result.RightCensoredClocks);Assert.Equal(BigInteger.Zero,result.Samples[0].Net);
    }
    [Fact]
    public void BotAndHumanSamplesStaySeparateAndHugeRatesKeepAnExactFraction()
    {
        var rows=new[]{new PlaytimeRateSample(Guid.NewGuid(),"Human","Mage",1,BigInteger.Parse("9223372036854775808",System.Globalization.CultureInfo.InvariantCulture)),new PlaytimeRateSample(Guid.NewGuid(),"Bot","Mage",TimeSpan.TicksPerHour,0)};
        Assert.Equal(2,PlaytimeStatistics.Distributions(rows).Count);var rate=PlaytimeStatistics.Rate(1,TimeSpan.TicksPerHour*3);Assert.Equal("1",rate.Numerator);Assert.Equal("3",rate.Denominator);Assert.Equal("0.333333",rate.DecimalDisplay);
        Assert.Equal("-0.666667",PlaytimeStatistics.Rate(-2,TimeSpan.TicksPerHour*3).DecimalDisplay);Assert.Throws<ArgumentOutOfRangeException>(()=>PlaytimeStatistics.Rate(1,0));
    }
    [Fact]
    public void ZeroAndInvalidClocksAreCountedWithoutInventingRatesOrCurrentProfiles()
    {
        var id=Guid.NewGuid();var rows=new[]{new PlaytimeInterval(id,"Human","Mage",Epoch,TimeSpan.Zero,TimeSpan.Zero,true),new PlaytimeInterval(id,"Human","Mage",Epoch,TimeSpan.FromSeconds(1),TimeSpan.FromSeconds(2),true),
            new PlaytimeInterval(id,"Human","Mage",Epoch,TimeSpan.FromMinutes(1),TimeSpan.FromMinutes(1),true),new PlaytimeInterval(id,"Human","unknown",Epoch,TimeSpan.FromMinutes(1),TimeSpan.FromMinutes(1),true)};
        var result=PlaytimeStatistics.Project(rows,Epoch,Epoch.AddHours(1),new Dictionary<Guid,BigInteger>());Assert.Equal(1,result.ZeroLengthClocks);Assert.Equal(1,result.InvalidClocks);Assert.Equal("Unknown",Assert.Single(result.Samples).Hero);
    }
}
