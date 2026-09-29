using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Server.Rooms;

public interface IRoomCommand<out TResult>
{
    TResult Execute(BattleRoom room);

    // Commands that only read a projection must not enqueue persistence work
    // or force RoomActor to create an unrelated full-room snapshot.
    bool NotifyObservers => true;
}

public sealed record GetRoomSnapshotCommand : IRoomCommand<BattleRoomSnapshot>
{
    public bool NotifyObservers => false;
    public BattleRoomSnapshot Execute(BattleRoom room) => room.Capture();
}

public sealed record RoomClientState(BattleRoomSnapshot Snapshot, ChaosMapProjection Map, RoomCombatInfo? CombatInfo = null);

public interface IRoomCommandSnapshotResult
{
    BattleRoomSnapshot? Snapshot { get; }
}

public sealed record RoomCommandWithClientState<TResult>(
    TResult Result,
    RoomClientState? ClientState) : IRoomCommandSnapshotResult
{
    public BattleRoomSnapshot? Snapshot => ClientState?.Snapshot;
}

public sealed record ExecuteWithClientStateCommand<TResult>(
    IRoomCommand<TResult> Mutation,
    Guid PlayerId) : IRoomCommand<RoomCommandWithClientState<TResult>>
{
    public bool NotifyObservers => Mutation.NotifyObservers;

    public RoomCommandWithClientState<TResult> Execute(BattleRoom room)
    {
        var result = Mutation.Execute(room);
        RoomClientState? clientState = null;
        try
        {
            clientState = new GetRoomClientStateCommand(PlayerId).Execute(room);
        }
        catch (Exception exception) when (exception is DomainValidationException or InvalidOperationException)
        {
            // A mutation remains authoritative even when a transitional room
            // cannot produce the optional map projection yet.
        }
        return new(result, clientState);
    }
}

public sealed record GetRoomClientStateCommand(Guid PlayerId) : IRoomCommand<RoomClientState>
{
    public bool NotifyObservers => false;
    public RoomClientState Execute(BattleRoom room) =>
        new(room.Capture(), room.GetMapProjection(PlayerId), room.GetCombatInfo(PlayerId));
}

public sealed record AdvanceRoomTimeCommand(TimeSpan Delta, DateTimeOffset? Now = null) : IRoomCommand<BattleRoomSnapshot>
{
    public BattleRoomSnapshot Execute(BattleRoom room)
    {
        room.Advance(Delta, Now);
        return room.Capture();
    }
}

public sealed record RecoverRoomDowntimeCommand(TimeSpan Downtime, DateTimeOffset RecoveredAt) : IRoomCommand<BattleRoomSnapshot>
{
    public BattleRoomSnapshot Execute(BattleRoom room)
    {
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(Downtime, TimeSpan.Zero);
        var remaining = Downtime;
        var tickAt = RecoveredAt - Downtime;
        while (remaining > TimeSpan.Zero)
        {
            var delta = remaining < RoomActor.TickInterval ? remaining : RoomActor.TickInterval;
            tickAt += delta;
            room.Advance(delta, tickAt);
            remaining -= delta;
        }
        return room.Capture();
    }
}

public sealed record StartRoomDuelCommand(
    Guid FirstPlayerId,
    Guid LatePlayerId,
    DateTimeOffset Now) : IRoomCommand<DuelStateSnapshot>
{
    public DuelStateSnapshot Execute(BattleRoom room) =>
        room.StartDuel(FirstPlayerId, LatePlayerId, Now).Capture();
}

public sealed record EndRoomDuelSurvivedCommand(
    Guid DuelId,
    DuelEndReason Reason) : IRoomCommand<BattleRoomSnapshot>
{
    public BattleRoomSnapshot Execute(BattleRoom room)
    {
        room.EndDuelSurvived(DuelId, Reason);
        return room.Capture();
    }
}

public sealed record EndRoomDuelWithDeathCommand(
    Guid DuelId,
    Guid LoserId) : IRoomCommand<BattleRoomSnapshot>
{
    public BattleRoomSnapshot Execute(BattleRoom room)
    {
        room.EndDuelWithDeath(DuelId, LoserId);
        return room.Capture();
    }
}

public sealed record SetPlayerConnectionCommand(Guid PlayerId, bool Connected) : IRoomCommand<BattleRoomSnapshot>
{
    public BattleRoomSnapshot Execute(BattleRoom room)
    {
        if (Connected) room.MarkPlayerConnected(PlayerId);
        else room.MarkPlayerDisconnected(PlayerId);
        return room.Capture();
    }
}

public sealed record RequestDuelLeaveResult(Guid DuelId, bool Completed, long RoomRevision);

public sealed record RequestDuelLeaveCommand(
    Guid PlayerId,
    Guid DuelId,
    DateTimeOffset Now) : IRoomCommand<RequestDuelLeaveResult>
{
    public RequestDuelLeaveResult Execute(BattleRoom room) =>
        new(DuelId, room.RequestDuelLeave(DuelId, PlayerId, Now), room.Revision);
}

public sealed record RequestDuelEscapeCommand(Guid PlayerId, Guid DuelId) : IRoomCommand<DuelEscapeRequestResult>
{
    public DuelEscapeRequestResult Execute(BattleRoom room) => room.RequestDuelEscape(DuelId, PlayerId);
}

public sealed record RequestRoomExtractionCommand(Guid PlayerId) : IRoomCommand<RoomExtractionRequestResult>
{
    public RoomExtractionRequestResult Execute(BattleRoom room) =>
        new(room.RequestExtraction(PlayerId), room.Revision);
}

public sealed record RoomExtractionRequestResult(TimeSpan Remaining, long RoomRevision);

public sealed record RequestRoomSpringCommand(Guid PlayerId) : IRoomCommand<RoomSpringRequestResult>
{
    public RoomSpringRequestResult Execute(BattleRoom room) =>
        new(room.RequestSpring(PlayerId), room.Revision);
}

public sealed record RoomSpringRequestResult(TimeSpan Remaining, long RoomRevision);

public sealed record UseRoomPotionCommand(Guid PlayerId) : IRoomCommand<PotionUseResult>
{
    public PotionUseResult Execute(BattleRoom room) => room.UsePotion(PlayerId);
}

public sealed record TakeRelicItemCommand(
    Guid PlayerId,
    Guid PileId,
    string ItemId,
    long PileVersion,
    string? ReplaceItemId) : IRoomCommand<RelicTakeResult>
{
    public RelicTakeResult Execute(BattleRoom room)
    {
        var version = room.TakeRelicItem(PlayerId, PileId, ItemId, PileVersion, ReplaceItemId);
        return new(PileId, ItemId, version, room.Revision);
    }
}

public sealed record RelicTakeResult(Guid PileId, string ItemId, long PileVersion, long RoomRevision);

public sealed record ReplaceRelicItemCommand(
    Guid PlayerId,
    Guid PileId,
    string ItemId,
    long PileVersion,
    string ReplaceItemId) : IRoomCommand<RelicReplaceResult>
{
    public RelicReplaceResult Execute(BattleRoom room)
    {
        var version = room.ReplaceRelicItem(PlayerId, PileId, ItemId, PileVersion, ReplaceItemId);
        return new(PileId, ItemId, ReplaceItemId, version, room.Revision);
    }
}

public sealed record RelicReplaceResult(Guid PileId, string ItemId, string ReturnedItemId, long PileVersion, long RoomRevision);

public sealed record GetRewardChoiceCommand(Guid PlayerId) : IRoomCommand<RewardChoiceSnapshot>
{
    public bool NotifyObservers => false;
    public RewardChoiceSnapshot Execute(BattleRoom room) => room.GetRewardChoice(PlayerId);
}

public sealed record RefreshRewardChoiceCommand(Guid PlayerId, long ExpectedRevision, long AccountGoldAvailable = 0, string? RequestId = null) : IRoomCommand<RewardRefreshReceiptSnapshot>
{
    public RewardRefreshReceiptSnapshot Execute(BattleRoom room) => room.RefreshRewardChoice(PlayerId, ExpectedRevision, AccountGoldAvailable, RequestId);
}

public sealed record ClaimRewardCommand(Guid PlayerId, string OptionId, string? ReplaceItemId, bool Equip = false) : IRoomCommand<int>
{
    public int Execute(BattleRoom room) => room.ClaimReward(PlayerId, OptionId, ReplaceItemId, Equip);
}

public sealed record MoveInventoryItemCommand(Guid PlayerId, string ItemId, int TargetSlotIndex) : IRoomCommand<long>
{
    public long Execute(BattleRoom room) => room.MoveInventoryItem(PlayerId, ItemId, TargetSlotIndex);
}

public sealed record EquipInventoryItemCommand(Guid PlayerId, string ItemId) : IRoomCommand<long>
{
    public long Execute(BattleRoom room) => room.EquipInventoryItem(PlayerId, ItemId);
}

public sealed record UnequipArmorCommand(Guid PlayerId, string Slot) : IRoomCommand<long>
{
    public long Execute(BattleRoom room) => room.UnequipArmor(PlayerId, Slot);
}

public sealed record GetRelicPilesCommand(Guid PlayerId) : IRoomCommand<IReadOnlyList<RelicPileSnapshot>>
{
    public bool NotifyObservers => false;
    public IReadOnlyList<RelicPileSnapshot> Execute(BattleRoom room) => room.GetAvailableRelicPiles(PlayerId);
}

public sealed record PlayRoomCardsCommand(
    Guid PlayerId,
    Guid BattleId,
    string TargetId,
    IReadOnlyList<Guid> CardInstanceIds,
    long ExpectedRevision,
    DateTimeOffset Now) : IRoomCommand<CombatResolution>
{
    public CombatResolution Execute(BattleRoom room) =>
        room.PlayCards(PlayerId, BattleId, TargetId, CardInstanceIds, ExpectedRevision, Now);
}

public sealed record PreviewRoomCardsCommand(
    Guid PlayerId,
    Guid BattleId,
    string TargetId,
    IReadOnlyList<Guid> CardInstanceIds,
    long ExpectedRevision,
    DateTimeOffset Now) : IRoomCommand<CombatResolution>
{
    public bool NotifyObservers => false;
    public CombatResolution Execute(BattleRoom room) =>
        room.PreviewCards(PlayerId, BattleId, TargetId, CardInstanceIds, ExpectedRevision, Now);
}

public sealed record GetCombatInfoCommand(Guid PlayerId) : IRoomCommand<RoomCombatInfo>
{
    public bool NotifyObservers => false;
    public RoomCombatInfo Execute(BattleRoom room) => room.GetCombatInfo(PlayerId);
}

public sealed record SelectPveTargetCommand(
    Guid PlayerId,
    Guid BattleId,
    string TargetId,
    long ExpectedRevision) : IRoomCommand<SelectPveTargetResult>
{
    public SelectPveTargetResult Execute(BattleRoom room) =>
        new(BattleId, TargetId, room.SelectPveTarget(PlayerId, BattleId, TargetId, ExpectedRevision));
}

public sealed record SelectPveTargetResult(Guid BattleId, string TargetId, long RoomRevision);

public sealed record AbandonBattleCommand(Guid PlayerId) : IRoomCommand<BattleRoomSnapshot>
{
    public BattleRoomSnapshot Execute(BattleRoom room)
    {
        room.AbandonBattle(PlayerId);
        return room.Capture();
    }
}

public sealed record MoveRoomPlayerResult(MapPosition Position, DuelStateSnapshot? StartedDuel, long RoomRevision);

public sealed record MoveRoomPlayerCommand(Guid PlayerId, MapPosition Target, long ExpectedRevision, DateTimeOffset Now) : IRoomCommand<MoveRoomPlayerResult>
{
    public MoveRoomPlayerResult Execute(BattleRoom room)
    {
        var result = room.MovePlayerAndPair(PlayerId, Target, ExpectedRevision, Now);
        return new(result.Position, result.StartedDuel, result.RoomRevision);
    }
}

public sealed record ChooseMonsterCardCommand(Guid PlayerId, Guid CandidateId, bool Accept, Guid? ReplaceId,
    string RequestId, long ExpectedRevision) : IRoomCommand<long>
{
    public long Execute(BattleRoom room) => room.DecideMonsterCard(PlayerId, CandidateId, Accept, ReplaceId, RequestId, ExpectedRevision);
}
