extends "res://tests/pr13_pool_continuity_natural_render.gd"

# Controlled RENDER injections only. The original native frames remain separate.
const HIDDEN_EXTENSION_FIELD := 60000

func varint_bytes(value: int) -> PackedByteArray:
	var result := PackedByteArray()
	while value >= 128:
		result.append((value & 127) | 128)
		value >>= 7
	result.append(value)
	return result

func read_control_varint(raw: PackedByteArray, cursor: int) -> Array:
	var value := 0
	for shift in range(0,70,7):
		assert(cursor < raw.size())
		var byte: int = raw[cursor]
		cursor += 1
		value |= (byte & 127) << shift
		if (byte & 128) == 0: return [value,cursor]
	assert(false, "Invalid native envelope varint")
	return []

func hidden_extension(original: PackedByteArray, ids: Array) -> PackedByteArray:
	var injected: PackedByteArray = JSON.stringify({"hidden_library_order":ids}).to_utf8_buffer()
	var cursor := 0
	while cursor < original.size():
		var tag := read_control_varint(original,cursor)
		cursor = int(tag[1])
		var number: int = int(tag[0]) >> 3
		var wire_type: int = int(tag[0]) & 7
		if wire_type == 2:
			var length_position := cursor
			var length := read_control_varint(original,cursor)
			cursor = int(length[1])
			var end := cursor + int(length[0])
			assert(end <= original.size())
			if number == 4:
				var payload := original.slice(cursor,end)
				payload.append_array(varint_bytes((HIDDEN_EXTENSION_FIELD << 3) | 2))
				payload.append_array(varint_bytes(injected.size()))
				payload.append_array(injected)
				var result := original.slice(0,length_position)
				result.append_array(varint_bytes(payload.size()))
				result.append_array(payload)
				result.append_array(original.slice(end))
				assert(result != original)
				return result
			cursor = end
		elif wire_type == 0: cursor = int(read_control_varint(original,cursor)[1])
		elif wire_type == 1: cursor += 8
		elif wire_type == 5: cursor += 4
		else: assert(false, "Unsupported native envelope field")
	assert(false, "Original native envelope payload missing")
	return PackedByteArray()

func prepare_native_context(row: Dictionary) -> void:
	var gateway: NaturalGateway = Game.gateway
	for dialog in $UI.find_children("*", "AcceptDialog", true, false): dialog.queue_free()
	await get_tree().process_frame
	Game.room = {}
	Game.selected_cards = []
	Game.hero_class = str(row.hero)
	gateway.clear_replay()
	gateway.room_id = str(row.room_id)
	gateway.current_match_id = ""
	gateway.room_context_epoch = -1
	gateway.authenticated_user_id = str(row.owner_id)
	gateway.online = true
	gateway.recovering = false
	gateway.sent.clear()
	$UI.screen = "exploration"

func apply_frame(wire: PackedByteArray, delay: int) -> bool:
	var gateway: NaturalGateway = Game.gateway
	var codec := Proto.new()
	var envelope: Dictionary = codec.decode("ServerEnvelope", wire)
	assert(codec.error.is_empty())
	gateway.send("room.snapshot.read", {}, str(envelope.request_id))
	var unchanged_while_waiting: bool = Game.room.is_empty()
	if delay > 0:
		await get_tree().create_timer(float(delay) / 1000.0).timeout
		unchanged_while_waiting = unchanged_while_waiting and Game.room.is_empty()
	gateway._receive(wire)
	await present()
	return unchanged_while_waiting

func pool_entry() -> Button:
	for button in $UI._reference.find_children("*", "Button", true, false):
		if button.text.begins_with(PoolView.text("title") + " ("): return button
	return null

func popup_labels() -> Array:
	var labels: Array = []
	var dialog := dialog_under($UI)
	if dialog != null:
		for label in dialog.find_children("*", "Label", true, false):
			if label.is_visible_in_tree() and not label.text.is_empty():
				labels.append({"text":label.text,"inside":dialog.get_visible_rect().encloses(label.get_global_rect()),"all_lines_visible":label.get_visible_line_count()==label.get_line_count()})
	return labels

func public_state() -> Dictionary:
	return {"room_id":Game.room.get("room_id", ""),"room_revision":Game.room.get("room_revision", -1),
		"allowed_actions":Game.room.get("allowed_actions", []).duplicate(true),
		"player":Game.room.get("player", {}).duplicate(true)}

func save_control_capture(row: Dictionary, variant: String, locale: String, size: Vector2i, fps: int, delay: int) -> String:
	if int(row.seed) != 450001 or fps != 30 or delay != 0: return ""
	# Allow deferred product refreshes to complete before reading the texture.
	for frame in range(4):
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
	var name := "%s_%s_%s_%s_%d.png" % [row.case_id,row.hero,variant,locale,size.x]
	if bool(row.optional):
		var popup := dialog_under($UI)
		assert(popup != null and popup.visible)
		assert(popup.get_texture().get_image().save_png(output + "/" + name) == OK)
	else:
		assert(get_viewport().get_texture().get_image().save_png(output + "/" + name) == OK)
	return name

func controlled_witness(row: Dictionary, index: int, locale: String, size: Vector2i, fps: int, delay: int) -> Dictionary:
	var original := Marshalls.base64_to_raw(str(row.original_response_wire))
	var snapshot := native_snapshot(original)
	await prepare_native_context(row)
	var original_wait_clean: bool = await apply_frame(original, delay)
	var original_applied: bool = Game.room.get("room_id", "") == row.room_id and Game.room.get("player", {}) == snapshot.player
	var baseline_public := public_state()
	var original_entry := pool_entry()
	var original_labels: Array = []
	var original_open := false
	if bool(row.optional):
		original_open = await pointer(original_entry)
		await RenderingServer.frame_post_draw
		original_labels = popup_labels()
	var captures: Array = []
	var first: String = await save_control_capture(row, "original", locale, size, fps, delay)
	if not first.is_empty(): captures.append(first)
	var unsupported := "room.library.read"
	var gateway: NaturalGateway = Game.gateway
	gateway.sent.clear()
	var denied_by_action_gate: bool = not Game.allowed(unsupported) and not Game.command(unsupported, {"fields":["hand","library-order"]})
	var denied_by_schema_gate: bool = not gateway.send(unsupported, {"fields":["library-order"]})
	var no_unsupported_packet: bool = gateway.sent.is_empty() and Game._pending_commands.is_empty()
	var injected_applied := true
	var no_hidden_field_or_ids := true
	var visible_state_and_labels_equal := true
	var injected_original_source_eligible := false
	var injected_wire := PackedByteArray()
	if bool(row.optional):
		injected_wire = hidden_extension(original, row.actual_hidden_library_instance_ids)
		await prepare_native_context(row)
		var injected_wait_clean: bool = await apply_frame(injected_wire, delay)
		injected_applied = injected_wait_clean and Game.room.get("room_id", "") == row.room_id
		var injected_public := public_state()
		var text: String = JSON.stringify(injected_public)
		no_hidden_field_or_ids = not text.contains("hidden_library_order") and not text.contains("library-order")
		for id in row.actual_hidden_library_instance_ids: no_hidden_field_or_ids = no_hidden_field_or_ids and not text.contains(str(id))
		var entered: bool = await pointer(pool_entry())
		await RenderingServer.frame_post_draw
		var injected_labels := popup_labels()
		visible_state_and_labels_equal = entered and injected_public == baseline_public and injected_labels == original_labels
		# Native-source eligibility is byte equality, independent of decoder tolerance.
		injected_original_source_eligible = injected_wire == original
		var picture: String = await save_control_capture(row, "hidden_extension", locale, size, fps, delay)
		if not picture.is_empty(): captures.append(picture)
	var off_policy_unchanged: bool = bool(row.optional) or (original_entry == null and not Game.allowed("monster.choose") and not Game.room.get("player", {}).has("monster_pool"))
	var text_geometry_ok: bool = not bool(row.optional) or (not original_labels.is_empty() and original_labels.all(func(label):return label.inside and label.all_lines_visible))
	var passed: bool = original_wait_clean and original_applied and denied_by_action_gate and denied_by_schema_gate and no_unsupported_packet and injected_applied and no_hidden_field_or_ids and visible_state_and_labels_equal and not injected_original_source_eligible and off_policy_unchanged and text_geometry_ok
	return {"case_id":row.case_id,"index":index,"hero":row.hero,"seed":row.seed,"locale":locale,"resolution":[size.x,size.y],"frame_cap":fps,"controlled_delay_ms":delay,
		"original_native_source_sha":row.source_sha,"original_response_wire":row.original_response_wire,"injected_response_wire":Marshalls.raw_to_base64(injected_wire) if not injected_wire.is_empty() else "",
		"original_snapshot_applied_without_projection":original_applied,"no_state_change_while_controlled_snapshot_waiting":original_wait_clean,
		"unsupported_hidden_order_action_denied":denied_by_action_gate,"unsupported_hidden_order_schema_denied":denied_by_schema_gate,"no_hidden_order_packet_or_pending_command":no_unsupported_packet,
		"unknown_extension_field":HIDDEN_EXTENSION_FIELD if bool(row.optional) else 0,"actual_hidden_library_fields_and_ids_absent_from_public_state":no_hidden_field_or_ids,
		"public_state_and_popup_labels_unchanged_by_extension":visible_state_and_labels_equal,"injected_frame_eligible_as_original_native_experiment":injected_original_source_eligible,
		"default_optional_pool_entry_and_choice_absent":off_policy_unchanged,"full_formal_default_rule_changed":false,"original_popup_opened":original_open,
		"visible_labels":original_labels,"captures":captures,"capture_scope":"popup" if bool(row.optional) else "root_viewport","controlled_injection_only":true,"natural_experiment_samples_added":0,"human_experience_claimed":false,"passed":passed}

func _run() -> void:
	output = OS.get_environment("PR13_INFORMATION_RENDER_OUTPUT")
	assert(not output.is_empty())
	DirAccess.make_dir_recursive_absolute(output)
	var corpus: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("PR13_INFORMATION_RENDER_INPUT")))
	assert(corpus.kind == "declared_native_snapshot_RENDER_controls" and corpus.rows.size() == 18)
	var rows: Array = corpus.rows
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := NaturalGateway.new()
	gateway.persist_session = false
	gateway.set_process(false)
	gateway.event_received.connect(Game._on_event)
	Game.gateway = gateway
	var original_locale := P.language()
	var locale := OS.get_environment("PR13_INFORMATION_RENDER_LOCALE")
	assert(locale in ["zh-CN","en"])
	P.set_language(locale)
	get_window().mode = Window.MODE_WINDOWED
	var probe: bool = OS.get_environment("PR13_INFORMATION_RENDER_MODE") == "development-smoke"
	var sizes: Array = [Vector2i(960,540)] if probe else [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]
	var caps: Array = [30] if probe else [30,60,144]
	var delays: Array = [0] if probe else [0,250,1000]
	for size in sizes:
		get_window().size = size
		for fps in caps:
			Engine.max_fps = fps
			for delay in delays:
				for index in range(rows.size()):
					var record: Dictionary = await controlled_witness(rows[index],index,locale,size,fps,delay)
					observations.append(record)
					FileAccess.open(output+"/checkpoint.json",FileAccess.WRITE).store_string(JSON.stringify({"rows":observations.size(),"last":record}))
	P.set_language(original_locale)
	Game.gateway = old_gateway
	gateway.event_received.disconnect(Game._on_event)
	gateway.free()
	var result := {"ok":observations.size()==rows.size()*sizes.size()*caps.size()*delays.size() and observations.all(func(row):return row.passed) and DisplayServer.get_name()!="headless", "observations":observations,"development_smoke":probe,"locale":locale,"source_sha":OS.get_environment("PR13_INFORMATION_RENDER_SOURCE"),"native_source_sha":corpus.native_source_sha,"no_new_natural_experiment_samples":true,"default_rule_changed":false,"MAIN_accepted":false}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit(0 if result.ok else 1)
