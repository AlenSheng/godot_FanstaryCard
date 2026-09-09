namespace FantasyCard.Domain.Rooms;

public sealed record RelicPileSnapshot(
    Guid PileId,
    string VictimId,
    MapPosition Position,
    long Version,
    IReadOnlyList<ExplorationItem> Items);

public sealed class RelicPile
{
    private readonly List<ExplorationItem> _items = [];

    public RelicPile(Guid pileId, string victimId, MapPosition position)
    {
        if (pileId == Guid.Empty) throw new ArgumentException("Pile id cannot be empty.", nameof(pileId));
        ArgumentException.ThrowIfNullOrWhiteSpace(victimId);
        PileId = pileId;
        VictimId = victimId;
        Position = position;
    }

    public Guid PileId { get; }
    public string VictimId { get; }
    public MapPosition Position { get; }
    public long Version { get; private set; } = 1;
    public IReadOnlyList<ExplorationItem> Items => _items;

    public void Add(ExplorationItem item)
    {
        if (item.Kind is not (ExplorationItemKind.Equipment or ExplorationItemKind.HealthPotion) &&
            _items.FindIndex(value => value.Kind == item.Kind && value.ItemId == item.ItemId) is var existing && existing >= 0)
        {
            _items[existing] = _items[existing] with { Quantity = checked(_items[existing].Quantity + item.Quantity) };
        }
        else
        {
            _items.Add(item);
        }
        Version++;
    }

    public bool TryTake(string itemId, long expectedVersion, out ExplorationItem? item)
    {
        if (expectedVersion != Version) throw new InvalidOperationException("The relic pile changed. Reload and retry.");
        var index = _items.FindIndex(value => value.ItemId == itemId);
        if (index < 0) { item = null; return false; }
        item = _items[index];
        _items.RemoveAt(index);
        Version++;
        return true;
    }

    public bool TakeToInventory(ExplorationInventory inventory, string itemId, long expectedVersion, string? replaceItemId = null)
    {
        ArgumentNullException.ThrowIfNull(inventory);
        if (!TryTake(itemId, expectedVersion, out var taken)) return false;
        ExplorationItem? replaced = null;
        if (replaceItemId is not null && !inventory.TryRemove(replaceItemId, out replaced))
        {
            Add(taken!);
            return false;
        }
        if (!inventory.TryAdd(taken!))
        {
            if (replaced is not null) inventory.TryAdd(replaced);
            Add(taken!);
            return false;
        }
        if (replaced is not null) Add(replaced);
        return true;
    }

    public RelicPileSnapshot Capture() => new(PileId, VictimId, Position, Version, _items.ToArray());

    public static RelicPile Restore(RelicPileSnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var pile = new RelicPile(snapshot.PileId, snapshot.VictimId, snapshot.Position);
        pile._items.AddRange(snapshot.Items);
        pile.Version = snapshot.Version;
        return pile;
    }
}
