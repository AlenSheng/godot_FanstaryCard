extends RefCounted

class TestGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var reconnects := 0
	func new_id() -> String: return "confirmed-" + str(sent.size())
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true
	func connect_realtime() -> void:
		reconnects += 1
		online = false

func _snapshot(revision: int, room_id: String = "room") -> Dictionary:
	return {"room_id": room_id, "room_revision": revision, "player": {"phase": "Choice", "hand": []},
		"allowed_actions": ["choice.pick"], "reward_choice": {"options": [{"option_id": "reward"}]}}

func run_test() -> Dictionary:
	var checks := {}
	for scenario in ["ack_before_snapshot", "old_snapshot", "other_room", "snapshot_before_ack", "missing_revision", "timeout"]:
		var store = load("res://state/game_store.gd").new()
		var gateway := TestGateway.new()
		gateway.persist_session = false
		gateway.online = true
		store.gateway = gateway
		store.room = _snapshot(10)
		store._send_queued_command({"action": "reward.choice.claim", "payload": {"option_id": "reward"}})
		var request_id: String = gateway.sent[0].request_id
		if scenario == "snapshot_before_ack": store._on_event("room.snapshot", _snapshot(11))
		store._on_event("reward.choice_claimed", {"_request_id": request_id, "_event_revision": -1 if scenario == "missing_revision" else 11})
		if scenario == "snapshot_before_ack": checks[scenario] = not store.has_pending_commands()
		else:
			var held: bool = store.has_pending_commands() and not store.command("reward.choice.claim", {"option_id": "reward"})
			if scenario == "old_snapshot":
				store._on_event("room.snapshot", _snapshot(10))
				held = held and store.has_pending_commands()
			elif scenario == "other_room":
				store._on_event("room.snapshot", _snapshot(12, "other"))
				held = held and store.has_pending_commands()
			elif scenario == "timeout":
				store._pending_commands[request_id].deadline = Time.get_ticks_msec() - 1
				store._process(0)
				checks[scenario] = held and gateway.reconnects == 1 and store.room.is_empty() and gateway.recovering and gateway.sent.filter(func(row): return row.kind == "reward.choice.claim").size() == 1
				store.free()
				gateway.free()
				continue
			store._on_event("room.snapshot", _snapshot(11))
			checks[scenario] = held and not store.has_pending_commands() and gateway.sent.filter(func(row): return row.kind == "reward.choice.claim").size() == 1
		store.free()
		gateway.free()
	var live_store = load("res://state/game_store.gd").new()
	var live_gateway := TestGateway.new()
	live_gateway.persist_session = false
	live_gateway.online = true
	live_store.gateway = live_gateway
	live_store.room = {"room_id": "room", "player": {"player_id": "player", "phase": "Pve", "hand": []},
		"pve": {"battle_id": "battle", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 46}]}}
	live_store._on_event("combat.hit", {"_request_id": "room-combat", "battle_id": "battle", "target_id": "player"})
	checks["synthetic_hit_refreshes_hand"] = live_gateway.sent.size() == 1 and live_gateway.sent[0].kind == "room.snapshot.read"
	live_store._combat_sync_at = Time.get_ticks_msec() - 1
	live_store._snapshot_request_at = Time.get_ticks_msec() - 4001
	live_store._process(0)
	checks["silent_draw_refresh_is_bounded"] = live_gateway.sent.size() == 2 and live_store._combat_sync_at > Time.get_ticks_msec()
	live_store._process(0)
	checks["no_per_frame_snapshot_loop"] = live_gateway.sent.size() == 2
	live_store.free()
	live_gateway.free()
	var target_contract: Dictionary = load("res://tests/test_target_confirmation_contract.gd").new().run_test()
	for name in target_contract.get("checks", {}):
		checks["preview_" + str(name)] = target_contract.checks[name]
	return {"ok": checks.values().all(func(value): return value == true), "checks": checks}
