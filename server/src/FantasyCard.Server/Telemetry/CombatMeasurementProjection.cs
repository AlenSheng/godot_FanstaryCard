using System.Globalization;
using System.Numerics;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;

namespace FantasyCard.Server.Telemetry;

public sealed record ExactCombatRatio(string Numerator,string Denominator);
public sealed record CombatMeasurementReport(Guid RoomId,Guid PlayerId,Guid? BattleId,string Mode,bool Partial,TimeSpan ObservedFromRoomElapsed,
    TimeSpan ObservedThroughRoomElapsed,SeasonEventDimensions Dimensions,IReadOnlyDictionary<string,string> Counters,
    double? NaturalIntervalMinimum,double? NaturalIntervalMaximum,double? EffectiveIntervalMinimum,double? EffectiveIntervalMaximum,
    double DiscardedFractionalCharge,bool Saturated,ExactCombatRatio? CastsPerObservedMinute,ExactCombatRatio? StunTimerCoverage,
    ExactCombatRatio? UnionBlockedCoverage,ExactCombatRatio? EnemyStunTimerCoverage,ExactCombatRatio? EnemySuppressedStepCoverage);

public static class CombatMeasurementProjection
{
    public static CombatMeasurementReport Project(Guid room,string config,SeasonContext? season,string difficulty,RoomObservationOwner owner,
        RoomCombatObservation row,RoomBuildProfile? battleProfile)
    {
        var counts=row.Counters;long Count(CombatMetric metric)=>counts.GetValueOrDefault(metric.ToString());
        ExactCombatRatio? Ratio(BigInteger numerator,BigInteger denominator)
        {
            if(row.Saturated||denominator<=0)return null;
            var divisor=BigInteger.GreatestCommonDivisor(numerator,denominator);return new((numerator/divisor).ToString(CultureInfo.InvariantCulture),(denominator/divisor).ToString(CultureInfo.InvariantCulture));
        }
        var dims=new SeasonEventDimensions(season?.SeasonId,season?.DifficultyId??difficulty,owner.HeroClass.ToString(),battleProfile?.BuildType,
            battleProfile?.GrowthStage,owner.IsBot?"Bot":"Human",row.CellType,season?.RulesetId,config,season?.StatsVersion,"CumulativeObservation");
        var advanced=Count(CombatMetric.AdvancedTicks);var enemies=Count(CombatMetric.EnemyObservedTicks);
        return new(room,row.PlayerId,row.BattleId,row.Mode,row.Partial,row.ObservedFromRoomElapsed,row.ObservedThroughRoomElapsed,dims,
            counts.OrderBy(p=>p.Key,StringComparer.Ordinal).ToDictionary(p=>p.Key,p=>p.Value.ToString(CultureInfo.InvariantCulture),StringComparer.Ordinal),row.NaturalIntervalMinimum,row.NaturalIntervalMaximum,
            row.EffectiveIntervalMinimum,row.EffectiveIntervalMaximum,row.DiscardedFractionalCharge,row.Saturated,
            Ratio((BigInteger)Count(CombatMetric.Casts)*TimeSpan.TicksPerMinute,advanced),Ratio(Count(CombatMetric.StunnedTicks),advanced),
            Ratio(Count(CombatMetric.UnionBlockedTicks),advanced),Ratio(Count(CombatMetric.EnemyStunTimerTicks),enemies),Ratio(Count(CombatMetric.EnemyStunSuppressedTicks),enemies));
    }
}
