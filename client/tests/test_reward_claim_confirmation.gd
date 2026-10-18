extends RefCounted

class ClaimGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var reconnects := 0
	func new_id() -> String: return "claim-" + str(sent.size())
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload.duplicate(true), "request_id": request_id})
		return true
	func connect_realtime() -> void:
		reconnects += 1
		online = false

func _snapshot(revision: int, selected_present: bool = true, room_id: String = "room") -> Dictionary:
	var result := {"room_id": room_id, "match_id": "match", "room_revision": revision,
		"player": {"player_id": "self", "phase": "Choice" if selected_present else "Action", "hand": []},
		"allowed_actions": ["choice.pick"] if selected_present else ["room.move"]}
	if selected_present:
		result["reward_choice"] = {"options": [{"option_id": "equipment:old"}, {"option_id": "heal:old"}]}
	return result

func _fixture() -> Dictionary:
	var gateway := ClaimGateway.new()
	gateway.persist_session = false
	gateway.online = true
	var store: Node = load("res://state/game_store.gd").new()
	store.gateway = gateway
	store.room = _snapshot(10)
	return {"gateway": gateway, "store": store}

func _close(f: Dictionary) -> void:
	f.store.free()
	f.gateway.free()

func run_test() -> Dictionary:
	var checks := {}
	for scenario in ["cached_missing_revision", "cached_revision_ahead", "ack_then_same_reward", "snapshot_then_ack", "selected_not_first", "timeout"]:
		var f := _fixture()
		var store: Node = f.store
		var option_id := "heal:old" if scenario == "selected_not_first" else "equipment:old"
		var payload := {"option_id": option_id, "equip": false}
		checks[scenario + ": initial command sent"] = store.command("reward.choice.claim", payload)
		var request_id: String = f.gateway.sent[0].request_id
		# Another player's update or a prior tick can advance the room revision
		# while this player's old reward remains selectable in the cached state.
		if scenario in ["cached_missing_revision", "cached_revision_ahead", "selected_not_first", "timeout"]:
			store.room = _snapshot(12)
		elif scenario == "snapshot_then_ack":
			store._on_event("room.snapshot", _snapshot(12))
		store._on_event("reward.choice_claimed", {"_request_id": request_id, "option_id": option_id,
			"_event_revision": 11 if scenario == "cached_revision_ahead" else -1})
		if scenario == "ack_then_same_reward": store._on_event("room.snapshot", _snapshot(13))
		checks[scenario + ": old reward keeps confirmation pending"] = store.has_pending_commands()
		checks[scenario + ": second claim cannot be sent"] = not store.command("reward.choice.claim", payload) and f.gateway.sent.filter(func(row): return row.kind == "reward.choice.claim").size() == 1
		if scenario == "timeout":
			# Confirmed writes recover authority on timeout; they never resend.
			if store._pending_commands.has(request_id):
				store._pending_commands[request_id].deadline = Time.get_ticks_msec() - 1
				store._process(0)
			checks[scenario + ": missing authority reconnects without repeating write"] = f.gateway.reconnects == 1 and store.room.is_empty() and f.gateway.recovering and f.gateway.sent.filter(func(row): return row.kind == "reward.choice.claim").size() == 1
		else:
			store._on_event("room.snapshot", _snapshot(14, false))
			checks[scenario + ": applied snapshot releases confirmation"] = not store.has_pending_commands()
		_close(f)
	var f := _fixture()
	var pending := {"action": "reward.choice.claim", "payload": {"option_id": "equipment:old"}, "room_id": "room", "sent_revision": 10, "confirmed_revision": -1}
	checks["other room never confirms claim"] = not f.store._snapshot_confirms_command(pending, _snapshot(20, false, "other"))
	checks["older snapshot never confirms claim"] = not f.store._snapshot_confirms_command(pending, _snapshot(9, false))
	checks["same revision without event revision cannot confirm"] = not f.store._snapshot_confirms_command(pending, _snapshot(10, false))
	pending.confirmed_revision = 11
	checks["exact event revision with reward removed confirms"] = f.store._snapshot_confirms_command(pending, _snapshot(11, false))
	var next_choice := _snapshot(12)
	next_choice.reward_choice.options = [{"option_id": "equipment:next"}, {"option_id": "heal:next"}]
	checks["distinct next choice does not stall old confirmation"] = f.store._snapshot_confirms_command(pending, next_choice)
	pending.action = "room.move"
	checks["other command confirmation remains revision based"] = f.store._snapshot_confirms_command(pending, _snapshot(11))
	pending.action = "choice.pick"
	checks["legacy choice alias also requires consumed option"] = not f.store._snapshot_confirms_command(pending, _snapshot(12))
	# The real server deliberately omits room_revision on this success event.
	var proto = load("res://network/protobuf.gd").new()
	var wire: PackedByteArray = proto.encode("ServerEnvelope", {"protocol_version": 1, "type": "reward.choice_claimed", "sequence": 1,
		"request_id": "claim-wire", "payload": proto.encode("RewardChoiceClaimedEvent", {"option_id": "equipment:old", "applied": 1})})
	var decoded: Dictionary = proto.decode("ServerEnvelope", wire)
	checks["real protobuf preserves absent success revision"] = not decoded.has("room_revision")
	_close(f)
	return {"ok": checks.values().all(func(value): return value == true), "checks": checks}
