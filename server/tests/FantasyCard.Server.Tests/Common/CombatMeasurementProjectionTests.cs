using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Telemetry;

namespace FantasyCard.Server.Tests.Common;

public sealed class CombatMeasurementProjectionTests
{
    private static RoomCombatObservation Row(IReadOnlyDictionary<string,long> counts,bool saturated=false)=>new(Guid.NewGuid(),Guid.NewGuid(),"Pve","Normal",false,
        TimeSpan.Zero,TimeSpan.FromMinutes(1),counts,4,4,2,4,.25,saturated);
    private static CombatMeasurementReport Project(RoomCombatObservation row)=>CombatMeasurementProjection.Project(Guid.NewGuid(),"original-config",null,"Standard",new(row.PlayerId,HeroClass.Mage,false),row,null);

    [Fact]
    public void CountsAboveJavascriptExactRangeAndMinuteRatesRemainExactStrings()
    {
        const long casts=9007199254740993;var row=Row(new Dictionary<string,long>{{nameof(CombatMetric.Casts),casts},{nameof(CombatMetric.AdvancedTicks),TimeSpan.TicksPerMinute}});
        var report=Project(row);Assert.Equal("9007199254740993",report.Counters[nameof(CombatMetric.Casts)]);Assert.Equal(new ExactCombatRatio("9007199254740993","1"),report.CastsPerObservedMinute);
    }

    [Fact]
    public void TimerUnionAndEnemySuppressedStepsHaveSeparateExactCoverage()
    {
        var row=Row(new Dictionary<string,long>{{nameof(CombatMetric.AdvancedTicks),8},{nameof(CombatMetric.StunnedTicks),2},{nameof(CombatMetric.UnionBlockedTicks),4},
            {nameof(CombatMetric.EnemyObservedTicks),7},{nameof(CombatMetric.EnemyStunTimerTicks),1},{nameof(CombatMetric.EnemyStunSuppressedTicks),2}});
        var report=Project(row);Assert.Equal(new ExactCombatRatio("1","4"),report.StunTimerCoverage);Assert.Equal(new("1","2"),report.UnionBlockedCoverage);
        Assert.Equal(new("1","7"),report.EnemyStunTimerCoverage);Assert.Equal(new("2","7"),report.EnemySuppressedStepCoverage);
    }

    [Fact]
    public void MissingDenominatorAndSaturatedCountsDoNotClaimAValidRate()
    {
        Assert.Null(Project(Row(new Dictionary<string,long>{{nameof(CombatMetric.Casts),1}})).CastsPerObservedMinute);
        var report=Project(Row(new Dictionary<string,long>{{nameof(CombatMetric.Casts),long.MaxValue},{nameof(CombatMetric.AdvancedTicks),1}},true));
        Assert.True(report.Saturated);Assert.Null(report.CastsPerObservedMinute);Assert.Null(report.StunTimerCoverage);
    }
}
