using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class GameplayProtocolTests
{
    [Fact]
    public void InventoryAndPreviewCommandsPreserveIdentityRevisionAndReplacementSemantics()
    {
        (string Type, object Payload)[] commands =
        [
            ("inventory.move", new InventoryMoveCommandPayload("carried", 35)),
            ("inventory.equip", new InventoryEquipCommandPayload("armor")),
            ("inventory.unequip", new InventoryUnequipCommandPayload("Head")),
            ("relic.read", new RelicReadCommandPayload(Guid.NewGuid())),
            ("reward.choice.claim", new RewardChoiceClaimCommandPayload("reward", Equip: true)),
            ("combat.preview", new BattlePlayCardsCommandPayload(Guid.NewGuid(), "target", [Guid.NewGuid(), Guid.NewGuid()]))
        ];
        foreach (var (type, payload) in commands)
        {
            var command = new ClientCommand(type, "request", 16, payload);
            Assert.Equivalent(command, RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(command)), strict: true);
        }
    }

    [Theory]
    [InlineData("combat.previewed")]
    [InlineData("battle.combo_resolved")]
    [InlineData("combat.hit")]
    public void TypedDamageAndAuxiliaryEffectsPreserveTheirWireValues(string type)
    {
        var payload = new BattleComboResolvedEventPayload(Guid.NewGuid(), Guid.NewGuid(), "target", 19, 5, 14, 3, 4,
            false, false, [new("Fire", 3), new("Metal", 6), new("Direct", 10)], "Fire", 3,
            "0.4", "2", 1, "0.5", 2, [Guid.NewGuid()], "source");
        var message = Event(type, payload);
        var decoded = RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(message));
        Assert.Equivalent(message, decoded, strict: true);
        var result = Assert.IsType<BattleComboResolvedEventPayload>(decoded.Payload);
        Assert.Equal(result.ShieldDamage + result.HpDamage, result.DamageSegments!.Sum(segment => segment.Amount));
    }

    [Fact]
    public void FullBackpackAndOnDemandRelicStayWithinBinaryMessageLimit()
    {
        var room = CreateRoom(out var playerId);
        var snapshot = room.Capture();
        var player = snapshot.Players.Single();
        var armor = Enumerable.Range(0, 36).Select(index => new ExplorationItem(
            Guid.NewGuid().ToString("D"), ExplorationItemKind.Equipment, 1, index >= 33,
            new("Head", "Purple", "Metal", "Piercing", "DrawInterval", 5, true), index)).ToArray();
        var piles = Enumerable.Range(0, 4).Select(index => new RelicPileSnapshot(Guid.NewGuid(), Guid.NewGuid().ToString("D"),
            player.Position!.Value, 2, Enumerable.Range(0, 41).Select(item => armor[item % armor.Length] with
            { ItemId = Guid.NewGuid().ToString("D"), SlotIndex = -1, IsSafe = false }).ToArray(), new string('旅', 20))).ToArray();
        snapshot = snapshot with
        {
            Players = [player with { Phase = RoomPlayerPhase.ActionBar, Pve = null,
                Inventory = new(36, 3, armor, SafeSlotIndexes: [33, 34, 35]) }],
            RelicPiles = piles
        };
        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 37);
        var projection = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(playerId).Execute(restored), playerId, null, DateTimeOffset.UnixEpoch);
        projection = projection with { Player = projection.Player with
        { Hand = [new(Guid.NewGuid(), "M-BOXSPIRIT", ElementOverride: "None"), new(Guid.NewGuid(), "M-BOXSPIRIT", ElementOverride: "Metal")] } };
        Assert.Equal(36, projection.Player.InventoryCapacity);
        Assert.Equal([33, 34, 35], projection.Player.SafeSlotIndexes);
        Assert.All(projection.CurrentCell.RelicPiles!, pile => Assert.Empty(pile.Items));
        Assert.Equal(4, projection.CurrentCell.RelicPiles!.Count);
        var snapshotBytes = RealtimeProtobufCodec.EncodeServer(Event("room.snapshot", projection));
        Assert.True(snapshotBytes.Length < 16 * 1024);
        var roundTrip = Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(snapshotBytes).Payload);
        Assert.Equal("None", roundTrip.Player.Hand[0].ElementOverride);
        Assert.Equal("Metal", roundTrip.Player.Hand[1].ElementOverride);
        var pile = piles[0];
        var detail = new RoomRelicPilePayload(pile.PileId, pile.VictimName!, pile.Version, pile.Items.Select(RoomSnapshotProjection.ToInventoryItem).ToArray());
        var bytes = RealtimeProtobufCodec.EncodeServer(Event("relic.contents", detail));
        Assert.True(bytes.Length < 16 * 1024);
        Assert.Equivalent(detail, RealtimeProtobufCodec.DecodeServer(bytes).Payload, strict: true);
    }

    [Fact]
    public async Task PreviewIsPureAndMatchesTheFollowingAuthoritativePlay()
    {
        var room = CreateRoom(out var playerId);
        var before = room.Capture();
        var pve = room.GetPlayer(playerId).Pve!;
        var hand = room.GetPlayer(playerId).Combat.Deck.Hand;
        var payload = new BattlePlayCardsCommandPayload(pve.BattleId, pve.CurrentTargetId!, hand.Take(2).Select(card => card.InstanceId).ToArray());
        var store = new RealtimeEventStore(TimeProvider.System);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(store, TimeProvider.System, registry);
        var player = PlayerProfile.Create(playerId, "Preview tester", DateTimeOffset.UnixEpoch);
        var preview = Assert.Single(await router.RouteAsync(player, new("combat.preview", "preview", room.Revision, payload), "test", TestContext.Current.CancellationToken));
        Assert.Equal("combat.previewed", preview.Type);
        Assert.Equal("preview", preview.RequestId);
        Assert.Equal(before.Revision, preview.RoomRevision);
        Assert.Equivalent(before, room.Capture(), strict: true);
        Assert.Empty(room.DrainCombatFeedback());
        var played = Assert.Single(await router.RouteAsync(player, new("battle.play_cards", "play", room.Revision, payload), "test", TestContext.Current.CancellationToken));
        Assert.Equal("battle.combo_resolved", played.Type);
        Assert.Equivalent(preview.Payload, played.Payload, strict: true);
        Assert.Equal(before.Revision + 1, room.Revision);
    }

    private static BattleRoom CreateRoom(out Guid playerId)
    {
        playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 37);
        room.AddPlayer(new(playerId, HeroClass.Mage, Enumerable.Range(1, 20).Select(index => $"C{index:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 1));
        return room;
    }

    private static ServerEvent Event(string type, object payload) => new(type, "test", payload, "event", 1, DateTimeOffset.UnixEpoch, "request", 16);
}
