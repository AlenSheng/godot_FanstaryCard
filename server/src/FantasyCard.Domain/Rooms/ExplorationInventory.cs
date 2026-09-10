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
    EquipmentRewardData? Equipment = null,
    int SlotIndex = -1,
    bool? IsGenerated = null);

public sealed record PendingChoiceReplacement(
    Guid Token,
    ExplorationItem Replaced,
    ExplorationItem Added);

public sealed record ExplorationInventorySnapshot(
    int Capacity,
    int SafeSlots,
    IReadOnlyList<ExplorationItem> Items,
    PendingChoiceReplacement? PendingReplacement = null,
    IReadOnlyList<int>? SafeSlotIndexes = null);

public sealed class ExplorationInventory
{
    private readonly List<ExplorationItem> _items = [];
    private PendingChoiceReplacement? _pendingReplacement;

    public ExplorationInventory(int capacity, int safeSlots, IReadOnlyList<int>? safeSlotIndexes = null)
    {
        if (!GameConfigCatalog.Current.Backpacks.Any(item => item.Capacity == capacity && item.SafeSlots == safeSlots))
            throw new ArgumentOutOfRangeException(nameof(capacity), "Use a configured exploration inventory tier.");
        ArgumentOutOfRangeException.ThrowIfNegative(safeSlots);
        Capacity = capacity;
        SafeSlots = safeSlots;
        SafeSlotIndexes = (safeSlotIndexes ?? Enumerable.Range(capacity - safeSlots, safeSlots).ToArray()).ToArray();
        if (SafeSlotIndexes.Count != safeSlots || SafeSlotIndexes.Distinct().Count() != safeSlots ||
            SafeSlotIndexes.Any(index => index < 0 || index >= capacity))
            throw new ArgumentException("Safe slot indexes do not match the selected backpack.", nameof(safeSlotIndexes));
    }

    public int Capacity { get; }
    public int SafeSlots { get; }
    public IReadOnlyList<int> SafeSlotIndexes { get; }
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
        if (existing >= 0) return false;
        var slot = item.SlotIndex;
        if (slot < 0)
            slot = Enumerable.Range(0, Capacity).FirstOrDefault(index =>
                !_items.Any(value => value.SlotIndex == index) && (!item.IsSafe || SafeSlotIndexes.Contains(index)), -1);
        if (slot < 0 || slot >= Capacity || _items.Any(value => value.SlotIndex == slot)) return false;
        _items.Add(item with { SlotIndex = slot, IsSafe = SafeSlotIndexes.Contains(slot) });
        return true;
    }

    public bool TrySetSafe(string itemId, bool safe)
    {
        var index = _items.FindIndex(value => value.ItemId == itemId);
        if (index < 0) return false;
        if (_items[index].IsSafe == safe) return true;
        var target = Enumerable.Range(0, Capacity).FirstOrDefault(slot =>
            SafeSlotIndexes.Contains(slot) == safe && !_items.Any(item => item.SlotIndex == slot), -1);
        return target >= 0 && TryMove(itemId, target);
    }

    public bool TryMove(string itemId, int targetSlotIndex)
    {
        if (_pendingReplacement is not null || targetSlotIndex < 0 || targetSlotIndex >= Capacity) return false;
        var source = _items.FindIndex(item => item.ItemId == itemId);
        if (source < 0) return false;
        var sourceSlot = _items[source].SlotIndex;
        var target = _items.FindIndex(item => item.SlotIndex == targetSlotIndex);
        if (target == source) return true;
        if (target >= 0)
            _items[target] = _items[target] with { SlotIndex = sourceSlot, IsSafe = SafeSlotIndexes.Contains(sourceSlot) };
        _items[source] = _items[source] with { SlotIndex = targetSlotIndex, IsSafe = SafeSlotIndexes.Contains(targetSlotIndex) };
        return true;
    }

    internal void Apply(ExplorationInventory staged)
    {
        if (staged.Capacity != Capacity || !staged.SafeSlotIndexes.SequenceEqual(SafeSlotIndexes))
            throw new InvalidOperationException("Staged inventory has different slots.");
        _items.Clear();
        _items.AddRange(staged._items);
        _pendingReplacement = staged._pendingReplacement;
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
        if (!TryAdd(added with { SlotIndex = replaced.SlotIndex, IsSafe = replaced.IsSafe }))
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
        new(Capacity, SafeSlots, _items.ToArray(), _pendingReplacement, SafeSlotIndexes);

    public static ExplorationInventory Restore(ExplorationInventorySnapshot snapshot)
    {
        ArgumentNullException.ThrowIfNull(snapshot);
        var inventory = new ExplorationInventory(snapshot.Capacity, snapshot.SafeSlots, snapshot.SafeSlotIndexes);
        // Old snapshots used flags without slots; reserve their safe items before assigning other slots.
        IEnumerable<ExplorationItem> items = snapshot.Items.All(item => item.SlotIndex < 0)
            ? snapshot.Items.OrderByDescending(item => item.IsSafe)
            : snapshot.Items;
        foreach (var item in items)
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
