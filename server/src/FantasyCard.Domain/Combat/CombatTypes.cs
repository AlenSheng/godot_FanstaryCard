namespace FantasyCard.Domain.Combat;

public enum CardElement : short
{
    None = 0,
    Fire = 1,
    Wood = 2,
    Earth = 3,
    Metal = 4,
    Water = 5
}

public enum FenxianImmediateDrawPolicy : short
{
    CurrentRhythm = 1,
    CoreCardsSpent = 2
}

public enum GuardianShieldBonusPolicy : short
{
    CurrentSteps = 1,
    FractionalRemainder = 2
}

public readonly record struct GuardianShieldResolutionDraft(int Shield, int? RemainderTenthsAfter);

public sealed record CombatCardEffect(
    int ElementalDamage = 0,
    CardElement Element = CardElement.None,
    int DirectDamage = 0,
    int Heal = 0,
    int Shield = 0,
    double DrawCharge = 0,
    int ImmediateDraw = 0,
    double DrawSpeedModifier = 0,
    double DrawSpeedSeconds = 0,
    double StunSeconds = 0,
    double DrawBlockSeconds = 0,
    int HealthCost = 0,
    int SameElementBonus = 0,
    int ResonanceBonus = 0,
    double ConflictCancelBonus = 0,
    double ConflictHealCoefficient = 0,
    bool IsClassReveal = false,
    int SecondaryElementalDamage = 0,
    CardElement SecondaryElement = CardElement.None,
    bool IsElementTuning = false);

public sealed record CombatCardDefinition(string CardId, CombatCardEffect Effect);

public sealed record CombatCardInstance(Guid InstanceId, string CardId, int Level = 0, CardElement? ElementOverride = null);

public sealed record CombatDeckSnapshot(
    IReadOnlyList<CombatCardInstance> Hand,
    IReadOnlyList<CombatCardInstance> Library,
    IReadOnlyList<CombatCardInstance> Discard,
    double DrawCharge);

public sealed record TargetStunWindowSnapshot(string TargetId, TimeSpan Remaining, int Count);

public sealed record PlayerCombatSnapshot(
    int MaximumHp,
    int Hp,
    int Shield,
    int WeaponLevel,
    ulong RandomState,
    CombatDeckSnapshot Deck,
    int FenxianCombo,
    CardElement? LastFenxianCore,
    TimeSpan DrawSpeedRemaining,
    double DrawSpeedModifier,
    TimeSpan StunRemaining,
    TimeSpan DrawBlockRemaining,
    IReadOnlyList<TargetStunWindowSnapshot> TargetStunWindows,
    CombatEquipmentProfile? Equipment = null,
    TimeSpan DrawBlockSpeedRemaining = default,
    int FenxianChargeLevel = 0,
    int GuardianShieldRemainderTenths = 0,
    FenxianImmediateDrawPolicy FenxianPolicy = FenxianImmediateDrawPolicy.CurrentRhythm,
    GuardianShieldBonusPolicy GuardianPolicy = GuardianShieldBonusPolicy.CurrentSteps);

public enum MonsterIntentKind : short
{
    Attack = 1,
    Direct = 2,
    Shield = 3,
    Charge = 4,
    Empower = 5
}

public sealed record MonsterIntentState(
    MonsterIntentKind Kind,
    int Value,
    CardElement Element);

public sealed record TimedCombatStatusSnapshot(string Key, TimeSpan Remaining);

public sealed record MonsterCombatSnapshot(
    string MonsterId,
    int MaximumHp,
    int Hp,
    int Shield,
    TimeSpan AttackInterval,
    double ElementalAmplification,
    IReadOnlyList<MonsterIntentState> Intents,
    int IntentIndex,
    TimeSpan IntervalProgress,
    TimeSpan WindupRemaining,
    bool IsCharging,
    int EmpowerBonus,
    TimeSpan StunRemaining,
    IReadOnlyList<TimedCombatStatusSnapshot> StatusRemaining,
    int BossPhase = 1,
    bool BossPhaseTransitionPending = false);

public enum PveBattlePhase : short
{
    Active = 1,
    Frozen = 2,
    Cleared = 3,
    Dead = 4
}

public sealed record PveBattleSnapshot(
    Guid BattleId,
    PveBattlePhase Phase,
    string? CurrentTargetId,
    IReadOnlyList<MonsterCombatSnapshot> Monsters);

public enum RoomPlayerPhase : short
{
    Pve = 1,
    ActionBar = 2,
    Pvp = 3,
    Dead = 4,
    Extracted = 5,
    Choice = 6
}

public sealed record RoomPlayerSnapshot(
    Guid PlayerId,
    Players.HeroClass HeroClass,
    RoomPlayerPhase Phase,
    Guid? CurrentDuelId,
    PlayerCombatSnapshot Combat,
    PveBattleSnapshot? Pve,
    Rooms.MapPosition? Position = null,
    Rooms.ExplorationInventorySnapshot? Inventory = null,
    IReadOnlyList<Rooms.ExplorationItem>? WornArmor = null,
    TimeSpan? ExtractionRemaining = null,
    TimeSpan? DisconnectedRemaining = null,
    Rooms.RewardChoiceSnapshot? RewardChoice = null,
    int? RewardRefreshCount = null,
    IReadOnlyList<Rooms.MapPosition>? ClearedCells = null,
    IReadOnlyList<Rooms.MapPosition>? ConsumedSprings = null,
    Rooms.SpringDrinkSnapshot? SpringDrink = null,
    bool IsBot = false,
    TimeSpan? BotPveRemaining = null,
    IReadOnlyList<Rooms.RewardRefreshReceiptSnapshot>? RewardRefreshReceipts = null,
    IReadOnlyList<Rooms.ExplorationItem>? RecycledEquipment = null,
    string? DisplayName = null);

public enum DuelEndReason : short
{
    Victory = 1,
    MutualLeave = 2,
    Escaped = 3
}

public sealed record DuelStateSnapshot(
    Guid DuelId,
    Guid FirstPlayerId,
    Guid LatePlayerId,
    DateTimeOffset StartedAt,
    DateTimeOffset LatePlayerUnlockAt,
    DateTimeOffset LeaveWindowEndsAt,
    FrozenParticipantSnapshot? FirstFrozen = null,
    FrozenParticipantSnapshot? LateFrozen = null,
    IReadOnlyList<Guid>? LeaveRequests = null,
    IReadOnlyList<DuelCooldownSnapshot>? EscapeCooldowns = null,
    DuelEscapeAttemptSnapshot? EscapeAttempt = null);

public sealed record FrozenParticipantSnapshot(
    RoomPlayerPhase Phase,
    PlayerCombatSnapshot Combat,
    PveBattleSnapshot? Pve);

public sealed record DuelCooldownSnapshot(Guid PlayerId, TimeSpan Remaining);

public sealed record DuelEscapeAttemptSnapshot(Guid PlayerId, TimeSpan Remaining, double Probability, int HpAtStart);

public sealed record BotDuelTimerSnapshot(Guid DuelId, TimeSpan Remaining);

public sealed record RoomRandomStreamsSnapshot(
    ulong PlayerSeed,
    ulong Reward,
    ulong Loot,
    ulong Escape,
    ulong Bot,
    ulong Duel);

public sealed record BattleRoomSnapshot(
    Guid RoomId,
    string ConfigVersion,
    long Revision,
    TimeSpan Elapsed,
    IReadOnlyList<RoomPlayerSnapshot> Players,
    IReadOnlyList<DuelStateSnapshot> Duels,
    Rooms.ChaosMapSnapshot? Map = null,
    IReadOnlyList<Rooms.CeasefireSnapshot>? Ceasefires = null,
    IReadOnlyList<Rooms.RelicPileSnapshot>? RelicPiles = null,
    ulong? RandomState = null,
    IReadOnlyList<BotDuelTimerSnapshot>? BotDuelTimers = null,
    RoomRandomStreamsSnapshot? RandomStreams = null);

public sealed record CombatDamageSegment(string Kind, int Amount);

public sealed record CombatPassiveInfo(
    string Kind,
    int Combo,
    CardElement? CoreElement,
    double HealBonus,
    double ControlBonus,
    double ShieldBonus,
    double WeaponBonus,
    int ShieldFlatBonus,
    int ChargeLevel = 0);

public sealed record CombatantPublicInfo(
    Guid PlayerId,
    string? DisplayName,
    Players.HeroClass HeroClass,
    int Hp,
    int MaximumHp,
    int EffectiveMaximumHp,
    int Shield,
    int WeaponLevel,
    IReadOnlyList<Rooms.ExplorationItem> WornArmor,
    CombatEquipmentProfile Equipment,
    CombatPassiveInfo Passive,
    double DrawIntervalSeconds);

public sealed record RoomCombatInfo(
    CombatantPublicInfo Self,
    CombatantPublicInfo? Opponent,
    double? EscapeProbability,
    long RoomRevision);

public sealed record CombatResolution(
    Guid BattleId,
    Guid AttackerId,
    string TargetId,
    int Damage,
    int ShieldDamage,
    int HpDamage,
    int Heal,
    int ShieldGain,
    bool TargetDefeated,
    bool BattleEnded,
    long RoomRevision,
    IReadOnlyList<CombatDamageSegment>? DamageSegments = null,
    CardElement? CoreElement = null,
    int CoreCount = 0,
    double StunSeconds = 0,
    double DrawBlockSeconds = 0,
    int HealthCost = 0,
    double DrawCharge = 0,
    int ImmediateDraw = 0,
    double DrawSpeedSeconds = 0,
    double DrawSpeedModifier = 0,
    double DrawBlockSpeedSeconds = 0,
    double ResonanceMultiplier = 1,
    int ConflictPairCount = 0,
    double ConflictCancellation = 0);

public sealed record CombatFeedbackResolution(string SourceId, CombatResolution Resolution);

public sealed record CardResolutionDraft(
    int Damage,
    int Heal,
    int Shield,
    TimeSpan Stun,
    TimeSpan DrawBlock,
    double DrawCharge,
    int ImmediateDraw,
    TimeSpan DrawSpeedDuration,
    double DrawSpeedModifier,
    int HealthCost,
    CardElement? CoreElement,
    int CoreCount,
    IReadOnlyList<CombatDamageSegment>? DamageSegments = null,
    double ResonanceMultiplier = 1,
    int ConflictPairCount = 0,
    double ConflictCancellation = 0,
    int? GuardianShieldRemainderTenthsAfter = null);
