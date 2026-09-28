using System.Numerics;
using System.Text.Json;
using FantasyCard.Domain.Configuration;
using FantasyCard.Domain.Rooms;

var options = SimulationOptions.Parse(args);
var analyzer = new RouteAnalyzer(GameConfigCatalog.Current);
var samples = Enumerable.Range(options.SeedStart, options.Samples)
    .Select(seed => analyzer.SimulateBossRush(seed, options.PlayerCount))
    .ToArray();

var summary = SimulationSummary.Create(
    GameConfigCatalog.Current.Version,
    options,
    samples,
    analyzer.MinimumEliteClearsToVisitMiddleCorners(3));

Console.WriteLine(JsonSerializer.Serialize(summary, new JsonSerializerOptions { WriteIndented = true }));

internal sealed class RouteAnalyzer(GameConfigCatalog config)
{
    public RouteSample SimulateBossRush(int seed, int playerCount)
    {
        var map = ChaosMapGenerator.Generate(seed, playerCount);
        var start = map.SpawnPositions[0];
        var route = ShortestPath(map, start, map.BossPosition);
        var loot = route.Select(position => ExpectedLoot(map.GetCell(position))).ToArray();
        var cells = route.Select(map.GetCell).ToArray();

        return new RouteSample(
            seed,
            route.Count,
            cells.Count(cell => cell.Layer == ChaosMapLayer.Outer),
            cells.Count(cell => cell.Layer == ChaosMapLayer.Middle && cell.MonsterGroupId.StartsWith("M", StringComparison.Ordinal)),
            cells.Count(cell => cell.Layer == ChaosMapLayer.Middle && cell.MonsterGroupId.StartsWith("E", StringComparison.Ordinal)),
            cells.Count(cell => cell.Layer == ChaosMapLayer.Core && !cell.IsBoss),
            cells.Count(cell => cell.IsBoss),
            cells.Count(cell => string.Equals(cell.MonsterGroupId, "BOX", StringComparison.Ordinal)),
            loot.Sum(value => value.Gold),
            loot.Sum(value => value.WarriorSoul),
            loot.Sum(value => value.ClassSoul),
            loot.Sum(value => value.Fragments));
    }

    public int MinimumEliteClearsToVisitMiddleCorners(int targetCornerCount)
    {
        if (targetCornerCount is < 1 or > 4)
            throw new ArgumentOutOfRangeException(nameof(targetCornerCount));

        var map = ChaosMapGenerator.Generate(0, 1);
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

        var queue = new PriorityQueue<RouteGeometryState, int>();
        var visited = new HashSet<RouteGeometryState>();
        foreach (var start in map.Cells.Where(cell => cell.Layer == ChaosMapLayer.Outer).Select(cell => cell.Position))
        {
            queue.Enqueue(new RouteGeometryState(start, 0, 0), 0);
        }

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

                var state = new RouteGeometryState(next, cornerMask, eliteMask);
                if (!visited.Contains(state))
                    queue.Enqueue(state, BitOperations.PopCount((uint)eliteMask));
            }
        }

        throw new InvalidOperationException("No legal route can satisfy the requested middle-corner target.");
    }

    private ExpectedLoot ExpectedLoot(ChaosMapCell cell)
    {
        var isBoss = cell.IsBoss || string.Equals(cell.MonsterGroupId, "BOSS", StringComparison.Ordinal);
        var loot = config.LootLayer(cell.Layer, isBoss);
        return new ExpectedLoot(
            loot.Gold,
            (loot.WarriorSoulMin + loot.WarriorSoulMax) / 2d,
            loot.ClassSoul,
            (loot.FragmentMin + loot.FragmentMax) / 2d);
    }

    private static IReadOnlyList<MapPosition> ShortestPath(ChaosMapState map, MapPosition start, MapPosition target)
    {
        var queue = new Queue<MapPosition>();
        var previous = new Dictionary<MapPosition, MapPosition?>();
        queue.Enqueue(start);
        previous[start] = null;

        while (queue.TryDequeue(out var current))
        {
            if (current == target)
                break;

            foreach (var next in map.GetNeighbors(current))
            {
                if (!map.CanMove(current, next) || previous.ContainsKey(next))
                    continue;
                previous[next] = current;
                queue.Enqueue(next);
            }
        }

        if (!previous.ContainsKey(target))
            throw new InvalidOperationException($"Boss position {target} is not reachable from spawn {start}.");

        var path = new List<MapPosition>();
        for (MapPosition? current = target; current is not null; current = previous[current.Value])
            path.Add(current.Value);
        path.Reverse();
        return path;
    }
}

internal sealed record SimulationOptions(int Samples, int SeedStart, int PlayerCount)
{
    public static SimulationOptions Parse(string[] args)
    {
        var samples = ReadInt(args, "--samples", 10_000);
        var seedStart = ReadInt(args, "--seed-start", 0);
        var players = ReadInt(args, "--players", 1);
        if (samples <= 0) throw new ArgumentOutOfRangeException(nameof(samples));
        if (players is < 1 or > 4) throw new ArgumentOutOfRangeException(nameof(players));
        return new SimulationOptions(samples, seedStart, players);
    }

    private static int ReadInt(string[] args, string name, int fallback)
    {
        var index = Array.IndexOf(args, name);
        if (index < 0) return fallback;
        if (index + 1 >= args.Length || !int.TryParse(args[index + 1], out var value))
            throw new ArgumentException($"{name} requires an integer value.");
        return value;
    }
}

internal sealed record ExpectedLoot(double Gold, double WarriorSoul, double ClassSoul, double Fragments);

internal readonly record struct RouteGeometryState(MapPosition Position, int CornerMask, int EliteMask);

internal sealed record RouteSample(
    int Seed,
    int ClearedCells,
    int OuterCells,
    int MiddleSmallCells,
    int MiddleEliteCells,
    int CoreEliteCells,
    int BossCells,
    int TreasureCells,
    double Gold,
    double WarriorSoul,
    double ClassSoul,
    double Fragments);

internal sealed record QuantileSummary(double P10, double P50, double P90, double Mean);

internal sealed record SimulationSummary(
    string ConfigVersion,
    int Samples,
    int SeedStart,
    int PlayerCount,
    string Strategy,
    int MinimumEliteClearsForThreeMiddleCorners,
    QuantileSummary ClearedCells,
    QuantileSummary MiddleEliteCells,
    QuantileSummary Gold,
    QuantileSummary WarriorSoul,
    QuantileSummary ClassSoul,
    QuantileSummary Fragments)
{
    public static SimulationSummary Create(
        string configVersion,
        SimulationOptions options,
        IReadOnlyList<RouteSample> samples,
        int minimumEliteClearsForThreeMiddleCorners) =>
        new(
            configVersion,
            options.Samples,
            options.SeedStart,
            options.PlayerCount,
            "VisibleBossShortestLegalPath",
            minimumEliteClearsForThreeMiddleCorners,
            Quantiles(samples.Select(sample => (double)sample.ClearedCells)),
            Quantiles(samples.Select(sample => (double)sample.MiddleEliteCells)),
            Quantiles(samples.Select(sample => sample.Gold)),
            Quantiles(samples.Select(sample => sample.WarriorSoul)),
            Quantiles(samples.Select(sample => sample.ClassSoul)),
            Quantiles(samples.Select(sample => sample.Fragments)));

    private static QuantileSummary Quantiles(IEnumerable<double> values)
    {
        var sorted = values.Order().ToArray();
        if (sorted.Length == 0) throw new InvalidOperationException("Simulation produced no samples.");
        return new QuantileSummary(
            At(sorted, .10),
            At(sorted, .50),
            At(sorted, .90),
            sorted.Average());
    }

    private static double At(IReadOnlyList<double> sorted, double percentile)
    {
        var index = (int)Math.Round((sorted.Count - 1) * percentile, MidpointRounding.AwayFromZero);
        return sorted[index];
    }
}
