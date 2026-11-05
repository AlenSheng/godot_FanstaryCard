extends RefCounted

const QUALITIES := ["White", "Green", "Blue", "Purple", "Orange", "Red"]

static func season_id(record: Dictionary) -> String:
	var value: Variant = record.get("seasonId")
	return value if value is String else ""

static func protected_ids(loadouts: Array, draft: Array) -> Dictionary:
	var ids := {}
	for value in draft:
		if value != null: ids[str(value)] = true
	for loadout in loadouts:
		for value in loadout.get("equipmentIds", []):
			if value != null: ids[str(value)] = true
	return ids

static func is_unlearned_sample(item: Dictionary) -> bool:
	return item.get("quality") in ["Purple", "Orange"] and item.get("sourceKind") in ["NaturalDrop", "MarkCraft"] and not bool(item.get("recipeExtracted", false))

static func blocked_reason(item: Dictionary, inventory: Dictionary, protected: Dictionary) -> String:
	var scope: Dictionary = inventory.scope if inventory.get("scope") is Dictionary else {}
	if bool(scope.get("readOnly", false)) or scope.get("state") == "Closed": return "inventory_manage_closed"
	if item.get("location") != "Inventory" or item.get("sourceKind") in ["Borrowed", "BotReward"]: return "inventory_manage_reserved"
	if protected.has(str(item.get("instanceId", ""))): return "inventory_manage_loadout"
	var season := season_id(scope)
	if season != season_id(item): return "inventory_manage_closed"
	if not season.is_empty() and item.get("assetScope") != "ActiveSeason": return "inventory_manage_closed"
	if season.is_empty() and item.get("assetScope") != null: return "inventory_manage_closed"
	return ""

static func sorted_items(items: Array, quality: String = "") -> Array:
	var result: Array = items.filter(func(item): return quality.is_empty() or item.get("quality") == quality).duplicate()
	result.sort_custom(func(a, b):
		var a_key := "%02d-%02d-%s-%s" % [QUALITIES.find(str(a.get("quality", ""))), int(a.get("level", 0)), str(a.get("slot", "")), str(a.get("instanceId", ""))]
		var b_key := "%02d-%02d-%s-%s" % [QUALITIES.find(str(b.get("quality", ""))), int(b.get("level", 0)), str(b.get("slot", "")), str(b.get("instanceId", ""))]
		return a_key < b_key)
	return result

static func request(inventory: Dictionary, loadouts: Array, draft: Array, selection: Dictionary) -> Dictionary:
	if selection.is_empty() or selection.size() > 50: return {}
	var protected := protected_ids(loadouts, draft)
	var items := []
	for id in selection:
		var matches: Array = inventory.get("equipments", []).filter(func(item): return str(item.get("instanceId", "")) == id)
		if matches.size() != 1: return {}
		var item: Dictionary = matches[0]
		if not blocked_reason(item, inventory, protected).is_empty() or item.get("version") != selection[id]: return {}
		items.append({"equipmentId": id, "expectedVersion": selection[id]})
	items.sort_custom(func(a, b): return a.equipmentId < b.equipmentId)
	var body := {"items": items}
	var scope: Dictionary = inventory.scope if inventory.get("scope") is Dictionary else {}
	if scope.get("seasonId") is String and not str(scope.seasonId).is_empty(): body["seasonId"] = scope.seasonId
	return body
