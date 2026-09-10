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
    public void Every_non_treasure_spawn_has_a_single_outer_monster_for_the_whole_room()
    {
        for (var seed = 0; seed < 100; seed++)
        {
            var map = ChaosMapGenerator.Generate(seed, 4);
            foreach (var position in map.SpawnPositions)
            {
                var cell = map.GetCell(position);
                if (cell.MonsterGroupId == "BOX") continue;
                Assert.StartsWith("O", cell.MonsterGroupId, StringComparison.Ordinal);
                Assert.InRange(int.Parse(cell.MonsterGroupId.AsSpan(1), System.Globalization.CultureInfo.InvariantCulture), 1, 5);
                Assert.Single(FantasyCard.Domain.Combat.PveBattleFactory.Create(cell).Monsters);
            }
        }
    }

    [Fact]
    public void Middle_cells_adjacent_to_the_core_use_elites_and_four_corners_use_middle_groups()
    {
        for (var seed = 0; seed < 100; seed++)
        {
            var map = ChaosMapGenerator.Generate(seed, 4);
            var middle = map.Cells.Where(cell => cell.Layer == ChaosMapLayer.Middle).ToArray();
            Assert.Equal(8, middle.Count(cell => cell.MonsterGroupId.StartsWith('E')));
            Assert.Equal(4, middle.Count(cell => cell.MonsterGroupId.StartsWith('M')));
            foreach (var cell in middle)
            {
                var neighborsCore = map.GetNeighbors(cell.Position).Any(position => map.GetCell(position).Layer == ChaosMapLayer.Core);
                Assert.StartsWith(neighborsCore ? "E" : "M", cell.MonsterGroupId, StringComparison.Ordinal);
                Assert.InRange(int.Parse(cell.MonsterGroupId.AsSpan(1), System.Globalization.CultureInfo.InvariantCulture), 1, neighborsCore ? 6 : 5);
            }
        }
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
