extends Node

const Proto = preload("res://network/protobuf.gd")

func _ready() -> void:
	_run.call_deferred()

func _run() -> void:
	var input_path := OS.get_environment("PR13_PREVIEW_WIRE_INPUT")
	var output_path := OS.get_environment("PR13_PREVIEW_WIRE_OUTPUT")
	var native = JSON.parse_string(FileAccess.get_file_as_string(input_path))
	var checks: Array = []
	if not native is Dictionary or native.get("caseId") != "PR13-B02.3-T02":
		get_tree().quit(2)
		return
	for row in native.actual.rows:
		var proto := Proto.new()
		var command: Dictionary = proto.decode("ClientEnvelope", Marshalls.base64_to_raw(row.commandWire))
		var request: Dictionary = proto.decode("BattlePlayCardsCommand", command.payload)
		var response: Dictionary = proto.decode("ServerEnvelope", Marshalls.base64_to_raw(row.responseWire))
		var payload: Dictionary = proto.decode("BattleComboResolvedEvent", response.payload)
		checks.append({"case_id": "PR13-B02.3-T02", "name": "native Protobuf order and core", "passed": proto.error.is_empty() and request.card_instance_ids == row.order and payload.card_instance_ids == row.order and payload.core_element == row.CoreElement})
		var store = load("res://state/game_store.gd").new()
		var gateway = load("res://network/gateway.gd").new()
		gateway.persist_session = false
		gateway.online = true
		store.gateway = gateway
		store.selected_cards.assign(row.order)
		store.room = {"room_id": "pg-wire-room", "room_revision": int(response.room_revision), "allowed_actions": ["battle.play_cards"], "player": {"hand": [{"instance_id": row.order[0]}, {"instance_id": row.order[1]}]}, "pve": {"battle_id": request.battle_id, "current_target_id": request.target_id, "monsters": [{"monster_id": request.target_id, "hp": 500}]}}
		store._preview_request = {"request_id": response.request_id, "context": store._preview_context(store.selected_cards), "revision": int(response.room_revision)}
		store._preview_deadline = Time.get_ticks_msec() + 1000
		payload["_request_id"] = response.request_id
		payload["_room_revision"] = int(response.room_revision)
		store._accept_combat_preview(payload)
		checks.append({"case_id": "PR13-B02.3-T02", "name": "current native preview accepted", "passed": not store.combat_preview.is_empty() and store.combat_preview.core_element == row.CoreElement})
		store.room.room_revision += 1
		store._preview_request = {"request_id": response.request_id, "context": store._preview_context(store.selected_cards), "revision": int(store.room.room_revision)}
		store._preview_deadline = Time.get_ticks_msec() + 1000
		store.combat_preview = {"current_marker": "newer-authority"}
		var current: Dictionary = store.combat_preview.duplicate(true)
		store._accept_combat_preview(payload)
		checks.append({"case_id": "PR13-B02.3-T03", "name": "delayed native preview cannot overwrite newer revision", "passed": store.combat_preview == current})
		store.free()
		gateway.free()
	for path in ["res://tests/test_protobuf.gd", "res://tests/test_combat_preview_state.gd"]:
		var result: Dictionary = load(path).new().run_test()
		checks.append({"name": path, "passed": result.ok, "message": result.message})
	var ok: bool = checks.size() == 8 and checks.all(func(row): return row.passed)
	var file := FileAccess.open(output_path, FileAccess.WRITE)
	file.store_string(JSON.stringify({"ok": ok, "checks": checks}) + "\n")
	file.close()
	get_tree().quit(0 if ok else 1)
