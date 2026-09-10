using FantasyCard.Domain.Combat;

namespace FantasyCard.Domain.Rooms;

public enum ChaosMapLayer : byte { Outer = 0, Middle = 1, Core = 2 }

public readonly record struct MapPosition(int Row, int Column)
{
    public int ManhattanDistance(MapPosition other) => Math.Abs(Row - other.Row) + Math.Abs(Column - other.Column);
}

public sealed record ChaosMapCell(MapPosition Position, ChaosMapLayer Layer, bool IsBoss, bool HasSpring, bool HasEvacuation,
    string MonsterGroupId = "O1", CardElement? TreasureElement = null);
public sealed record ChaosMapSnapshot(
    IReadOnlyList<ChaosMapCell> Cells,
    MapPosition BossPosition,
    IReadOnlyList<MapPosition> SpawnPositions,
    IReadOnlyList<MapPosition>? ConsumedSprings = null);
public sealed record SpringDrinkSnapshot(MapPosition Position, TimeSpan Remaining);
public sealed record MapCellProjection(MapPosition Position, ChaosMapLayer Layer, bool IsBoss, bool HasSpring);
public sealed record CurrentCellProjection(bool HasEvacuation, string MonsterGroupId, bool SpringConsumed);
public sealed record ChaosMapProjection(
    IReadOnlyList<MapCellProjection> Cells,
    MapPosition Self,
    IReadOnlyList<MapPosition> LegalMoves,
    CurrentCellProjection CurrentCell);

public sealed class ChaosMapState
{
    private readonly Dictionary<MapPosition, ChaosMapCell> _cells;

    internal ChaosMapState(
        IReadOnlyList<ChaosMapCell> cells,
        MapPosition bossPosition,
        IReadOnlyList<MapPosition> spawnPositions)
    {
        Cells = cells;
        BossPosition = bossPosition;
        SpawnPositions = spawnPositions;
        _cells = cells.ToDictionary(cell => cell.Position);
    }

    public IReadOnlyList<ChaosMapCell> Cells { get; }
    public MapPosition BossPosition { get; }
    public IReadOnlyList<MapPosition> SpawnPositions { get; }

    public ChaosMapCell GetCell(MapPosition position) =>
        _cells.TryGetValue(position, out var cell)
            ? cell
            : throw new ArgumentOutOfRangeException(nameof(position));

    public IReadOnlyList<MapPosition> GetNeighbors(MapPosition position) =>
        new MapPosition[]
        {
            new(position.Row - 1, position.Column),
            new(position.Row + 1, position.Column),
            new(position.Row, position.Column - 1),
            new(position.Row, position.Column + 1)
        }.Where(_cells.ContainsKey).ToArray();

    public bool CanMove(MapPosition from, MapPosition to) =>
        _cells.ContainsKey(to) &&
        GetNeighbors(from).Contains(to) &&
        GetCell(to).Layer >= GetCell(from).Layer;

    // ConsumedSprings is retained in the snapshot contract only for migration from
    // the old room-global spring model. New snapshots always persist an empty list;
    // per-player usage is owned by RoomPlayerSnapshot.
    public ChaosMapSnapshot Capture() => new(Cells, BossPosition, SpawnPositions, []);

    public static ChaosMapState Restore(ChaosMapSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        return new ChaosMapState(snapshot.Cells, snapshot.BossPosition, snapshot.SpawnPositions);
    }
}

public static class ChaosMapGenerator
{
    public static ChaosMapState Generate(int seed, int playerCount)
    {
        if (playerCount is < 1 or > 4) throw new ArgumentOutOfRangeException(nameof(playerCount));
        var random = new Random(seed);
        var positions = Enumerable.Range(0, 6)
            .SelectMany(row => Enumerable.Range(0, 6).Select(column => new MapPosition(row, column)))
            .ToArray();
        var layers = positions.ToDictionary(position => position, LayerOf);
        var core = positions.Where(position => layers[position] == ChaosMapLayer.Core).ToArray();
        var boss = core[random.Next(core.Length)];
        var springs = new HashSet<MapPosition>();
        AddRandom(random, springs, positions.Where(p => layers[p] == ChaosMapLayer.Outer).ToArray(), WeightedCount(random, 2, 3, 4, 35, 45));
        AddRandom(random, springs, positions.Where(p => layers[p] == ChaosMapLayer.Middle).ToArray(), WeightedCount(random, 1, 2, 80));
        AddRandom(random, springs, core.Where(p => p != boss).ToArray(), WeightedCount(random, 0, 1, 75));
        var evacuationCandidates = positions.Where(p => layers[p] != ChaosMapLayer.Core).ToArray();
        var evacuations = new HashSet<MapPosition>();
        AddRandom(random, evacuations, evacuationCandidates, random.Next(1, 3));
        var spawnPositions = PickSpawns(random, positions.Where(p => layers[p] == ChaosMapLayer.Outer).ToArray(), playerCount);
        var cells = positions.Select(position => new ChaosMapCell(
            position, layers[position], position == boss, springs.Contains(position), evacuations.Contains(position),
            position == boss ? "BOSS" : GroupFor(random, layers[position], position, spawnPositions.Contains(position)))).ToArray();
        // Keep existing map rolls stable while pinning each treasure's position and element once.
        var treasureRandom = new Random(unchecked(seed ^ 0x54524541));
        var treasureCount = RollTreasureCount(treasureRandom.Next(100));
        var treasurePositions = new HashSet<MapPosition>();
        AddRandom(treasureRandom, treasurePositions, positions.Where(p => layers[p] == ChaosMapLayer.Outer).ToArray(), treasureCount);
        for (var index = 0; index < cells.Length; index++)
        {
            if (treasurePositions.Contains(cells[index].Position))
                cells[index] = cells[index] with { MonsterGroupId = "BOX", TreasureElement = RollTreasureElement(treasureRandom.Next(100)) };
        }
        return new ChaosMapState(cells, boss, spawnPositions);
    }

    public static int RollTreasureCount(int roll)
    {
        if (roll is < 0 or > 99) throw new ArgumentOutOfRangeException(nameof(roll));
        return roll < 40 ? 0 : roll < 75 ? 1 : roll < 95 ? 2 : 3;
    }

    public static CardElement RollTreasureElement(int roll)
    {
        if (roll is < 0 or > 99) throw new ArgumentOutOfRangeException(nameof(roll));
        return roll < 80 ? (CardElement)(roll / 16 + 1) : CardElement.None;
    }

    private static ChaosMapLayer LayerOf(MapPosition position)
    {
        var ring = Math.Min(Math.Min(position.Row, 5 - position.Row), Math.Min(position.Column, 5 - position.Column));
        return ring == 0 ? ChaosMapLayer.Outer : ring == 1 ? ChaosMapLayer.Middle : ChaosMapLayer.Core;
    }

    private static int WeightedCount(Random random, int first, int second, int third, int firstWeight, int secondWeight)
    {
        var roll = random.Next(100);
        if (roll < firstWeight) return first;
        if (roll < firstWeight + secondWeight) return second;
        return third;
    }

    private static int WeightedCount(Random random, int first, int second, int firstWeight) => random.Next(100) < firstWeight ? first : second;

    private static string GroupFor(Random random, ChaosMapLayer layer, MapPosition position, bool isSpawn) => layer switch
    {
        ChaosMapLayer.Outer => $"O{random.Next(1, isSpawn ? 6 : 9)}",
        ChaosMapLayer.Middle when position.Row is 1 or 4 && position.Column is 1 or 4 => $"M{random.Next(1, 6)}",
        _ => $"E{random.Next(1, 7)}"
    };

    private static void AddRandom(Random random, HashSet<MapPosition> destination, IReadOnlyList<MapPosition> source, int count)
    {
        foreach (var position in source.OrderBy(_ => random.Next()).Take(count)) destination.Add(position);
    }

    private static List<MapPosition> PickSpawns(Random random, IReadOnlyList<MapPosition> outer, int count)
    {
        var candidates = outer.OrderBy(_ => random.Next()).ToList();
        var result = new List<MapPosition> { candidates[0] };
        while (result.Count < count)
        {
            result.Add(candidates.OrderByDescending(candidate => result.Min(existing => candidate.ManhattanDistance(existing))).First(candidate => !result.Contains(candidate)));
        }
        return result;
    }
}
