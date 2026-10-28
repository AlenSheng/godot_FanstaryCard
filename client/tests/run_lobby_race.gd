extends SceneTree

class DelayedGateway extends Node:
	var session_generation := 1
	var room_id := ""
	var room_revision := 0
	var online := true
	var recovering := false
	var requests: Array = []
	func request(_path: String, _method: int = 0, _data: Variant = null, _quiet: Array = []) -> Dictionary:
		var flight := {"done": false, "result": {}}
		requests.append(flight)
		while not flight.done: await get_tree().process_frame
		return flight.result
	func complete(index: int, data: Dictionary) -> void:
		requests[index].result = {"ok": true, "data": data, "status": 200}
		requests[index].done = true

var failures: Array = []
func check(ok: bool, name: String) -> void:
	if not ok: failures.append(name)

func _initialize() -> void: call_deferred("run")
func run() -> void:
	var store = load("res://state/game_store.gd").new()
	var gateway := DelayedGateway.new()
	root.add_child(gateway)
	store.gateway = gateway
	var bootstrap := {"configVersion": store.CATALOG.data.version, "player": {"selectedClass": "Mage"},
		"wallet": {"gold": 1}, "materials": {}, "shop": {}, "market": [], "inventory": {}, "mail": {}, "activePreparation": null}
	store.refresh_lobby()
	store.room = {"match_id": "new-match"}
	gateway.room_id = "new-room"
	var old: Dictionary = bootstrap.duplicate(true)
	old["unfinishedSettlement"] = {"settlementId": "old", "matchId": "old-match"}
	gateway.complete(0, old)
	await process_frame
	check(store.settlement.is_empty() and gateway.room_id == "new-room" and store.lobby.is_empty(), "old match bootstrap cannot overwrite new room")
	store.room = {}
	gateway.room_id = ""
	store.refresh_lobby()
	store.refresh_lobby()
	var newer: Dictionary = bootstrap.duplicate(true)
	newer.wallet.gold = 2
	gateway.complete(2, newer)
	await process_frame
	gateway.complete(1, bootstrap)
	await process_frame
	check(int(store.lobby.wallet.gold) == 2, "newer refresh wins within same session")
	store.room = {"player": {"hand": [], "draw_block_remaining_ms": 1500}}
	check(store.combat_wait_state().reason == "target", "missing target explained")
	store.room["duel"] = {"duel_id": "d", "opponent_id": "p"}
	check(store.combat_wait_state().reason == "draw_blocked", "blocked draw explained")
	store.room.player.stun_remaining_ms = 1000
	check(store.combat_wait_state().reason == "stunned", "stun explained")
	gateway.recovering = true
	check(store.combat_wait_state().reason == "recovering", "recovery precedes combat waits")
	store.free()
	gateway.queue_free()
	print(JSON.stringify({"ok": failures.is_empty(), "failures": failures}))
	quit(0 if failures.is_empty() else 1)
