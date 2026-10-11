extends RefCounted

# Receives original native events through the product gateway and GameStore.
# send is intercepted only to keep this OFFLINE fixture from initiating network I/O.
class QuietGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var fixture_request_id := ""
	func new_id() -> String:
		if not fixture_request_id.is_empty():
			var result := fixture_request_id
			fixture_request_id = ""
			return result
		return super.new_id()
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		sent.append({"kind": kind, "payload": payload, "request_id": request_id})
		if not request_id.is_empty():
			_pending_request_started[request_id] = {"action": kind, "started_at": Time.get_ticks_msec(), "context": capture_context().duplicate(true)}
		return true

var failures: Array = []
var commands_encoded := 0
var native_rows_received := 0
var native_frames_received := 0
var replay_frames_received := 0
var operation_counts := {}

func _check(condition: bool, field: String, row: Dictionary = {}) -> void:
	if not condition:
		failures.append({"field": field, "row_id": row.get("row_id", row.get("RowId", "")), "operation": row.get("operation", row.get("Operation", ""))})

func _read_rows(path: String) -> Array:
	var rows: Array = []
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		_check(false, "input_file_open:" + path)
		return rows
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty():
			continue
		var parsed = JSON.parse_string(line)
		if not parsed is Dictionary:
			_check(false, "input_line_dictionary")
			continue
		rows.append(parsed)
	file.close()
	return rows

func _encode() -> void:
	var phase := OS.get_environment("PR13_LEGAL_ROUTE_BATCH")
	var expected_counts := {"kill": 9, "choose": 27, "final": 27}
	_check(expected_counts.has(phase), "encode_batch")
	var source := OS.get_environment("PR13_LEGAL_ROUTE_SOURCE")
	var rows := _read_rows(OS.get_environment("PR13_LEGAL_ROUTE_DESCRIPTORS"))
	var outgoing_path := OS.get_environment("PR13_LEGAL_ROUTE_COMMANDS")
	if outgoing_path.is_empty() or FileAccess.file_exists(outgoing_path):
		_check(false, "fresh_command_file_required")
		return
	var outgoing := FileAccess.open(outgoing_path, FileAccess.WRITE)
	if outgoing == null:
		_check(false, "command_file_open")
		return
	var seen := {}
	var proto: RefCounted = load("res://network/protobuf.gd").new()
	var gateway: Node = QuietGateway.new()
	for row in rows:
		_check(str(row.SourceSha) == source and source.length() == 40, "command_source", row)
		var key := str(row.RowId) + ":" + str(row.Operation)
		_check(not seen.has(key), "unique_descriptor", row)
		seen[key] = true
		_check(str(gateway.COMMANDS.get(str(row.Type), "")) == str(row.Schema), "product_command_schema", row)
		_check(str(row.RequestId).length() > 0 and str(row.RequestId).length() <= 80, "request_id_bound", row)
		var payload: PackedByteArray = proto.encode(str(row.Schema), row.Payload)
		_check(proto.error.is_empty(), "encode_payload", row)
		var envelope := {"protocol_version": 1, "type": str(row.Type), "request_id": str(row.RequestId),
			"expected_revision": int(row.ExpectedRevision), "room_id": str(row.RoomId), "match_id": str(row.MatchId), "payload": payload}
		var wire: PackedByteArray = proto.encode("ClientEnvelope", envelope)
		_check(proto.error.is_empty() and wire.size() > 0 and wire.size() <= 16384, "encode_complete_envelope", row)
		var decoded: Dictionary = proto.decode("ClientEnvelope", wire)
		_check(proto.error.is_empty(), "decode_own_envelope", row)
		for field in ["protocol_version", "type", "request_id", "expected_revision", "room_id", "match_id"]:
			_check(decoded.get(field) == envelope.get(field), "complete_envelope:" + field, row)
		var decoded_payload: Dictionary = proto.decode(str(row.Schema), decoded.get("payload", PackedByteArray()))
		_check(proto.error.is_empty(), "decode_own_payload", row)
		for field in row.Payload:
			_check(decoded_payload.get(field, false if field == "accept" else null) == row.Payload[field], "payload:" + field, row)
		_check(not decoded_payload.has("player_id") and not decoded_payload.has("owner_id") and not decoded_payload.has("epoch") and not decoded_payload.has("version"), "owner_is_authenticated_not_payload", row)
		outgoing.store_line(JSON.stringify({"source_sha": source, "row_id": row.RowId, "operation": row.Operation,
			"actor_id": row.ActorId, "wire": Marshalls.raw_to_base64(wire), "wire_bytes": wire.size()}))
		commands_encoded += 1
	outgoing.close()
	gateway.free()
	_check(commands_encoded == int(expected_counts.get(phase, -1)), "complete_encode_batch")

func _native_player(snapshot: Dictionary, actor: String) -> Dictionary:
	for player in snapshot.get("Players", []):
		if str(player.PlayerId) == actor:
			return player
	return {}

func _cards_match(actual: Array, native: Array) -> bool:
	if actual.size() != native.size():
		return false
	for index in range(actual.size()):
		if str(actual[index].get("instance_id", "")) != str(native[index].InstanceId):
			return false
		if str(actual[index].get("card_id", "")) != str(native[index].CardId):
			return false
		if int(actual[index].get("level", 0)) != int(native[index].Level):
			return false
	return true

func _inspect_store(store: Node, native: Dictionary, row: Dictionary, label: String) -> void:
	var expected := _native_player(native, str(row.actor_id))
	_check(not expected.is_empty(), label + ":native_actor", row)
	if expected.is_empty():
		return
	var snapshot: Dictionary = store.room
	var player: Dictionary = snapshot.get("player", {})
	var pool: Dictionary = player.get("monster_pool", {})
	_check(str(snapshot.get("room_id", "")) == str(native.RoomId) and int(snapshot.get("room_revision", -1)) == int(native.Revision), label + ":room_revision", row)
	_check(str(snapshot.get("match_id", "")) == str(row.command.MatchId), label + ":match", row)
	_check(str(player.get("player_id", "")) == str(row.actor_id), label + ":authenticated_actor", row)
	_check(str(player.get("hero_class", "")) == str(row.hero), label + ":hero", row)
	_check(int(pool.get("capacity", -1)) == 5, label + ":frozen_candidate_capacity", row)
	_check(_cards_match(pool.get("pending", []), expected.MonsterPool.Pending), label + ":pending_instance_order", row)
	_check(_cards_match(pool.get("active", []), expected.MonsterPool.Active), label + ":active_instance_order", row)
	_check(_cards_match(player.get("hand", []), expected.Combat.Deck.Hand), label + ":hand_instance_order", row)
	_check(int(player.get("library_count", -1)) == expected.Combat.Deck.Library.size(), label + ":library_count", row)
	_check(int(player.get("discard_count", -1)) == expected.Combat.Deck.Discard.size(), label + ":discard_count", row)
	var combat: Dictionary = player.get("combat", {})
	_check(int(combat.get("hp", 0)) == int(expected.Combat.Hp) and int(combat.get("shield", 0)) == int(expected.Combat.Shield) and int(combat.get("maximum_hp", 0)) == int(expected.Combat.MaximumHp), label + ":native_combat_values", row)
	var phases := {1: "Pve", 2: "ActionBar", 3: "Pvp", 4: "Dead", 5: "Extracted", 6: "Choice"}
	_check(str(player.get("phase", "")) == str(phases.get(int(expected.Phase), "invalid")), label + ":phase", row)
	_check(snapshot.get("allowed_actions", []).has("monster.choose") == (not expected.MonsterPool.Pending.is_empty() and str(player.get("phase", "")) in ["Choice", "ActionBar"]), label + ":typed_choice_allowed", row)
	if str(row.operation) == "terminal-late":
		_check(store._pending_commands.is_empty() and store._queued_command.is_empty() and not store.allowed("monster.choose") and not store.allowed("battle.play_cards"), label + ":terminal_never_confirms_mutation", row)

func _receive_row(row: Dictionary) -> void:
	var gateway: Node = QuietGateway.new()
	gateway.persist_session = false
	gateway.online = true
	var store: Node = load("res://state/game_store.gd").new()
	store.gateway = gateway
	var delivered: Array = []
	var samples: Array = []
	gateway.event_received.connect(store._on_event)
	gateway.event_received.connect(func(kind, payload): delivered.append({"kind": kind, "payload": payload}))
	gateway.telemetry.connect(func(sample): samples.append(sample))
	var proto: RefCounted = load("res://network/protobuf.gd").new()
	var initial := Marshalls.base64_to_raw(str(row.initial_wire))
	var initial_envelope: Dictionary = proto.decode("ServerEnvelope", initial)
	_check(proto.error.is_empty() and initial_envelope.get("type", "") == "room.snapshot", "native_initial_event", row)
	gateway._receive(initial)
	native_frames_received += 1
	_inspect_store(store, row.before, row, "before")
	if str(row.operation) == "foreign":
		_check(not store._intent_valid("monster.choose", row.command.Payload), "actual_store_rejects_foreign_candidate_before_send", row)
	elif str(row.operation) == "accept":
		_check(store.allowed("monster.choose") and store._intent_valid("monster.choose", row.command.Payload), "actual_store_accepts_owned_pending_intent", row)
	elif str(row.operation) == "kill":
		_check(store.allowed("battle.play_cards") and store._intent_valid("battle.play_cards", row.command.Payload), "actual_store_accepts_legal_native_finishing_intent", row)
	var request_id := str(row.command.RequestId)
	var origin: Dictionary = gateway.capture_context().duplicate(true)
	gateway.fixture_request_id = request_id
	_check(store._send_queued_command({"action": str(row.command.Type), "payload": row.command.Payload.duplicate(true)}), "actual_product_pending_command_registered", row)
	_check(store._pending_commands.has(request_id) and store._pending_commands[request_id].has("retry") and store._pending_commands[request_id].has("deadline"), "complete_product_pending_command_fields", row)
	# In the fingerprint control the original accepted snapshot precedes the
	# changed request rejection in the same original native event sequence.
	for encoded in row.response_wires:
		var bytes := Marshalls.base64_to_raw(str(encoded))
		_check(bytes.size() > 0 and bytes.size() <= 16384, "native_event_bound", row)
		var event_envelope: Dictionary = proto.decode("ServerEnvelope", bytes)
		_check(proto.error.is_empty() and int(event_envelope.get("protocol_version", 0)) == 1 and not str(event_envelope.get("event_id", "")).is_empty(), "native_typed_event_identity", row)
		gateway._receive(bytes)
		native_frames_received += 1
	_inspect_store(store, row.after, row, "after")
	var after_state: Dictionary = store.room.duplicate(true)
	var delivered_after := delivered.size()
	var samples_after := samples.size()
	if not row.replay_response_wires.is_empty():
		_check(row.replay_response_wires == row.response_wires, "complete_response_wire_EventId_Sequence_replay", row)
	for encoded in row.replay_response_wires:
		gateway._receive(Marshalls.base64_to_raw(str(encoded)))
		replay_frames_received += 1
	_check(store.room == after_state and delivered.size() == delivered_after and samples.size() == samples_after, "original_event_replay_is_not_applied_twice", row)
	if str(row.operation) == "terminal-late":
		_check(delivered.any(func(event): return event.kind == "room.command_cancelled" and event.payload.get("reason", "") == "RoomEndedBeforeApply" and event.payload.get("command_type", "") == "monster.choose" and str(event.payload.get("room_id", "")) == str(row.command.RoomId) and str(event.payload.get("match_id", "")) == str(row.command.MatchId)), "typed_terminal_cancel_delivered", row)
		_check(samples.size() == 1 and samples[0].get("result", "") == "cancelled", "terminal_measured_cancelled_once", row)
	elif str(row.operation) in ["leave-first", "leave-second"]:
		var completed := str(row.operation) == "leave-second"
		_check(delivered.any(func(event): return event.kind == "duel.leave_ack" and str(event.payload.get("duel_id", "")) == str(row.command.Payload.duel_id) and bool(event.payload.get("completed", false)) == completed and str(event.payload.get("_request_id", "")) == request_id and str(event.payload.get("_command_action", "")) == "duel.leave" and event.payload.get("_origin_context", {}) == origin and int(event.payload.get("_sequence", 0)) == int(initial_envelope.get("sequence", 0)) + 1 and int(event.payload.get("_event_revision", -1)) == int(row.after.Revision)), "typed_duel_leave_ack_fields_and_original_context", row)
	elif str(row.operation) == "kill":
		_check(delivered.any(func(event): return event.kind == "battle.combo_resolved" and str(event.payload.get("battle_id", "")) == str(row.command.Payload.battle_id) and str(event.payload.get("attacker_id", "")) == str(row.owner_id) and str(event.payload.get("target_id", "")) == str(row.command.Payload.target_id) and bool(event.payload.get("target_defeated", false))), "typed_native_kill_owner_and_target", row)
	elif str(row.operation) == "foreign":
		var eligible_peer := _native_player(row.before, str(row.actor_id))
		_check(int(eligible_peer.get("Phase", 0)) == 6 and eligible_peer.MonsterPool.Pending.size() == 1 and str(eligible_peer.MonsterPool.Pending[0].InstanceId) == str(row.peer_control_candidate_id) and str(row.peer_control_candidate_id) != str(row.candidate_id), "foreign_owner_reaches_candidate_lookup", row)
		_check(delivered.any(func(event): return event.kind == "error.command_rejected" and event.payload.get("code", "") == "COMMAND_REJECTED" and event.payload.get("detail", "") == "The monster candidate no longer exists."), "foreign_owner_rejected_by_candidate_lookup", row)
	elif str(row.operation) == "fingerprint-mismatch":
		_check(delivered.any(func(event): return event.kind == "error.command_rejected" and event.payload.get("code", "") == "REQUEST_ID_REUSED"), "changed_same_request_rejected", row)
	elif str(row.operation) in ["accept", "restore-receipt"]:
		_check(store.room.player.monster_pool.active.size() == 1 and str(store.room.player.monster_pool.active[0].instance_id) == str(row.candidate_id), "owned_candidate_single_instance", row)
	_check(not gateway.recovering, "native_sequence_did_not_enter_gap_recovery", row)
	operation_counts[row.operation] = int(operation_counts.get(row.operation, 0)) + 1
	native_rows_received += 1
	store.free()
	gateway.free()

func _receive() -> void:
	var directory := OS.get_environment("PR13_LEGAL_ROUTE_DIRECTORY")
	var source := OS.get_environment("PR13_LEGAL_ROUTE_SOURCE")
	for name in ["kill-events.jsonl", "choose-events.jsonl", "final-events.jsonl"]:
		for row in _read_rows(directory.path_join(name)):
			_check(str(row.get("source_sha", "")) == source and source.length() == 40, "native_row_source", row)
			_receive_row(row)
	var expected := {"kill": 9, "foreign": 9, "accept": 9, "fingerprint-mismatch": 9,
		"restore-receipt": 9, "leave-first": 9, "leave-second": 9, "terminal-late": 9}
	_check(native_rows_received == 72 and operation_counts == expected, "complete_legal_route_matrix")
	_check(native_frames_received == 189 and replay_frames_received == 45, "complete_original_event_and_replay_frame_counts")

func run_test() -> Dictionary:
	var mode := OS.get_environment("PR13_LEGAL_ROUTE_GODOT_MODE")
	if mode == "encode":
		_encode()
	elif mode == "receive":
		_receive()
	else:
		_check(false, "explicit_encode_or_receive_mode_required")
	return {"ok": failures.is_empty(), "mode": mode, "source_sha": OS.get_environment("PR13_LEGAL_ROUTE_SOURCE"),
		"commands_encoded": commands_encoded, "native_rows_received": native_rows_received,
		"original_native_frames_received": native_frames_received, "original_replay_frames_received": replay_frames_received,
		"operation_counts": operation_counts, "failures": failures,
		"scope": "OFFLINE legal base deck, controlled O1 HP1 and explicit actor PVP start; real original Godot wire and product typed Gateway/GameStore; no LIVE/GUI/MAIN acceptance"}
