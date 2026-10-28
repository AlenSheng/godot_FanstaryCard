extends RefCounted

class InventoryGateway extends Node:
	var session_generation := 1
	var token := "test-session"
	var requests: Array = []
	var inventory := {"equipments": [{"instanceId": "saved-head", "slot": "Head", "quality": "Blue", "level": 3, "location": "Equipped"}], "consumables": {"potionCount": 2}}

	func request(path: String, method: HTTPClient.Method = HTTPClient.METHOD_GET, _body: Variant = null, _allowed: Array = []) -> Dictionary:
		requests.append({"path": path, "method": method})
		return {"ok": true, "data": inventory.duplicate(true)}

func run_test() -> Dictionary:
	var store = load("res://state/game_store.gd").new()
	var gateway := InventoryGateway.new()
	store.gateway = gateway
	var saved_loadout := {"heroClass": "Mage", "equipmentIds": ["saved-head", null, null, null, null], "version": 4}
	store.lobby = {"equippedLoadouts": [saved_loadout.duplicate(true)], "inventory": {"equipments": []}, "activePreparation": {"preparationId": "prep-1"}}
	store.preparation = store.lobby.activePreparation.duplicate(true)
	store.ticket = {"ticketId": "ticket-1"}
	store.ready_prompt = {"room_id": "room-1"}
	var modules: Array = []
	store.cache_changed.connect(func(module): modules.append(module))
	store._on_event("room.ready_removed", {})
	var checks := {
		"timeout clears pending preparation": store.preparation.is_empty() and store.ticket.is_empty() and store.ready_prompt.is_empty() and store.lobby.activePreparation == null,
		"saved equipment selection and version survive": store.loadout() == saved_loadout,
		"released equipment details are reloaded": store.lobby.inventory == gateway.inventory,
		"preparation UI receives inventory update": modules.has("inventory"),
		"timeout refreshes inventory without saving an empty loadout": gateway.requests == [{"path": "/api/v1/inventory/", "method": HTTPClient.METHOD_GET}],
	}
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "message": "Ready timeout preserves saved equipment and reloads released inventory", "checks": checks}
