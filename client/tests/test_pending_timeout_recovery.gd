extends RefCounted

class RecordingGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var reconnects := 0
	var serial := 0
	func new_id() -> String:
		serial += 1
		return "ambiguous-write-" + str(serial)
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true
	func connect_realtime() -> void:
		reconnects += 1
		online = false

func _room(action: String, room_id: String = "timeout-room", match_id: String = "timeout-match") -> Dictionary:
	return {"room_id": room_id, "match_id": match_id, "room_revision": 10,
		"allowed_actions": [action, "battle.select_target"],
		"player": {"player_id": "owner", "phase": "Pve" if action == "battle.play_cards" else "Choice" if action == "reward.choice.claim" else "ActionBar",
			"hand": [{"instance_id": "card"}], "combat": {"hp": 70, "maximum_hp": 70}},
		"pve": {"battle_id": "timeout-battle", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 84}]},
		"reward_choice": {"options": [{"option_id": "reward"}]}}

func run_test() -> Dictionary:
	var checks := {}
	for action in ["battle.play_cards", "room.move", "reward.choice.claim"]:
		for scenario in ["unknown_timeout", "not_expired", "old_room", "old_session", "old_epoch"]:
			var store = load("res://state/game_store.gd").new()
			var gateway := RecordingGateway.new()
			gateway.persist_session = false
			gateway.base_url = OS.get_environment("FANTASYCARD_SERVER_URL")
			gateway.online = true
			gateway.session_generation = 4
			gateway.room_context_epoch = 7
			gateway.room_id = "timeout-room"
			gateway.current_match_id = "timeout-match"
			store.gateway = gateway
			store._room_context_epoch = 7
			store._room_context_room_id = gateway.room_id
			store._room_context_match_id = gateway.current_match_id
			store.room = _room(action)
			store.selected_cards = ["card"]
			store._preview_request = {"request_id": "old-preview"}
			var payload := {"battle_id": "timeout-battle", "target_id": "monster", "card_instance_ids": ["card"]} if action == "battle.play_cards" else {"row": 1, "column": 1} if action == "room.move" else {"option_id": "reward"}
			store.command(action, payload)
			var original: String = gateway.sent[0].request_id
			var telemetry: Array = []
			store.network_telemetry.connect(func(row): telemetry.append(row.duplicate(true)))
			if scenario != "not_expired":
				store._pending_commands[original].deadline = Time.get_ticks_msec() - 1
				store._play_deadline = Time.get_ticks_msec() - 1
			if scenario == "old_room":
				store.room = _room(action, "new-room", "new-match")
				gateway.room_id = "new-room"
				gateway.current_match_id = "new-match"
			elif scenario == "old_session": gateway.session_generation += 1
			elif scenario == "old_epoch":
				store._room_context_epoch += 1
				gateway.room_context_epoch = store._room_context_epoch
			if scenario == "unknown_timeout":
				store.command("battle.select_target", {"battle_id": "timeout-battle", "target_id": "monster"})
				store._latest_commands["battle.select_target"].due = 0
			store._process(0)
			var label: String = action + ":" + scenario
			if scenario == "unknown_timeout":
				checks[label + ": blocks stale action and enters one authority recovery"] = gateway.reconnects == 1 and gateway.recovering and store.room.is_empty() and not store.command(action, payload)
				checks[label + ": blocks a different room write during ambiguous outcome"] = not store.command("battle.select_target", {"battle_id": "timeout-battle", "target_id": "monster"}) and store._latest_commands.is_empty()
				checks[label + ": no replay of uncertain write or stale selection"] = gateway.sent.filter(func(row): return row.kind == action).size() == 1 and store.selected_cards.is_empty() and store._preview_request.is_empty()
				checks[label + ": keeps original unknown execution telemetry"] = telemetry.any(func(row): return row.get("event_type") == "command.timeout" and row.get("request_id") == original and row.get("execution_outcome") == "unknown")
				checks[label + ": keeps the original match for a receipt during recovery"] = store._settlement_match_id() == "timeout-match"
				checks[label + ": explicit room-authority recovery is visible to the UI"] = store.room_authority_recovering()
				checks[label + ": queued write cannot escape on the timeout frame"] = gateway.sent.all(func(row): return row.kind != "battle.select_target")
				store._process(0)
				checks[label + ": recovery does not repeat per frame"] = gateway.reconnects == 1
				gateway.online = true
				gateway.recovering = false
				checks[label + ": connection marker alone cannot revive the stale room"] = not store.command(action, payload) and store.room.is_empty() and store._settlement_match_id() == "timeout-match"
				gateway.recovering = true
				var fresh := _room(action)
				fresh["config_version"] = store.CATALOG.data.version
				fresh.room_revision = 20
				fresh.player.hand = [{"instance_id": "new-card"}]
				fresh.reward_choice.options = [{"option_id": "new-reward"}]
				store._on_event("room.snapshot", fresh)
				checks[label + ": fresh scoped authority retires the recovery UI"] = not store.room_authority_recovering()
				checks[label + ": snapshot alone cannot bypass transport recovery"] = not store.command(action, payload) and gateway.sent.filter(func(row): return row.kind == action).size() == 1
				gateway.online = true
				gateway.recovering = false
				var next_payload := {"battle_id": "timeout-battle", "target_id": "monster", "card_instance_ids": ["new-card"]} if action == "battle.play_cards" else {"row": 2, "column": 2} if action == "room.move" else {"option_id": "new-reward"}
				checks[label + ": only explicit new intent proceeds after recovery"] = store.command(action, next_payload) and gateway.sent.back().payload == next_payload and gateway.sent.back().request_id != original and gateway.sent.filter(func(row): return row.kind == action).size() == 2
			elif scenario == "not_expired":
				checks[label] = gateway.reconnects == 0 and store.has_pending_commands() and not store.command(action, payload)
			else:
				checks[label + ": obsolete timeout cannot reset current room"] = gateway.reconnects == 0 and not gateway.recovering and not store.room.is_empty() and not store._pending_commands.has(original)
			store.free()
			gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks,
		"scope": "Controlled real store timer/command branches with recorded gateway; expired clock injected, no real API/account/PG or natural gameplay acceptance"}
