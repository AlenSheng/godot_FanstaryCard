using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class RealtimeProtobufCodecTests
{
    [Fact]
    public void ReadyCommandAndEvents_RoundTripTypedPayloads()
    {
        var matchId = Guid.NewGuid();
        var roomId = Guid.NewGuid();
        var deadline = DateTimeOffset.UtcNow.AddSeconds(15).ToUnixTimeMilliseconds();
        var command = RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(
            new ClientCommand("room.ready", "ready-01", null, new RoomReadyCommandPayload())));
        Assert.IsType<RoomReadyCommandPayload>(command.Payload);

        (string Type, object Payload)[] events =
        [
            ("match.found", new MatchFoundEventPayload(matchId, roomId, deadline)),
            ("room.ready_required", new RoomReadyRequiredEventPayload(matchId, roomId, deadline, 1, 3)),
            ("room.ready_accepted", new RoomReadyAcceptedEventPayload(matchId, roomId, deadline, 2, 3)),
            ("room.ready_removed", new RoomReadyRemovedEventPayload(matchId, "ready_timeout")),
            ("room.started", new RoomStartedEventPayload(matchId, roomId, 4)),
            ("settlement.ready", new SettlementReadyEventPayload(Guid.NewGuid(), matchId, "Extracted")),
            ("match.settled", new SettlementReadyEventPayload(Guid.NewGuid(), matchId, "Dead"))
        ];
        foreach (var (type, payload) in events)
        {
            var original = new ServerEvent(type, "trace", payload, "event", 1, DateTimeOffset.UnixEpoch);
            Assert.Equivalent(original,
                RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(original)), strict: true);
        }
    }

    [Fact]
    public void RoomEvents_PreservePayloadAndEnvelope()
    {
        var id = Guid.NewGuid();
        var now = DateTimeOffset.FromUnixTimeMilliseconds(1788289200123);
        (string Type, object Payload)[] events =
        [
            ("reward.choice_claimed", new RewardChoiceClaimedEventPayload("heal:confirmed", 0)),
            ("reward.choice_claimed", new RewardChoiceClaimedEventPayload("fragments:confirmed", 7)),
            ("room.moved", new RoomMovedEventPayload(id, 0, 5)),
            ("duel.leave_ack", new DuelLeaveEventPayload(id, false)),
            ("duel.escape_started", new DuelEscapeEventPayload(id, 0.375, "Started")),
            ("duel.escape_interrupted", new DuelEscapeEventPayload(id, 0.375, "Interrupted")),
            ("duel.escape_failed", new DuelEscapeEventPayload(id, 0.375, "Failed")),
            ("action.extract_started", new ActionExtractEventPayload("Started", TimeSpan.FromSeconds(3))),
            ("action.extract_cancelled", new ActionExtractEventPayload("Cancelled", TimeSpan.Zero)),
            ("action.extract_completed", new ActionExtractEventPayload("Completed", TimeSpan.Zero)),
            ("action.spring_started", new ActionSpringEventPayload("Started", TimeSpan.FromSeconds(1.2))),
            ("action.spring_cancelled", new ActionSpringEventPayload("Cancelled", TimeSpan.Zero)),
            ("action.spring_completed", new ActionSpringEventPayload("Completed", TimeSpan.Zero)),
            ("action.potion_used", new ActionPotionEventPayload("health_potion:1", 14)),
            ("relic.taken", new RelicTakeEventPayload(id, "equipment-1", 42)),
            ("relic.replaced", new RelicReplacedEventPayload(id, "equipment-2", "equipment-old", 43)),
            ("battle.target_selected", new BattleTargetSelectedEventPayload(id, "monster-2")),
            ("duel.started", new DuelStartedEventPayload(id, Guid.NewGuid(), Guid.NewGuid(), now.ToUnixTimeMilliseconds() + 800, now.ToUnixTimeMilliseconds() + 8000)),
            ("duel.ended", new DuelEndedEventPayload(id, "death", Guid.NewGuid())),
            ("player.died", new PlayerDiedEventPayload(Guid.NewGuid(), "PvpDeath", id)),
            ("reward.choice", new RewardChoiceEventPayload(2,
                [new("heal:boss", RewardChoiceKindDto.ImmediateHeal, null, 0, 32)], 3, true))
        ];
        foreach (var (type, payload) in events)
        {
            var original = new ServerEvent(type, "trace", payload, "event-1", 15, now, "request-1", 42);
            var decoded = RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(original));
            Assert.Equivalent(original, decoded, strict: true);
        }
    }

    [Fact]
    public void ClientResume_RoundTripsTypedPayload()
    {
        var roomId = Guid.NewGuid();
        var encoded = RealtimeProtobufCodec.EncodeClient(new ClientCommand(
            "session.resume", "resume-1", 42, new SessionResumeCommandPayload(17, roomId, 23)));
        var decoded = RealtimeProtobufCodec.DecodeClient(encoded);

        Assert.Equal("session.resume", decoded.Type);
        Assert.Equal("resume-1", decoded.RequestId);
        Assert.Equal(42, decoded.ExpectedRevision);
        var resume = Assert.IsType<SessionResumeCommandPayload>(decoded.Payload);
        Assert.Equal(17, resume.LastSequence);
        Assert.Equal(roomId, resume.RoomId);
        Assert.Equal(23, resume.RoomRevision);
        Assert.NotEqual((byte)'{', encoded[0]);
    }

    [Fact]
    public void ServerPong_RoundTripsTypedPayload()
    {
        var now = DateTimeOffset.FromUnixTimeMilliseconds(1_788_289_200_123);
        var encoded = RealtimeProtobufCodec.EncodeServer(new ServerEvent(
            "pong", "trace", new PongEventPayload(now), "event-1", 2, now, "ping-1", null));
        var decoded = RealtimeProtobufCodec.DecodeServer(encoded);

        Assert.Equal("pong", decoded.Type);
        Assert.Equal(2, decoded.Sequence);
        Assert.Equal("ping-1", decoded.RequestId);
        Assert.Equal(now, Assert.IsType<PongEventPayload>(decoded.Payload).ServerTime);
    }

    [Fact]
    public void DecodeClient_RejectsWrongProtocolVersion()
    {
        var encoded = RealtimeProtobufCodec.EncodeClient(new ClientCommand("ping", "ping-1", null, null));
        encoded[1] = 2;
        Assert.Throws<InvalidDataException>(() => RealtimeProtobufCodec.DecodeClient(encoded));
    }

    [Fact]
    public void BattlePlayCards_RoundTripsAllCardInstanceIds()
    {
        var battleId = Guid.NewGuid();
        var cards = new[] { Guid.NewGuid(), Guid.NewGuid(), Guid.NewGuid() };
        var encoded = RealtimeProtobufCodec.EncodeClient(new ClientCommand(
            "battle.play_cards",
            "play-1",
            7,
            new BattlePlayCardsCommandPayload(battleId, "monster-1", cards)));
        var decoded = RealtimeProtobufCodec.DecodeClient(encoded);
        var payload = Assert.IsType<BattlePlayCardsCommandPayload>(decoded.Payload);

        Assert.Equal(battleId, payload.BattleId);
        Assert.Equal("monster-1", payload.TargetId);
        Assert.Equal(cards, payload.CardInstanceIds);
    }

    [Fact]
    public void BattleComboResolved_RoundTripsTypedPayload()
    {
        var now = DateTimeOffset.FromUnixTimeMilliseconds(1_788_289_200_123);
        var payload = new BattleComboResolvedEventPayload(
            Guid.NewGuid(),
            Guid.NewGuid(),
            "monster-1",
            12,
            2,
            10,
            3,
            4,
            false,
            false);
        var decoded = RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(
            new ServerEvent("battle.combo_resolved", "trace", payload, "event", 3, now, "play", 8)));

        Assert.Equivalent(payload, Assert.IsType<BattleComboResolvedEventPayload>(decoded.Payload), strict: true);
        Assert.Equal(8, decoded.RoomRevision);
    }

    [Fact]
    public void RoomAndRewardCommands_RoundTripTypedPayloads()
    {
        var move = Assert.IsType<RoomMoveCommandPayload>(RealtimeProtobufCodec.DecodeClient(
            RealtimeProtobufCodec.EncodeClient(new ClientCommand("room.move", "move", 9, new RoomMoveCommandPayload(2, 4)))).Payload);
        Assert.Equal((2, 4), (move.Row, move.Column));

        var mapMove = Assert.IsType<RoomMoveCommandPayload>(RealtimeProtobufCodec.DecodeClient(
            RealtimeProtobufCodec.EncodeClient(new ClientCommand("map.move", "map-move", 9, new RoomMoveCommandPayload(3, 1)))).Payload);
        Assert.Equal((3, 1), (mapMove.Row, mapMove.Column));

        var claim = new RewardChoiceClaimCommandPayload("heal:abc", "old-item");
        var decodedClaim = RealtimeProtobufCodec.DecodeClient(
            RealtimeProtobufCodec.EncodeClient(new ClientCommand("reward.choice.claim", "claim", 10, claim)));
        Assert.Equivalent(claim, Assert.IsType<RewardChoiceClaimCommandPayload>(decodedClaim.Payload), strict: true);

        var spring = RealtimeProtobufCodec.DecodeClient(
            RealtimeProtobufCodec.EncodeClient(new ClientCommand("action.spring", "spring", 11, new ActionSpringCommandPayload())));
        Assert.IsType<ActionSpringCommandPayload>(spring.Payload);
        Assert.Equal(11, spring.ExpectedRevision);

        var potion = RealtimeProtobufCodec.DecodeClient(
            RealtimeProtobufCodec.EncodeClient(new ClientCommand("action.potion", "potion", 12, new ActionPotionCommandPayload())));
        Assert.IsType<ActionPotionCommandPayload>(potion.Payload);
        Assert.Equal(12, potion.ExpectedRevision);

        var roomSnapshot = RealtimeProtobufCodec.DecodeClient(
            RealtimeProtobufCodec.EncodeClient(new ClientCommand("room.snapshot.read", "snapshot", null, new RoomSnapshotCommandPayload())));
        Assert.IsType<RoomSnapshotCommandPayload>(roomSnapshot.Payload);

        var battleId = Guid.NewGuid();
        var target = new BattleSelectTargetCommandPayload(battleId, "monster-2");
        var decodedTarget = RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(
            new ClientCommand("battle.select_target", "target", 12, target)));
        Assert.Equivalent(target, Assert.IsType<BattleSelectTargetCommandPayload>(decodedTarget.Payload), strict: true);

        var replace = new RelicReplaceCommandPayload(Guid.NewGuid(), "loot", 7, "old-item");
        var decodedReplace = RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(
            new ClientCommand("relic.replace", "replace", 13, replace)));
        Assert.Equivalent(replace, Assert.IsType<RelicReplaceCommandPayload>(decodedReplace.Payload), strict: true);
    }

    [Theory]
    [InlineData(1)]
    [InlineData(2)]
    public void RoomSnapshot_RoundTripsTypedPayloadWithinMessageLimit(int bossPhase)
    {
        var playerId = Guid.NewGuid();
        var battleId = Guid.NewGuid();
        var payload = new RoomSnapshotEventPayload(
            Guid.NewGuid(),
            Guid.NewGuid(),
            27,
            "gdd-test",
            new(0, 2),
            Enumerable.Range(0, 36).Select(index => new RoomMapCellPayload(index / 6, index % 6, index == 14, index is 2 or 9)).ToArray(),
            [new(0, 1), new(0, 3)],
            new(true, "O3", false, [Guid.NewGuid()]),
            new(
                playerId,
                "Mage",
                "Pve",
                new(61, 70, 70, 4),
                [new(Guid.NewGuid(), "common-01"), new(Guid.NewGuid(), "mage-01")],
                16,
                2,
                "0.375",
                [new("equipment-1", "Equipment", 1, true, new("Head", "Purple", "Fire", "Piercing", "DrawInterval"))]),
            new(battleId, "Active", "monster-1",
                [new("monster-1", 84, 60, 3, "Attack", 9, "Fire", 1200, 0, 0, bossPhase)]),
            null,
            null,
            null,
            null,
            ["battle.play_cards"]);
        var original = new ServerEvent("room.snapshot", "trace", payload, "event-room", 44, DateTimeOffset.UnixEpoch, "snapshot", 27);

        var encoded = RealtimeProtobufCodec.EncodeServer(original);
        var decoded = RealtimeProtobufCodec.DecodeServer(encoded);

        Assert.True(encoded.Length <= 16 * 1024);
        Assert.Equivalent(original, decoded, strict: true);
    }

    [Fact]
    public void LegacyRoomMonsterWithoutBossPhaseDefaultsToFirstStage()
    {
        // Legacy wire fixture contains only monster fields 1, 2 and 3, including half HP.
        const string legacy = "CAESDXJvb20uc25hcHNob3QimQEKJDAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMUomCiQwMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDFSSQokMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAxEgZBY3RpdmUiGQoRYW5uaWhpbGF0aW9uLWNvcmUQmAIYjAE=";
        var message = RealtimeProtobufCodec.DecodeServer(Convert.FromBase64String(legacy));
        var snapshot = Assert.IsType<RoomSnapshotEventPayload>(message.Payload);
        var monster = Assert.Single(snapshot.Pve!.Monsters);
        Assert.Equal(140, monster.Hp);
        Assert.Equal(1, monster.BossPhase);
    }
}
