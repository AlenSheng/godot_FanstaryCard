extends RefCounted

class SettlementGateway extends Node:
	var token := "test-session"
	var session_generation := 1
	var calls := 0
	var room_id := ""
	var room_revision := 0
	var response := {"ok": false, "status": 503}

	func request(_path: String, _method: int = HTTPClient.METHOD_GET, _body: Variant = null, _quiet: Array = []) -> Dictionary:
		calls += 1
		return response

func run_test() -> Dictionary:
	var store: Node = load("res://state/game_store.gd").new()
	var gateway := SettlementGateway.new()
	store.gateway = gateway
	store.room = {"match_id": "boss-match", "player": {"phase": "Extracted"}}
	store.retry_settlement()
	var checks := {"failed query is visible and retryable": store.settlement_query_failed and not store._settlement_polling and store.settlement.is_empty()}
	gateway.response = {"ok": true, "data": {"unfinishedSettlement": null}}
	store.retry_settlement()
	checks["pending assets are not treated as received"] = not store.settlement_query_failed and store.settlement.is_empty()
	gateway.response.data.unfinishedSettlement = {"settlementId": "receipt", "matchId": "old-match", "result": "Extracted"}
	store.retry_settlement()
	checks["another match is ignored"] = store.settlement.is_empty()
	store._settlement_polling = true
	var before := gateway.calls
	store.retry_settlement()
	checks["in-flight query is not duplicated"] = gateway.calls == before
	store._settlement_polling = false
	gateway.response.data.unfinishedSettlement.matchId = "boss-match"
	store.retry_settlement()
	checks["boss receipt replaces pending screen"] = store.settlement.get("settlementId") == "receipt"
	before = gateway.calls
	store.retry_settlement()
	checks["ready receipt stops polling"] = gateway.calls == before
	store.settlement = {}
	store.room = {}
	store._settlement_recovery_match_id = "boss-match"
	gateway.response.data.unfinishedSettlement = null
	store.retry_settlement()
	checks["lost room keeps polling original match"] = store.settlement.is_empty() and store._settlement_recovery_match_id == "boss-match"
	gateway.response.data.unfinishedSettlement = {"settlementId": "other", "matchId": "old-match"}
	store.retry_settlement()
	checks["lost room rejects unrelated receipt"] = store.settlement.is_empty()
	gateway.response.data.unfinishedSettlement = {"settlementId": "receipt", "matchId": "boss-match"}
	store.retry_settlement()
	checks["lost room recovers ready receipt"] = store.settlement.get("settlementId") == "receipt" and store._settlement_recovery_match_id.is_empty()
	# Reproduce through the public error callback, without seeding recovery state.
	store.settlement = {}
	store.room = {"match_id": "match-M", "room_id": "room-M"}
	gateway.response = {"ok": true, "data": {"configVersion": store.CATALOG.data.version,
		"player": {}, "wallet": {}, "materials": {}, "shop": {}, "market": [],
		"inventory": {}, "mail": {}, "activePreparation": null, "unfinishedSettlement": null}}
	# Real Gateway responses retain the initiating room, match and session.
	# Uncorrelated errors belong to the negative cases in pr13_callback_isolation.
	var rejection := {"code": "NOT_IN_ROOM", "_origin_context": {
		"match_id": "match-M", "room_id": "room-M", "session_generation": gateway.session_generation}}
	store._on_event("error.command_rejected", rejection.duplicate(true))
	store._on_event("error.command_rejected", rejection.duplicate(true))
	checks["duplicate real rejection preserves M"] = store.room.is_empty() and store._settlement_recovery_match_id == "match-M"
	gateway.response.data.unfinishedSettlement = {"settlementId": "receipt-M", "matchId": "match-M"}
	store.retry_settlement()
	checks["M becomes ready after duplicate error"] = store.settlement.get("settlementId", "") == "receipt-M"
	store.settlement = {}
	store.room = {"match_id": "new-match", "room_id": "new-room"}
	store._on_event("error.command_rejected", {"code": "NOT_IN_ROOM", "_origin_context": {"match_id": "match-M"}})
	checks["old rejection cannot clear new match"] = store.room.get("match_id") == "new-match"
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks}
