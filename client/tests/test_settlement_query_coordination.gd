extends RefCounted

class DelayedGateway extends Node:
	var token := "test-session"
	var session_generation := 1
	var room_id := "room-M"
	var room_revision := 1
	var calls: Array = []
	var point: Dictionary = {}
	var bootstrap := {"ok": true, "status": 200, "data": {"unfinishedSettlement": null}}
	func request(path: String, _method: int = HTTPClient.METHOD_GET, _body: Variant = null, _quiet: Array = []) -> Dictionary:
		calls.append(path)
		if path.get_slice("?", 0) == "/api/v1/bootstrap": return bootstrap.duplicate(true)
		point = {"done": false, "result": {}}
		var active := point
		while not active.done: await Engine.get_main_loop().process_frame
		return active.result

func run_test() -> Dictionary:
	var checks := {}
	var tree = Engine.get_main_loop()
	for succeeds in [true, false]:
		var store: Node = load("res://state/game_store.gd").new()
		var gateway := DelayedGateway.new()
		store.gateway = gateway
		store._client_info_retry_at = Time.get_ticks_msec() + 60000
		store.room = {"match_id": "match-M", "room_id": "room-M", "player": {"phase": "Dead"}}
		store._load_settlement("receipt-M")
		await tree.process_frame
		checks["known-ID point read is actually pending %s" % succeeds] = store._settlement_loading == "receipt-M" and gateway.calls == ["/api/v1/settlements/receipt-M"]
		store._process(0.0)
		await tree.process_frame
		checks["normal known-ID read defers automatic Bootstrap during grace %s" % succeeds] = gateway.calls == ["/api/v1/settlements/receipt-M"] and not store._settlement_polling and store._settlement_poll_at > Time.get_ticks_msec()
		gateway.point.result = {"ok": succeeds, "status": 200 if succeeds else 503, "data": {"settlementId": "receipt-M", "matchId": "match-M"}}
		gateway.point.done = true
		await tree.process_frame
		await tree.process_frame
		checks["point completion always releases loading %s" % succeeds] = store._settlement_loading.is_empty()
		if succeeds:
			var before := gateway.calls.size()
			store.retry_settlement()
			checks["successful own point read needs no catalog fallback"] = store.settlement.get("settlementId") == "receipt-M" and gateway.calls.size() == before
		else:
			var before := gateway.calls.size()
			store.retry_settlement()
			checks["failed known-ID read still permits immediate unknown-ID fallback"] = gateway.calls.size() == before + 1 and gateway.calls[-1] == "/api/v1/bootstrap?settlementMatchId=match-M" and store.settlement.is_empty()
			checks["Pending Bootstrap stays notready and ends singleflight"] = not store._settlement_polling and not store.settlement_query_failed
			gateway.bootstrap.data.unfinishedSettlement = {"settlementId": "receipt-M", "matchId": "match-M"}
			store.retry_settlement()
			checks["fallback can subsequently recover the same ready receipt"] = store.settlement.get("settlementId") == "receipt-M"
		store.free()
		gateway.free()
	var store: Node = load("res://state/game_store.gd").new()
	var gateway := DelayedGateway.new()
	store.gateway = gateway
	store.room = {"match_id": "match-M", "room_id": "room-M", "player": {"phase": "Dead"}}
	store._load_settlement("receipt-M")
	await tree.process_frame
	store.room = {"match_id": "match-N", "room_id": "room-N", "player": {"phase": "Dead"}}
	store._adopt_room_context(store.room)
	gateway.bootstrap.data.unfinishedSettlement = {"settlementId": "receipt-N", "matchId": "match-N"}
	store.retry_settlement()
	checks["old match pending read cannot suppress new match fallback"] = gateway.calls[-1] == "/api/v1/bootstrap?settlementMatchId=match-N" and store.settlement.get("settlementId") == "receipt-N"
	gateway.point.result = {"ok": true, "data": {"settlementId": "receipt-M", "matchId": "match-M"}}
	gateway.point.done = true
	await tree.process_frame
	await tree.process_frame
	checks["late old point result cannot replace new match receipt"] = store.settlement.get("settlementId") == "receipt-N"
	store.free()
	gateway.free()
	store = load("res://state/game_store.gd").new()
	gateway = DelayedGateway.new()
	store.gateway = gateway
	store.room = {"match_id": "match-M", "room_id": "room-M", "player": {"phase": "Dead"}}
	store._load_settlement("receipt-M")
	await tree.process_frame
	gateway.bootstrap.data.unfinishedSettlement = {"settlementId": "receipt-M", "matchId": "match-M"}
	store.retry_settlement()
	checks["explicit retry remains available while point response is still pending"] = gateway.calls == ["/api/v1/settlements/receipt-M", "/api/v1/bootstrap?settlementMatchId=match-M"] and store.settlement.get("settlementId") == "receipt-M" and not gateway.point.done
	gateway.point.result = {"ok": false, "status": 503}
	gateway.point.done = true
	await tree.process_frame
	await tree.process_frame
	checks["late failed point response retains explicit fallback receipt"] = store._settlement_loading.is_empty() and store.settlement.get("settlementId") == "receipt-M"
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "OFFLINE automatic scheduling during suspended point read, explicit retry, failure/Pending recovery and room epoch; no API/world/performance claim"}
