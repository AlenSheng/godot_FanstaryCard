using FantasyCard.Contracts.Realtime;
using Wire = FantasyCard.Contracts.Wire.Realtime.V1;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class LocalizedNameProtocolTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void On_demand_relic_preserves_name_and_optional_fallback_flag(bool fallback)
    {
        var original = new RoomRelicPilePayload(Guid.NewGuid(), "旅人", 7, [], fallback);
        var bytes = RealtimeProtobufCodec.EncodeServer(Event("relic.contents", original));
        var decoded = Assert.IsType<RoomRelicPilePayload>(RealtimeProtobufCodec.DecodeServer(bytes).Payload);
        Assert.Equivalent(original, decoded, strict: true);
        var wire = Wire.RoomRelicPile.Parser.ParseFrom(Wire.ServerEnvelope.Parser.ParseFrom(bytes).Payload);
        Assert.Equal(fallback, wire.OwnerNameIsFallback);
        Assert.Equal(fallback, wire.HasOwnerNameIsFallback);
        Assert.Equal("旅人", wire.OwnerName);
        Assert.Equal(5, Wire.RoomRelicPile.Descriptor.FindFieldByName("owner_name_is_fallback").FieldNumber);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Snapshot_relic_and_duel_flags_roundtrip_and_old_absence_means_false(bool fallback)
    {
        var pile = new RoomRelicPilePayload(Guid.NewGuid(), "旅人", 3, [], fallback);
        var duel = new RoomDuelPayload(Guid.NewGuid(), Guid.NewGuid(), new(70, 70, 70, 0),
            0, 0, false, null, "Priest", "旅人", OpponentNameIsFallback: fallback);
        var original = new RoomSnapshotEventPayload(Guid.NewGuid(), null, 5, "test", new(0, 0), [], [],
            new(false, "outer", false, [pile.PileId], [pile]),
            new(Guid.NewGuid(), "Mage", "Pvp", new(80, 80, 80, 0), [], 0, 0, "0", []),
            null, duel, null, null, null, []);
        var bytes = RealtimeProtobufCodec.EncodeServer(Event("room.snapshot", original));
        var decoded = Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(bytes).Payload);
        Assert.Equal(fallback, Assert.Single(decoded.CurrentCell.RelicPiles!).OwnerNameIsFallback);
        Assert.Equal(fallback, decoded.Duel!.OpponentNameIsFallback);
        Assert.Equal("旅人", decoded.Duel.OpponentName);
        var wire = Wire.RoomSnapshotEvent.Parser.ParseFrom(Wire.ServerEnvelope.Parser.ParseFrom(bytes).Payload);
        Assert.Equal(fallback, Assert.Single(wire.CurrentCell.RelicPiles).HasOwnerNameIsFallback);
        Assert.Equal(fallback, wire.Duel.HasOpponentNameIsFallback);
        Assert.Equal(16, Wire.RoomDuel.Descriptor.FindFieldByName("opponent_name_is_fallback").FieldNumber);
    }

    private static ServerEvent Event(string type, object payload) =>
        new(type, "localized-name", payload, "event", 1, DateTimeOffset.UnixEpoch);
}
