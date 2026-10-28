using FantasyCard.Contracts.Realtime;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class NumericalProtocolTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Monster_decision_roundtrips_identity_choice_and_replacement(bool accept)
    {
        var command = new ClientCommand("monster.choose", "monster-1", 17,
            new MonsterCardChooseCommandPayload(Guid.NewGuid(), accept, accept ? Guid.NewGuid() : null));
        Assert.Equivalent(command, RealtimeProtobufCodec.DecodeClient(RealtimeProtobufCodec.EncodeClient(command)), strict: true);
    }

    [Fact]
    public void New_snapshot_fields_roundtrip_and_do_not_replace_existing_tags()
    {
        var card = new RoomCardPayload(Guid.NewGuid(), "M-FIREBAT");
        var player = new RoomPlayerPayload(Guid.NewGuid(), "Guardian", "Choice", new(100, 100, 100, 0), [], 20, 0,
            "0", [], MonsterPool: new(5, [card], []), NumericalState: new("CoreCardsSpent", "FractionalRemainder", 4));
        var snapshot = new RoomSnapshotEventPayload(Guid.NewGuid(), null, 17, "test", new(0, 0), [], [],
            new(false, "O1", false, []), player, null, null, null, null, null, ["monster.choose"]);
        var message = new ServerEvent("room.snapshot", "test", snapshot, "event", 1, DateTimeOffset.UnixEpoch);
        Assert.Equivalent(message, RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(message)), strict: true);
    }
}
