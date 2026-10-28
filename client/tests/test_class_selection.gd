extends RefCounted
class ClassGateway extends Node:
	var session_generation := 1
	var calls := 0
	func request(_path: String, _method: int, data: Dictionary) -> Dictionary:
		calls += 1
		return {"ok": true, "data": {"selectedClass": data.selectedClass, "displayName": data.displayName, "version": 2}}

func run_test() -> Dictionary:
	var store = load("res://state/game_store.gd").new()
	var gateway := ClassGateway.new()
	store.gateway = gateway
	store.hero_class = "Mage"
	store.lobby = {"player": {"selectedClass": null, "displayName": "fixture", "version": 1}}
	store.select_class("Mage")
	var persisted: bool = gateway.calls == 1 and store.lobby.player.selectedClass == "Mage"
	store.select_class("Mage")
	var deduplicated: bool = gateway.calls == 1
	store.free()
	gateway.free()
	return {"ok": persisted and deduplicated, "checks": {"default visual class is persisted": persisted, "confirmed class needs no duplicate write": deduplicated}}
