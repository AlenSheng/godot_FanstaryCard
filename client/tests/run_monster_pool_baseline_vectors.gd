extends SceneTree

var failures: Array = []
var count := 0
var policy_counts := {"automatic":0, "optional":0}

func _initialize() -> void:
	call_deferred("_run")

func check(ok: bool, field: String, row: Dictionary) -> void:
	if not ok: failures.append({"field":field, "hero":row.get("hero"), "seed":row.get("seed"), "optional":row.get("optional")})

func _run() -> void:
	root.get_node("Game").set_process(false)
	var codec = load("res://network/protobuf.gd").new()
	var source := OS.get_environment("PR13_POOL_SOURCE")
	var file := FileAccess.open(OS.get_environment("PR13_POOL_VECTORS"), FileAccess.READ)
	if file == null:
		quit(2)
		return
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var row: Dictionary = JSON.parse_string(line)
		check(row.source_sha==source, "original_source", row)
		var wire := Marshalls.base64_to_raw(row.response_wire)
		check(wire.size()==int(row.wire_bytes) and wire.size()<=16384, "original_wire_length", row)
		var envelope: Dictionary = codec.decode("ServerEnvelope", wire)
		check(codec.error.is_empty() and envelope.get("type", "")=="room.snapshot", "original_server_envelope", row)
		var payload: Dictionary = codec.decode("RoomSnapshotEvent", envelope.payload)
		check(codec.error.is_empty(), "original_room_snapshot", row)
		var player: Dictionary = payload.player
		check(str(player.hero_class)==str(row.hero) and str(player.player_id)==str(row.actual_actor), "actor_and_hero", row)
		check(player.hand.size()+int(player.library_count)+int(player.discard_count)==int(row.expected_total_pool), "actual_pool_count", row)
		var pool: Dictionary = player.get("monster_pool", {})
		if bool(row.optional):
			policy_counts.optional += 1
			check(pool.get("pending", []).size()==1 and pool.get("active", []).is_empty(), "actual_optional_offer", row)
			check(payload.get("allowed_actions", []).has("monster.choose"), "optional_choice_action", row)
			check(str(pool.pending[0].card_id)=="M-FIREBAT", "actual_kill_source_card", row)
		else:
			policy_counts.automatic += 1
			check(pool.is_empty(), "default_optional_pool_absent", row)
			check(not payload.get("allowed_actions", []).has("monster.choose"), "default_no_choice_action", row)
		check(bool(row.actual_resolution.TargetDefeated) and str(row.actual_killed_monster)=="fire-bat", "actual_finishing_kill", row)
		count += 1
	check(count==18 and policy_counts.automatic==9 and policy_counts.optional==9, "whole_declared_matrix", {})
	var result := {"ok":failures.is_empty(), "native_rows":count, "policy_rows":policy_counts, "failures":failures, "scope":"Original native room projection and Protobuf; controlled OFFLINE boundaries only, no render or LIVE acceptance"}
	FileAccess.open(OS.get_environment("PR13_POOL_RESULT"), FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
