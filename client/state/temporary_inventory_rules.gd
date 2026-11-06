extends RefCounted

## Shared public-snapshot capacity rule for inventory UI and reward hints.
static func can_add(player: Dictionary, item: Dictionary) -> bool:
	var items: Array = player.get("inventory", [])
	if items.size() < int(player.get("inventory_capacity", 0)): return true
	if item.get("kind", "") not in ["Equipment", "HealthPotion"]:
		for current in items:
			if current.get("kind") == item.get("kind") and current.get("item_id") == item.get("item_id"): return true
	return false
