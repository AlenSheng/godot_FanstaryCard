namespace FantasyCard.Contracts.Realtime;

public sealed record ClientCommand(
    string Type,
    string? RequestId,
    long? ExpectedRevision,
    object? Payload);

public sealed record ServerEvent(
    string Type,
    string TraceId,
    object? Payload,
    string EventId,
    long Sequence,
    DateTimeOffset OccurredAt,
    string? RequestId = null,
    long? RoomRevision = null);
public sealed record SessionResumeCommandPayload(long LastSequence, Guid? RoomId = null, long? RoomRevision = null);
public sealed record SessionConnectedEventPayload(Guid PlayerId);
public sealed record SessionReplacedEventPayload(string Reason);
public sealed record PongEventPayload(DateTimeOffset ServerTime);
public sealed record SessionSnapshotEventPayload(Guid PlayerId, long PlayerVersion, string? SelectedClass, string Reason, long PreviousLastSequence);
public sealed record MatchFoundEventPayload(Guid MatchId, Guid RoomId, long DeadlineUnixMs);
public sealed record RoomReadyCommandPayload;
public sealed record RoomReadyRequiredEventPayload(Guid MatchId, Guid RoomId, long DeadlineUnixMs, int ReadyPlayers, int RequiredPlayers);
public sealed record RoomReadyAcceptedEventPayload(Guid MatchId, Guid RoomId, long DeadlineUnixMs, int ReadyPlayers, int RequiredPlayers);
public sealed record RoomReadyRemovedEventPayload(Guid MatchId, string Reason);
public sealed record RoomStartedEventPayload(Guid MatchId, Guid RoomId, int PlayerCount, RoomSnapshotEventPayload? Snapshot = null);
public sealed record SettlementReadyEventPayload(Guid SettlementId, Guid MatchId, string Result);
public sealed record RoomSnapshotCommandPayload;
public sealed record RoomPositionPayload(int Row, int Column);
public sealed record RoomMapCellPayload(int Row, int Column, bool IsBoss, bool HasSpring);
public sealed record RoomCardPayload(Guid InstanceId, string CardId, int Level = 0, string? ElementOverride = null);
public sealed record RoomCombatantPayload(int Hp, int MaximumHp, int EffectiveMaximumHp, int Shield);
public sealed record RoomStatPayload(string Key, string Value);
public sealed record RoomSetPayload(string Kind, int Count, int Required, bool Active);
public sealed record RoomBattleStatusPayload(string PassiveKind, int Combo, string? CoreElement,
    IReadOnlyList<RoomStatPayload> Bonuses, IReadOnlyList<RoomSetPayload> Sets, string DrawIntervalSeconds,
    int ChargeLevel = 0);
public sealed record RoomEquipmentPayload(string Slot, string Quality, string Element, string? EffectAffix, string? SecondaryTrait, int Level = 0, bool IsBound = false);
public sealed record RoomInventoryItemPayload(string ItemId, string Kind, int Quantity, bool IsSafe, RoomEquipmentPayload? Equipment = null, int SlotIndex = -1);
public sealed record RoomRelicPilePayload(Guid PileId, string OwnerName, long Version, IReadOnlyList<RoomInventoryItemPayload> Items);
public sealed record RoomMonsterPayload(
    string MonsterId,
    int MaximumHp,
    int Hp,
    int Shield,
    string IntentKind,
    int IntentValue,
    string IntentElement,
    long IntervalProgressMs,
    long WindupRemainingMs,
    long StunRemainingMs,
    int BossPhase = 1);
public sealed record RoomPvePayload(Guid BattleId, string Phase, string? CurrentTargetId, IReadOnlyList<RoomMonsterPayload> Monsters);
public sealed record RoomDuelPayload(
    Guid DuelId,
    Guid OpponentId,
    RoomCombatantPayload Opponent,
    long LatePlayerUnlockAtUnixMs,
    long LeaveWindowEndsAtUnixMs,
    bool SelfRequestedLeave,
    long? EscapeRemainingMs,
    string? OpponentClass = null,
    string? OpponentName = null,
    string? EscapeProbability = null,
    RoomBattleStatusPayload? OpponentStatus = null,
    long OpponentStunRemainingMs = 0,
    long OpponentDrawBlockRemainingMs = 0,
    bool SeparateLoot = false,
    IReadOnlyList<RoomInventoryItemPayload>? SearchableLoot = null);
public sealed record RoomCurrentCellPayload(
    bool HasEvacuation,
    string MonsterGroupId,
    bool SpringConsumed,
    IReadOnlyList<Guid> RelicPileIds,
    IReadOnlyList<RoomRelicPilePayload>? RelicPiles = null);
public sealed record MapPlayerCountEventPayload(int PlayerCount);
public sealed record RoomPlayerPayload(
    Guid PlayerId,
    string HeroClass,
    string Phase,
    RoomCombatantPayload Combat,
    IReadOnlyList<RoomCardPayload> Hand,
    int LibraryCount,
    int DiscardCount,
    string DrawCharge,
    IReadOnlyList<RoomInventoryItemPayload> Inventory,
    int InventoryCapacity = 0,
    IReadOnlyList<int>? SafeSlotIndexes = null,
    IReadOnlyList<RoomInventoryItemPayload>? EquippedItems = null,
    int WeaponLevel = 0,
    RoomBattleStatusPayload? BattleStatus = null,
    long StunRemainingMs = 0,
    long DrawBlockRemainingMs = 0,
    long DrawSpeedRemainingMs = 0,
    long DrawBlockSpeedRemainingMs = 0,
    string? BaseDrawIntervalSeconds = null,
    RoomMonsterPoolPayload? MonsterPool = null,
    RoomNumericalStatePayload? NumericalState = null);
public sealed record RoomSnapshotEventPayload(
    Guid RoomId,
    Guid? MatchId,
    long RoomRevision,
    string ConfigVersion,
    RoomPositionPayload Self,
    IReadOnlyList<RoomMapCellPayload> Map,
    IReadOnlyList<RoomPositionPayload> LegalMoves,
    RoomCurrentCellPayload CurrentCell,
    RoomPlayerPayload Player,
    RoomPvePayload? Pve,
    RoomDuelPayload? Duel,
    RewardChoiceEventPayload? RewardChoice,
    long? ExtractionRemainingMs,
    long? SpringRemainingMs,
    IReadOnlyList<string> AllowedActions,
    int MapPlayerCount = 0);
public sealed record CommandRejectedEventPayload(string Code, string Detail);
public sealed record BattlePlayCardsCommandPayload(
    Guid BattleId,
    string TargetId,
    IReadOnlyList<Guid> CardInstanceIds);
public sealed record BattleSelectTargetCommandPayload(Guid BattleId, string TargetId);
public sealed record BattleAbandonCommandPayload;
public sealed record MonsterCardChooseCommandPayload(Guid CandidateId, bool Accept, Guid? ReplaceInstanceId = null);
public sealed record RoomMonsterPoolPayload(int Capacity, IReadOnlyList<RoomCardPayload> Pending, IReadOnlyList<RoomCardPayload> Active);
public sealed record RoomNumericalStatePayload(string FenxianPolicy, string GuardianPolicy, int GuardianRemainderTenths);
public sealed record BattleTargetSelectedEventPayload(Guid BattleId, string TargetId);
public sealed record BattleComboResolvedEventPayload(
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
    IReadOnlyList<CombatDamageSegmentPayload>? DamageSegments = null,
    string? CoreElement = null,
    int CoreCount = 0,
    string? StunSeconds = null,
    string? DrawBlockSeconds = null,
    int HealthCost = 0,
    string? DrawCharge = null,
    int ImmediateDraw = 0,
    IReadOnlyList<Guid>? CardInstanceIds = null,
    string? SourceId = null,
    string? DrawSpeedSeconds = null,
    string? DrawSpeedModifier = null,
    string? DrawBlockSpeedSeconds = null,
    string? ResonanceMultiplier = null,
    int ConflictPairCount = 0,
    string? ConflictCancellation = null);
public sealed record CombatDamageSegmentPayload(string Kind, int Amount);
public sealed record RoomMoveCommandPayload(int Row, int Column);
public sealed record RoomMovedEventPayload(Guid PlayerId, int Row, int Column);
public sealed record DuelLeaveCommandPayload(Guid DuelId);
public sealed record DuelLeaveEventPayload(Guid DuelId, bool Completed);
public sealed record DuelEscapeCommandPayload(Guid DuelId);
public sealed record DuelEscapeEventPayload(Guid DuelId, double Probability, string Status);
public sealed record DuelStartedEventPayload(Guid DuelId, Guid FirstPlayerId, Guid LatePlayerId, long LatePlayerUnlockAtUnixMs, long LeaveWindowEndsAtUnixMs);
public sealed record DuelEndedEventPayload(Guid DuelId, string Reason, Guid? WinnerId, bool SnapshotRequired = true);
public sealed record PlayerDiedEventPayload(Guid PlayerId, string Cause, Guid? DuelId = null);
public sealed record ActionExtractCommandPayload;
public sealed record ActionExtractEventPayload(string Status, TimeSpan Remaining);
public sealed record ActionSpringCommandPayload;
public sealed record ActionSpringEventPayload(string Status, TimeSpan Remaining);
public sealed record ActionPotionCommandPayload;
public sealed record ActionPotionEventPayload(string ItemId, int Healed);
public sealed record RelicTakeCommandPayload(Guid PileId, string ItemId, long PileVersion, string? ReplaceItemId = null);
public sealed record RelicReadCommandPayload(Guid PileId);
public sealed record RelicTakeEventPayload(Guid PileId, string ItemId, long PileVersion);
public sealed record RelicReplaceCommandPayload(Guid PileId, string ItemId, long PileVersion, string ReplaceItemId);
public sealed record RelicReplacedEventPayload(Guid PileId, string ItemId, string ReturnedItemId, long PileVersion);
public sealed record InventoryMoveCommandPayload(string ItemId, int TargetSlotIndex);
public sealed record InventoryEquipCommandPayload(string ItemId);
public sealed record InventoryUnequipCommandPayload(string Slot);
public sealed record InventoryChangedEventPayload(
    string Action,
    string ItemId,
    FantasyCard.Contracts.Progression.MarketListingResponse? Listing = null,
    long? SellerGoldAfter = null);
public sealed record RewardChoiceRefreshCommandPayload;
public sealed record RewardChoiceClaimCommandPayload(string OptionId, string? ReplaceItemId = null, bool Equip = false);
public sealed record RewardChoiceClaimedEventPayload(string OptionId, int Applied);
public enum RewardChoiceKindDto : short { Equipment = 1, EquipmentFragments = 2, ImmediateHeal = 3 }
public sealed record RewardChoiceOptionPayload(string OptionId, RewardChoiceKindDto Kind, string? ItemId, int Quantity, int HealPercent, RoomEquipmentPayload? Equipment = null);
public sealed record RewardChoiceEventPayload(int Layer, IReadOnlyList<RewardChoiceOptionPayload> Options, int RefreshCount, bool IsBoss = false);
