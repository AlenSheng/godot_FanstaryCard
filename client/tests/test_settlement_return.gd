extends RefCounted

class AcknowledgeGateway extends Node:
	var session_generation := 1
	var room_id := "old-room"
	var room_revision := 7
	var acknowledge_ok := false
	var acknowledge_calls := 0
	var saw_hall_before_request := false
	var store: Node

	func request(path: String, _method: HTTPClient.Method = HTTPClient.METHOD_GET, _body: Variant = null, _allowed: Array = []) -> Dictionary:
		if path.ends_with("/acknowledge"):
			acknowledge_calls += 1
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
		store.ready_prompt = {"match_id": "match-1"}
		store.preparation = {"preparationId": "prep-1"}
		store.ticket = {"ticketId": "ticket-1"}
		store.selected_cards = ["card-1"]
		store.lobby = {"unfinishedSettlement": store.settlement.duplicate(true), "unfinishedMatch": {"roomId": "old-room"}}
		var confirmed: bool = store.acknowledge_settlement()
		checks["result reflects server acknowledgement %s" % succeeds] = confirmed == succeeds
		checks["hall shown before %s response" % ("successful" if succeeds else "failed")] = gateway.saw_hall_before_request
		checks["%s response handled" % ("successful" if succeeds else "failed")] = store.settlement.is_empty() if succeeds else store.settlement.get("settlementId", "") == "settled" and store.room.get("room_id", "") == "old-room"
		checks["ready prompt follows acknowledgement %s" % succeeds] = store.ready_prompt.is_empty() if succeeds else store.ready_prompt.get("match_id", "") == "match-1"
		checks["preparation follows acknowledgement %s" % succeeds] = store.preparation.is_empty() if succeeds else store.preparation.get("preparationId", "") == "prep-1" and store.ticket.get("ticketId", "") == "ticket-1" and store.selected_cards == ["card-1"]
		checks["acknowledgement ends busy state"] = not store.busy
		if not succeeds:
			gateway.acknowledge_ok = true
			checks["failed acknowledgement can be retried"] = store.acknowledge_settlement() and gateway.acknowledge_calls == 2 and store.settlement.is_empty()
			checks["completed receipt cannot be acknowledged twice"] = not store.acknowledge_settlement() and gateway.acknowledge_calls == 2
		store.free()
		gateway.free()
	return {"ok": not checks.values().has(false), "message": "Settlement return is optimistic and restores the receipt on failure", "checks": checks}
