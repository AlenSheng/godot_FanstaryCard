using FantasyCard.Domain.Configuration;

namespace FantasyCard.Domain.Rooms;

public enum ExplorationItemKind
{
    Gold,
    WarriorSoul,
    ClassSoul,
    EquipmentFragments,
    HealthPotion,
    Equipment
}

public sealed record ExplorationItem(
    string ItemId,
    ExplorationItemKind Kind,
    int Quantity = 1,
    bool IsSafe = false,
    EquipmentRewardData? Equipment = null);

public sealed record PendingChoiceReplacement(
    Guid Token,
    ExplorationItem Replaced,
    ExplorationItem Added);

public sealed record ExplorationInventorySnapshot(
    int Capacity,
    int SafeSlots,
    IReadOnlyList<ExplorationItem> Items,
    PendingChoiceReplacement? PendingReplacement = null);

public sealed class ExplorationInventory
{
    private readonly List<ExplorationItem> _items = [];
    private PendingChoiceReplacement? _pendingReplacement;

    public ExplorationInventory(int capacity, int safeSlots)
    {
        if (!GameConfigCatalog.Current.Backpacks.Any(item => item.Capacity == capacity && item.SafeSlots == safeSlots))
            throw new ArgumentOutOfRangeException(nameof(capacity), "Use a configured exploration inventory tier.");
        ArgumentOutOfRangeException.ThrowIfNegative(safeSlots);
        Capacity = capacity;
        SafeSlots = safeSlots;
    }

    public int Capacity { get; }
    public int SafeSlots { get; }
    public IReadOnlyList<ExplorationItem> Items => _items;
    public int FreeSlots => Capacity - _items.Count;
    public PendingChoiceReplacement? PendingReplacement => _pendingReplacement;
    public int GoldQuantity => _items.Where(item => item.Kind == ExplorationItemKind.Gold).Sum(item => item.Quantity);

    public bool TryAdd(ExplorationItem item)
    {
        Validate(item);
        var existing = _items.FindIndex(value => value.Kind == item.Kind && value.ItemId == item.ItemId);
        if (item.Kind is not (ExplorationItemKind.Equipment or ExplorationItemKind.HealthPotion) && existing >= 0)
        {
            var current = _items[existing];
            _items[existing] = current with { Quantity = checked(current.Quantity + item.Quantity) };
            return true;
        }
        if (FreeSlots == 0) return false;
        _items.Add(item);
        return true;
    }

    public bool TrySetSafe(string itemId, bool safe)
    {
        var index = _items.FindIndex(value => value.ItemId == itemId);
        if (index < 0) return false;
        if (safe && !_items[index].IsSafe && _items.Count(value => value.IsSafe) >= SafeSlots) return false;
        _items[index] = _items[index] with { IsSafe = safe };
        return true;
    }

    public bool TryRemove(string itemId, out ExplorationItem? removed)
    {
        var index = _items.FindIndex(value => value.ItemId == itemId);
        if (index < 0) { removed = null; return false; }
        removed = _items[index];
        _items.RemoveAt(index);
        return true;
    }

    public int TrySpendGold(int amount)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(amount);
        var index = _items.FindIndex(item => item.Kind == ExplorationItemKind.Gold);
        if (index < 0) return amount;
        var current = _items[index];
        var spent = Math.Min(amount, current.Quantity);
        if (spent == current.Quantity) _items.RemoveAt(index);
        else _items[index] = current with { Quantity = current.Quantity - spent };
        return amount - spent;
    }

    public PendingChoiceReplacement BeginChoiceReplacement(string itemId, ExplorationItem added)
    {
        if (_pendingReplacement is not null) throw new InvalidOperationException("A choice replacement is already pending.");
        Validate(added);
        var index = _items.FindIndex(value => value.ItemId == itemId);
        if (index < 0) throw new InvalidOperationException("The replacement item was not found.");
        var replaced = _items[index];
        _items.RemoveAt(index);
        if (!TryAdd(added))
        {
            _items.Insert(index, replaced);
            throw new InvalidOperationException("The replacement item cannot be added.");
        }
        _pendingReplacement = new PendingChoiceReplacement(Guid.CreateVersion7(), replaced, added);
        return _pendingReplacement;
    }

    public ExplorationItem FinalizeChoiceReplacement(Guid token)
    {
        if (_pendingReplacement is not { } pending || pending.Token != token)
            throw new InvalidOperationException("The replacement token is not active.");
        _pendingReplacement = null;
        return pending.Replaced;
    }

    public void CancelChoiceReplacement(Guid token)
    {
        if (_pendingReplacement is not { } pending || pending.Token != token)
            throw new InvalidOperationException("The replacement token is not active.");
        var addedIndex = _items.FindIndex(value => value.ItemId == pending.Added.ItemId && value.Kind == pending.Added.Kind);
        if (addedIndex < 0) throw new InvalidOperationException("The pending replacement item is missing.");
        _items.RemoveAt(addedIndex);
        _items.Insert(Math.Min(addedIndex, _items.Count), pending.Replaced);
        _pendingReplacement = null;
    }

    public ExplorationInventorySnapshot Capture() =>
        new(Capacity, SafeSlots, _items.ToArray(), _pendingReplacement);

    public static ExplorationInventory Restore(ExplorationInventorySnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var inventory = new ExplorationInventory(snapshot.Capacity, snapshot.SafeSlots);
        foreach (var item in snapshot.Items)
        {
            if (!inventory.TryAdd(item)) throw new InvalidOperationException("The inventory snapshot exceeds its capacity.");
        }
        inventory._pendingReplacement = snapshot.PendingReplacement;
        return inventory;
    }

    private static void Validate(ExplorationItem item)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(item.ItemId);
        ArgumentOutOfRangeException.ThrowIfLessThanOrEqual(item.Quantity, 0);
    }
}
