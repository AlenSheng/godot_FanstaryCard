extends "res://tests/pr13_pool_continuity_natural_render.gd"

var boundary_failures: Array = []

func decode_snapshot(encoded: String) -> Dictionary:
	return native_snapshot(Marshalls.base64_to_raw(encoded))

func seed_authority(row: Dictionary, encoded: String) -> Dictionary:
	var gateway: NaturalGateway = Game.gateway
	# Retire only the previous independent fixture's transient notice. Responses
	# delivered after this reset retain the product's normal rejection feedback.
	if is_instance_valid($UI.tips_overlay): $UI.tips_overlay.clear()
	Game.room = {}
	Game.selected_cards = []
	Game._pending_commands = {}
	Game._latest_commands = {}
	Game._pending_play = {}
	Game._queued_command = {}
	gateway.clear_replay()
	gateway.room_id = str(row.roomId)
	gateway.current_match_id = str(row.matchId)
	gateway.room_context_epoch = -1
	gateway.authenticated_user_id = str(row.ownerId)
	gateway.online = true
	gateway.recovering = false
	var codec := Proto.new()
	var wire := Marshalls.base64_to_raw(encoded)
	var envelope: Dictionary = codec.decode("ServerEnvelope", wire)
	assert(codec.error.is_empty())
	gateway.send("room.snapshot.read", {}, str(envelope.request_id))
	gateway._receive(wire)
	gateway.sent.clear()
	var snapshot := decode_snapshot(encoded)
	Game.hero_class = str(snapshot.player.hero_class)
	$UI.screen = "exploration"
	return snapshot

func boundary_witness(row: Dictionary, index: int, locale: String, size: Vector2i, fps: int = 30, delay: int = 0) -> Dictionary:
	for previous in $UI.find_children("*", "AcceptDialog", true, false): previous.queue_free()
	await get_tree().process_frame
	var gateway: NaturalGateway = Game.gateway
	var before := seed_authority(row, str(row.beforeWire))
	var capture_pixels := fps == 30 and delay == 0
	await present()
	if capture_pixels: await get_tree().create_timer(2.1).timeout
	await RenderingServer.frame_post_draw
	var before_applied: bool = Game.room.get("player", {}) == before.player
	var image_names: Array = []
	var labels: Array = []
	var opened := false
	var submitted := false
	var command_exact := false
	var result_ok := false
	var authority_checks := {}
	if row.operation == "pvp-state":
		var original_pool: Dictionary = before.player.get("monster_pool", {}).duplicate(true)
		var first_name := "%s_%d_pvp_%s_%d.png" % [row.hero, row.capacity, locale, index]
		var first_image_ok := true
		if capture_pixels:
			first_image_ok = get_viewport().get_texture().get_image().save_png(output + "/" + first_name) == OK
			image_names.append(first_name)
		# The native checkpoint rebuild starts a new event stream. Read its actual
		# public return snapshot through a fresh reader, with the same room/match.
		if delay > 0: await get_tree().create_timer(delay / 1000.0).timeout
		var after := seed_authority(row, str(row.afterSnapshotWire))
		await present()
		if capture_pixels: await get_tree().create_timer(2.1).timeout
		await RenderingServer.frame_post_draw
		var last_name := "%s_%d_return_%s_%d.png" % [row.hero, row.capacity, locale, index]
		var last_image_ok := true
		if capture_pixels:
			last_image_ok = get_viewport().get_texture().get_image().save_png(output + "/" + last_name) == OK
			image_names.append(last_name)
		result_ok = first_image_ok and last_image_ok and before.player.phase == "Pvp" and not before.get("duel", {}).is_empty()
		result_ok = result_ok and after.player.phase != "Pvp" and after.get("duel", {}).is_empty()
		result_ok = result_ok and Game.room.get("player", {}).get("monster_pool", {}) == original_pool
		authority_checks = {"return_original_player_applied":Game.room.get("player", {}) == after.player,"return_original_revision_exact":Game.room.get("room_revision", -1) == after.room_revision}
		result_ok = result_ok and authority_checks.values().all(func(value): return value)
	else:
		var entry: Button
		for candidate in $UI._reference.find_children("*", "Button", true, false):
			if candidate.text.begins_with(PoolView.text("title") + " ("): entry = candidate
		var entered := await pointer(entry)
		await get_tree().process_frame
		await RenderingServer.frame_post_draw
		var dialog := dialog_under($UI)
		opened = entered and dialog != null
		if dialog != null:
			for label in dialog.find_children("*", "Label", true, false):
				if label.is_visible_in_tree() and not label.text.is_empty():
					labels.append({"text":label.text,"inside":dialog.get_visible_rect().encloses(label.get_global_rect()),"all_lines_visible":label.get_visible_line_count()==label.get_line_count()})
			var picture := "%s_%d_%s_%s_%d.png" % [row.hero,row.capacity,row.operation,locale,index]
			result_ok = true
			if capture_pixels:
				result_ok = dialog.get_texture().get_image().save_png(output + "/" + picture) == OK
				image_names.append(picture)
		var codec := Proto.new()
		var request: Dictionary = codec.decode("ClientEnvelope",Marshalls.base64_to_raw(str(row.commandWire)))
		assert(codec.error.is_empty())
		gateway.fixture_request_id = str(request.request_id)
		if row.operation == "choice-replay":
			submitted = await pointer(button_text(dialog, PoolView.text("accept")))
			var sent: Array = gateway.sent.filter(func(record): return record.kind == "monster.choose")
			if sent.size() == 1:
				var actual: Dictionary = codec.decode("ClientEnvelope",sent[0].wire)
				command_exact = codec.error.is_empty() and actual == request
		else:
			# No product control exposes another player's candidate. The negative
			# typed request is recorded by the transport without a product click.
			var payload: Dictionary = codec.decode("MonsterCardChooseCommand",request.payload)
			var own: Array = before.player.monster_pool.pending
			command_exact = not own.any(func(card): return str(card.instance_id) == str(payload.candidate_id))
			# The decoder supplies default scalar fields. Rebuild the same sparse
			# product command as the original native request instead of encoding
			# absent/default replacement text as an additional empty wire field.
			var transport_payload := {"candidate_id":str(payload.candidate_id),"accept":bool(payload.accept)}
			if not str(payload.get("replace_instance_id", "")).is_empty(): transport_payload.replace_instance_id = str(payload.replace_instance_id)
			var sent_foreign := gateway.send("monster.choose",transport_payload,str(request.request_id))
			var actual_foreign: Dictionary = codec.decode("ClientEnvelope",gateway.sent[-1].wire) if sent_foreign else {}
			command_exact = command_exact and codec.error.is_empty() and actual_foreign == request
		var unchanged_before: bool = Game.room.get("player", {}).get("monster_pool", {}) == before.player.monster_pool
		var pending_registered: bool = Game._pending_commands.has(str(request.request_id))
		if delay > 0: await get_tree().create_timer(delay / 1000.0).timeout
		var unchanged_after_delay: bool = Game.room.get("player", {}) == before.player
		var expected_after := {}
		for encoded in row.responseWires:
			var response_wire := Marshalls.base64_to_raw(str(encoded))
			var response: Dictionary = codec.decode("ServerEnvelope",response_wire)
			assert(codec.error.is_empty())
			if response.type == "room.snapshot": expected_after = native_snapshot(response_wire)
			gateway._receive(response_wire)
		await present()
		if row.operation == "choice-replay":
			var first_state: Dictionary = Game.room.duplicate(true)
			var first_applied: bool = not expected_after.is_empty() and Game.room.get("player", {}) == expected_after.player
			var first_revision: bool = not expected_after.is_empty() and Game.room.get("room_revision", -1) == expected_after.room_revision
			var pending_cleared: bool = not Game._pending_commands.has(str(request.request_id))
			if delay > 0: await get_tree().create_timer(delay / 1000.0).timeout
			for encoded in row.replayWires: gateway._receive(Marshalls.base64_to_raw(str(encoded)))
			await present()
			authority_checks = {"pending_registered":pending_registered,"no_player_mutation_during_controlled_delay":unchanged_after_delay,"first_original_player_applied":first_applied,"first_original_revision_exact":first_revision,"pending_cleared":pending_cleared,"replay_kept_full_state":first_state == Game.room,"replay_original_player_applied":not expected_after.is_empty() and Game.room.get("player", {}) == expected_after.player}
			result_ok = result_ok and submitted and authority_checks.values().all(func(value): return value)
		else:
			authority_checks = {"negative_original_transport_request_exact":command_exact,"negative_transport_request_correlated":gateway._response_contexts.has(str(request.request_id)),"no_player_mutation_during_controlled_delay":unchanged_after_delay,"rejection_preserved_full_player":Game.room.get("player", {}) == before.player}
			result_ok = result_ok and authority_checks.values().all(func(value): return value)
		result_ok = result_ok and opened and command_exact and unchanged_before and not labels.is_empty()
		result_ok = result_ok and labels.all(func(label): return label.inside and label.all_lines_visible)
	var passed: bool = before_applied and result_ok
	return {"hero":row.hero,"capacity":row.capacity,"seed":row.seed,"operation":row.operation,"locale":locale,"resolution":[size.x,size.y],"actual_window_size":[get_window().size.x,get_window().size.y],"frame_cap":Engine.max_fps,"requested_frame_cap":fps,"controlled_response_delay_ms":delay,"native_source_sha":row.source,"original_before_snapshot_applied":before_applied,"authority_checks":authority_checks,"dialog_opened":opened,"choice_input_submitted":submitted,"original_command_exact":command_exact,"labels":labels,"screenshots":image_names,"checkpoint_reader_reset_explicit":row.operation=="pvp-state","PVP_leave_button_clicked":false,"foreign_candidate_UI_click_claimed":false,"passed":passed}

func _run() -> void:
	output = OS.get_environment("PR13_DUAL_RENDER_OUTPUT")
	assert(not output.is_empty())
	DirAccess.make_dir_recursive_absolute(output)
	var rows: Array = []
	var file := FileAccess.open(OS.get_environment("PR13_DUAL_RENDER_VECTORS"),FileAccess.READ)
	assert(file != null)
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var row: Dictionary = JSON.parse_string(line)
		assert(str(row.source)=="2a1d7e649f61aa1dc04bf50899f7cc32bb553d26")
		if int(row.seed)==484001 and int(row.capacity)>0: rows.append(row)
	file.close()
	assert(rows.size()==9)
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := NaturalGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	gateway.event_received.connect(Game._on_event)
	var language := OS.get_environment("PR13_DUAL_RENDER_LANGUAGE")
	P.set_language(language)
	get_window().mode = Window.MODE_WINDOWED
	var full_matrix := OS.get_environment("PR13_DUAL_RENDER_MODE") == "full"
	var sizes: Array = [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)] if full_matrix else [Vector2i(960,540)]
	var frames: Array = [30,60,144] if full_matrix else [30]
	var delays: Array = [0,250,1000] if full_matrix else [0]
	for size in sizes:
		get_window().size = size
		await get_tree().process_frame
		await get_tree().process_frame
		for fps in frames:
			Engine.max_fps = fps
			for delay in delays:
				for row in rows:
					var record: Dictionary = await boundary_witness(row,observations.size(),language,size,fps,delay)
					observations.append(record)
					FileAccess.open(output+"/checkpoint.json",FileAccess.WRITE).store_string(JSON.stringify({"rows":observations.size(),"last":record}))
	Game.gateway = old_gateway
	gateway.event_received.disconnect(Game._on_event)
	gateway.free()
	var result := {"ok":observations.size()==(243 if full_matrix else 9) and observations.all(func(row): return row.passed) and DisplayServer.get_name()!="headless","observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"language":language,"development_smoke":not full_matrix,"full_matrix_claimed":false,"declared_full_segment_executed":full_matrix,"source_sha":OS.get_environment("PR13_DUAL_RENDER_SOURCE"),"original_vector_source_sha":"2a1d7e649f61aa1dc04bf50899f7cc32bb553d26","human_experience_claimed":false,"MAIN_accepted":false}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit(0 if result.ok else 1)
