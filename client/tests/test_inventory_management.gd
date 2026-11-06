extends RefCounted

const Model = preload("res://ui/inventory_management_model.gd")

func run_test() -> Dictionary:
	var checks := {}
	var item := {"instanceId": "10000000-0000-0000-0000-000000000001", "slot": "Chest", "quality": "Purple", "level": 0, "location": "Inventory", "version": 9007199254740993, "sourceKind": "NaturalDrop", "seasonId": "original", "assetScope": "ActiveSeason"}
	var original := item.duplicate(true)
	var inventory := {"scope": {"state": "ActiveSeason", "seasonId": "original", "readOnly": false}, "equipments": [item]}
	var selected := {item.instanceId: item.version}
	var body := Model.request(inventory, [], [], selected)
	checks["original season and exact int64 version"] = body.seasonId == "original" and body.items[0].expectedVersion == 9007199254740993
	checks["unlearned actual purple sample identified"] = Model.is_unlearned_sample(item)
	var learned := item.duplicate(true)
	learned.recipeExtracted = true
	checks["learned sample no longer needs warning"] = not Model.is_unlearned_sample(learned)
	checks["all saved classes protected"] = Model.request(inventory, [{"heroClass": "Priest", "equipmentIds": [null, item.instanceId]}], [], selected).is_empty()
	checks["unsaved current draft protected"] = Model.request(inventory, [], [item.instanceId], selected).is_empty()
	checks["old selected version rejected"] = Model.request(inventory, [], [], {item.instanceId: 3}).is_empty()
	checks["removed selected item rejected"] = Model.request(inventory, [], [], {"missing": 1}).is_empty()
	checks["empty selection rejected"] = Model.request(inventory, [], [], {}).is_empty()
	var locked := item.duplicate(true)
	for location in ["Equipped", "PreparationLocked", "MarketListed", "InMatchBackpack", "Recycled"]:
		locked.location = location
		checks[location + " rejected"] = not Model.blocked_reason(locked, inventory, {}).is_empty()
	locked = item.duplicate(true)
	for source in ["Borrowed", "BotReward"]:
		locked.sourceKind = source
		checks[source + " rejected"] = not Model.blocked_reason(locked, inventory, {}).is_empty()
	locked = item.duplicate(true)
	locked.seasonId = "old"
	checks["another season rejected"] = not Model.blocked_reason(locked, inventory, {}).is_empty()
	var closed := inventory.duplicate(true)
	closed.scope.readOnly = true
	checks["closed inventory rejected"] = Model.request(closed, [], [], selected).is_empty()
	var legacy := item.duplicate(true)
	legacy.erase("seasonId")
	legacy.erase("assetScope")
	var legacy_inventory := {"equipments": [legacy], "scope": null}
	var legacy_body := Model.request(legacy_inventory, [], [], selected)
	checks["legacy does not invent a season"] = not legacy_body.is_empty() and not legacy_body.has("seasonId")
	legacy.seasonId = null
	checks["explicit null is legacy"] = Model.blocked_reason(legacy, legacy_inventory, {}).is_empty()
	var bound := item.duplicate(true)
	bound.isBound = true
	checks["bound body may be explicitly discarded"] = Model.blocked_reason(bound, inventory, {}).is_empty()
	var white := item.duplicate(true)
	white.instanceId = "20000000-0000-0000-0000-000000000001"
	white.quality = "White"
	checks["quality filter and material ordering"] = Model.sorted_items([item, white])[0].instanceId == white.instanceId and Model.sorted_items([item, white], "Purple").size() == 1
	checks["source inventory and item not mutated"] = item == original and inventory.equipments[0] == original
	var ok := true
	for value in checks.values():
		if not value: ok = false
	return {"ok": ok, "checks": checks}
