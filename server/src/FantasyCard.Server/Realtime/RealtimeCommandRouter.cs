using System.Collections.Concurrent;
using System.Security.Cryptography;
using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;
using FantasyCard.Server.Progression;
using FantasyCard.Server.Common;
using FantasyCard.Server.Matchmaking;

namespace FantasyCard.Server.Realtime;

public sealed partial class RealtimeCommandRouter
{
    private readonly RealtimeEventStore _eventStore;
    private readonly TimeProvider _timeProvider;
    private readonly RoomRegistry? _roomRegistry;
    private readonly EconomyRepository? _economyRepository;
    private readonly ServerMetrics? _metrics;
    private readonly IRoomReadyService? _roomReadyService;
    private readonly RoomSnapshotRepository? _roomSnapshotRepository;
    private readonly ILogger<RealtimeCommandRouter>? _logger;
    private readonly RealtimeRequestStore _requestStore = new();

    public RealtimeCommandRouter(
        RealtimeEventStore eventStore,
        TimeProvider timeProvider,
        RoomRegistry? roomRegistry = null,
        EconomyRepository? economyRepository = null,
        ServerMetrics? metrics = null,
        IRoomReadyService? roomReadyService = null,
        RoomSnapshotRepository? roomSnapshotRepository = null,
        ILogger<RealtimeCommandRouter>? logger = null)
    {
        _eventStore = eventStore;
        _timeProvider = timeProvider;
        _roomRegistry = roomRegistry;
        _economyRepository = economyRepository;
        _metrics = metrics;
        _roomReadyService = roomReadyService;
        _roomSnapshotRepository = roomSnapshotRepository;
        _logger = logger;
    }

    public IReadOnlyList<ServerEvent> Route(
        PlayerProfile player,
        ClientCommand command,
        string traceId)
    {
        if (TryRouteCommon(player, command, traceId, out var common))
        {
            return common;
        }
        return
        [
            Reject(
                player.UserId,
                traceId,
                command.RequestId,
                "UNSUPPORTED_COMMAND",
                $"Command '{command.Type}' is not implemented in this server milestone.")
        ];
    }

    public async ValueTask<IReadOnlyList<ServerEvent>> RouteAsync(
        PlayerProfile player,
        ClientCommand command,
        string traceId,
        CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(command.RequestId))
            return await RouteCoreAsync(player, command, traceId, cancellationToken);

        var fingerprint = Convert.ToHexString(
            SHA256.HashData(RealtimeProtobufCodec.EncodeClient(command)));
        var once = await _requestStore.ExecuteAsync(
            player.UserId,
            command.RequestId,
            fingerprint,
            () => RouteCoreAsync(player, command, traceId, cancellationToken));
        if (once.FingerprintMismatch)
        {
            return
            [
                Reject(
                    player.UserId,
                    traceId,
                    command.RequestId,
                    "REQUEST_ID_REUSED",
                    "requestId was already used for a different command.")
            ];
        }
        return once.Events!;
    }

    private async ValueTask<IReadOnlyList<ServerEvent>> RouteCoreAsync(
        PlayerProfile player,
        ClientCommand command,
        string traceId,
        CancellationToken cancellationToken)
    {
        if (string.Equals(command.Type, "session.resume", StringComparison.Ordinal))
        {
            _metrics?.RealtimeResumed();
            var resumed = Resume(player, command, traceId);
            if (_roomRegistry is null ||
                !_roomRegistry.TryGetForPlayer(player.UserId, out var resumeActor, out var resumeMatchId) ||
                resumeActor is null)
                return resumed;
            var state = await resumeActor.ExecuteAsync(new GetRoomClientStateCommand(player.UserId), cancellationToken);
            var resumePayload = command.Payload as SessionResumeCommandPayload;
            var needsRoomSnapshot = resumed.Any(message => message.Type == "session.snapshot") ||
                resumePayload?.RoomId != state.Snapshot.RoomId ||
                resumePayload.RoomRevision != state.Snapshot.Revision;
            if (!needsRoomSnapshot) return resumed;
            return [.. resumed, CreateRoomSnapshot(player.UserId, traceId, command.RequestId, state, resumeMatchId)];
        }
        if (TryRouteCommon(player, command, traceId, out var common))
        {
            return common;
        }
        if (string.Equals(command.Type, "room.ready", StringComparison.Ordinal))
        {
            if (command.Payload is not RoomReadyCommandPayload)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "room.ready payload is required.")];
            if (_roomReadyService is null)
                return [Reject(player.UserId, traceId, command.RequestId, "READY_UNAVAILABLE", "The ready service is unavailable.")];
            try
            {
                var ready = await _roomReadyService.ReadyAsync(player.UserId, cancellationToken);
                return [_eventStore.Create(player.UserId, "room.ready_accepted", traceId,
                    new RoomReadyAcceptedEventPayload(ready.MatchId, ready.RoomId,
                        ready.ReadyDeadline.ToUnixTimeMilliseconds(), ready.ReadyPlayers, ready.RequiredPlayers),
                    command.RequestId)];
            }
            catch (MatchReadyException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, exception.Code, exception.Message)];
            }
        }
        if (string.Equals(command.Type, "room.snapshot.read", StringComparison.Ordinal))
        {
            if (command.Payload is not RoomSnapshotCommandPayload)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "room.snapshot.read payload is required.")];
            if (_roomRegistry is null ||
                !_roomRegistry.TryGetForPlayer(player.UserId, out var snapshotActor, out var snapshotMatchId) ||
                snapshotActor is null)
                return [Reject(player.UserId, traceId, command.RequestId, "NOT_IN_ROOM", "The player is not assigned to an active room.")];
            var state = await snapshotActor.ExecuteAsync(new GetRoomClientStateCommand(player.UserId), cancellationToken);
            return [CreateRoomSnapshot(player.UserId, traceId, command.RequestId, state, snapshotMatchId)];
        }
        if (!string.Equals(command.Type, "battle.play_cards", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "combat.preview", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "battle.select_target", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "room.move", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "map.move", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "duel.leave", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "duel.escape", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "action.extract", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "action.spring", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "action.use_spring", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "action.potion", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "relic.take", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "relic.replace", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "relic.read", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "inventory.move", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "inventory.equip", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "inventory.unequip", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "reward.choice.read", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "choice.read", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "reward.choice.refresh", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "choice.refresh", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "reward.choice.claim", StringComparison.Ordinal) &&
            !string.Equals(command.Type, "choice.pick", StringComparison.Ordinal))
        {
            return
            [
                Reject(
                    player.UserId,
                    traceId,
                    command.RequestId,
                    "UNSUPPORTED_COMMAND",
                    $"Command '{command.Type}' is not implemented in this server milestone.")
            ];
        }
        var isReadCommand = IsReadCommand(command.Type);
        if (!isReadCommand && command.ExpectedRevision is null)
        {
            return
            [
                Reject(
                    player.UserId,
                    traceId,
                    command.RequestId,
                    "EXPECTED_REVISION_REQUIRED",
                    "State-changing room commands require expectedRevision.")
            ];
        }
        if (_roomRegistry is null ||
            !_roomRegistry.TryGetForPlayer(player.UserId, out var actor, out var currentMatchId) ||
            actor is null)
        {
            return
            [
                Reject(
                    player.UserId,
                    traceId,
                    command.RequestId,
                    "NOT_IN_ROOM",
                    "The player is not assigned to an active room.")
            ];
        }
        var expectedRevision = command.ExpectedRevision ?? 0;

        if (command.Type == "relic.read")
        {
            if (command.Payload is not RelicReadCommandPayload read || read.PileId == Guid.Empty)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "pileId is required.")];
            try
            {
                var piles = await actor.ExecuteAsync(new GetRelicPilesCommand(player.UserId), cancellationToken);
                var pile = piles.SingleOrDefault(value => value.PileId == read.PileId)
                    ?? throw new DomainValidationException("This relic pile is not available in the current cell.");
                var state = await actor.ExecuteAsync(new GetRoomClientStateCommand(player.UserId), cancellationToken);
                var name = pile.VictimName ?? state.Snapshot.Players.FirstOrDefault(value => value.PlayerId.ToString("D") == pile.VictimId)?.DisplayName ?? "旅人";
                return [_eventStore.Create(player.UserId, "relic.contents", traceId,
                    new RoomRelicPilePayload(pile.PileId, name, pile.Version, pile.Items.Select(RoomSnapshotProjection.ToInventoryItem).ToArray()),
                    command.RequestId, state.Snapshot.Revision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (command.Type is "inventory.move" or "inventory.equip" or "inventory.unequip")
        {
            try
            {
                var revision = command.Payload switch
                {
                    InventoryMoveCommandPayload move when command.Type == "inventory.move" &&
                        !string.IsNullOrWhiteSpace(move.ItemId) && move.TargetSlotIndex is >= 0 and < 36 =>
                        await actor.ExecuteAsync(new MoveInventoryItemCommand(player.UserId, move.ItemId, move.TargetSlotIndex), expectedRevision, cancellationToken),
                    InventoryEquipCommandPayload equip when command.Type == "inventory.equip" && !string.IsNullOrWhiteSpace(equip.ItemId) =>
                        await actor.ExecuteAsync(new EquipInventoryItemCommand(player.UserId, equip.ItemId), expectedRevision, cancellationToken),
                    InventoryUnequipCommandPayload unequip when command.Type == "inventory.unequip" && !string.IsNullOrWhiteSpace(unequip.Slot) =>
                        await actor.ExecuteAsync(new UnequipArmorCommand(player.UserId, unequip.Slot), expectedRevision, cancellationToken),
                    _ => throw new DomainValidationException("A valid inventory item and destination are required.")
                };
                var itemId = command.Payload switch
                {
                    InventoryMoveCommandPayload move => move.ItemId,
                    InventoryEquipCommandPayload equip => equip.ItemId,
                    InventoryUnequipCommandPayload unequip => unequip.Slot,
                    _ => ""
                };
                var state = await actor.ExecuteAsync(new GetRoomClientStateCommand(player.UserId), cancellationToken);
                return
                [
                    _eventStore.Create(player.UserId, "inventory.changed", traceId,
                        new InventoryChangedEventPayload(command.Type, itemId), command.RequestId, revision),
                    CreateRoomSnapshot(player.UserId, traceId, command.RequestId, state, currentMatchId)
                ];
            }
            catch (Exception exception) when (exception is DomainValidationException or InvalidOperationException or ArgumentException)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "battle.select_target", StringComparison.Ordinal))
        {
            if (command.Payload is not BattleSelectTargetCommandPayload target || target.BattleId == Guid.Empty ||
                string.IsNullOrWhiteSpace(target.TargetId))
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "battleId and targetId are required.")];
            try
            {
                var selected = await actor.ExecuteAsync(new SelectPveTargetCommand(
                    player.UserId, target.BattleId, target.TargetId, expectedRevision), cancellationToken);
                return [_eventStore.Create(player.UserId, "battle.target_selected", traceId,
                    new BattleTargetSelectedEventPayload(selected.BattleId, selected.TargetId),
                    command.RequestId, selected.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (command.Type is "reward.choice.read" or "choice.read")
        {
            try
            {
                var choice = await actor.ExecuteAsync(new GetRewardChoiceCommand(player.UserId), cancellationToken);
                return [_eventStore.Create(player.UserId, "reward.choice", traceId,
                    new RewardChoiceEventPayload((int)choice.Layer, choice.Options.Select(ToPayload).ToArray(), choice.RefreshCount, choice.IsBoss), command.RequestId, roomRevision: null)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (command.Type is "reward.choice.refresh" or "choice.refresh")
        {
            if (command.Payload is not RewardChoiceRefreshCommandPayload)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "reward.choice.refresh payload is required.")];
            try
            {
                var roomSnapshot = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
                var playerSnapshot = roomSnapshot.Players.Single(playerSnapshot => playerSnapshot.PlayerId == player.UserId);
                var receipt = playerSnapshot.RewardRefreshReceipts?
                    .SingleOrDefault(value => value.RequestId == command.RequestId);
                var persisted = _economyRepository is null
                    ? null
                    : await _economyRepository.GetRewardRefreshAsync(
                        player.UserId, command.RequestId!, cancellationToken);
                var accountRequired = 0L;
                if (persisted is not null)
                {
                    if (persisted.MatchId != currentMatchId || persisted.RoomId != roomSnapshot.RoomId ||
                        persisted.ExpectedRevision != expectedRevision)
                        throw new IdempotencyConflictException();
                    if (persisted.State == "Refunded")
                        throw new DomainValidationException("This reward refresh request was previously rolled back.");
                    accountRequired = persisted.AccountGold;
                    if (persisted.State == "Applied")
                        receipt ??= persisted.Receipt ?? throw new InvalidOperationException("Applied reward refresh is missing its persisted response.");
                }
                else if (receipt is null)
                {
                    var choice = playerSnapshot.RewardChoice ?? throw new DomainValidationException("The player has no pending reward choice.");
                    var cost = GameConfigCatalog.Current.RewardRefreshGold(choice.RefreshCount + 1);
                    var temporaryGold = playerSnapshot.Inventory?.Items
                        .Where(item => item.Kind == ExplorationItemKind.Gold).Sum(item => item.Quantity) ?? 0;
                    accountRequired = Math.Max(0, cost - temporaryGold);
                    if (accountRequired > 0)
                    {
                        if (_economyRepository is null)
                            throw new DomainValidationException($"Insufficient exploration gold; account gold required: {accountRequired}.");
                        if (currentMatchId is null || _roomSnapshotRepository is null)
                            throw new DomainValidationException("Account gold refresh persistence is unavailable for this room.");
                        var reservation = await _economyRepository.ReserveRewardRefreshAsync(
                            player.UserId, currentMatchId.Value, roomSnapshot.RoomId, expectedRevision,
                            accountRequired, command.RequestId!, cancellationToken);
                        if (reservation.State == "Refunded")
                            throw new DomainValidationException("This reward refresh request was previously rolled back.");
                        if (reservation.State == "Applied")
                            receipt = reservation.Receipt ?? throw new InvalidOperationException("Applied reward refresh is missing its persisted response.");
                    }
                }
                try
                {
                    receipt ??= await actor.ExecuteAsync(new RefreshRewardChoiceCommand(
                        player.UserId, expectedRevision, accountRequired, command.RequestId), cancellationToken);
                    if (accountRequired > 0)
                    {
                        try
                        {
                            var durableSnapshot = await actor.ExecuteAsync(new GetRoomSnapshotCommand(), cancellationToken);
                            await _roomSnapshotRepository!.SaveIfDueAsync(durableSnapshot, cancellationToken);
                            await _economyRepository!.MarkRewardRefreshAppliedAsync(
                                player.UserId, command.RequestId!, receipt, cancellationToken);
                        }
                        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
                        {
                            throw;
                        }
                        catch (Exception exception)
                        {
                            if (_logger is not null)
                                RewardRefreshAwaitsReconciliation(
                                    _logger, command.RequestId!, roomSnapshot.RoomId, exception);
                        }
                    }
                    return [_eventStore.Create(player.UserId, "reward.choice", traceId,
                        new RewardChoiceEventPayload((int)receipt.Choice.Layer, receipt.Choice.Options.Select(ToPayload).ToArray(), receipt.Choice.RefreshCount, receipt.Choice.IsBoss), command.RequestId, receipt.RoomRevision)];
                }
                catch
                {
                    if (accountRequired > 0 && receipt is null)
                        await _economyRepository!.RefundReservedRewardRefreshAsync(player.UserId, command.RequestId!, cancellationToken);
                    throw;
                }
            }
            catch (IdempotencyConflictException)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "REQUEST_ID_REUSED", "requestId was already used for another reward refresh.")];
            }
            catch (InvalidOperationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (command.Type is "reward.choice.claim" or "choice.pick")
        {
            if (command.Payload is not RewardChoiceClaimCommandPayload claim || string.IsNullOrWhiteSpace(claim.OptionId))
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "optionId is required.")];
            try
            {
                var applied = await actor.ExecuteAsync(new ClaimRewardCommand(player.UserId, claim.OptionId, claim.ReplaceItemId, claim.Equip), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "reward.choice_claimed", traceId,
                    new RewardChoiceClaimedEventPayload(claim.OptionId, applied), command.RequestId, roomRevision: null)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (command.Type is "room.move" or "map.move")
        {
            if (command.Payload is not RoomMoveCommandPayload move || move.Row is < 0 or > 5 || move.Column is < 0 or > 5)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "row and column must be within the 6x6 map.")];
            try
            {
                var position = await actor.ExecuteAsync(new MoveRoomPlayerCommand(player.UserId, new FantasyCard.Domain.Rooms.MapPosition(move.Row, move.Column), expectedRevision, _timeProvider.GetUtcNow()), cancellationToken);
                var events = new List<ServerEvent>
                {
                    _eventStore.Create(player.UserId, "room.moved", traceId, new RoomMovedEventPayload(player.UserId, position.Position.Row, position.Position.Column), command.RequestId, position.RoomRevision)
                };
                if (position.StartedDuel is not null)
                    events.Add(_eventStore.Create(player.UserId, "duel.started", traceId,
                        new DuelStartedEventPayload(position.StartedDuel.DuelId, position.StartedDuel.FirstPlayerId, position.StartedDuel.LatePlayerId,
                            position.StartedDuel.LatePlayerUnlockAt.ToUnixTimeMilliseconds(), position.StartedDuel.LeaveWindowEndsAt.ToUnixTimeMilliseconds()), roomRevision: position.RoomRevision));
                return events;
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "duel.leave", StringComparison.Ordinal))
        {
            if (command.Payload is not DuelLeaveCommandPayload leave || leave.DuelId == Guid.Empty)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "duelId is required.")];
            try
            {
                var result = await actor.ExecuteAsync(new RequestDuelLeaveCommand(player.UserId, leave.DuelId, _timeProvider.GetUtcNow()), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "duel.leave_ack", traceId, new DuelLeaveEventPayload(result.DuelId, result.Completed), command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "duel.escape", StringComparison.Ordinal))
        {
            if (command.Payload is not DuelEscapeCommandPayload escape || escape.DuelId == Guid.Empty)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "duelId is required.")];
            try
            {
                var result = await actor.ExecuteAsync(new RequestDuelEscapeCommand(player.UserId, escape.DuelId), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "duel.escape_started", traceId, new DuelEscapeEventPayload(result.DuelId, result.Probability, "Started"), command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "action.extract", StringComparison.Ordinal))
        {
            if (command.Payload is not ActionExtractCommandPayload)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "action.extract payload is required.")];
            try
            {
                var result = await actor.ExecuteAsync(new RequestRoomExtractionCommand(player.UserId), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "action.extract_started", traceId,
                    new ActionExtractEventPayload("Started", result.Remaining), command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (command.Type is "action.spring" or "action.use_spring")
        {
            if (command.Payload is not ActionSpringCommandPayload)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "action.spring payload is required.")];
            try
            {
                var result = await actor.ExecuteAsync(new RequestRoomSpringCommand(player.UserId), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "action.spring_started", traceId,
                    new ActionSpringEventPayload("Started", result.Remaining), command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "action.potion", StringComparison.Ordinal))
        {
            if (command.Payload is not ActionPotionCommandPayload)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "action.potion payload is required.")];
            try
            {
                var result = await actor.ExecuteAsync(new UseRoomPotionCommand(player.UserId), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "action.potion_used", traceId,
                    new ActionPotionEventPayload(result.ItemId, result.Healed), command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "relic.take", StringComparison.Ordinal))
        {
            if (command.Payload is not RelicTakeCommandPayload take || take.PileId == Guid.Empty ||
                string.IsNullOrWhiteSpace(take.ItemId) || take.PileVersion < 1)
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "pileId, itemId, and pileVersion are required.")];
            try
            {
                var result = await actor.ExecuteAsync(new TakeRelicItemCommand(player.UserId, take.PileId, take.ItemId, take.PileVersion, take.ReplaceItemId), expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "relic.taken", traceId,
                    new RelicTakeEventPayload(result.PileId, result.ItemId, result.PileVersion), command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
            catch (InvalidOperationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "STALE_RELIC", exception.Message)];
            }
        }

        if (string.Equals(command.Type, "relic.replace", StringComparison.Ordinal))
        {
            if (command.Payload is not RelicReplaceCommandPayload replace || replace.PileId == Guid.Empty ||
                string.IsNullOrWhiteSpace(replace.ItemId) || replace.PileVersion < 1 ||
                string.IsNullOrWhiteSpace(replace.ReplaceItemId))
                return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "pileId, itemId, pileVersion, and replaceItemId are required.")];
            try
            {
                var result = await actor.ExecuteAsync(new ReplaceRelicItemCommand(
                    player.UserId, replace.PileId, replace.ItemId, replace.PileVersion, replace.ReplaceItemId),
                    expectedRevision, cancellationToken);
                return [_eventStore.Create(player.UserId, "relic.replaced", traceId,
                    new RelicReplacedEventPayload(result.PileId, result.ItemId, result.ReturnedItemId, result.PileVersion),
                    command.RequestId, result.RoomRevision)];
            }
            catch (DomainValidationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "COMMAND_REJECTED", exception.Message)];
            }
            catch (InvalidOperationException exception)
            {
                return [Reject(player.UserId, traceId, command.RequestId, "STALE_RELIC", exception.Message)];
            }
        }

        if (command.Payload is not BattlePlayCardsCommandPayload payload ||
            payload.BattleId == Guid.Empty ||
            string.IsNullOrWhiteSpace(payload.TargetId) ||
            payload.CardInstanceIds.Count is < 1 or > 5 ||
            payload.CardInstanceIds.Distinct().Count() != payload.CardInstanceIds.Count)
        {
            return
            [
                Reject(
                    player.UserId,
                    traceId,
                    command.RequestId,
                    "INVALID_PAYLOAD",
                    "battleId, targetId, and 1-5 distinct cardInstanceIds are required.")
            ];
        }

        try
        {
            var preview = command.Type == "combat.preview";
            var resolution = preview
                ? await actor.ExecuteAsync(new PreviewRoomCardsCommand(player.UserId, payload.BattleId,
                    payload.TargetId, payload.CardInstanceIds, expectedRevision, _timeProvider.GetUtcNow()), cancellationToken)
                : await actor.ExecuteAsync(new PlayRoomCardsCommand(
                    player.UserId,
                    payload.BattleId,
                    payload.TargetId,
                    payload.CardInstanceIds,
                    expectedRevision,
                    _timeProvider.GetUtcNow()),
                cancellationToken);
            return
            [
                _eventStore.Create(
                    player.UserId,
                    preview ? "combat.previewed" : "battle.combo_resolved",
                    traceId,
                    new BattleComboResolvedEventPayload(
                        resolution.BattleId,
                        resolution.AttackerId,
                        resolution.TargetId,
                        resolution.Damage,
                        resolution.ShieldDamage,
                        resolution.HpDamage,
                        resolution.Heal,
                        resolution.ShieldGain,
                        resolution.TargetDefeated,
                        resolution.BattleEnded,
                        resolution.DamageSegments?.Select(segment => new CombatDamageSegmentPayload(segment.Kind, segment.Amount)).ToArray(),
                        resolution.CoreElement?.ToString(), resolution.CoreCount,
                        resolution.StunSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.DrawBlockSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.HealthCost, resolution.DrawCharge.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.ImmediateDraw, payload.CardInstanceIds, resolution.AttackerId.ToString("D"),
                        resolution.DrawSpeedSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.DrawSpeedModifier.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.DrawBlockSpeedSeconds.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.ResonanceMultiplier.ToString("R", System.Globalization.CultureInfo.InvariantCulture),
                        resolution.ConflictPairCount,
                        resolution.ConflictCancellation.ToString("R", System.Globalization.CultureInfo.InvariantCulture)),
                    command.RequestId,
                    resolution.RoomRevision)
            ];
        }
        catch (DomainValidationException exception)
        {
            return
            [
                Reject(
                    player.UserId,
                    traceId,
                    command.RequestId,
                    "COMMAND_REJECTED",
                    exception.Message)
            ];
        }
    }

    private bool TryRouteCommon(
        PlayerProfile player,
        ClientCommand command,
        string traceId,
        out IReadOnlyList<ServerEvent> result)
    {
        if (string.IsNullOrWhiteSpace(command.Type) || command.Type.Length > 80)
        {
            result = [Reject(player.UserId, traceId, command.RequestId, "INVALID_COMMAND", "Command type is required.")];
            return true;
        }
        if (command.RequestId is { Length: > 80 })
        {
            result = [Reject(player.UserId, traceId, null, "INVALID_REQUEST_ID", "requestId cannot exceed 80 characters.")];
            return true;
        }
        if (string.Equals(command.Type, "ping", StringComparison.Ordinal))
        {
            result =
            [
                _eventStore.Create(
                    player.UserId,
                    "pong",
                    traceId,
                    new PongEventPayload(_timeProvider.GetUtcNow()),
                    command.RequestId)
            ];
            return true;
        }
        if (string.Equals(command.Type, "session.resume", StringComparison.Ordinal))
        {
            result = Resume(player, command, traceId);
            return true;
        }
        if (string.IsNullOrWhiteSpace(command.RequestId) && !IsReadCommand(command.Type))
        {
            result =
            [
                Reject(
                    player.UserId,
                    traceId,
                    null,
                    "REQUEST_ID_REQUIRED",
                    "State-changing commands require a unique requestId.")
            ];
            return true;
        }
        result = [];
        return false;
    }

    private static bool IsReadCommand(string type) =>
        type is "room.snapshot.read" or "reward.choice.read" or "choice.read" or "relic.read";

    private IReadOnlyList<ServerEvent> Resume(
        PlayerProfile player,
        ClientCommand command,
        string traceId)
    {
        long lastSequence;
        try
        {
            lastSequence = (command.Payload as SessionResumeCommandPayload)?.LastSequence
                ?? throw new InvalidOperationException();
        }
        catch (Exception exception) when (exception is InvalidOperationException or KeyNotFoundException)
        {
            return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "lastSequence is required.")];
        }
        if (lastSequence < 0)
        {
            return [Reject(player.UserId, traceId, command.RequestId, "INVALID_PAYLOAD", "lastSequence cannot be negative.")];
        }

        var replay = _eventStore.ReadAfter(player.UserId, lastSequence);
        if (!replay.HasGap)
        {
            return replay.Events;
        }
        return
        [
            _eventStore.Create(
                player.UserId,
                "session.snapshot",
                traceId,
                new SessionSnapshotEventPayload(
                    player.UserId,
                    player.Version,
                    player.SelectedClass?.ToString(),
                    "event_buffer_gap",
                    replay.LastSequence),
                command.RequestId)
        ];
    }

    private static RewardChoiceOptionPayload ToPayload(FantasyCard.Domain.Rooms.RewardChoiceOption option) =>
        new(option.OptionId, (RewardChoiceKindDto)option.Kind, option.Item?.ItemId, option.Item?.Quantity ?? 0, option.HealPercent,
            RoomSnapshotProjection.ToEquipment(option.Item?.Equipment));

    private ServerEvent CreateRoomSnapshot(
        Guid playerId,
        string traceId,
        string? requestId,
        RoomClientState state,
        Guid? matchId) =>
        _eventStore.Create(
            playerId,
            "room.snapshot",
            traceId,
            RoomSnapshotProjection.Build(state, playerId, matchId, _timeProvider.GetUtcNow()),
            requestId,
            state.Snapshot.Revision);

    private ServerEvent Reject(
        Guid playerId,
        string traceId,
        string? requestId,
        string code,
        string detail)
    {
        _metrics?.RealtimeCommandRejected(code);
        return _eventStore.Create(
            playerId,
            "error.command_rejected",
            traceId,
            new CommandRejectedEventPayload(code, detail),
            requestId);
    }

    [LoggerMessage(EventId = 5101, Level = LogLevel.Error,
        Message = "Reward refresh {RequestId} applied in room {RoomId} but awaits durable reconciliation.")]
    private static partial void RewardRefreshAwaitsReconciliation(
        ILogger logger, string requestId, Guid roomId, Exception exception);

    private sealed class RealtimeRequestStore
    {
        private const int MaximumCompletedRequests = 256;
        private readonly ConcurrentDictionary<Guid, PlayerRequests> _players = new();

        public async ValueTask<RequestResult> ExecuteAsync(
            Guid playerId,
            string requestId,
            string fingerprint,
            Func<ValueTask<IReadOnlyList<ServerEvent>>> execute)
        {
            var requests = _players.GetOrAdd(playerId, static _ => new PlayerRequests());
            RequestExecution execution;
            var ownsExecution = false;
            lock (requests.Gate)
            {
                if (requests.Entries.TryGetValue(requestId, out execution!))
                {
                    if (!string.Equals(execution.Fingerprint, fingerprint, StringComparison.Ordinal))
                        return new(true, null);
                }
                else
                {
                    execution = new RequestExecution(fingerprint);
                    requests.Entries.Add(requestId, execution);
                    ownsExecution = true;
                }
            }

            if (!ownsExecution)
                return new(false, await execution.Completion.Task);

            try
            {
                var events = await execute();
                execution.Completion.SetResult(events);
                lock (requests.Gate)
                {
                    requests.CompletedOrder.Enqueue((requestId, execution));
                    while (requests.CompletedOrder.Count > MaximumCompletedRequests)
                    {
                        var expired = requests.CompletedOrder.Dequeue();
                        if (requests.Entries.TryGetValue(expired.RequestId, out var current) &&
                            ReferenceEquals(current, expired.Execution))
                            requests.Entries.Remove(expired.RequestId);
                    }
                }
                return new(false, events);
            }
            catch (Exception exception)
            {
                lock (requests.Gate)
                {
                    if (requests.Entries.TryGetValue(requestId, out var current) &&
                        ReferenceEquals(current, execution))
                        requests.Entries.Remove(requestId);
                }
                execution.Completion.SetException(exception);
                throw;
            }
        }

        public sealed record RequestResult(bool FingerprintMismatch, IReadOnlyList<ServerEvent>? Events);

        private sealed class PlayerRequests
        {
            public object Gate { get; } = new();
            public Dictionary<string, RequestExecution> Entries { get; } = new(StringComparer.Ordinal);
            public Queue<(string RequestId, RequestExecution Execution)> CompletedOrder { get; } = new();
        }

        private sealed class RequestExecution(string fingerprint)
        {
            public string Fingerprint { get; } = fingerprint;
            public TaskCompletionSource<IReadOnlyList<ServerEvent>> Completion { get; } =
                new(TaskCreationOptions.RunContinuationsAsynchronously);
        }
    }
}
