using System.Text;
using FantasyCard.Contracts.Progression;

namespace FantasyCard.Contracts.Realtime;

public static class RealtimeProtobufCodec
{
    public const uint ProtocolVersion = 1;

    public static byte[] EncodeClient(ClientCommand command)
    {
        ArgumentNullException.ThrowIfNull(command);
        var writer = new ProtoWriter();
        writer.UInt32(1, ProtocolVersion);
        writer.String(2, command.Type);
        writer.String(3, command.RequestId);
        writer.OptionalInt64(4, command.ExpectedRevision);
        writer.Bytes(5, command.Type switch
        {
            "ping" when command.Payload is null => null,
            "session.resume" when command.Payload is SessionResumeCommandPayload payload => Message(w =>
            {
                w.Int64(1, payload.LastSequence);
                w.String(2, payload.RoomId?.ToString("D"));
                w.OptionalInt64(3, payload.RoomRevision);
            }),
            "room.ready" when command.Payload is RoomReadyCommandPayload => Message(_ => { }),
            "room.snapshot.read" when command.Payload is RoomSnapshotCommandPayload => Message(_ => { }),
            "battle.play_cards" or "combat.preview" when command.Payload is BattlePlayCardsCommandPayload payload => Message(w =>
            {
                w.String(1, payload.BattleId.ToString("D"));
                w.String(2, payload.TargetId);
                foreach (var cardInstanceId in payload.CardInstanceIds)
                {
                    w.String(3, cardInstanceId.ToString("D"));
                }
            }),
            "battle.select_target" when command.Payload is BattleSelectTargetCommandPayload payload => Message(w =>
            {
                w.String(1, payload.BattleId.ToString("D"));
                w.String(2, payload.TargetId);
            }),
            "battle.abandon" when command.Payload is BattleAbandonCommandPayload => Message(_ => { }),
            "reward.choice.refresh" or "choice.refresh" when command.Payload is RewardChoiceRefreshCommandPayload => Message(_ => { }),
            "reward.choice.claim" or "choice.pick" when command.Payload is RewardChoiceClaimCommandPayload payload => Message(w => { w.String(1, payload.OptionId); w.String(2, payload.ReplaceItemId); w.Bool(3, payload.Equip); }),
            "inventory.move" when command.Payload is InventoryMoveCommandPayload payload => Message(w => { w.String(1, payload.ItemId); w.Int64(2, payload.TargetSlotIndex); }),
            "inventory.equip" when command.Payload is InventoryEquipCommandPayload payload => Message(w => w.String(1, payload.ItemId)),
            "inventory.unequip" when command.Payload is InventoryUnequipCommandPayload payload => Message(w => w.String(1, payload.Slot)),
            "room.move" or "map.move" when command.Payload is RoomMoveCommandPayload payload => Message(w => { w.Int64(1, payload.Row); w.Int64(2, payload.Column); }),
            "duel.leave" when command.Payload is DuelLeaveCommandPayload payload => Message(w => w.String(1, payload.DuelId.ToString("D"))),
            "duel.escape" when command.Payload is DuelEscapeCommandPayload payload => Message(w => w.String(1, payload.DuelId.ToString("D"))),
            "action.extract" when command.Payload is ActionExtractCommandPayload => Message(_ => { }),
            "action.spring" or "action.use_spring" when command.Payload is ActionSpringCommandPayload => Message(_ => { }),
            "action.potion" when command.Payload is ActionPotionCommandPayload => Message(_ => { }),
            "relic.take" when command.Payload is RelicTakeCommandPayload payload => Message(w => { w.String(1, payload.PileId.ToString("D")); w.String(2, payload.ItemId); w.Int64(3, payload.PileVersion); w.String(4, payload.ReplaceItemId); }),
            "relic.read" when command.Payload is RelicReadCommandPayload payload => Message(w => w.String(1, payload.PileId.ToString("D"))),
            "relic.replace" when command.Payload is RelicReplaceCommandPayload payload => Message(w => { w.String(1, payload.PileId.ToString("D")); w.String(2, payload.ItemId); w.Int64(3, payload.PileVersion); w.String(4, payload.ReplaceItemId); }),
            _ when command.Payload is null => null,
            _ => throw new InvalidDataException($"No protobuf payload schema is registered for command '{command.Type}'.")
        });
        return writer.ToArray();
    }

    public static ClientCommand DecodeClient(ReadOnlySpan<byte> bytes)
    {
        var envelope = Fields.Read(bytes);
        ValidateVersion(envelope.UInt32(1));
        var type = envelope.String(2);
        if (string.IsNullOrWhiteSpace(type)) throw new InvalidDataException("Protobuf command type is required.");
        var payloadBytes = envelope.Bytes(5);
        object? payload = type switch
        {
            "ping" => null,
            "session.resume" => DecodeSessionResume(payloadBytes),
            "room.ready" => new RoomReadyCommandPayload(),
            "room.snapshot.read" => new RoomSnapshotCommandPayload(),
            "battle.play_cards" or "combat.preview" => DecodeBattlePlayCards(payloadBytes),
            "battle.select_target" => DecodeBattleSelectTarget(payloadBytes),
            "battle.abandon" => new BattleAbandonCommandPayload(),
            "reward.choice.refresh" or "choice.refresh" => new RewardChoiceRefreshCommandPayload(),
            "reward.choice.claim" or "choice.pick" => DecodeRewardClaim(payloadBytes),
            "room.move" or "map.move" => DecodeRoomMove(payloadBytes),
            "duel.leave" => new DuelLeaveCommandPayload(ParseGuid(Fields.Read(payloadBytes).String(1), type)),
            "duel.escape" => new DuelEscapeCommandPayload(ParseGuid(Fields.Read(payloadBytes).String(1), type)),
            "action.extract" => new ActionExtractCommandPayload(),
            "action.spring" or "action.use_spring" => new ActionSpringCommandPayload(),
            "action.potion" => new ActionPotionCommandPayload(),
            "relic.take" => DecodeRelicTake(payloadBytes),
            "relic.read" => new RelicReadCommandPayload(ParseGuid(Fields.Read(payloadBytes).String(1), type)),
            "relic.replace" => DecodeRelicReplace(payloadBytes),
            "inventory.move" => DecodeInventoryMove(payloadBytes),
            "inventory.equip" => new InventoryEquipCommandPayload(Fields.Read(payloadBytes).String(1)),
            "inventory.unequip" => new InventoryUnequipCommandPayload(Fields.Read(payloadBytes).String(1)),
            _ when payloadBytes.Length == 0 => null,
            _ => throw new InvalidDataException($"No protobuf payload schema is registered for command '{type}'.")
        };
        return new ClientCommand(type, NullIfEmpty(envelope.String(3)), envelope.OptionalInt64(4), payload);
    }

    public static byte[] EncodeServer(ServerEvent message)
    {
        ArgumentNullException.ThrowIfNull(message);
        var writer = new ProtoWriter();
        writer.UInt32(1, ProtocolVersion);
        writer.String(2, message.Type);
        writer.String(3, message.TraceId);
        writer.Bytes(4, EncodePayload(message));
        writer.String(5, message.EventId);
        writer.Int64(6, message.Sequence);
        writer.Int64(7, message.OccurredAt.ToUnixTimeMilliseconds());
        writer.String(8, message.RequestId);
        writer.OptionalInt64(9, message.RoomRevision);
        return writer.ToArray();
    }

    public static ServerEvent DecodeServer(ReadOnlySpan<byte> bytes)
    {
        var envelope = Fields.Read(bytes);
        ValidateVersion(envelope.UInt32(1));
        var type = envelope.String(2);
        if (string.IsNullOrWhiteSpace(type)) throw new InvalidDataException("Protobuf event type is required.");
        var payload = DecodePayload(type, envelope.Bytes(4));
        return new ServerEvent(
            type,
            envelope.String(3),
            payload,
            envelope.String(5),
            envelope.Int64(6),
            DateTimeOffset.FromUnixTimeMilliseconds(envelope.Int64(7)),
            NullIfEmpty(envelope.String(8)),
            envelope.OptionalInt64(9));
    }

    private static byte[]? EncodePayload(ServerEvent message) => message.Type switch
    {
        "session.connected" when message.Payload is SessionConnectedEventPayload value => Message(w => w.String(1, value.PlayerId.ToString("D"))),
        "session.replaced" when message.Payload is SessionReplacedEventPayload value => Message(w => w.String(1, value.Reason)),
        "pong" when message.Payload is PongEventPayload value => Message(w => w.Int64(1, value.ServerTime.ToUnixTimeMilliseconds())),
        "session.snapshot" when message.Payload is SessionSnapshotEventPayload value => Message(w =>
        {
            w.String(1, value.PlayerId.ToString("D"));
            w.Int64(2, value.PlayerVersion);
            w.String(3, value.SelectedClass);
            w.String(4, value.Reason);
            w.Int64(5, value.PreviousLastSequence);
        }),
        "match.found" when message.Payload is MatchFoundEventPayload value => Message(w =>
        {
            w.String(1, value.MatchId.ToString("D")); w.String(2, value.RoomId.ToString("D")); w.Int64(3, value.DeadlineUnixMs);
        }),
        "room.ready_required" when message.Payload is RoomReadyRequiredEventPayload value => Message(w =>
        {
            w.String(1, value.MatchId.ToString("D")); w.String(2, value.RoomId.ToString("D"));
            w.Int64(3, value.DeadlineUnixMs); w.Int64(4, value.ReadyPlayers); w.Int64(5, value.RequiredPlayers);
        }),
        "room.ready_accepted" when message.Payload is RoomReadyAcceptedEventPayload value => Message(w =>
        {
            w.String(1, value.MatchId.ToString("D")); w.String(2, value.RoomId.ToString("D"));
            w.Int64(3, value.DeadlineUnixMs); w.Int64(4, value.ReadyPlayers); w.Int64(5, value.RequiredPlayers);
        }),
        "room.ready_removed" when message.Payload is RoomReadyRemovedEventPayload value => Message(w =>
        {
            w.String(1, value.MatchId.ToString("D")); w.String(2, value.Reason);
        }),
        "room.started" when message.Payload is RoomStartedEventPayload value => Message(w =>
        {
            w.String(1, value.MatchId.ToString("D")); w.String(2, value.RoomId.ToString("D")); w.Int64(3, value.PlayerCount);
            if (value.Snapshot is not null) w.Bytes(4, EncodeRoomSnapshot(value.Snapshot));
        }),
        "settlement.ready" or "match.settled" when message.Payload is SettlementReadyEventPayload value => Message(w =>
        {
            w.String(1, value.SettlementId.ToString("D")); w.String(2, value.MatchId.ToString("D")); w.String(3, value.Result);
        }),
        "error.command_rejected" when message.Payload is CommandRejectedEventPayload value => Message(w =>
        {
            w.String(1, value.Code);
            w.String(2, value.Detail);
        }),
        "battle.combo_resolved" or "combat.previewed" or "combat.hit" when message.Payload is BattleComboResolvedEventPayload value => Message(w =>
        {
            w.String(1, value.BattleId.ToString("D"));
            w.String(2, value.AttackerId.ToString("D"));
            w.String(3, value.TargetId);
            w.Int64(4, value.Damage);
            w.Int64(5, value.ShieldDamage);
            w.Int64(6, value.HpDamage);
            w.Int64(7, value.Heal);
            w.Int64(8, value.ShieldGain);
            w.Bool(9, value.TargetDefeated);
            w.Bool(10, value.BattleEnded);
            foreach (var segment in value.DamageSegments ?? [])
                w.Bytes(11, Message(s => { s.String(1, segment.Kind); s.Int64(2, segment.Amount); }));
            w.String(12, value.CoreElement); w.Int64(13, value.CoreCount);
            w.String(14, value.StunSeconds); w.String(15, value.DrawBlockSeconds);
            w.Int64(16, value.HealthCost); w.String(17, value.DrawCharge); w.Int64(18, value.ImmediateDraw);
            foreach (var id in value.CardInstanceIds ?? []) w.String(19, id.ToString("D"));
            w.String(20, value.SourceId);
            w.String(21, value.DrawSpeedSeconds); w.String(22, value.DrawSpeedModifier); w.String(23, value.DrawBlockSpeedSeconds);
            w.String(24, value.ResonanceMultiplier); w.Int64(25, value.ConflictPairCount); w.String(26, value.ConflictCancellation);
        }),
        "battle.target_selected" when message.Payload is BattleTargetSelectedEventPayload value => Message(w =>
        {
            w.String(1, value.BattleId.ToString("D"));
            w.String(2, value.TargetId);
        }),
        "room.snapshot" when message.Payload is RoomSnapshotEventPayload value => EncodeRoomSnapshot(value),
        "map.player_count" when message.Payload is MapPlayerCountEventPayload value => Message(w => w.Int64(1, value.PlayerCount)),
        "reward.choice" when message.Payload is RewardChoiceEventPayload value => EncodeRewardChoice(value),
        "reward.choice_claimed" when message.Payload is RewardChoiceClaimedEventPayload value => Message(w => { w.String(1, value.OptionId); w.Int64(2, value.Applied); }),
        "room.moved" when message.Payload is RoomMovedEventPayload value => Message(w => { w.String(1, value.PlayerId.ToString("D")); w.Int64(2, value.Row); w.Int64(3, value.Column); }),
        "duel.leave_ack" when message.Payload is DuelLeaveEventPayload value => Message(w => { w.String(1, value.DuelId.ToString("D")); w.Bool(2, value.Completed); }),
        "duel.escape_started" or "duel.escape_interrupted" or "duel.escape_failed" when message.Payload is DuelEscapeEventPayload value => Message(w => { w.String(1, value.DuelId.ToString("D")); w.String(2, value.Probability.ToString(System.Globalization.CultureInfo.InvariantCulture)); w.String(3, value.Status); }),
        "action.extract_started" or "action.extract_cancelled" or "action.extract_completed" when message.Payload is ActionExtractEventPayload value => Message(w => { w.String(1, value.Status); w.Int64(2, (long)value.Remaining.TotalMilliseconds); }),
        "action.spring_started" or "action.spring_cancelled" or "action.spring_completed" when message.Payload is ActionSpringEventPayload value => Message(w => { w.String(1, value.Status); w.Int64(2, (long)value.Remaining.TotalMilliseconds); }),
        "action.potion_used" when message.Payload is ActionPotionEventPayload value => Message(w => { w.String(1, value.ItemId); w.Int64(2, value.Healed); }),
        "relic.taken" when message.Payload is RelicTakeEventPayload value => Message(w => { w.String(1, value.PileId.ToString("D")); w.String(2, value.ItemId); w.Int64(3, value.PileVersion); }),
        "relic.contents" when message.Payload is RoomRelicPilePayload value => EncodeRelicPile(value),
        "relic.replaced" when message.Payload is RelicReplacedEventPayload value => Message(w => { w.String(1, value.PileId.ToString("D")); w.String(2, value.ItemId); w.String(3, value.ReturnedItemId); w.Int64(4, value.PileVersion); }),
        "inventory.changed" when message.Payload is InventoryChangedEventPayload value => Message(w =>
        {
            w.String(1, value.Action);
            w.String(2, value.ItemId);
            if (value.Listing is { } listing) w.Bytes(3, EncodeMarketListing(listing));
            w.OptionalInt64(4, value.SellerGoldAfter);
        }),
        "duel.started" when message.Payload is DuelStartedEventPayload value => Message(w => { w.String(1, value.DuelId.ToString("D")); w.String(2, value.FirstPlayerId.ToString("D")); w.String(3, value.LatePlayerId.ToString("D")); w.Int64(4, value.LatePlayerUnlockAtUnixMs); w.Int64(5, value.LeaveWindowEndsAtUnixMs); }),
        "duel.ended" when message.Payload is DuelEndedEventPayload value => Message(w => { w.String(1, value.DuelId.ToString("D")); w.String(2, value.Reason); w.String(3, value.WinnerId?.ToString("D")); w.Bool(4, value.SnapshotRequired); }),
        "player.died" when message.Payload is PlayerDiedEventPayload value => Message(w => { w.String(1, value.PlayerId.ToString("D")); w.String(2, value.Cause); w.String(3, value.DuelId?.ToString("D")); }),
        "error.invalid_message" when message.Payload is null => null,
        _ when message.Payload is null => null,
        _ => throw new InvalidDataException($"No protobuf payload schema is registered for event '{message.Type}'.")
    };

    private static object? DecodePayload(string type, ReadOnlySpan<byte> bytes)
    {
        if (bytes.Length == 0) return null;
        var payload = Fields.Read(bytes);
        return type switch
        {
            "session.connected" => new SessionConnectedEventPayload(ParseGuid(payload.String(1), type)),
            "session.replaced" => new SessionReplacedEventPayload(payload.String(1)),
            "pong" => new PongEventPayload(DateTimeOffset.FromUnixTimeMilliseconds(payload.Int64(1))),
            "session.snapshot" => new SessionSnapshotEventPayload(ParseGuid(payload.String(1), type), payload.Int64(2), NullIfEmpty(payload.String(3)), payload.String(4), payload.Int64(5)),
            "match.found" => new MatchFoundEventPayload(ParseGuid(payload.String(1), type), ParseGuid(payload.String(2), type), payload.Int64(3)),
            "room.ready_required" => new RoomReadyRequiredEventPayload(ParseGuid(payload.String(1), type), ParseGuid(payload.String(2), type), payload.Int64(3), checked((int)payload.Int64(4)), checked((int)payload.Int64(5))),
            "room.ready_accepted" => new RoomReadyAcceptedEventPayload(ParseGuid(payload.String(1), type), ParseGuid(payload.String(2), type), payload.Int64(3), checked((int)payload.Int64(4)), checked((int)payload.Int64(5))),
            "room.ready_removed" => new RoomReadyRemovedEventPayload(ParseGuid(payload.String(1), type), payload.String(2)),
            "room.started" => DecodeRoomStarted(payload),
            "settlement.ready" or "match.settled" => new SettlementReadyEventPayload(
                ParseGuid(payload.String(1), type), ParseGuid(payload.String(2), type), payload.String(3)),
            "room.snapshot" => DecodeRoomSnapshot(payload),
            "map.player_count" => new MapPlayerCountEventPayload(checked((int)payload.Int64(1))),
            "error.command_rejected" => new CommandRejectedEventPayload(payload.String(1), payload.String(2)),
            "battle.combo_resolved" or "combat.previewed" or "combat.hit" => new BattleComboResolvedEventPayload(
                ParseGuid(payload.String(1), type),
                ParseGuid(payload.String(2), type),
                payload.String(3),
                checked((int)payload.Int64(4)),
                checked((int)payload.Int64(5)),
                checked((int)payload.Int64(6)),
                checked((int)payload.Int64(7)),
                checked((int)payload.Int64(8)),
                payload.Bool(9),
                payload.Bool(10),
                NullIfEmpty(payload.RepeatedBytes(11).Select(bytes => { var s = Fields.Read(bytes); return new CombatDamageSegmentPayload(s.String(1), checked((int)s.Int64(2))); }).ToArray()),
                NullIfEmpty(payload.String(12)), checked((int)payload.Int64(13)),
                NullIfEmpty(payload.String(14)), NullIfEmpty(payload.String(15)), checked((int)payload.Int64(16)),
                NullIfEmpty(payload.String(17)), checked((int)payload.Int64(18)),
                NullIfEmpty(payload.RepeatedStrings(19).Select(id => ParseGuid(id, type)).ToArray()), NullIfEmpty(payload.String(20)),
                NullIfEmpty(payload.String(21)), NullIfEmpty(payload.String(22)), NullIfEmpty(payload.String(23)),
                NullIfEmpty(payload.String(24)), checked((int)payload.Int64(25)), NullIfEmpty(payload.String(26))),
            "battle.target_selected" => new BattleTargetSelectedEventPayload(
                ParseGuid(payload.String(1), type), payload.String(2)),
            "reward.choice" => DecodeRewardChoice(payload),
            "reward.choice_claimed" => new RewardChoiceClaimedEventPayload(payload.String(1), checked((int)payload.Int64(2))),
            "room.moved" => new RoomMovedEventPayload(ParseGuid(payload.String(1), type), (int)payload.Int64(2), (int)payload.Int64(3)),
            "duel.leave_ack" => new DuelLeaveEventPayload(ParseGuid(payload.String(1), type), payload.Bool(2)),
            "duel.escape_started" or "duel.escape_interrupted" or "duel.escape_failed" => new DuelEscapeEventPayload(ParseGuid(payload.String(1), type), double.Parse(payload.String(2), System.Globalization.CultureInfo.InvariantCulture), payload.String(3)),
            "action.extract_started" or "action.extract_cancelled" or "action.extract_completed" => new ActionExtractEventPayload(payload.String(1), TimeSpan.FromMilliseconds(payload.Int64(2))),
            "action.spring_started" or "action.spring_cancelled" or "action.spring_completed" => new ActionSpringEventPayload(payload.String(1), TimeSpan.FromMilliseconds(payload.Int64(2))),
            "action.potion_used" => new ActionPotionEventPayload(payload.String(1), checked((int)payload.Int64(2))),
            "relic.taken" => new RelicTakeEventPayload(ParseGuid(payload.String(1), type), payload.String(2), payload.Int64(3)),
            "relic.contents" => DecodeRelicPile(payload),
            "relic.replaced" => new RelicReplacedEventPayload(ParseGuid(payload.String(1), type), payload.String(2), payload.String(3), payload.Int64(4)),
            "inventory.changed" => new InventoryChangedEventPayload(
                payload.String(1), payload.String(2),
                payload.Bytes(3).Length == 0 ? null : DecodeMarketListing(Fields.Read(payload.Bytes(3))),
                payload.OptionalInt64(4)),
            "duel.started" => new DuelStartedEventPayload(ParseGuid(payload.String(1), type), ParseGuid(payload.String(2), type), ParseGuid(payload.String(3), type), payload.Int64(4), payload.Int64(5)),
            "duel.ended" => new DuelEndedEventPayload(ParseGuid(payload.String(1), type), payload.String(2), ParseOptionalGuid(payload.String(3), type), payload.Bool(4)),
            "player.died" => new PlayerDiedEventPayload(ParseGuid(payload.String(1), type), payload.String(2), ParseOptionalGuid(payload.String(3), type)),
            _ => null
        };
    }

    private static Guid ParseGuid(string value, string type) => Guid.TryParse(value, out var parsed)
        ? parsed
        : throw new InvalidDataException($"{type} contains an invalid player_id.");

    private static Guid? ParseOptionalGuid(string value, string type) =>
        string.IsNullOrEmpty(value) ? null : ParseGuid(value, type);

    private static BattlePlayCardsCommandPayload DecodeBattlePlayCards(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        var ids = payload.RepeatedStrings(3).Select(value => ParseGuid(value, "battle.play_cards")).ToArray();
        return new BattlePlayCardsCommandPayload(
            ParseGuid(payload.String(1), "battle.play_cards"),
            payload.String(2),
            ids);
    }

    private static BattleSelectTargetCommandPayload DecodeBattleSelectTarget(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        return new BattleSelectTargetCommandPayload(
            ParseGuid(payload.String(1), "battle.select_target"),
            payload.String(2));
    }

    private static RelicReplaceCommandPayload DecodeRelicReplace(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        return new RelicReplaceCommandPayload(
            ParseGuid(payload.String(1), "relic.replace"),
            payload.String(2),
            payload.Int64(3),
            payload.String(4));
    }

    private static SessionResumeCommandPayload DecodeSessionResume(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        var roomIdText = payload.String(2);
        Guid? roomId = null;
        if (roomIdText.Length > 0)
            roomId = ParseGuid(roomIdText, "session.resume");
        return new(payload.Int64(1), roomId, payload.OptionalInt64(3));
    }

    private static RewardChoiceClaimCommandPayload DecodeRewardClaim(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        return new RewardChoiceClaimCommandPayload(payload.String(1), NullIfEmpty(payload.String(2)), payload.Bool(3));
    }

    private static InventoryMoveCommandPayload DecodeInventoryMove(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        return new(payload.String(1), checked((int)payload.Int64(2)));
    }

    private static RoomMoveCommandPayload DecodeRoomMove(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        return new RoomMoveCommandPayload((int)payload.Int64(1), (int)payload.Int64(2));
    }

    private static RelicTakeCommandPayload DecodeRelicTake(ReadOnlySpan<byte> bytes)
    {
        var payload = Fields.Read(bytes);
        return new RelicTakeCommandPayload(ParseGuid(payload.String(1), "relic.take"), payload.String(2), payload.Int64(3), NullIfEmpty(payload.String(4)));
    }

    private static RewardChoiceEventPayload DecodeRewardChoice(Fields payload) =>
        new((int)payload.Int64(1), payload.RepeatedBytes(2).Select(bytes =>
        {
            var option = Fields.Read(bytes);
            return new RewardChoiceOptionPayload(option.String(1), (RewardChoiceKindDto)option.Int64(2), NullIfEmpty(option.String(3)), (int)option.Int64(4), (int)option.Int64(5), DecodeEquipment(option.Bytes(6)));
        }).ToArray(), (int)payload.Int64(3), payload.Bool(4));

    private static RoomStartedEventPayload DecodeRoomStarted(Fields payload)
    {
        var snapshot = payload.Bytes(4);
        return new(ParseGuid(payload.String(1), "room.started"), ParseGuid(payload.String(2), "room.started"),
            checked((int)payload.Int64(3)), snapshot.Length == 0 ? null : DecodeRoomSnapshot(Fields.Read(snapshot)));
    }

    private static byte[] EncodeMarketListing(MarketListingResponse value) => Message(w =>
    {
        w.String(1, value.ListingId.ToString("D"));
        w.String(2, value.SellerId.ToString("D"));
        w.String(3, value.EquipmentId.ToString("D"));
        w.Int64(4, value.PriceGold);
        w.String(5, value.Status);
        w.Int64(6, value.Version);
        w.Int64(7, value.CreatedAt.ToUnixTimeMilliseconds());
        w.Int64(8, value.ExpiresAt.ToUnixTimeMilliseconds());
        if (value.Equipment is { } equipment)
            w.Bytes(9, Message(e =>
            {
                e.String(1, equipment.InstanceId.ToString("D"));
                e.String(2, equipment.Slot);
                e.String(3, equipment.Quality);
                e.Int64(4, equipment.Level);
                e.Bool(5, equipment.IsBound);
                e.String(6, equipment.Location);
                e.Int64(7, equipment.Version);
                e.String(8, equipment.Element);
                e.String(9, equipment.EffectAffix);
                e.String(10, equipment.SecondaryTrait);
            }));
    });

    private static MarketListingResponse DecodeMarketListing(Fields value)
    {
        var equipmentBytes = value.Bytes(9);
        EquipmentResponse? equipment = null;
        if (equipmentBytes.Length > 0)
        {
            var item = Fields.Read(equipmentBytes);
            equipment = new EquipmentResponse(
                ParseGuid(item.String(1), "market.listing"), item.String(2), item.String(3),
                checked((int)item.Int64(4)), item.Bool(5), item.String(6), item.Int64(7),
                NullIfEmpty(item.String(8)), NullIfEmpty(item.String(9)), NullIfEmpty(item.String(10)));
        }
        return new MarketListingResponse(
            ParseGuid(value.String(1), "market.listing"),
            ParseGuid(value.String(2), "market.listing"),
            ParseGuid(value.String(3), "market.listing"),
            value.Int64(4), value.String(5), value.Int64(6),
            DateTimeOffset.FromUnixTimeMilliseconds(value.Int64(7)),
            DateTimeOffset.FromUnixTimeMilliseconds(value.Int64(8)), equipment);
    }

    private static byte[] EncodeRewardChoice(RewardChoiceEventPayload value) => Message(w =>
    {
        w.Int64(1, value.Layer);
        foreach (var option in value.Options)
            w.Bytes(2, Message(o =>
            {
                o.String(1, option.OptionId);
                o.Int64(2, (int)option.Kind);
                o.String(3, option.ItemId);
                o.Int64(4, option.Quantity);
                o.Int64(5, option.HealPercent);
                if (option.Equipment is { } equipment) o.Bytes(6, EncodeEquipment(equipment));
            }));
        w.Int64(3, value.RefreshCount);
        w.Bool(4, value.IsBoss);
    });

    private static byte[] EncodeRoomSnapshot(RoomSnapshotEventPayload value) => Message(w =>
    {
        w.String(1, value.RoomId.ToString("D"));
        w.String(2, value.MatchId?.ToString("D"));
        w.Int64(3, value.RoomRevision);
        w.String(4, value.ConfigVersion);
        w.Bytes(5, EncodePosition(value.Self));
        foreach (var cell in value.Map)
            w.Bytes(6, Message(c => { c.Int64(1, cell.Row); c.Int64(2, cell.Column); c.Bool(3, cell.IsBoss); c.Bool(4, cell.HasSpring); }));
        foreach (var move in value.LegalMoves) w.Bytes(7, EncodePosition(move));
        w.Bytes(8, Message(c =>
        {
            c.Bool(1, value.CurrentCell.HasEvacuation);
            c.String(2, value.CurrentCell.MonsterGroupId);
            c.Bool(3, value.CurrentCell.SpringConsumed);
            foreach (var pileId in value.CurrentCell.RelicPileIds) c.String(4, pileId.ToString("D"));
            foreach (var pile in value.CurrentCell.RelicPiles ?? [])
                c.Bytes(5, EncodeRelicPile(pile));
        }));
        w.Bytes(9, EncodeRoomPlayer(value.Player));
        if (value.Pve is { } pve) w.Bytes(10, EncodePve(pve));
        if (value.Duel is { } duel) w.Bytes(11, EncodeDuel(duel));
        if (value.RewardChoice is { } reward) w.Bytes(12, EncodeRewardChoice(reward));
        w.OptionalInt64(13, value.ExtractionRemainingMs);
        w.OptionalInt64(14, value.SpringRemainingMs);
        foreach (var action in value.AllowedActions) w.String(15, action);
        w.Int64(16, value.MapPlayerCount);
    });

    private static byte[] EncodePosition(RoomPositionPayload value) =>
        Message(w => { w.Int64(1, value.Row); w.Int64(2, value.Column); });

    private static byte[] EncodeCombatant(RoomCombatantPayload value) => Message(w =>
    {
        w.Int64(1, value.Hp); w.Int64(2, value.MaximumHp);
        w.Int64(3, value.EffectiveMaximumHp); w.Int64(4, value.Shield);
    });

    private static byte[] EncodeRoomPlayer(RoomPlayerPayload value) => Message(w =>
    {
        w.String(1, value.PlayerId.ToString("D"));
        w.String(2, value.HeroClass);
        w.String(3, value.Phase);
        w.Bytes(4, EncodeCombatant(value.Combat));
        foreach (var card in value.Hand)
            w.Bytes(5, Message(c => { c.String(1, card.InstanceId.ToString("D")); c.String(2, card.CardId); c.Int64(3, card.Level); c.String(4, card.ElementOverride); }));
        w.Int64(6, value.LibraryCount);
        w.Int64(7, value.DiscardCount);
        w.String(8, value.DrawCharge);
        foreach (var item in value.Inventory) w.Bytes(9, EncodeInventoryItem(item));
        w.Int64(10, value.InventoryCapacity);
        foreach (var index in value.SafeSlotIndexes ?? []) w.Int64(11, index);
        foreach (var item in value.EquippedItems ?? []) w.Bytes(12, EncodeInventoryItem(item));
        w.Int64(13, value.WeaponLevel);
        if (value.BattleStatus is { } status) w.Bytes(14, EncodeBattleStatus(status));
        w.Int64(15, value.StunRemainingMs);
        w.Int64(16, value.DrawBlockRemainingMs);
        w.Int64(17, value.DrawSpeedRemainingMs);
        w.Int64(18, value.DrawBlockSpeedRemainingMs);
        w.String(19, value.BaseDrawIntervalSeconds);
    });

    private static byte[] EncodeBattleStatus(RoomBattleStatusPayload value) => Message(w =>
    {
        w.String(1, value.PassiveKind); w.Int64(2, value.Combo); w.String(3, value.CoreElement);
        foreach (var stat in value.Bonuses) w.Bytes(4, Message(s => { s.String(1, stat.Key); s.String(2, stat.Value); }));
        foreach (var set in value.Sets) w.Bytes(5, Message(s => { s.String(1, set.Kind); s.Int64(2, set.Count); s.Int64(3, set.Required); s.Bool(4, set.Active); }));
        w.String(6, value.DrawIntervalSeconds);
        w.Int64(7, value.ChargeLevel);
    });

    private static RoomBattleStatusPayload DecodeBattleStatus(byte[] bytes)
    {
        var value = Fields.Read(bytes);
        return new(value.String(1), checked((int)value.Int64(2)), NullIfEmpty(value.String(3)),
            value.RepeatedBytes(4).Select(b => { var s = Fields.Read(b); return new RoomStatPayload(s.String(1), s.String(2)); }).ToArray(),
            value.RepeatedBytes(5).Select(b => { var s = Fields.Read(b); return new RoomSetPayload(s.String(1), checked((int)s.Int64(2)), checked((int)s.Int64(3)), s.Bool(4)); }).ToArray(), value.String(6), checked((int)value.Int64(7)));
    }

    private static byte[] EncodeEquipment(RoomEquipmentPayload value) => Message(w =>
    {
        w.String(1, value.Slot); w.String(2, value.Quality); w.String(3, value.Element);
        w.String(4, value.EffectAffix); w.String(5, value.SecondaryTrait);
        w.Int64(6, value.Level); w.Bool(7, value.IsBound);
    });

    private static byte[] EncodeInventoryItem(RoomInventoryItemPayload value) => Message(w =>
    {
        w.String(1, value.ItemId); w.String(2, value.Kind); w.Int64(3, value.Quantity); w.Bool(4, value.IsSafe);
        if (value.Equipment is { } equipment) w.Bytes(5, EncodeEquipment(equipment));
        if (value.SlotIndex >= 0) w.Int64(6, value.SlotIndex);
    });

    private static byte[] EncodeRelicPile(RoomRelicPilePayload value) => Message(w =>
    {
        w.String(1, value.PileId.ToString("D")); w.String(2, value.OwnerName); w.Int64(3, value.Version);
        foreach (var item in value.Items) w.Bytes(4, EncodeInventoryItem(item));
    });

    private static RoomRelicPilePayload DecodeRelicPile(Fields value) => new(
        ParseGuid(value.String(1), "relic.contents"), value.String(2), value.Int64(3),
        value.RepeatedBytes(4).Select(DecodeInventoryItem).ToArray());

    private static RoomEquipmentPayload? DecodeEquipment(byte[] bytes)
    {
        if (bytes.Length == 0) return null;
        var e = Fields.Read(bytes);
        return new(e.String(1), e.String(2), e.String(3), NullIfEmpty(e.String(4)), NullIfEmpty(e.String(5)), checked((int)e.Int64(6)), e.Bool(7));
    }

    private static RoomInventoryItemPayload DecodeInventoryItem(byte[] bytes)
    {
        var i = Fields.Read(bytes);
        return new(i.String(1), i.String(2), checked((int)i.Int64(3)), i.Bool(4), DecodeEquipment(i.Bytes(5)), checked((int)(i.OptionalInt64(6) ?? -1)));
    }

    private static byte[] EncodePve(RoomPvePayload value) => Message(w =>
    {
        w.String(1, value.BattleId.ToString("D")); w.String(2, value.Phase); w.String(3, value.CurrentTargetId);
        foreach (var monster in value.Monsters)
            w.Bytes(4, Message(m =>
            {
                m.String(1, monster.MonsterId); m.Int64(2, monster.MaximumHp); m.Int64(3, monster.Hp); m.Int64(4, monster.Shield);
                m.String(5, monster.IntentKind); m.Int64(6, monster.IntentValue); m.String(7, monster.IntentElement);
                m.Int64(8, monster.IntervalProgressMs); m.Int64(9, monster.WindupRemainingMs); m.Int64(10, monster.StunRemainingMs);
                m.Int64(11, monster.BossPhase);
            }));
    });

    private static byte[] EncodeDuel(RoomDuelPayload value) => Message(w =>
    {
        w.String(1, value.DuelId.ToString("D")); w.String(2, value.OpponentId.ToString("D"));
        w.Bytes(3, EncodeCombatant(value.Opponent)); w.Int64(4, value.LatePlayerUnlockAtUnixMs);
        w.Int64(5, value.LeaveWindowEndsAtUnixMs); w.Bool(6, value.SelfRequestedLeave);
        w.OptionalInt64(7, value.EscapeRemainingMs);
        w.String(8, value.OpponentClass); w.String(9, value.OpponentName); w.String(10, value.EscapeProbability);
        if (value.OpponentStatus is { } status) w.Bytes(11, EncodeBattleStatus(status));
        w.Int64(12, value.OpponentStunRemainingMs);
        w.Int64(13, value.OpponentDrawBlockRemainingMs);
    });

    private static RoomSnapshotEventPayload DecodeRoomSnapshot(Fields payload)
    {
        var player = Fields.Read(payload.Bytes(9));
        var current = Fields.Read(payload.Bytes(8));
        var pveBytes = payload.Bytes(10);
        var duelBytes = payload.Bytes(11);
        var rewardBytes = payload.Bytes(12);
        return new RoomSnapshotEventPayload(
            ParseGuid(payload.String(1), "room.snapshot"),
            Guid.TryParse(payload.String(2), out var matchId) ? matchId : null,
            payload.Int64(3),
            payload.String(4),
            DecodePosition(payload.Bytes(5)),
            payload.RepeatedBytes(6).Select(bytes =>
            {
                var cell = Fields.Read(bytes);
                return new RoomMapCellPayload((int)cell.Int64(1), (int)cell.Int64(2), cell.Bool(3), cell.Bool(4));
            }).ToArray(),
            payload.RepeatedBytes(7).Select(DecodePosition).ToArray(),
            new RoomCurrentCellPayload(
                current.Bool(1), current.String(2), current.Bool(3),
                current.RepeatedStrings(4).Select(id => ParseGuid(id, "room.snapshot")).ToArray(),
                NullIfEmpty(current.RepeatedBytes(5).Select(bytes =>
                {
                    var pile = Fields.Read(bytes);
                    return new RoomRelicPilePayload(ParseGuid(pile.String(1), "room.snapshot"), pile.String(2), pile.Int64(3), pile.RepeatedBytes(4).Select(DecodeInventoryItem).ToArray());
                }).ToArray())),
            DecodeRoomPlayer(player),
            pveBytes.Length == 0 ? null : DecodePve(Fields.Read(pveBytes)),
            duelBytes.Length == 0 ? null : DecodeDuel(Fields.Read(duelBytes)),
            rewardBytes.Length == 0 ? null : DecodeRewardChoice(Fields.Read(rewardBytes)),
            payload.OptionalInt64(13),
            payload.OptionalInt64(14),
            payload.RepeatedStrings(15),
            checked((int)payload.Int64(16)));
    }

    private static RoomPositionPayload DecodePosition(byte[] bytes)
    {
        var value = Fields.Read(bytes);
        return new((int)value.Int64(1), (int)value.Int64(2));
    }

    private static RoomCombatantPayload DecodeCombatant(byte[] bytes)
    {
        var value = Fields.Read(bytes);
        return new((int)value.Int64(1), (int)value.Int64(2), (int)value.Int64(3), (int)value.Int64(4));
    }

    private static RoomPlayerPayload DecodeRoomPlayer(Fields value) => new(
        ParseGuid(value.String(1), "room.snapshot"),
        value.String(2),
        value.String(3),
        DecodeCombatant(value.Bytes(4)),
        value.RepeatedBytes(5).Select(bytes =>
        {
            var card = Fields.Read(bytes);
            return new RoomCardPayload(ParseGuid(card.String(1), "room.snapshot"), card.String(2), checked((int)card.Int64(3)), NullIfEmpty(card.String(4)));
        }).ToArray(),
        (int)value.Int64(6),
        (int)value.Int64(7),
        value.String(8),
        value.RepeatedBytes(9).Select(DecodeInventoryItem).ToArray(),
        checked((int)value.Int64(10)),
        NullIfEmpty(value.RepeatedInt64(11).Select(index => checked((int)index)).ToArray()),
        NullIfEmpty(value.RepeatedBytes(12).Select(DecodeInventoryItem).ToArray()),
        checked((int)value.Int64(13)),
        value.Bytes(14).Length > 0 ? DecodeBattleStatus(value.Bytes(14)) : null,
        value.Int64(15), value.Int64(16), value.Int64(17), value.Int64(18), NullIfEmpty(value.String(19)));

    private static RoomPvePayload DecodePve(Fields value) => new(
        ParseGuid(value.String(1), "room.snapshot"),
        value.String(2),
        NullIfEmpty(value.String(3)),
        value.RepeatedBytes(4).Select(bytes =>
        {
            var monster = Fields.Read(bytes);
            return new RoomMonsterPayload(
                monster.String(1), (int)monster.Int64(2), (int)monster.Int64(3), (int)monster.Int64(4),
                monster.String(5), (int)monster.Int64(6), monster.String(7),
                monster.Int64(8), monster.Int64(9), monster.Int64(10), (int)(monster.OptionalInt64(11) ?? 1));
        }).ToArray());

    private static RoomDuelPayload DecodeDuel(Fields value) => new(
        ParseGuid(value.String(1), "room.snapshot"),
        ParseGuid(value.String(2), "room.snapshot"),
        DecodeCombatant(value.Bytes(3)),
        value.Int64(4), value.Int64(5), value.Bool(6), value.OptionalInt64(7),
        NullIfEmpty(value.String(8)), NullIfEmpty(value.String(9)), NullIfEmpty(value.String(10)),
        value.Bytes(11).Length > 0 ? DecodeBattleStatus(value.Bytes(11)) : null,
        value.Int64(12), value.Int64(13));

    private static byte[] Message(Action<ProtoWriter> action)
    {
        var writer = new ProtoWriter();
        action(writer);
        return writer.ToArray();
    }

    private static string? NullIfEmpty(string value) => value.Length == 0 ? null : value;
    private static T[]? NullIfEmpty<T>(T[] value) => value.Length == 0 ? null : value;

    private static void ValidateVersion(uint version)
    {
        if (version != ProtocolVersion) throw new InvalidDataException($"Unsupported realtime protobuf version {version}.");
    }

    private sealed class ProtoWriter
    {
        private readonly List<byte> _stream = [];
        public void UInt32(int field, uint value) => Int64(field, value);
        public void Bool(int field, bool value) => Int64(field, value ? 1 : 0);
        public void OptionalInt64(int field, long? value) { if (value.HasValue) Int64(field, value.Value); }
        public void Int64(int field, long value) { Varint((ulong)(field << 3)); Varint(unchecked((ulong)value)); }
        public void String(int field, string? value) { if (!string.IsNullOrEmpty(value)) Bytes(field, Encoding.UTF8.GetBytes(value)); }
        public void Bytes(int field, byte[]? value)
        {
            if (value is null || value.Length == 0) return;
            Varint((ulong)((field << 3) | 2));
            Varint((ulong)value.Length);
            _stream.AddRange(value);
        }
        public byte[] ToArray() => [.. _stream];
        private void Varint(ulong value)
        {
            while (value >= 0x80) { _stream.Add((byte)(value | 0x80)); value >>= 7; }
            _stream.Add((byte)value);
        }
    }

    private sealed class Fields
    {
        private readonly Dictionary<int, ulong> _integers = [];
        private readonly Dictionary<int, List<long>> _repeatedIntegers = [];
        private readonly Dictionary<int, List<byte[]>> _bytes = [];
        public uint UInt32(int field) => checked((uint)Int64(field));
        public long Int64(int field) => unchecked((long)_integers.GetValueOrDefault(field));
        public long? OptionalInt64(int field) => _integers.TryGetValue(field, out var value) ? unchecked((long)value) : null;
        public bool Bool(int field) => Int64(field) != 0;
        public string String(int field) => Encoding.UTF8.GetString(Bytes(field));
        public byte[] Bytes(int field) => _bytes.TryGetValue(field, out var values) && values.Count > 0
            ? values[^1]
            : [];
        public string[] RepeatedStrings(int field) =>
            _bytes.TryGetValue(field, out var values)
                ? values.Select(value => Encoding.UTF8.GetString(value)).ToArray()
                : [];
        public byte[][] RepeatedBytes(int field) => _bytes.TryGetValue(field, out var values) ? values.ToArray() : [];
        public long[] RepeatedInt64(int field)
        {
            var values = new List<long>(_repeatedIntegers.GetValueOrDefault(field) ?? []);
            foreach (var packed in RepeatedBytes(field))
            {
                var offset = 0;
                while (offset < packed.Length) values.Add(unchecked((long)ReadVarint(packed, ref offset)));
            }
            return values.ToArray();
        }

        public static Fields Read(ReadOnlySpan<byte> source)
        {
            var result = new Fields();
            var offset = 0;
            while (offset < source.Length)
            {
                var tag = ReadVarint(source, ref offset);
                var field = checked((int)(tag >> 3));
                var wireType = (int)(tag & 7);
                if (field == 0) throw new InvalidDataException("Invalid protobuf field number 0.");
                switch (wireType)
                {
                    case 0:
                        var integer = ReadVarint(source, ref offset);
                        result._integers[field] = integer;
                        if (!result._repeatedIntegers.TryGetValue(field, out var integers))
                            result._repeatedIntegers[field] = integers = [];
                        integers.Add(unchecked((long)integer));
                        break;
                    case 1: Ensure(source, offset, 8); offset += 8; break;
                    case 2:
                        var length = checked((int)ReadVarint(source, ref offset));
                        Ensure(source, offset, length);
                        if (!result._bytes.TryGetValue(field, out var values))
                        {
                            values = [];
                            result._bytes[field] = values;
                        }
                        values.Add(source.Slice(offset, length).ToArray());
                        offset += length;
                        break;
                    case 5: Ensure(source, offset, 4); offset += 4; break;
                    default: throw new InvalidDataException($"Unsupported protobuf wire type {wireType}.");
                }
            }
            return result;
        }

        private static ulong ReadVarint(ReadOnlySpan<byte> source, ref int offset)
        {
            ulong value = 0;
            for (var shift = 0; shift < 64; shift += 7)
            {
                Ensure(source, offset, 1);
                var current = source[offset++];
                value |= (ulong)(current & 0x7F) << shift;
                if ((current & 0x80) == 0) return value;
            }
            throw new InvalidDataException("Malformed protobuf varint.");
        }

        private static void Ensure(ReadOnlySpan<byte> source, int offset, int count)
        {
            if (count < 0 || offset > source.Length - count) throw new InvalidDataException("Truncated protobuf message.");
        }
    }
}
