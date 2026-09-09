using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class ChaosMapTests
{
    [Fact]
    public void Generate_is_deterministic_and_has_three_rings()
    {
        var first = ChaosMapGenerator.Generate(12345, 4);
        var second = ChaosMapGenerator.Generate(12345, 4);

        Assert.Equivalent(first.Cells, second.Cells, strict: true);
        Assert.Equal(first.SpawnPositions, second.SpawnPositions);
        Assert.Equal(20, first.Cells.Count(cell => cell.Layer == ChaosMapLayer.Outer));
        Assert.Equal(12, first.Cells.Count(cell => cell.Layer == ChaosMapLayer.Middle));
        Assert.Equal(4, first.Cells.Count(cell => cell.Layer == ChaosMapLayer.Core));
        Assert.Single(first.Cells, cell => cell.IsBoss);
        Assert.Equal(4, first.SpawnPositions.Distinct().Count());
    }

    [Fact]
    public void CanMove_allows_same_ring_and_inward_but_not_outward()
    {
        var map = ChaosMapGenerator.Generate(17, 1);
        var outer = map.Cells.Single(cell => cell.Layer == ChaosMapLayer.Outer && cell.Position.Row == 0 && cell.Position.Column == 2).Position;
        var inward = new MapPosition(1, 2);
        var outward = new MapPosition(0, 1);

        Assert.True(map.CanMove(outer, inward));
        Assert.True(map.CanMove(outer, outward));
        Assert.False(map.CanMove(inward, outer));
    }

    [Fact]
    public void Map_snapshot_keeps_spring_layout_but_no_longer_owns_consumption()
    {
        var map = ChaosMapGenerator.Generate(99, 1);
        Assert.Contains(map.Cells, cell => cell.HasSpring);
        var restored = ChaosMapState.Restore(map.Capture());

        Assert.Equivalent(map.Cells, restored.Cells, strict: true);
        Assert.Empty(restored.Capture().ConsumedSprings!);
    }
}
