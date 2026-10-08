extends SceneTree

const LoadClient = preload("res://tests/gameplay_load_client.gd")

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	await process_frame
	var game: Node = root.get_node("Game")
	var gateway: Node = game.get("gateway")
	var session := ConfigFile.new()
	var seeded := session.load("user://session.cfg") == OK
	var isolated: bool = seeded and not gateway.persist_session and gateway.last_sequence == 0 and gateway.room_id.is_empty() and gateway.room_revision == 0 and gateway.device_id != "fixture-shared-device"
	var session_case := {"case_id": "LOAD-07.3-T03", "passed": isolated,
		"actual": {"pid": OS.get_process_id(), "userdata": OS.get_user_data_dir(),
			"seeded_session_present": seeded, "persist_session": gateway.persist_session,
			"sequence": gateway.last_sequence, "room_id": gateway.room_id,
			"device_id_sha256": str(gateway.device_id).sha256_text()}}
	var probe: Node = LoadClient.new()
	probe.report_path = "user://blocked-audit"
	DirAccess.make_dir_recursive_absolute("user://blocked-audit.telemetry.jsonl")
	probe.audit_buffer.append('{"event_seq":1}')
	probe.audit_buffer.append('{"event_seq":2}')
	probe._flush_audit()
	var write_error := FileAccess.get_open_error()
	var loss_case := {"case_id": "LOAD-07.3-T02", "passed": probe.audit_lost_count == 2 and probe.audit_buffer.is_empty() and write_error != OK,
		"actual": {"audit_lost_count": probe.audit_lost_count, "buffer_remaining": probe.audit_buffer.size(),
			"file_open_error": write_error, "injection": "Owned audit destination is a directory; actual FileAccess write-open fails."}}
	probe.free()
	var result := {"schema_version": 1, "kind": "real_godot_offline_fault_fixture", "cases": [session_case, loss_case]}
	var output := FileAccess.open(OS.get_environment("PR13_FAULT_REPORT"), FileAccess.WRITE)
	if output == null:
		printerr("PR13 fixture result could not be written")
		quit(1)
		return
	output.store_string(JSON.stringify(result))
	output.close()
	print("PR13_FAULT " + JSON.stringify(result))
	quit(0 if isolated and loss_case.passed else 1)
