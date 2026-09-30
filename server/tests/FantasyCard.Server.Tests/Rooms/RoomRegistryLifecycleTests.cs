using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;
using FantasyCard.Server.Rooms;

namespace FantasyCard.Server.Tests.Rooms;

public sealed class RoomRegistryLifecycleTests
{
    [Fact]
    public async Task SettledPlayerCanJoinNextRoomWhileTeammatesRemainInFormerRoom()
    {
        var playerId = Guid.NewGuid();
        var teammateId = Guid.NewGuid();
        var former = CreateRoom(playerId, teammateId);
        var next = CreateRoom(playerId);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(former, startTicker: false);

        var terminal = former.Capture() with
        {
            Players = former.Capture().Players.Select(player =>
                player.PlayerId == playerId ? player with { Phase = RoomPlayerPhase.Extracted } : player).ToArray()
        };
        registry.ReleaseTerminalPlayers(terminal);
        registry.Register(next, startTicker: false);

        Assert.True(registry.TryGetForPlayer(playerId, out var routed));
        Assert.Equal(next.RoomId, routed!.RoomId);
        Assert.True(registry.TryGetForPlayer(teammateId, out var teammate));
        Assert.Equal(former.RoomId, teammate!.RoomId);
        registry.ReleaseTerminalPlayers(terminal);
        Assert.True(registry.TryGetForPlayer(playerId, out routed));
        Assert.Equal(next.RoomId, routed!.RoomId);
        await registry.RemoveAsync(former.RoomId);
        Assert.True(registry.TryGetForPlayer(playerId, out routed));
        Assert.Equal(next.RoomId, routed!.RoomId);
    }

    [Fact]
    public async Task RecoveredTerminalPlayerDoesNotReserveAnActiveRoomRoute()
    {
        var playerId = Guid.NewGuid();
        var former = CreateRoom(playerId);
        var snapshot = former.Capture() with
        {
            Players = former.Capture().Players.Select(player =>
                player with { Phase = RoomPlayerPhase.Dead }).ToArray()
        };
        var recovered = BattleRoom.Restore(snapshot, Catalog(), 17);
        await using var registry = new RoomRegistry(TimeProvider.System);
        registry.Register(recovered, startTicker: false);
        Assert.False(registry.TryGetForPlayer(playerId, out _));

        var next = CreateRoom(playerId);
        registry.Register(next, startTicker: false);
        Assert.True(registry.TryGetForPlayer(playerId, out var routed));
        Assert.Equal(next.RoomId, routed!.RoomId);
    }

    private static CombatCardCatalog Catalog() =>
        new([new("test-hit", new CombatCardEffect(DirectDamage: 1))]);

    private static BattleRoom CreateRoom(params Guid[] playerIds)
    {
        var room = new BattleRoom(Guid.NewGuid(), "test", Catalog(), seed: 17);
        foreach (var playerId in playerIds)
            room.AddPlayer(new(playerId, HeroClass.Mage,
                Enumerable.Repeat("test-hit", 20).ToArray(), null));
        return room;
    }
}
