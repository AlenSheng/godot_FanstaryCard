extends SceneTree

const Proto = preload("res://network/protobuf.gd")
var failures: Array = []
var count := 0

func check(condition: bool, field: String, row: Dictionary, actual: Variant = null, expected: Variant = null) -> void:
	if not condition and failures.size() < 100:
		failures.append({"case_id":row.get("case_id", ""),"hero":row.get("hero", ""),"recipe":row.get("recipe", ""),"seed":row.get("seed",0),"group":row.get("group", ""),"weapon_level":row.get("weapon_level",0),"hp_boundary":row.get("hp_boundary", ""),"equipment_profile":row.get("equipment_profile", ""),"field":field,"actual":actual,"expected":expected})

func _initialize() -> void:
	var file := FileAccess.open(OS.get_environment("PR13_TUNING_VECTORS"), FileAccess.READ)
	if file == null:
		quit(2)
		return
	var store = load("res://state/game_store.gd").new()
	var gateway = load("res://network/gateway.gd").new()
	gateway.persist_session = false
	gateway.online = true
	store.gateway = gateway
	var cases := {}
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var value: Variant = JSON.parse_string(line)
		if not value is Dictionary:
			failures.append({"field":"invalid_native_row"})
			break
		var row: Dictionary = value
		check(row.schema == "actual_tuning_recovery_v1" and row.passed and row.source_sha == OS.get_environment("PR13_TUNING_NATIVE_SOURCE"), "native_identity", row)
		store.room = row.input_room
		store.hero_class = row.hero
		store.selected_cards.assign(row.ids)
		var before := JSON.stringify(store.room)
		var calculated: Dictionary = store._calculate_combat_preview(row.ids)
		check(before == JSON.stringify(store.room), "pure_client_preview", row)
		var proto := Proto.new()
		var command: Dictionary = proto.decode("ClientEnvelope", Marshalls.base64_to_raw(row.command_wire))
		var request: Dictionary = proto.decode("BattlePlayCardsCommand", command.get("payload", PackedByteArray()))
		var response: Dictionary = proto.decode("ServerEnvelope", Marshalls.base64_to_raw(row.response_wire))
		var payload: Dictionary = proto.decode("BattleComboResolvedEvent", response.get("payload", PackedByteArray()))
		check(proto.error.is_empty(), "original_server_protocol_decoded", row, proto.error)
		check(request.get("card_instance_ids", []) == row.ids and payload.get("card_instance_ids", []) == row.ids, "original_order_preserved", row)
		check(command.get("type", "") == "combat.preview" and response.get("type", "") == "combat.previewed", "actual_router_response", row)
		for key in row.expected:
			var expected: Variant = row.expected[key]
			if key == "core_element":
				check(calculated.get(key, "") == expected and payload.get(key, "") == expected, key, row, [calculated.get(key),payload.get(key)], expected)
			else:
				check(absf(float(calculated.get(key, -999)) - float(expected)) < .000001, "client_" + key, row, calculated.get(key), expected)
				check(absf(float(payload.get(key, 0)) - float(expected)) < .000001, "wire_" + key, row, payload.get(key,0), expected)
		check(int(calculated.get("heal_overflow",-1)) == int(row.heal_overflow), "separate_heal_overflow", row, calculated.get("heal_overflow"), row.heal_overflow)
		store._preview_request = {"request_id":response.request_id,"context":store._preview_context(store.selected_cards),"revision":int(response.room_revision)}
		store._preview_deadline = Time.get_ticks_msec() + 1000
		payload["_request_id"] = response.request_id
		payload["_room_revision"] = int(response.room_revision)
		store.combat_preview = {}
		store._accept_combat_preview(payload)
		check(not store.combat_preview.is_empty() and store.combat_preview.get("core_element", "") == row.expected.core_element, "current_native_preview_accepted", row)
		store.room.room_revision += 1
		store._preview_request = {"request_id":response.request_id,"context":store._preview_context(store.selected_cards),"revision":int(store.room.room_revision)}
		store._preview_deadline = Time.get_ticks_msec() + 1000
		store.combat_preview = {"marker":"newer_authority"}
		store._accept_combat_preview(payload)
		check(store.combat_preview == {"marker":"newer_authority"}, "stale_native_preview_rejected", row)
		count += 1
		cases[row.case_id] = int(cases.get(row.case_id, 0)) + 1
	file.close()
	store.free()
	gateway.free()
	var result := {"ok":failures.is_empty() and count == 13824,"native_rows":count,"case_rows":cases,"failures":failures,"scope":"Actual C# router wire and legal room fixtures versus Godot preview; controlled boundaries, no LIVE or render claim."}
	FileAccess.open(OS.get_environment("PR13_TUNING_VECTOR_RESULT"),FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify({"ok":result.ok,"native_rows":count,"first_failures":failures.slice(0,15)}))
	quit(0 if result.ok else 1)
