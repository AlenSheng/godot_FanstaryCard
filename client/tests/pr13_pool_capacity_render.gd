extends "res://tests/pr13_b10_render_cases.gd"

@export var pool_probe := true
@export var pool_hero := "Guardian"
@export var pool_capacity := 8
@export var pool_case := "PR13-B09.2-T02"
@export var pool_language := ""
const PoolView = preload("res://ui/monster_pool_view.gd")
const ORIGINAL_SOURCE := "1341e160afc67ba826d4b37250c9ec58f8c99462"
var pool_traces: Array = []

class PoolGateway extends CodecGateway:
	var original_request := ""
	func new_id() -> String: return original_request

func pointer(control: Control) -> bool:
	if control==null or not control.is_visible_in_tree(): return false
	var viewport: Viewport = control.get_viewport()
	var point: Vector2 = viewport.get_screen_transform()*control.get_global_transform_with_canvas()*(control.size*.5)
	var window_id: int = control.get_window().get_window_id() if control.get_window().get_window_id()>=0 else get_window().get_window_id()
	pool_traces.append({"control":str(control.get_path()),"screen_point":[point.x,point.y],"route":"Input.parse_input_event targeted mouse motion/down/up","window_id":window_id})
	var motion := InputEventMouseMotion.new()
	motion.window_id=window_id
	motion.position = point
	motion.global_position = point
	Input.parse_input_event(motion)
	await get_tree().process_frame
	for pressed in [true,false]:
		var event := InputEventMouseButton.new()
		event.window_id=window_id
		event.button_index = MOUSE_BUTTON_LEFT
		event.button_mask = MOUSE_BUTTON_MASK_LEFT if pressed else 0
		event.pressed = pressed
		event.position = point
		event.global_position = point
		Input.parse_input_event(event)
		await get_tree().process_frame
	return true

func key_input(code: int, target: Window) -> void:
	for pressed in [true,false]:
		var event := InputEventKey.new()
		event.keycode = code
		event.physical_keycode = code
		event.pressed = pressed
		event.window_id = target.get_window_id() if target.get_window_id()>=0 else get_window().get_window_id()
		Input.parse_input_event(event)
		await get_tree().process_frame
	pool_traces.append({"route":"Input.parse_input_event targeted window key press/release","key":code,"window_id":target.get_window_id(),"embedded":target.is_embedded(),"focused":target.has_focus()})

func choose_first_active(popup: PopupMenu) -> bool:
	if not is_instance_valid(popup) or not popup.visible: return false
	var panel: StyleBox = popup.get_theme_stylebox("panel")
	var top: float = panel.get_content_margin(SIDE_TOP)
	var bottom: float = panel.get_content_margin(SIDE_BOTTOM)
	var height: float = (popup.size.y-top-bottom)/float(popup.item_count)
	var local_point := Vector2(popup.size.x*.5,top+height*1.5)
	var screen_point: Vector2 = popup.get_screen_transform()*local_point
	var window_id: int = popup.get_window_id() if popup.get_window_id()>=0 else get_window().get_window_id()
	var point: Vector2 = screen_point if popup.is_embedded() else screen_point-Vector2(popup.position)
	pool_traces.append({"route":"Actual popup mouse selection","window_id":window_id,"embedded":popup.is_embedded(),"popup_position":[popup.position.x,popup.position.y],"popup_size":[popup.size.x,popup.size.y],"point":[point.x,point.y],"item_count":popup.item_count})
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

func snapshot(row: Dictionary, tag: String) -> Dictionary:
	var codec := Proto.new()
	var envelope: Dictionary = codec.decode("ServerEnvelope", Marshalls.base64_to_raw(row[tag+"_wire"]))
	assert(codec.error.is_empty())
	var result: Dictionary = codec.decode("RoomSnapshotEvent", envelope.payload)
	assert(codec.error.is_empty())
	return result

func dialog_under(node: Node) -> AcceptDialog:
	for child in node.get_children():
		if child is AcceptDialog and child.visible: return child
		var found := dialog_under(child)
		if found!=null: return found
	return null

func button_text(node: Node, words: String) -> Button:
	for button in node.find_children("*","Button",true,false):
		if button.text==words: return button
	return null

func witness(row: Dictionary, language: String, size: Vector2i, fps: int, delay: int, cycle: int, capture: bool) -> Dictionary:
	reset_battle()
	pool_traces.clear()
	var before := snapshot(row,"before")
	var after := snapshot(row,"after")
	Game.room = before.duplicate(true)
	Game.hero_class = pool_hero
	Game.selected_cards = []
	Game.gateway.sent = []
	var codec := Proto.new()
	var request: Dictionary = codec.decode("ClientEnvelope",Marshalls.base64_to_raw(row.request_wire))
	var expected: Dictionary = codec.decode("MonsterCardChooseCommand",request.payload)
	Game.gateway.original_request = str(request.request_id)
	$UI.screen = "exploration"
	await present()
	var entry: Button
	for candidate in $UI._reference.find_children("*","Button",true,false):
		if candidate.text.begins_with(PoolView.text("title")+" ("): entry=candidate
	var entered := await pointer(entry)
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var dialog := dialog_under($UI)
	var dialog_opened: bool = dialog!=null
	var geometry := false
	var window_geometry: Dictionary = {}
	var labels: Array = []
	var picture := ""
	var picture_ok := not capture
	var initially_disabled := false
	var replacement_selected := false
	var submitted := false
	if dialog!=null:
		var embedded: bool = dialog.is_embedded()
		var bounds := get_viewport().get_visible_rect() if embedded else Rect2(Vector2(get_window().position),Vector2(size))
		window_geometry = {"embedded":embedded,"dialog_position":[dialog.position.x,dialog.position.y],"dialog_size":[dialog.size.x,dialog.size.y],"root_position":[get_window().position.x,get_window().position.y],"root_size":[get_window().size.x,get_window().size.y],"viewport_size":[dialog.get_visible_rect().size.x,dialog.get_visible_rect().size.y],"pixel_size":[dialog.get_texture().get_image().get_width(),dialog.get_texture().get_image().get_height()],"window_id":dialog.get_window_id()}
		FileAccess.open(output+"/geometry-before-click.json",FileAccess.WRITE).store_string(JSON.stringify(window_geometry))
		geometry = bounds.encloses(Rect2(Vector2(dialog.position),Vector2(dialog.size)))
		for label in dialog.find_children("*","Label",true,false):
			if label.is_visible_in_tree() and not label.text.is_empty():
				var inside: bool = dialog.get_visible_rect().encloses(label.get_global_rect())
				var readable: bool = label.get_visible_line_count()==label.get_line_count()
				labels.append({"text":label.text,"inside":inside,"all_lines_visible":readable,"font_size":label.get_theme_font_size("font_size")})
		if capture:
			picture = "%s_%s_%d_%d_%d.png" % [pool_case,language,size.x,fps,pool_capacity]
			picture_ok = dialog.get_texture().get_image().save_png(output+"/"+picture)==OK
		var take := button_text(dialog,PoolView.text("accept"))
		var skip := button_text(dialog,PoolView.text("skip"))
		if pool_case.ends_with("T02"):
			initially_disabled = take!=null and take.disabled
			var options: Array = dialog.find_children("*","OptionButton",true,false)
			if not options.is_empty():
				var option_ref: WeakRef = weakref(options[0])
				var take_ref: WeakRef = weakref(take)
				await pointer(options[0])
				var popup: PopupMenu = options[0].get_popup()
				await choose_first_active(popup)
				var live_option: OptionButton = option_ref.get_ref() as OptionButton
				var live_take: Button = take_ref.get_ref() as Button
				replacement_selected = live_option!=null and live_option.selected==1 and live_take!=null and not live_take.disabled
				submitted = await pointer(live_take)
		elif pool_case.ends_with("T03"):
			submitted = await pointer(skip)
		else:
			submitted = take!=null and not take.disabled and await pointer(take)
	await get_tree().process_frame
	var sent: Array = Game.gateway.sent
	var exact: bool = sent.size()==1 and sent[0].kind=="monster.choose" and sent[0].codec_error.is_empty()
	if exact:
		var decoded: Dictionary = codec.decode("MonsterCardChooseCommand",sent[0].wire)
		exact = codec.error.is_empty() and decoded==expected
	var unchanged_until_response: bool = JSON.stringify(Game.room)==JSON.stringify(before)
	if delay>0: await get_tree().create_timer(float(delay)/1000.0).timeout
	# The exact original snapshot is the controlled response; request metadata
	# is projected because the original snapshot generator had no event header.
	var response: Dictionary = after.duplicate(true)
	response["_request_id"] = str(request.request_id)
	Game._on_event("room.snapshot",response)
	await present()
	var after_exact: bool = Game.room.get("player",{}).get("monster_pool",{})==after.player.monster_pool
	var closed := dialog_under($UI)==null
	var all_text: bool = not labels.is_empty() and labels.all(func(label):return label.inside and label.all_lines_visible)
	var passed: bool = entered and dialog_opened and geometry and all_text and picture_ok and submitted and exact and unchanged_until_response and after_exact and closed
	if pool_case.ends_with("T02"): passed=passed and initially_disabled and replacement_selected
	return {"case_id":pool_case,"hero":pool_hero,"capacity":pool_capacity,"native_source_sha":row.source_sha,"seed":row.actual.seed,"cycle":cycle,"language":language,"resolution":[size.x,size.y],"frame_cap":fps,"controlled_response_delay_ms":delay,"entry_clicked":entered,"dialog_inside_window":geometry,"window_geometry":window_geometry,"labels":labels,"full_accept_initially_disabled":initially_disabled,"actual_replacement_selected":replacement_selected,"command_exact":exact,"state_unchanged_until_response":unchanged_until_response,"original_after_pool_applied":after_exact,"closed_after_actual_click":closed,"input_traces":pool_traces.duplicate(true),"screenshot":picture,"diagnostic_only":pool_probe,"request_header_projection_only":true,"passed":passed}

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := PoolGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://tests/data/pool_capacity_native_witnesses.json"))
	assert(data.source_sha==ORIGINAL_SOURCE)
	var rows: Array = data.rows.filter(func(row):return row.case_id==pool_case and row.actual.hero==pool_hero and int(row.actual.capacity)==pool_capacity)
	var wanted: Array = []
	for row in rows:
		if pool_case.ends_with("T01") and int(row.actual.occupancy)==pool_capacity-1: wanted.append(row)
		elif pool_case.ends_with("T02") and str(row.actual.pile)==({460001:"Hand",461001:"Library",462001:"Discard"}.get(int(row.actual.seed),"")): wanted.append(row)
		elif pool_case.ends_with("T03"): wanted.append(row)
	assert(wanted.size()==(6 if pool_case.ends_with("T03") else 3))
	var old_language := P.language()
	get_window().mode = Window.MODE_WINDOWED
	var languages: Array = ["en"] if pool_probe else ["zh-CN","zh-TW","en","ja","ko"]
	if not pool_language.is_empty():
		assert(not pool_probe and pool_language in ["zh-CN","zh-TW","en","ja","ko"])
		languages = [pool_language]
	var sizes: Array = [Vector2i(960,540)] if pool_probe else [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]
	var caps: Array = [60] if pool_probe else [30,60,144]
	var delays: Array = [0] if pool_probe else [0,250,1000]
	for language in languages:
		P.set_language(language)
		for size in sizes:
			get_window().size = size
			for fps in caps:
				Engine.max_fps=fps
				for delay in delays:
					for row in (wanted.slice(0,1) if pool_probe else wanted):
						var cycle: int = [460001,461001,462001].find(int(row.actual.seed))+1
						var result: Dictionary = await witness(row,language,size,fps,delay,cycle,delay==0 and row==wanted[0])
						observations.append(result)
						FileAccess.open(output+"/checkpoint.json",FileAccess.WRITE).store_string(JSON.stringify({"rows":observations.size(),"last":result}))
	P.set_language(old_language)
	Game.gateway = old_gateway
	gateway.free()
	var result := {"ok":observations.all(func(row):return row.passed) and DisplayServer.get_name()!="headless","observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"diagnostic_only":pool_probe,"whole_task_accepted":false}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit(0 if result.ok else 1)
