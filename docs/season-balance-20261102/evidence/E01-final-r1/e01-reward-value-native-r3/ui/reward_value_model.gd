extends RefCounted

const Compare = preload("res://ui/equipment_compare_model.gd")
const Details = preload("res://ui/equipment_details.gd")
const Inventory = preload("res://state/temporary_inventory_rules.gd")

static func evaluate(option: Dictionary, player: Dictionary, index: Dictionary = {}) -> Dictionary:
	var kind := int(option.get("kind", 0))
	var result := {"kind": kind, "carry_required": kind != 3, "bag_full": false, "slot_empty": false, "current_item": {}, "set_changes": [], "catalog_ready": true, "high_quality_blocked": false, "heal_gain": 0, "heal_overflow": 0}
	if kind == 3:
		var combat: Dictionary = player.get("combat", {})
		var base: int = maxi(0, int(combat.get("maximum_hp", 0)))
		var effective: int = maxi(base, int(combat.get("effective_maximum_hp", base)))
		var raw: int = maxi(0, floori(base * int(option.get("heal_percent", 0)) / 100.0))
		var gain: int = mini(maxi(0, effective - int(combat.get("hp", 0))), raw)
		result.heal_gain = gain
		result.heal_overflow = maxi(0, raw - gain)
		return result
	var item := {"kind": "Equipment" if kind == 1 else "EquipmentFragments", "item_id": option.get("item_id", ""), "equipment": option.get("equipment", {})}
	result.bag_full = not Inventory.can_add(player, item)
	if kind != 1: return result
	var gear: Dictionary = option.get("equipment", {})
	var worn: Array = player.get("equipped_items", [])
	for current in worn:
		if Details.equipment(current).get("slot") == gear.get("slot"):
			result.current_item = current.duplicate(true)
			break
	result.slot_empty = result.current_item.is_empty()
	var replaced := Compare.replace_slot(worn, item)
	result.high_quality_blocked = replaced.filter(func(value): return Details.equipment(value).get("quality") in ["Orange", "Red"]).size() > 1
	result.catalog_ready = Compare.can_inspect(worn + [item], index)
	if result.catalog_ready and not result.high_quality_blocked:
		for change in Compare.changed_sets(worn, replaced, index):
			# A changed contributor is not automatically an improvement. Show the
			# public before/after counts and activation state, without scoring it.
			result.set_changes.append({"kind": change.kind, "before_count": change.before.count, "after_count": change.after.count, "before_required": change.before.required, "after_required": change.after.required, "before_active": change.before.active, "after_active": change.after.active})
	return result
