extends RefCounted

class AcknowledgeGateway extends Node:
	var session_generation := 1
	var room_id := "old-room"
	var room_revision := 7
	var acknowledge_ok := false
	var saw_hall_before_request := false
	var store: Node

	func request(path: String, _method: HTTPClient.Method = HTTPClient.METHOD_GET, _body: Variant = null, _allowed: Array = []) -> Dictionary:
		if path.ends_with("/acknowledge"):
			saw_hall_before_request = store.settlement.is_empty() and store.room.is_empty() and store.lobby.get("unfinishedSettlement") == null and room_id.is_empty()
			return {"ok": acknowledge_ok}
		return {"ok": false}

func run_test() -> Dictionary:
	var checks := {}
	for succeeds in [false, true]:
		var store: Node = load("res://state/game_store.gd").new()
		var gateway := AcknowledgeGateway.new()
		gateway.store = store
		gateway.acknowledge_ok = succeeds
		store.gateway = gateway
		store.settlement = {"settlementId": "settled", "matchId": "match-1", "result": "Dead"}
		store.room = {"room_id": "old-room", "match_id": "match-1"}
		store.lobby = {"unfinishedSettlement": store.settlement.duplicate(true), "unfinishedMatch": {"roomId": "old-room"}}
		store.acknowledge_settlement()
		checks["hall shown before %s response" % ("successful" if succeeds else "failed")] = gateway.saw_hall_before_request
		checks["%s response handled" % ("successful" if succeeds else "failed")] = store.settlement.is_empty() if succeeds else store.settlement.get("settlementId", "") == "settled" and store.room.get("room_id", "") == "old-room"
		checks["acknowledgement ends busy state"] = not store.busy
		store.free()
		gateway.free()
	return {"ok": not checks.values().has(false), "message": "Settlement return is optimistic and restores the receipt on failure", "checks": checks}
