extends RefCounted

class QuietGateway extends "res://network/gateway.gd":
	var sent: Array = []
	func send(kind: String, _payload: Dictionary = {}, _request_id: String = "") -> bool:
		sent.append(kind)
		return true

class ConfirmationStore extends "res://state/game_store.gd":
	var confirmations := 0
	func _snapshot_confirms_command(_pending: Dictionary, _snapshot: Dictionary) -> bool:
		confirmations += 1
		return false

func _room(store: Node) -> Dictionary:
	return {"config_version": store.CATALOG.data.version, "match_id": "match", "room_id": "room", "room_revision": 10,
		"player": {"player_id": "self", "phase": "Pve", "hand": [{"instance_id": "card"}]},
		"pve": {"battle_id": "battle", "current_target_id": "monster", "monsters": [{"monster_id": "monster", "hp": 10}]},
		"allowed_actions": ["battle.play_cards", "battle.select_target"]}

func _packet(proto: RefCounted, kind: String, schema: String, sequence: int, payload: Dictionary, request_id: String = "") -> PackedByteArray:
	return proto.encode("ServerEnvelope", {"protocol_version": 1, "type": kind, "sequence": sequence, "request_id": request_id, "payload": proto.encode(schema, payload)})

func run_test() -> Dictionary:
	var checks := {}
	for kind in ["player.died", "action.extract_completed", "room.command_cancelled"]:
		var gateway := QuietGateway.new()
		gateway.persist_session = false
		gateway.online = true
		var store: Node = load("res://state/game_store.gd").new()
		store.gateway = gateway
		store._on_event("room.snapshot", _room(store))
		gateway.room_id = "room"
		gateway.current_match_id = "match"
		var origin := gateway.capture_context()
		var reads_before := gateway.sent.size()
		var payload := {"room_id": "room", "match_id": "match", "player_id": "self", "status": "Completed", "command_type": "battle.play_cards", "reason": "RoomEndedBeforeApply", "_command_action": "battle.play_cards", "_origin_context": origin, "_request_id": "pending"}
		var wrong := payload.duplicate(true)
		wrong.match_id = "old-match"
		store._on_event(kind, wrong)
		checks[kind + ": other match keeps current actions"] = store.allowed("battle.play_cards")
		wrong = payload.duplicate(true)
		wrong.room_id = "other-room"
		store._on_event(kind, wrong)
		checks[kind + ": other room keeps current actions"] = store.allowed("battle.play_cards")
		checks[kind + ": foreign terminal frames trigger no read"] = gateway.sent.size() == reads_before
		if kind == "player.died":
			wrong = payload.duplicate(true)
			wrong.player_id = "teammate"
			store._on_event(kind, wrong)
			checks["teammate death cannot end self"] = store.allowed("battle.play_cards")
		if kind == "room.command_cancelled":
			for key in ["session_generation", "room_context_epoch"]:
				wrong = payload.duplicate(true)
				wrong._origin_context[key] = int(origin.get(key, 0)) + 1
				store._on_event(kind, wrong)
				checks["cancellation stale " + key + " cannot end self"] = store.allowed("battle.play_cards")
			wrong = payload.duplicate(true)
			wrong.command_type = "room.move"
			store._on_event(kind, wrong)
			checks["cancellation action must match original request"] = store.allowed("battle.play_cards")
			wrong = payload.duplicate(true)
			wrong.command_type = ""
			wrong._command_action = ""
			store._on_event(kind, wrong)
			checks["cancellation without command identity cannot end self"] = store.allowed("battle.play_cards")
		store._pending_commands["pending"] = {"action": "battle.play_cards", "confirmed": false}
		store._on_event(kind, payload)
		checks[kind + ": terminal closes without confirming or replaying intent"] = not store.allowed("battle.play_cards") and store._pending_commands.is_empty() and store._queued_command.is_empty()
		gateway.sent.clear()
		store.refresh_room_snapshot()
		checks[kind + ": closed room sends no additional read"] = gateway.sent.is_empty()
		store.free()
		gateway.free()

	var gateway := QuietGateway.new()
	gateway.persist_session = false
	gateway.room_id = "room"
	gateway.current_match_id = "match"
	gateway.room_context_epoch = 1
	var proto: RefCounted = load("res://network/protobuf.gd").new()
	var samples: Array = []
	var delivered: Array = []
	gateway.telemetry.connect(func(sample): samples.append(sample))
	gateway.event_received.connect(func(kind, payload): delivered.append({"kind": kind, "payload": payload}))
	gateway._pending_request_started["late"] = {"context": gateway.capture_context(), "action": "battle.play_cards", "started_at": Time.get_ticks_msec()}
	gateway._receive(_packet(proto, "room.command_cancelled", "RoomCommandCancelledEvent", 1, {"room_id": "room", "match_id": "match", "command_type": "battle.play_cards", "reason": "RoomEndedBeforeApply"}, "late"))
	checks["cancelled request measured once with distinct result"] = samples.filter(func(sample): return sample.get("type", "") == "realtime").size() == 1 and samples[0].result == "cancelled"
	# The same IDs in a later local context must not accept an old second frame.
	gateway.room_context_epoch = 2
	gateway.recovering = true
	gateway._receive(_packet(proto, "room.snapshot", "RoomSnapshotEvent", 2, {"room_id": "room", "match_id": "match", "room_revision": 99}, "late"))
	var measurements: Array = samples.filter(func(sample): return sample.get("type", "") == "realtime")
	var ignored: Array = samples.filter(func(sample): return sample.get("type", "") == "lifecycle_guard")
	checks["follow-up retains old epoch and cannot release new recovery"] = gateway.room_revision == 0 and gateway.recovering and delivered.size() == 1 and measurements.size() == 1 and gateway.last_sequence == 2
	checks["ignored follow-up trace is separate from one cancellation measurement"] = ignored.size() == 1 and ignored[0].reason == "prior_room_context" and ignored[0].trace_only and measurements[0].result == "cancelled"
	gateway._receive(_packet(proto, "room.snapshot", "RoomSnapshotEvent", 3, {"room_id": "other-room", "match_id": "other-match", "room_revision": 99}))
	checks["unsolicited old snapshot cannot replace current room"] = gateway.room_id == "room" and gateway.current_match_id == "match" and gateway.room_revision == 0
	gateway._pending_request_started["current"] = {"context": gateway.capture_context(), "action": "room.snapshot.read", "started_at": Time.get_ticks_msec()}
	gateway._receive(_packet(proto, "room.snapshot", "RoomSnapshotEvent", 4, {"room_id": "room", "match_id": "match", "room_revision": 12}, "current"))
	checks["fresh scoped read releases recovery"] = gateway.room_revision == 12 and not gateway.recovering and delivered.size() == 2
	gateway.end_session("", false)
	checks["authentication reset clears follow-up contexts"] = gateway._response_contexts.is_empty()
	gateway.free()
	var recovering_gateway := QuietGateway.new()
	recovering_gateway.persist_session = false
	recovering_gateway.online = true
	recovering_gateway.room_id = "room"
	recovering_gateway.current_match_id = "match"
	var recovering_store := ConfirmationStore.new()
	recovering_store.gateway = recovering_gateway
	recovering_store._on_event("room.snapshot", _room(recovering_store))
	recovering_gateway.event_received.connect(recovering_store._on_event)
	recovering_store._pending_commands["gap-cancel"] = {"action": "battle.play_cards", "confirmed": false}
	recovering_gateway._pending_request_started["gap-cancel"] = {"context": recovering_gateway.capture_context(), "action": "battle.play_cards", "started_at": Time.get_ticks_msec()}
	# A sequence gap suppresses delivery of the cancellation to GameStore.
	# Its following terminal snapshot must still never acknowledge the mutation.
	recovering_gateway._receive(_packet(proto, "room.command_cancelled", "RoomCommandCancelledEvent", 2, {"room_id": "room", "match_id": "match", "command_type": "battle.play_cards", "reason": "RoomEndedBeforeApply"}, "gap-cancel"))
	checks["gap defers cancellation delivery for authoritative recovery"] = recovering_gateway.recovering and recovering_store._pending_commands.has("gap-cancel")
	var terminal := _room(recovering_store)
	terminal.player.phase = "Dead"
	recovering_gateway._receive(_packet(proto, "room.snapshot", "RoomSnapshotEvent", 3, terminal, "gap-cancel"))
	checks["terminal follow-up after gap never confirms cancelled mutation"] = recovering_store.confirmations == 0 and recovering_store._pending_commands.is_empty() and not recovering_store.allowed("battle.play_cards") and not recovering_gateway.recovering
	recovering_store.free()
	recovering_gateway.free()
	return {"ok": not checks.values().has(false), "checks": checks}
