extends RefCounted

class SettlementGateway extends Node:
	var token := "test-session"
	var session_generation := 1
	var calls := 0
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
	store.free()
	gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks}
