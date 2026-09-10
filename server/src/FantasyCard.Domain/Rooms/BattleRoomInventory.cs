using FantasyCard.Domain.Combat;
using FantasyCard.Domain.Players;

namespace FantasyCard.Domain.Rooms;

public sealed partial class BattleRoom
{
    public long MoveInventoryItem(Guid playerId, string itemId, int targetSlotIndex)
    {
        var player = GetInventoryPlayer(playerId);
        if (!player.Inventory.TryMove(itemId, targetSlotIndex))
            throw new DomainValidationException("The inventory item or destination slot is not available.");
        return ++Revision;
    }

    public long EquipInventoryItem(Guid playerId, string itemId)
    {
        var player = GetInventoryPlayer(playerId);
        var item = player.Inventory.Items.SingleOrDefault(value => value.ItemId == itemId)
            ?? throw new DomainValidationException("The equipment is not in the backpack.");
        var (armor, previous, profile) = PrepareEquipmentChange(player, item);
        var staged = ExplorationInventory.Restore(player.Inventory.Capture());
        if (!staged.TryRemove(itemId, out _) || previous is not null &&
            !staged.TryAdd(previous with { SlotIndex = item.SlotIndex, IsSafe = item.IsSafe }))
            throw new DomainValidationException("The previous equipment cannot be returned to the backpack.");
        player.Inventory.Apply(staged);
        player.WornArmor = armor;
        player.Combat.UpdateEquipment(profile);
        return ++Revision;
    }

    public long UnequipArmor(Guid playerId, string slot)
    {
        var player = GetInventoryPlayer(playerId);
        var previous = player.WornArmor.SingleOrDefault(item => item.Equipment?.Slot == slot)
            ?? throw new DomainValidationException("There is no armor in that slot.");
        var armor = player.WornArmor.Where(item => item.ItemId != previous.ItemId).ToArray();
        var profile = CalculateArmor(armor);
        var staged = ExplorationInventory.Restore(player.Inventory.Capture());
        if (!staged.TryAdd(previous with { SlotIndex = -1, IsSafe = false }))
            throw new DomainValidationException("The backpack is full.");
        player.Inventory.Apply(staged);
        player.WornArmor = armor;
        player.Combat.UpdateEquipment(profile);
        return ++Revision;
    }

    public IReadOnlyList<RelicPileSnapshot> GetAvailableRelicPiles(Guid playerId)
    {
        var player = GetInventoryPlayer(playerId);
        if (player.Position is not { } position) return [];
        return GetRelicPilesAt(position).OrderBy(pile => pile.PileId).ToArray();
    }

    private RoomPlayerState GetInventoryPlayer(Guid playerId)
    {
        var player = GetPlayer(playerId);
        if (player.Phase != RoomPlayerPhase.ActionBar || player.Combat.IsDead ||
            player.Pve is { IsCleared: false } || _springDrinks.ContainsKey(playerId) ||
            _extractions.ContainsKey(playerId) || _disconnects.ContainsKey(playerId))
            throw new DomainValidationException("Inventory operations require an available action bar after clearing the player's battle.");
        return player;
    }

    private static (ExplorationItem[] Armor, ExplorationItem? Previous, CombatEquipmentProfile Profile)
        PrepareEquipmentChange(RoomPlayerState player, ExplorationItem item)
    {
        var incoming = ToCombatEquipment(item);
        // An old opaque snapshot can resume safely, but cannot discard unidentified armor bonuses.
        if (player.WornArmor.Any(value => value.Equipment is null))
            throw new DomainValidationException("This recovered equipment needs a complete snapshot before it can be changed.");
        var previous = player.WornArmor.SingleOrDefault(value => value.Equipment!.Slot == incoming.Slot);
        var armor = player.WornArmor.Where(value => value.ItemId != previous?.ItemId)
            .Append(item with { SlotIndex = -1, IsSafe = false }).ToArray();
        return (armor, previous, CalculateArmor(armor));
    }

    private static CombatEquipmentProfile CalculateArmor(IReadOnlyList<ExplorationItem> armor) =>
        EquipmentCombatRules.Calculate(armor.Select(ToCombatEquipment).ToArray());

    private static CombatEquipmentItem ToCombatEquipment(ExplorationItem item)
    {
        if (item.Kind != ExplorationItemKind.Equipment || item.Quantity != 1 ||
            item.Equipment is not { } data || !Guid.TryParse(item.ItemId, out var id) ||
            !Enum.TryParse<CardElement>(data.Element, out var element))
            throw new DomainValidationException("The armor has no valid combat attributes.");
        return new(id, data.Slot, data.Quality, data.Level, element, data.EffectAffix, data.SecondaryTrait);
    }

    private static int EquipReward(RoomPlayerState player, ExplorationItem item, string? replaceItemId)
    {
        var (armor, previous, profile) = PrepareEquipmentChange(player, item);
        var staged = ExplorationInventory.Restore(player.Inventory.Capture());
        ExplorationItem? recycled = null;
        if (replaceItemId is not null)
        {
            if (previous?.ItemId == replaceItemId)
                recycled = previous;
            else if (!staged.TryRemove(replaceItemId, out recycled))
                throw new DomainValidationException("The reward replacement item is not available.");
        }
        if (previous is not null && previous != recycled &&
            !staged.TryAdd(previous with { SlotIndex = recycled?.SlotIndex ?? -1, IsSafe = false }))
            throw new DomainValidationException("The backpack is full; select the removed armor or a backpack item to recycle.");
        if (previous is null && staged.FreeSlots == 0 && replaceItemId is null)
            throw new DomainValidationException("A full backpack requires an explicit reward replacement.");
        player.Inventory.Apply(staged);
        player.WornArmor = armor;
        player.Combat.UpdateEquipment(profile);
        if (recycled is not null) TrackRecycled(player, recycled);
        return item.Quantity;
    }

    private static void TrackRecycled(RoomPlayerState player, ExplorationItem item)
    {
        if (item.Kind == ExplorationItemKind.Equipment)
            player.RecycledEquipment.Add(item with { SlotIndex = -1, IsSafe = false });
    }
}
