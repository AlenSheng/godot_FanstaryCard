extends "res://tests/pr13_pool_capacity_render.gd"

# All inputs are original typed frames from the frozen natural route matrix.
# The fixture transport encodes complete envelopes and records them without WSS.
class NaturalGateway extends "res://network/gateway.gd":
	var sent: Array = []
	var fixture_request_id := ""
	func new_id() -> String:
		return fixture_request_id
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		if not COMMANDS.has(kind): return false
		var codec := Proto.new()
		var effective_id := request_id if not request_id.is_empty() else fixture_request_id
		var origin := capture_context()
		var envelope := {"protocol_version":1,"type":kind,"request_id":effective_id}
		if not str(origin.room_id).is_empty() and not str(origin.match_id).is_empty():
			envelope.room_id = origin.room_id
			envelope.match_id = origin.match_id
		if not COMMANDS[kind].is_empty():
			envelope.payload = codec.encode(COMMANDS[kind],payload)
		if kind not in ["ping","session.resume","room.snapshot.read","room.ready","relic.read"]:
			envelope.expected_revision = room_revision
		var wire: PackedByteArray = codec.encode("ClientEnvelope",envelope)
		if not codec.error.is_empty(): return false
		sent.append({"kind":kind,"payload":payload.duplicate(true),"wire":wire,"request_id":effective_id})
		_pending_request_started[effective_id] = {"action":kind,"started_at":Time.get_ticks_msec(),"context":origin.duplicate(true)}
		return true

var natural_failures: Array = []

func choose_native_active(popup: PopupMenu, item_index: int) -> bool:
	if not is_instance_valid(popup) or not popup.visible or item_index<=0 or item_index>=popup.item_count: return false
	var panel: StyleBox = popup.get_theme_stylebox("panel")
	var top: float = panel.get_content_margin(SIDE_TOP)
	var bottom: float = panel.get_content_margin(SIDE_BOTTOM)
	var height: float = (popup.size.y-top-bottom)/float(popup.item_count)
	var local_point := Vector2(popup.size.x*.5,top+height*(float(item_index)+.5))
	var screen_point: Vector2 = popup.get_screen_transform()*local_point
	var point: Vector2 = screen_point if popup.is_embedded() else screen_point-Vector2(popup.position)
	var window_id: int = popup.get_window_id() if popup.get_window_id()>=0 else get_window().get_window_id()
	var motion := InputEventMouseMotion.new()
	motion.window_id=window_id
	motion.position=point
	motion.global_position=point
	Input.parse_input_event(motion)
	await get_tree().process_frame
	for pressed in [true,false]:
		var event := InputEventMouseButton.new()
		event.window_id=window_id
		event.button_index=MOUSE_BUTTON_LEFT
		event.button_mask=MOUSE_BUTTON_MASK_LEFT if pressed else 0
		event.pressed=pressed
		event.position=point
		event.global_position=point
		Input.parse_input_event(event)
		await get_tree().process_frame
	return true

func native_snapshot(wire: PackedByteArray) -> Dictionary:
	var codec := Proto.new()
	var envelope: Dictionary = codec.decode("ServerEnvelope",wire)
	assert(codec.error.is_empty() and envelope.get("type","")=="room.snapshot")
	var snapshot: Dictionary = codec.decode("RoomSnapshotEvent",envelope.payload)
	assert(codec.error.is_empty())
	return snapshot

func native_rows(path: String) -> Array:
	var rows: Array = []
	var file := FileAccess.open(path,FileAccess.READ)
	assert(file!=null)
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var row = JSON.parse_string(line)
		assert(row is Dictionary and str(row.source)=="0d56ceccf526f6ae8973f57da152d67faf93a5d5")
		rows.append(row)
	file.close()
	return rows

func natural_witness(row: Dictionary, index: int, locale: String, size: Vector2i, fps: int, delay: int) -> Dictionary:
	var gateway: NaturalGateway = Game.gateway
	# Each vector is an independent scoped authority read of its original room.
	# These are live original choice snapshots, so do not mark their room as
	# terminal between successive vectors belonging to the same authority room.
	for previous_dialog in $UI.find_children("*","AcceptDialog",true,false):
		previous_dialog.queue_free()
	await get_tree().process_frame
	Game.room = {}
	Game.selected_cards = []
	Game.hero_class = str(row.hero)
	Game.set_process(false)
	gateway.clear_replay()
	gateway.room_id = str(row.roomId)
	gateway.current_match_id = str(row.matchId)
	gateway.room_context_epoch = -1
	gateway.authenticated_user_id = str(row.ownerId)
	gateway.online = true
	gateway.recovering = false
	gateway.sent.clear()
	var before_wire := Marshalls.base64_to_raw(str(row.beforeWire))
	var command_wire := Marshalls.base64_to_raw(str(row.commandWire))
	var codec := Proto.new()
	var before_envelope: Dictionary = codec.decode("ServerEnvelope",before_wire)
	assert(codec.error.is_empty())
	gateway.send("room.snapshot.read",{},str(before_envelope.request_id))
	gateway._receive(before_wire)
	var before := native_snapshot(before_wire)
	var before_applied: bool = Game.room.get("room_id","")==row.roomId and Game.room.get("player",{}).get("monster_pool",{})==before.player.monster_pool
	var choice_allowed_before_input: bool = Game.allowed("monster.choose")
	var room_terminal_before_input: bool = Game._room_actions_closed()
	var request: Dictionary = codec.decode("ClientEnvelope",command_wire)
	var payload: Dictionary = codec.decode("MonsterCardChooseCommand",request.payload)
	assert(codec.error.is_empty() and request.type=="monster.choose")
	var expected_accept: bool = payload.get("accept",false)
	var expected_replace: String = str(payload.get("replace_instance_id",""))
	assert(str(payload.candidate_id)==str(row.candidateId) and expected_accept==bool(row.accept))
	gateway.fixture_request_id = str(request.request_id)
	gateway.sent.clear()
	$UI.screen = "exploration"
	await present()
	var entry: Button
	for candidate in $UI._reference.find_children("*","Button",true,false):
		if candidate.text.begins_with(PoolView.text("title")+" ("): entry=candidate
	var began := Time.get_ticks_usec()
	var entered: bool = await pointer(entry)
	await RenderingServer.frame_post_draw
	var dialog := dialog_under($UI)
	var opened: bool = dialog!=null
	var labels: Array = []
	var image_name := ""
	var image_ok := true
	var submitted := false
	if dialog!=null:
		for label in dialog.find_children("*","Label",true,false):
			if label.is_visible_in_tree() and not label.text.is_empty():
				labels.append({"text":label.text,"inside":dialog.get_visible_rect().encloses(label.get_global_rect()),"all_lines_visible":label.get_visible_line_count()==label.get_line_count()})
		if fps==30 and delay==0:
			image_name = "%s_%d_%s_%d_%d.png" % [row.hero,row.seed,locale,size.x,index]
			image_ok = dialog.get_texture().get_image().save_png(output+"/"+image_name)==OK
		if expected_accept:
			if not expected_replace.is_empty():
				var active: Array = before.player.monster_pool.active
				var wanted_index := -1
				for active_index in range(active.size()):
					if str(active[active_index].instance_id)==expected_replace: wanted_index=active_index+1
				var options: Array = dialog.find_children("*","OptionButton",true,false)
				if wanted_index>0 and options.size()==1:
					var option_ref: WeakRef = weakref(options[0])
					var take_ref: WeakRef = weakref(button_text(dialog,PoolView.text("accept")))
					await pointer(options[0])
					var selected := await choose_native_active(options[0].get_popup(),wanted_index)
					var live_option: OptionButton = option_ref.get_ref() as OptionButton
					var live_take: Button = take_ref.get_ref() as Button
					if selected and live_option!=null and live_option.selected==wanted_index and live_take!=null and not live_take.disabled:
						submitted=await pointer(live_take)
				else: natural_failures.append({"index":index,"reason":"Original replacement is not present in the authoritative visible pool"})
			else: submitted = await pointer(button_text(dialog,PoolView.text("accept")))
		else: submitted = await pointer(button_text(dialog,PoolView.text("skip")))
	var choice_input_usec := Time.get_ticks_usec()-began
	var sent: Array = gateway.sent.filter(func(record):return record.kind=="monster.choose")
	var actual_request := {}
	var command_exact := false
	if sent.size()==1:
		actual_request = codec.decode("ClientEnvelope",sent[0].wire)
		var actual_payload: Dictionary = codec.decode("MonsterCardChooseCommand",actual_request.payload)
		command_exact = codec.error.is_empty() and actual_payload==payload
		for field in ["protocol_version","type","request_id","expected_revision","room_id","match_id"]:
			command_exact = command_exact and actual_request.get(field)==request.get(field)
	var pending_registered: bool = Game._pending_commands.has(str(request.request_id))
	var unchanged_before_response: bool = Game.room.get("player",{}).get("monster_pool",{})==before.player.monster_pool
	if delay>0: await get_tree().create_timer(float(delay)/1000.0).timeout
	var frames := 0
	var expected_after := {}
	for encoded in row.afterWires:
		var raw := Marshalls.base64_to_raw(str(encoded))
		var envelope: Dictionary = codec.decode("ServerEnvelope",raw)
		assert(codec.error.is_empty())
		if envelope.type=="room.snapshot": expected_after=native_snapshot(raw)
		gateway._receive(raw)
		frames+=1
	await present()
	var after_applied: bool = not expected_after.is_empty() and Game.room.get("player",{}).get("monster_pool",{})==expected_after.player.monster_pool
	var after_revision: bool = not expected_after.is_empty() and Game.room.get("room_revision",-1)==expected_after.room_revision
	var closed: bool = dialog_under($UI)==null
	var pending_cleared: bool = not Game._pending_commands.has(str(request.request_id))
	var text_ok: bool = not labels.is_empty() and labels.all(func(label):return label.inside and label.all_lines_visible)
	var passed: bool = before_applied and entered and opened and submitted and command_exact and pending_registered and unchanged_before_response and after_applied and after_revision and closed and pending_cleared and text_ok and image_ok
	return {"index":index,"hero":row.hero,"seed":row.seed,"capacity":row.capacity,"candidate_id":row.candidateId,"source_sha":row.source,"reader_source_sha":OS.get_environment("PR13_CONTINUITY_RENDER_SOURCE"),"locale":locale,"resolution":[size.x,size.y],"frame_cap":fps,"controlled_delay_ms":delay,"before_native_snapshot_received":before_applied,"choice_allowed_before_input":choice_allowed_before_input,"room_terminal_before_input":room_terminal_before_input,"entry_clicked":entered,"dialog_opened":opened,"choice_submitted":submitted,"original_command_headers_and_payload_exact":command_exact,"actual_full_command_wire":Marshalls.raw_to_base64(sent[0].wire) if sent.size()==1 else "","product_pending_command_registered":pending_registered,"no_state_change_before_authority":unchanged_before_response,"original_after_native_snapshot_received":after_applied,"after_revision_exact":after_revision,"product_pending_command_cleared":pending_cleared,"actual_original_response_frames":frames,"popup_closed":closed,"visible_labels":labels,"choice_input_usec_includes_render_and_synthetic_pointer_frames":choice_input_usec,"human_decision_time_claimed":false,"screenshot":image_name,"passed":passed}

func _run() -> void:
	output = OS.get_environment("PR13_CONTINUITY_RENDER_OUTPUT")
	assert(not output.is_empty())
	DirAccess.make_dir_recursive_absolute(output)
	var rows := native_rows(OS.get_environment("PR13_CONTINUITY_RENDER_VECTORS"))
	assert(not rows.is_empty())
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
	var original_locale: String = P.language()
	var locale := OS.get_environment("PR13_CONTINUITY_RENDER_LOCALE")
	assert(locale in ["zh-CN","en"])
	var development_smoke: bool = OS.get_environment("PR13_CONTINUITY_RENDER_MODE")=="development-smoke"
	P.set_language(locale)
	get_window().mode = Window.MODE_WINDOWED
	var sizes: Array = [Vector2i(960,540)] if development_smoke else [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]
	var frame_caps: Array = [30] if development_smoke else [30,60,144]
	var delays: Array = [0] if development_smoke else [0,250,1000]
	for size in sizes:
		get_window().size = size
		for fps in frame_caps:
			Engine.max_fps = fps
			for delay in delays:
				for index in range(rows.size()):
					var record: Dictionary = await natural_witness(rows[index],index,locale,size,fps,delay)
					observations.append(record)
					FileAccess.open(output+"/checkpoint.json",FileAccess.WRITE).store_string(JSON.stringify({"rows":observations.size(),"last":record}))
	P.set_language(original_locale)
	Game.gateway = old_gateway
	gateway.event_received.disconnect(Game._on_event)
	gateway.free()
	var expected_count: int = rows.size()*sizes.size()*frame_caps.size()*delays.size()
	var result := {"ok":natural_failures.is_empty() and observations.size()==expected_count and observations.all(func(row):return row.passed) and DisplayServer.get_name()!="headless","observations":observations,"original_vectors":rows.size(),"matrix_observations_expected":expected_count,"development_smoke":development_smoke,"full_render_matrix_claimed":false,"locale":locale,"failures":natural_failures,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"reader_source_sha":OS.get_environment("PR13_CONTINUITY_RENDER_SOURCE"),"original_native_source_sha":"0d56ceccf526f6ae8973f57da152d67faf93a5d5","controlled_response_delay_not_WAN":true,"whole_task_accepted":false,"human_experience_claimed":false}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit(0 if result.ok else 1)
