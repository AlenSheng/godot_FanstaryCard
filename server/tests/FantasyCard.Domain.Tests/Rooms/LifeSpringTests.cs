using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class LifeSpringTests
{
    [Theory]
    [InlineData(ChaosMapLayer.Outer, 18)]
    [InlineData(ChaosMapLayer.Middle, 25)]
    [InlineData(ChaosMapLayer.Core, 35)]
    public void Spring_completes_after_1_2_seconds_and_heals_by_layer(ChaosMapLayer layer, int percent)
    {
        var playerId = Guid.NewGuid();
        var room = CreateAtSpring([playerId], layer);
        var player = room.GetPlayer(playerId);
        player.Combat.TakeDamage(player.Combat.MaximumHp - 1);

        Assert.Equal(TimeSpan.FromSeconds(1.2), room.RequestSpring(playerId));
        room.Advance(TimeSpan.FromSeconds(1.1));
        Assert.Equal(1, player.Combat.Hp);
        Assert.False(room.GetMapProjection(playerId).CurrentCell.SpringConsumed);

        room.Advance(TimeSpan.FromSeconds(0.1));

        Assert.Equal(1 + (int)Math.Floor(player.Combat.MaximumHp * percent / 100d), player.Combat.Hp);
        Assert.True(room.GetMapProjection(playerId).CurrentCell.SpringConsumed);
    }

    [Fact]
    public void Players_consume_the_same_spring_independently_and_full_health_still_consumes_it()
    {
        var firstId = Guid.NewGuid();
        var secondId = Guid.NewGuid();
        var room = CreateAtSpring([firstId, secondId], ChaosMapLayer.Outer);
        var second = room.GetPlayer(secondId);
        second.Combat.TakeDamage(20);

        room.RequestSpring(firstId);
        room.Advance(TimeSpan.FromSeconds(1.2));

        Assert.True(room.GetMapProjection(firstId).CurrentCell.SpringConsumed);
        Assert.False(room.GetMapProjection(secondId).CurrentCell.SpringConsumed);
        Assert.Equal(room.GetPlayer(firstId).Combat.MaximumHp, room.GetPlayer(firstId).Combat.Hp);
        Assert.Throws<DomainValidationException>(() => room.RequestSpring(firstId));

        var before = second.Combat.Hp;
        room.RequestSpring(secondId);
        room.Advance(TimeSpan.FromSeconds(1.2));
        Assert.True(room.GetMapProjection(secondId).CurrentCell.SpringConsumed);
        Assert.True(second.Combat.Hp > before);
    }

    [Fact]
    public void Pvp_pairing_interrupts_spring_without_healing_or_consuming_it()
    {
        var firstId = Guid.NewGuid();
        var secondId = Guid.NewGuid();
        var room = CreateAtSpring([firstId, secondId], ChaosMapLayer.Middle);
        var first = room.GetPlayer(firstId);
        first.Combat.TakeDamage(30);
        var hp = first.Combat.Hp;

        room.RequestSpring(firstId);
        var duel = room.StartDuel(firstId, secondId, DateTimeOffset.UnixEpoch);
        room.Advance(TimeSpan.FromSeconds(2));
        room.EndDuelSurvived(duel.DuelId, DuelEndReason.MutualLeave);

        Assert.Equal(hp, first.Combat.Hp);
        Assert.False(room.GetMapProjection(firstId).CurrentCell.SpringConsumed);
        Assert.Null(room.CapturePlayer(firstId).SpringDrink);
    }

    [Fact]
    public void Active_spring_read_round_trips_with_its_remaining_time()
    {
        var playerId = Guid.NewGuid();
        var room = CreateAtSpring([playerId], ChaosMapLayer.Core);
        room.GetPlayer(playerId).Combat.TakeDamage(40);
        room.RequestSpring(playerId);
        room.Advance(TimeSpan.FromMilliseconds(450));
        var snapshot = room.Capture();

        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 992);

        Assert.Equivalent(snapshot, restored.Capture(), strict: true);
        restored.Advance(TimeSpan.FromMilliseconds(750));
        Assert.True(restored.GetMapProjection(playerId).CurrentCell.SpringConsumed);
    }

    [Fact]
    public void Legacy_global_consumption_is_conservatively_migrated_to_every_player()
    {
        var firstId = Guid.NewGuid();
        var secondId = Guid.NewGuid();
        var room = CreateAtSpring([firstId, secondId], ChaosMapLayer.Outer);
        var snapshot = room.Capture();
        var spring = snapshot.Players[0].Position!.Value;
        snapshot = snapshot with
        {
            Map = snapshot.Map! with { ConsumedSprings = [spring] },
            Players = snapshot.Players.Select(player => player with { ConsumedSprings = null }).ToArray()
        };

        var restored = BattleRoom.Restore(snapshot, CombatCardCatalog.CreatePrototype(), 993);

        Assert.All(restored.Capture().Players, player => Assert.Contains(spring, player.ConsumedSprings!));
        Assert.True(restored.GetMapProjection(firstId).CurrentCell.SpringConsumed);
        Assert.True(restored.GetMapProjection(secondId).CurrentCell.SpringConsumed);
    }

    private static BattleRoom CreateAtSpring(IReadOnlyList<Guid> playerIds, ChaosMapLayer layer)
    {
        var catalog = CombatCardCatalog.CreatePrototype();
        var room = new BattleRoom(Guid.NewGuid(), "spring-test", catalog, 991);
        foreach (var (playerId, index) in playerIds.Select((id, index) => (id, index)))
        {
            room.AddPlayer(new BattleRoomPlayerSetup(
                playerId,
                index == 0 ? HeroClass.Mage : HeroClass.Guardian,
                Enumerable.Range(1, 20).Select(card => $"common-{card:D2}").ToArray(),
                null));
        }
        room.InitializeMap(ChaosMapGenerator.Generate(991, playerIds.Count));
        var snapshot = room.Capture();
        var target = snapshot.Map!.Cells.First(cell => cell.Layer == layer && !cell.IsBoss).Position;
        snapshot = snapshot with
        {
            Map = snapshot.Map with
            {
                Cells = snapshot.Map.Cells.Select(cell =>
                    cell.Position == target ? cell with { HasSpring = true } : cell).ToArray()
            },
            Players = snapshot.Players.Select(player => player with
            {
                Position = target,
                Phase = RoomPlayerPhase.ActionBar,
                Pve = null
            }).ToArray()
        };
        return BattleRoom.Restore(snapshot, catalog, 991);
    }
}
