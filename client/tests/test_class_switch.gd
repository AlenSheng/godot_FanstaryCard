extends RefCounted

class ImmediateGateway extends Node:
	var session_generation := 7
	var requests: Array = []

	func request(path: String, method: HTTPClient.Method = HTTPClient.METHOD_GET, body: Variant = null) -> Dictionary:
		requests.append({"path": path, "method": method, "body": body})
		return {"ok": true, "data": {"displayName": body.displayName, "selectedClass": body.selectedClass, "version": int(body.expectedVersion) + 1}}

func run_test() -> Dictionary:
	var store = load("res://state/game_store.gd").new()
	var gateway := ImmediateGateway.new()
	store.gateway = gateway
	store.hero_class = "Mage"
	store.lobby = {"player": {"displayName": "Test", "selectedClass": "Mage", "version": 3}}
	var renders := [0]
	store.changed.connect(func(): renders[0] += 1)
	store.select_class("Priest")
	var checks := {
		"selection updates immediately": store.hero_class == "Priest" and renders[0] == 1,
		"selection does not use global busy lock": not store.busy,
		"selection persists once": gateway.requests.size() == 1 and gateway.requests[0].body.selectedClass == "Priest",
		"profile version refreshes": store.lobby.player.version == 4,
	}
	store.select_class("Priest")
	checks["same class is ignored"] = gateway.requests.size() == 1 and renders[0] == 1
	store.select_class("Unknown")
	checks["invalid class is ignored"] = gateway.requests.size() == 1 and store.hero_class == "Priest"
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "message": "Hall class selection updates immediately and saves without cooldown or a global UI lock", "checks": checks}
