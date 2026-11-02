using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Domain.Seasons;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class SeasonRoomProtocolTests
{
    [Theory]
    [InlineData(HeroClass.Mage, 70)]
    [InlineData(HeroClass.Priest, 80)]
    [InlineData(HeroClass.Guardian, 100)]
    public void PublicSnapshotCarriesSeasonAndKeepsLegalClassHealth(HeroClass hero, int hp)
    {
        var season = new SeasonContext("s", 2, "season-v1", "cfg", "stats");
        var payload = Projection(hero, season);
        Assert.Equal(hp, payload.Player.Combat.MaximumHp);
        Assert.Equal("SeasonBoundedRhythm", payload.Player.NumericalState!.FenxianPolicy);
        Assert.Equal(new RoomSeasonContextPayload("s", "D2", "season-v1", "cfg", "stats"), payload.Season);
        var envelope = new ServerEvent("room.snapshot", "trace", payload, Guid.NewGuid().ToString("D"), 1, DateTimeOffset.UnixEpoch);
        var wire = RealtimeProtobufCodec.EncodeServer(envelope);
        var golden = Convert.FromHexString("8A011E0A0173120244321A09736561736F6E2D763122036366672A057374617473");
        Assert.True(wire.AsSpan().IndexOf(golden) >= 0, "Root tag 17 must contain the independent season-context golden.");
        var decoded = Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(wire).Payload);
        Assert.Equal(payload.Season, decoded.Season);
        Assert.Equal(payload.Player.PlayerId, decoded.Player.PlayerId);
    }

    [Fact]
    public void LegacyWireDoesNotInferTheCurrentSeason()
    {
        var payload = Projection(HeroClass.Mage, null);
        var envelope = new ServerEvent("room.snapshot", "trace", payload, Guid.NewGuid().ToString("D"), 1, DateTimeOffset.UnixEpoch);
        var decoded = Assert.IsType<RoomSnapshotEventPayload>(RealtimeProtobufCodec.DecodeServer(RealtimeProtobufCodec.EncodeServer(envelope)).Payload);
        Assert.Null(decoded.Season);
        Assert.Equal("legacy", decoded.ConfigVersion);
    }

    private static RoomSnapshotEventPayload Projection(HeroClass hero, SeasonContext? season)
    {
        var room = new BattleRoom(Guid.NewGuid(), season?.ConfigVersion ?? "legacy", CombatCardCatalog.CreatePrototype(), 73, season: season);
        var player = Guid.NewGuid();
        room.AddPlayer(new(player, hero, Enumerable.Range(1, 20).Select(i => $"common-{i:D2}").ToArray(), null));
        room.InitializeMap(ChaosMapGenerator.Generate(73, 1));
        return RoomSnapshotProjection.Build(new GetRoomClientStateCommand(player).Execute(room), player, Guid.NewGuid(), DateTimeOffset.UnixEpoch);
    }
}
