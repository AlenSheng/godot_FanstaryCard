using FantasyCard.Contracts.Realtime;
using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Mail;
using FantasyCard.Server.Realtime;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Realtime;

public sealed class LocalizedNameProjectionTests
{
    [Theory]
    [InlineData(null, true)]
    [InlineData("旅人", false)]
    [InlineData("Gold", false)]
    [InlineData("", false)]
    [InlineData(" Fire  Gold / 装备 ", false)]
    public async Task Relic_list_and_router_only_mark_a_real_null_fallback(string? owner, bool fallback)
    {
        var playerId = Guid.NewGuid();
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 37);
        room.AddPlayer(new(playerId, HeroClass.Mage, Cards(), null, DisplayName: "Viewer"));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 1));
        var snapshot = room.Capture();
        var player = Assert.Single(snapshot.Players);
        var pile = new RelicPileSnapshot(Guid.NewGuid(), Guid.NewGuid().ToString("D"), player.Position!.Value,
            1, [new("gold", ExplorationItemKind.Gold, 1)], owner);
        room = BattleRoom.Restore(snapshot with
        {
            Players = [player with { Phase = RoomPlayerPhase.ActionBar, Pve = null }], RelicPiles = [pile]
        }, catalog, 37);
        var projection = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(playerId).Execute(room),
            playerId, null, DateTimeOffset.UnixEpoch);
        var listed = Assert.Single(projection.CurrentCell.RelicPiles!);
        Assert.Equal(fallback, listed.OwnerNameIsFallback);
        Assert.Equal(owner ?? SystemMailCatalog.Current.TravelerFallback, listed.OwnerName);

        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(room, startTicker: false);
        var router = new RealtimeCommandRouter(new RealtimeEventStore(TimeProvider.System), TimeProvider.System, registry);
        var result = await router.RouteAsync(PlayerProfile.Create(playerId, "Viewer", DateTimeOffset.UnixEpoch),
            new("relic.read", "read-localized-name", room.Revision, new RelicReadCommandPayload(pile.PileId)),
            "test", TestContext.Current.CancellationToken);
        var contents = Assert.IsType<RoomRelicPilePayload>(Assert.Single(result).Payload);
        Assert.Equal(listed.OwnerName, contents.OwnerName);
        Assert.Equal(fallback, contents.OwnerNameIsFallback);
        Assert.Single(contents.Items);
        Assert.Equal(projection.RoomRevision, room.Revision);
    }

    [Theory]
    [InlineData(null, true)]
    [InlineData("旅人", false)]
    [InlineData("Gold", false)]
    public void Relic_can_resolve_the_real_player_name_without_reclassifying_it(string? name, bool fallback)
    {
        var playerId = Guid.NewGuid();
        var room = new BattleRoom(Guid.NewGuid(), "test", CombatCardCatalog.CreatePrototype(), 37);
        room.AddPlayer(new(playerId, HeroClass.Mage, Cards(), null, DisplayName: name));
        var pile = new RelicPileSnapshot(Guid.NewGuid(), playerId.ToString("D"), new(0, 0), 1, []);
        var result = RoomSnapshotProjection.ToRelicPile(pile, room.Capture().Players, []);
        Assert.Equal(name ?? SystemMailCatalog.Current.TravelerFallback, result.OwnerName);
        Assert.Equal(fallback, result.OwnerNameIsFallback);
    }

    [Theory]
    [InlineData(null, true)]
    [InlineData("旅人", false)]
    [InlineData("Gold", false)]
    [InlineData("", false)]
    public void Duel_projection_preserves_real_names_and_marks_only_null(string? opponentName, bool fallback)
    {
        var viewer = Guid.NewGuid();
        var opponent = Guid.NewGuid();
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "test", catalog, 37);
        room.AddPlayer(new(viewer, HeroClass.Mage, Cards(), null, DisplayName: "Viewer"));
        room.AddPlayer(new(opponent, HeroClass.Priest, Cards(), null, DisplayName: opponentName));
        room.InitializeMap(ChaosMapGenerator.Generate(37, 2));
        var snapshot = room.Capture();
        var position = snapshot.Players[0].Position;
        room = BattleRoom.Restore(snapshot with
        {
            Players = snapshot.Players.Select(player => player with
            { Position = position, Phase = RoomPlayerPhase.ActionBar, Pve = null }).ToArray()
        }, catalog, 37);
        room.StartDuel(viewer, opponent, DateTimeOffset.UnixEpoch);
        var projection = RoomSnapshotProjection.Build(new GetRoomClientStateCommand(viewer).Execute(room),
            viewer, null, DateTimeOffset.UnixEpoch);
        Assert.Equal(opponentName ?? SystemMailCatalog.Current.TravelerFallback, projection.Duel!.OpponentName);
        Assert.Equal(fallback, projection.Duel.OpponentNameIsFallback);
    }

    private static string[] Cards() => Enumerable.Range(1, 20).Select(index => $"C{index:D2}").ToArray();
}
