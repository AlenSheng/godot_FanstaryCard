namespace FantasyCard.Domain.Combat;

public enum CombatDrawSource { Natural, PassiveCharge, Instant, Opening, Chain }
public enum CombatMetric
{
    EntryHandObserved, AdvancedTicks, DrawEnabledTicks, EligibleDrawTicks, StunnedTicks, DrawBlockedTicks, UnionBlockedTicks,
    NaturalIntervalSample, EffectiveIntervalSample, DiscardedFractionSample,
    NaturalAttempts, NaturalEffective, NaturalEmpty, NaturalFullResets, NaturalDiscardedWholeCharge,
    PassiveChargeAttempts, PassiveChargeEffective, PassiveChargeEmpty, PassiveChargeFullResets, PassiveChargeDiscardedWholeCharge,
    InstantRequested, InstantEffective, InstantEmpty, InstantFullBlocked,
    OpeningRequested, OpeningEffective, OpeningEmpty, OpeningFullBlocked,
    ChainRequested, ChainEffective, ChainEmpty, ChainFullBlocked,
    HealRequested, HealApplied, HealOverflow, HealClampCorrection,
    ShieldRequested, ShieldApplied, ShieldOverflow, ShieldClampCorrection,
    StunRequestedTicks, StunExtendedTicks, BlockRequestedTicks, BlockExtendedTicks,
    Casts, CardsPlayed, ZeroDamageCasts, OutgoingResolvedDamage, OutgoingAppliedDamage,
    RequestedTargetStunTicks, GrantedTargetStunTicks, RequestedTargetDrawBlockTicks, GrantedTargetDrawBlockTicks,
    DamageIntents, PositiveBaseDamageIntents, ZeroResolvedDamageIntents, ZeroAppliedDamageIntents,
    EnemyObservedTicks, EnemyStunTimerTicks, EnemyStunSuppressedTicks
}
public readonly record struct CombatMeasurement(CombatMetric Metric,long Amount=0,double? Sample=null);
