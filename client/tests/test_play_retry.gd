extends RefCounted

class RetryGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var serial := 0
	var send_ok := true
	func new_id() -> String:
		serial += 1
		return "retry-test-" + str(serial)
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		if not send_ok: return false
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id, "revision": room_revision})
		return true

func _snapshot() -> Dictionary:
	return {"room_id": "room", "room_revision": 10, "player": {"hand": [{"instance_id": "a"}, {"instance_id": "b"}, {"instance_id": "c"}]}, "pve": {"battle_id": "battle", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 84}]}, "allowed_actions": ["battle.play_cards"]}

func _reject(gateway: Node, request_id: String, detail: String = "Room revision conflict. Expected 10, current 11.") -> void:
	var proto = load("res://network/protobuf.gd").new()
	gateway._receive(proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "error.command_rejected", "sequence": gateway.last_sequence + 1, "request_id": request_id, "payload": proto.encode("CommandRejectedEvent", {"code": "COMMAND_REJECTED", "detail": detail})}))

func run_test() -> Dictionary:
	var checks := {}
	for scenario in ["once", "dead", "hand", "battle", "room", "locked", "disconnect", "other_error", "unknown", "send_failed", "success", "timeout"]:
		var store = load("res://state/game_store.gd").new()
		var gateway := RetryGateway.new()
		gateway.persist_session = false
		gateway.online = true
		gateway.room_id = "room"
		gateway.room_revision = 10
		store.gateway = gateway
		gateway.event_received.connect(store._on_event)
		var failures: Array = []
		gateway.failed.connect(func(message): failures.append(message))
		store.room = _snapshot()
		var intent := {"battle_id": "battle", "target_id": "monster", "card_instance_ids": ["a", "b", "c"]}
		store._send_queued_command({"action": "battle.play_cards", "payload": intent})
		var original: String = gateway.sent[0].request_id
		var blocked: bool = not store.command("battle.play_cards", intent)
		if scenario == "disconnect": store._on_connection_changed("正在连接实时服务")
		if scenario == "success": store._on_event("battle.combo_resolved", {"_request_id": original})
		if scenario == "timeout": store._play_deadline = Time.get_ticks_msec() - 1
		if scenario == "send_failed": gateway.send_ok = false
		_reject(gateway, "unrelated" if scenario == "unknown" else original, "A stunned player cannot play cards." if scenario == "other_error" else "Room revision conflict. Expected 10, current 11.")
		if scenario in ["disconnect", "other_error", "unknown", "send_failed", "success", "timeout"]:
			checks[scenario] = blocked and failures.size() == 1 and store._queued_command.is_empty() and gateway.sent.filter(func(value): return value.kind == "battle.play_cards").size() == 1
		else:
			var snapshot := _snapshot()
			var snapshot_id: String = gateway.sent.back().request_id
			# An unrelated periodic snapshot cannot trigger the retry.
			store._on_event("room.snapshot", snapshot)
			var waiting: bool = gateway.sent.size() == 2
			snapshot._request_id = snapshot_id
			if scenario == "dead": snapshot.pve.monsters[0].hp = 0
			if scenario == "hand": snapshot.player.hand.pop_back()
			if scenario == "battle": snapshot.pve.battle_id = "new-battle"
			if scenario == "room": snapshot.room_id = "new-room"
			if scenario == "locked": snapshot.allowed_actions = []
			gateway.room_revision = 12
			store._on_event("room.snapshot", snapshot)
			if scenario == "once":
				var retry: Dictionary = gateway.sent.back()
				var correct: bool = retry.kind == "battle.play_cards" and retry.payload == intent and retry.request_id != original and retry.revision == 12 and failures.is_empty()
				_reject(gateway, retry.request_id)
				checks[scenario] = blocked and waiting and correct and failures.size() == 1 and store._queued_command.is_empty() and store._pending_play.is_empty() and gateway.sent.filter(func(value): return value.kind == "battle.play_cards").size() == 2
			else:
				checks[scenario] = waiting and failures.is_empty() and gateway.sent.size() == 2 and store._queued_command.is_empty()
		store.free()
		gateway.free()
	return {"ok": checks.values().all(func(value): return value == true), "checks": checks}
