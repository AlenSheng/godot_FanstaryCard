extends RefCounted

class ReceiptGateway extends "res://network/gateway.gd":
	signal receipt_response
	var hold_receipt := true
	var sent: Array = []
	var requests: Array = []
	func send(kind: String, _payload: Dictionary = {}, _request_id: String = "") -> bool:
		sent.append(kind)
		return true
	func request(path: String, _method: int = HTTPClient.METHOD_GET, _body: Variant = null, _quiet: Array = []) -> Dictionary:
		requests.append(path)
		if hold_receipt and path == "/api/v1/settlements/receipt": await receipt_response
		return {"ok": false, "status": 503}

func _snapshot(store: Node, match_id: String = "match", room_id: String = "room") -> Dictionary:
	return {"config_version": store.CATALOG.data.version, "match_id": match_id, "room_id": room_id, "room_revision": 10,
		"player": {"player_id": "self", "phase": "Pve", "hand": [{"instance_id": "card"}]},
		"pve": {"battle_id": "battle", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 10}]},
		"allowed_actions": ["battle.play_cards", "battle.select_target"]}

func run_test() -> Dictionary:
	var checks := {}
	for notification in ["settlement.ready", "match.settled"]:
		var store: Node = load("res://state/game_store.gd").new()
		var gateway := ReceiptGateway.new()
		gateway.persist_session = false
		gateway.online = true
		gateway.token = "test"
		store.gateway = gateway
		var snapshot := _snapshot(store)
		store._on_event("room.snapshot", snapshot.duplicate(true))
		store.refresh_room_snapshot()
		var in_flight_reads := gateway.sent.count("room.snapshot.read")
		store._latest_commands["battle.select_target"] = {"payload": {}, "due": 0}
		store._queued_command = {"action": "battle.play_cards", "payload": {}}
		store._on_event(notification, {"match_id": "match", "settlement_id": "receipt"})
		checks[notification + ": notification closes actions before HTTP finishes"] = store._settlement_loading == "receipt" and not store.allowed("battle.play_cards") and not store.command("battle.play_cards", {}) and store._queued_command.is_empty() and store._latest_commands.is_empty()
		checks[notification + ": ordinary terminal room remains distinct from lost-route recovery"] = store._settlement_recovery_match_id.is_empty()
		store.refresh_room_snapshot()
		checks[notification + ": already sent read retained, no additional read"] = in_flight_reads == 1 and gateway.sent.count("room.snapshot.read") == in_flight_reads
		gateway.receipt_response.emit()
		checks[notification + ": HTTP failure does not reopen actions"] = store._settlement_loading.is_empty() and store.settlement.is_empty() and not store.allowed("battle.play_cards")
		store._on_event("room.snapshot", snapshot.duplicate(true))
		store.refresh_room_snapshot()
		checks[notification + ": older playing snapshot cannot reopen room"] = not store.allowed("battle.play_cards") and gateway.sent.count("room.snapshot.read") == in_flight_reads
		gateway.hold_receipt = false
		store.retry_settlement()
		checks[notification + ": failed receipt remains recoverable"] = gateway.requests.back() == "/api/v1/bootstrap?settlementMatchId=" + str(snapshot.match_id).uri_encode() and store.settlement_query_failed
		store.settlement = {"settlementId": "receipt", "matchId": "match"}
		var acknowledged: bool = await store.acknowledge_settlement()
		checks[notification + ": failed acknowledgement keeps terminal authority"] = not acknowledged and store.settlement.get("settlementId", "") == "receipt" and not store.allowed("battle.play_cards")
		store._on_event("room.snapshot", _snapshot(store, "next-match", "next-room"))
		checks[notification + ": new room restores legal actions"] = store.allowed("battle.play_cards")
		store._on_event(notification, {"match_id": "match", "settlement_id": "receipt"})
		checks[notification + ": prior match notification cannot close new room"] = store.allowed("battle.play_cards")
		store._on_event(notification, {"match_id": "next-match", "settlement_id": ""})
		checks[notification + ": malformed receipt does not close room"] = store.allowed("battle.play_cards")
		var terminal := _snapshot(store, "next-match", "next-room")
		terminal.player.phase = "Dead"
		store._on_event("room.snapshot", terminal)
		checks[notification + ": authoritative death snapshot closes actions"] = not store.allowed("battle.play_cards")
		store._clear_authenticated_state()
		store._on_event("room.snapshot", snapshot.duplicate(true))
		checks[notification + ": authentication reset cannot retain old closure"] = store.allowed("battle.play_cards")
		store.free()
		gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks}
