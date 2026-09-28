using System.Numerics;
using FantasyCard.Domain.Rooms;

namespace FantasyCard.Domain.Tests.Rooms;

public sealed class RouteGeometryRegressionTests
{
    [Fact]
    public void Middle_ring_has_four_small_corners_and_eight_elite_cells()
    {
        var map = ChaosMapGenerator.Generate(123, 1);

        var middle = map.Cells.Where(cell => cell.Layer == ChaosMapLayer.Middle).ToArray();

        Assert.Equal(12, middle.Length);
        Assert.Equal(4, middle.Count(cell => cell.MonsterGroupId.StartsWith("M", StringComparison.Ordinal)));
        Assert.Equal(8, middle.Count(cell => cell.MonsterGroupId.StartsWith("E", StringComparison.Ordinal)));
    }

    [Fact]
    public void Visiting_three_distinct_middle_small_corners_requires_at_least_four_unique_elite_cells()
    {
        var map = ChaosMapGenerator.Generate(0, 1);

        var minimum = MinimumEliteClearsToVisitMiddleCorners(map, 3);

        Assert.Equal(4, minimum);
    }

    private static int MinimumEliteClearsToVisitMiddleCorners(ChaosMapState map, int targetCornerCount)
    {
        var corners = map.Cells
            .Where(cell => cell.Layer == ChaosMapLayer.Middle && cell.MonsterGroupId.StartsWith("M", StringComparison.Ordinal))
            .Select(cell => cell.Position)
            .OrderBy(position => position.Row)
            .ThenBy(position => position.Column)
            .ToArray();
        var elites = map.Cells
            .Where(cell => cell.Layer == ChaosMapLayer.Middle && cell.MonsterGroupId.StartsWith("E", StringComparison.Ordinal))
            .Select(cell => cell.Position)
            .OrderBy(position => position.Row)
            .ThenBy(position => position.Column)
            .ToArray();

        var cornerIndex = corners.Select((position, index) => (position, index))
            .ToDictionary(value => value.position, value => value.index);
        var eliteIndex = elites.Select((position, index) => (position, index))
            .ToDictionary(value => value.position, value => value.index);

        var queue = new PriorityQueue<RouteState, int>();
        var visited = new HashSet<RouteState>();
        foreach (var start in map.Cells.Where(cell => cell.Layer == ChaosMapLayer.Outer).Select(cell => cell.Position))
            queue.Enqueue(new RouteState(start, 0, 0), 0);

        while (queue.TryDequeue(out var current, out _))
        {
            if (!visited.Add(current))
                continue;
            if (BitOperations.PopCount((uint)current.CornerMask) >= targetCornerCount)
                return BitOperations.PopCount((uint)current.EliteMask);

            foreach (var next in map.GetNeighbors(current.Position))
            {
                if (!map.CanMove(current.Position, next))
                    continue;

                var cornerMask = current.CornerMask;
                if (cornerIndex.TryGetValue(next, out var cornerBit))
                    cornerMask |= 1 << cornerBit;

                var eliteMask = current.EliteMask;
                if (eliteIndex.TryGetValue(next, out var eliteBit))
                    eliteMask |= 1 << eliteBit;

                var state = new RouteState(next, cornerMask, eliteMask);
                if (!visited.Contains(state))
                    queue.Enqueue(state, BitOperations.PopCount((uint)eliteMask));
            }
        }

        throw new InvalidOperationException("No legal route reached the requested number of middle corners.");
    }

    private readonly record struct RouteState(MapPosition Position, int CornerMask, int EliteMask);
}
