extends RefCounted

class DelayedGateway extends Node:
	var token := "owned-offline-session"
	var session_generation := 1
	var room_id := "room-M"
	var room_revision := 1
	var calls: Array = []
	var detail := {"done": false, "result": {}}
	var projected := {"ok": true, "status": 200, "data": {"unfinishedSettlement": null}}
	func request(path: String, _method: int = HTTPClient.METHOD_GET, _body: Variant = null, _quiet: Array = []) -> Dictionary:
		calls.append(path)
		if path.begins_with("/api/v1/bootstrap?"): return projected.duplicate(true)
		while not detail.done: await Engine.get_main_loop().process_frame
		return detail.result

func run_test() -> Dictionary:
	var checks := {}
	var tree = Engine.get_main_loop()
	for pending_first in [false, true]:
		var store: Node = load("res://state/game_store.gd").new()
		var gateway := DelayedGateway.new()
		store.gateway = gateway
		store._client_info_retry_at = Time.get_ticks_msec() + 60000
		store.room = {"match_id": "match-M", "room_id": "room-M", "player": {"phase": "ActionBar"}}
		store._adopt_room_context(store.room)
		store._close_room_actions()
		store.lobby = {"player": {"userId": "owned-offline"}, "wallet": {"gold": 23}}
		var original_lobby: Dictionary = store.lobby.duplicate(true)
		store._load_settlement("receipt-M")
		await tree.process_frame
		store._process(0.0)
		checks["fast point read avoids immediate projection %s" % pending_first] = gateway.calls == ["/api/v1/settlements/receipt-M"]
		if not pending_first: gateway.projected.data.unfinishedSettlement = {"settlementId": "receipt-M", "matchId": "match-M"}
		# Drive the existing poll deadline without a wall-clock sleep. The detail
		# coroutine remains suspended throughout this automatic process tick.
		store._settlement_poll_at = Time.get_ticks_msec() - 1
		store._process(0.0)
		await tree.process_frame
		checks["stalled point read permits bounded same-match projection %s" % pending_first] = gateway.calls == ["/api/v1/settlements/receipt-M", "/api/v1/bootstrap?settlementMatchId=match-M"] and not gateway.detail.done
		if pending_first:
			checks["Pending projection never fabricates a ready receipt"] = store.settlement.is_empty() and not store._settlement_polling and not store.settlement_query_failed
			var count := gateway.calls.size()
			store._process(0.0)
			checks["Pending projection respects the existing poll interval"] = gateway.calls.size() == count
			gateway.projected.data.unfinishedSettlement = {"settlementId": "receipt-M", "matchId": "match-M"}
			store._settlement_poll_at = Time.get_ticks_msec() - 1
			store._process(0.0)
		checks["automatic fallback adopts actual ready receipt %s" % pending_first] = store.settlement.get("settlementId") == "receipt-M" and store.lobby == original_lobby
		var count := gateway.calls.size()
		store._process(0.0)
		checks["ready receipt ends further automatic reads %s" % pending_first] = gateway.calls.size() == count
		store.room = {"match_id": "match-N", "room_id": "room-N", "player": {"phase": "ActionBar"}}
		store._adopt_room_context(store.room)
		store.settlement = {"settlementId": "receipt-N", "matchId": "match-N"}
		gateway.detail.result = {"ok": true, "status": 200, "data": {"settlementId": "receipt-M", "matchId": "match-M"}}
		gateway.detail.done = true
		await tree.process_frame
		await tree.process_frame
		checks["late old detail cannot replace new room receipt %s" % pending_first] = store.settlement.get("settlementId") == "receipt-N" and store.room.match_id == "match-N"
		store.free()
		gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "OFFLINE stalled real GameStore detail coroutine and automatic same-match ready projection; no server, PG or world claim"}
