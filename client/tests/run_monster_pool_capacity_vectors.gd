extends SceneTree

var failures: Array = []
var count := 0
var counts := {"PR13-B09.2-T01":0, "PR13-B09.2-T02":0, "PR13-B09.2-T03":0}

func _initialize() -> void:
	call_deferred("_run")

func check(ok: bool, field: String, row: Dictionary) -> void:
	if not ok: failures.append({"field":field, "case":row.get("case_id"), "hero":row.get("actual", {}).get("hero"), "seed":row.get("actual", {}).get("seed"), "capacity":row.get("actual", {}).get("capacity")})

func cards_match(actual: Array, original: Array) -> bool:
	if actual.size()!=original.size(): return false
	for index in range(actual.size()):
		if str(actual[index].get("instance_id", ""))!=str(original[index].InstanceId): return false
		if str(actual[index].get("card_id", ""))!=str(original[index].CardId): return false
		if int(actual[index].get("level", 0))!=int(original[index].Level): return false
	return true

func inspect_snapshot(codec, row: Dictionary, label: String) -> Dictionary:
	var native: Dictionary = row.actual[label]
	var expected: Dictionary = native.Players[0]
	var wire := Marshalls.base64_to_raw(row[label+"_wire"])
	check(wire.size()==int(row[label+"_wire_bytes"]) and wire.size()<=16384, label+"_wire_length", row)
	var envelope: Dictionary = codec.decode("ServerEnvelope", wire)
	check(codec.error.is_empty() and envelope.get("type", "")=="room.snapshot", label+"_envelope", row)
	var snapshot: Dictionary = codec.decode("RoomSnapshotEvent", envelope.get("payload", PackedByteArray()))
	check(codec.error.is_empty(), label+"_decode", row)
	var player: Dictionary = snapshot.get("player", {})
	var pool: Dictionary = player.get("monster_pool", {})
	check(str(player.get("player_id", ""))==str(expected.PlayerId) and str(player.get("hero_class", ""))==str(row.actual.hero), label+"_actor", row)
	check(int(pool.get("capacity", 0))==int(row.actual.capacity), label+"_capacity", row)
	check(cards_match(pool.get("pending", []), expected.MonsterPool.Pending), label+"_pending_identity", row)
	check(cards_match(pool.get("active", []), expected.MonsterPool.Active), label+"_active_identity", row)
	check(cards_match(player.get("hand", []), expected.Combat.Deck.Hand), label+"_hand_identity_and_order", row)
	check(int(player.get("library_count", -1))==expected.Combat.Deck.Library.size(), label+"_library_count", row)
	check(int(player.get("discard_count", -1))==expected.Combat.Deck.Discard.size(), label+"_discard_count", row)
	var allowed: Array = snapshot.get("allowed_actions", [])
	check(allowed.has("monster.choose")== (not expected.MonsterPool.Pending.is_empty()), label+"_choice_action", row)
	check(int(snapshot.get("room_revision", -1))==int(native.Revision) and str(snapshot.get("room_id", ""))==str(native.RoomId), label+"_room_identity", row)
	return snapshot

func _run() -> void:
	var game = root.get_node("Game")
	game.set_process(false)
	var codec = load("res://network/protobuf.gd").new()
	var outbound := FileAccess.open(OS.get_environment("PR13_POOL_CAPACITY_CLIENT_COMMANDS"), FileAccess.WRITE)
	var file := FileAccess.open(OS.get_environment("PR13_POOL_CAPACITY_VECTORS"), FileAccess.READ)
	if file==null or outbound==null:
		quit(2)
		return
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var row: Dictionary = JSON.parse_string(line)
		check(str(row.source_sha)==OS.get_environment("PR13_POOL_CAPACITY_SOURCE"), "source", row)
		var before := inspect_snapshot(codec, row, "before")
		var after := inspect_snapshot(codec, row, "after")
		var request := Marshalls.base64_to_raw(row.request_wire)
		var envelope: Dictionary = codec.decode("ClientEnvelope", request)
		check(codec.error.is_empty() and envelope.get("type", "")=="monster.choose" and request.size()==int(row.request_wire_bytes), "native_choice_envelope", row)
		check(str(envelope.get("room_id", ""))==str(row.actual.before.RoomId) and int(envelope.get("expected_revision", -1))==int(row.actual.before.Revision), "choice_room_and_revision", row)
		var choice: Dictionary = codec.decode("MonsterCardChooseCommand", envelope.get("payload", PackedByteArray()))
		check(codec.error.is_empty(), "choice_payload", row)
		check(str(choice.get("candidate_id", ""))==str(row.actual.candidate.InstanceId), "choice_candidate", row)
		var accept := str(row.case_id)!="PR13-B09.2-T03"
		check(bool(choice.get("accept", false))==accept, "choice_accept_or_skip", row)
		if row.actual.has("replacement"):
			check(str(choice.get("replace_instance_id", ""))==str(row.actual.replacement.InstanceId), "choice_replacement", row)
		else:
			check(str(choice.get("replace_instance_id", "")).is_empty(), "choice_no_replacement", row)
		var outgoing := {"candidate_id":str(row.actual.candidate.InstanceId), "accept":accept}
		if row.actual.has("replacement"): outgoing.replace_instance_id = str(row.actual.replacement.InstanceId)
		var payload: PackedByteArray = codec.encode("MonsterCardChooseCommand", outgoing)
		check(codec.error.is_empty(), "Godot_encode_choice", row)
		var outgoing_envelope := {"protocol_version":1, "type":"monster.choose", "request_id":str(envelope.request_id), "expected_revision":int(row.actual.before.Revision), "room_id":str(row.actual.before.RoomId), "payload":payload}
		var outbound_wire: PackedByteArray = codec.encode("ClientEnvelope", outgoing_envelope)
		check(codec.error.is_empty(), "Godot_encode_envelope", row)
		outbound.store_line(JSON.stringify({"case_id":row.case_id, "source_sha":row.source_sha, "wire":Marshalls.raw_to_base64(outbound_wire), "candidate_id":outgoing.candidate_id, "accept":accept, "replacement":outgoing.get("replace_instance_id", ""), "room_id":outgoing_envelope.room_id, "request_id":outgoing_envelope.request_id, "expected_revision":outgoing_envelope.expected_revision}))
		game.room = before
		check(game._intent_valid("monster.choose", choice), "original_choice_intent", row)
		check(not game._intent_valid("monster.choose", {"candidate_id":"00000000-0000-0000-0000-000000000001", "accept":accept}), "foreign_candidate_rejected", row)
		if row.actual.has("replacement"):
			var invalid: Dictionary = choice.duplicate(true)
			invalid.replace_instance_id = str(row.actual.Base[0].InstanceId)
			check(not game._intent_valid("monster.choose", invalid), "base_replacement_rejected", row)
		game.room = after
		check(not game._intent_valid("monster.choose", choice), "resolved_candidate_not_reused", row)
		count += 1
		counts[row.case_id] = int(counts.get(row.case_id, 0))+1
	game.room = {}
	outbound.close()
	check(count==279 and counts=={"PR13-B09.2-T01":144, "PR13-B09.2-T02":81, "PR13-B09.2-T03":54}, "whole_matrix", {})
	var result := {"ok":failures.is_empty(), "native_decision_rows":count, "original_snapshot_frames":count*2, "case_rows":counts, "failures":failures, "scope":"Original cloud Protobuf and actual Game intent validation; OFFLINE only, no GUI or LIVE acceptance"}
	FileAccess.open(OS.get_environment("PR13_POOL_CAPACITY_RESULT"), FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
