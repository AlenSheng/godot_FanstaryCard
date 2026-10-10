extends "res://tests/pr13_b10_render_cases.gd"

const Details = preload("res://ui/numerical_details.gd")

func guardian_dialog() -> AcceptDialog:
	for node in $UI.find_children("*", "AcceptDialog", true, false):
		if node.visible: return node
	return null

func dialog_text(dialog: AcceptDialog) -> String:
	var lines := PackedStringArray()
	for node in dialog.find_children("*", "Label", true, false):
		if node.visible: lines.append(node.text)
	return "\n".join(lines)

func scroll_to_scope(dialog: AcceptDialog) -> Dictionary:
	var scroll: ScrollContainer = dialog.find_children("*", "ScrollContainer", true, false)[0]
	var point: Vector2 = scroll.get_global_transform_with_canvas() * (scroll.size * .5)
	dialog.notify_mouse_entered()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	dialog.push_input(motion, true)
	await get_tree().process_frame
	for i in range(16):
		var wheel := InputEventMouseButton.new()
		wheel.button_index = MOUSE_BUTTON_WHEEL_DOWN
		wheel.pressed = true
		wheel.position = point
		wheel.global_position = point
		dialog.push_input(wheel, true)
		await get_tree().process_frame
	var label: Label = scroll.find_children("*", "Label", true, false)[0]
	var last_line: int = label.get_line_count() - 1
	var line_rect := Rect2(label.get_global_rect().position + Vector2(0, label.get_line_height(last_line) * last_line), Vector2(label.size.x, label.get_line_height(last_line)))
	return {"wheel_inputs":16,"vertical_scroll":scroll.scroll_vertical,"horizontal_scroll_disabled":scroll.horizontal_scroll_mode==ScrollContainer.SCROLL_MODE_DISABLED,"last_line_visible":scroll.get_global_rect().intersects(line_rect),"line_count":label.get_line_count()}

func capture_case(id: String, passed: bool, actual: Dictionary, language: String, resolution: Vector2i, fps: int) -> void:
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var pixels := get_viewport().get_texture().get_image()
	var screenshot := ""
	if language == "en" and resolution.x == 960 and fps == 60:
		screenshot = id + ".png"
		passed = passed and pixels.save_png(output + "/" + screenshot) == OK
	passed = passed and pixels.get_size() == resolution
	if not case_verdicts.has(id): case_verdicts[id] = true
	case_verdicts[id] = case_verdicts[id] and passed
	observations.append({"case_id": id, "language": language, "resolution": [resolution.x, resolution.y], "fps_cap": fps, "actual": actual, "screenshot": screenshot, "actual_pixel_size": [pixels.get_width(), pixels.get_height()], "passed": passed})

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var original_language: String = P.language()
	var original_hero: String = Game.hero_class
	var original_fps: int = Engine.max_fps
	get_window().mode = Window.MODE_WINDOWED
	get_viewport().gui_embed_subwindows = true
	Game.hero_class = "Guardian"
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080), Vector2i(1280,720), Vector2i(960,540)]:
			get_window().size = resolution
			for fps in [30,60,144]:
				Engine.max_fps = fps
				reset_cards(["C09"], "Guardian", 100)
				Game.room.player.weapon_level = 2
				Game.room.player.numerical_state = {"guardian_policy":"FractionalRemainder", "guardian_remainder_tenths":4}
				await present()
				var clicked: bool = await click_named("GuardianRemainder")
				await get_tree().process_frame
				var dialog := guardian_dialog()
				var text := dialog_text(dialog) if dialog != null else ""
				var labels: Dictionary = Details.GUARDIAN_IMPACT[language]
				var current := [1.0,1.0,2.0,2.0,3.0,3.0]
				var mean := [1.0,1.4,1.8,2.2,2.6,3.0]
				var rows: Array = []
				for level in range(6): rows.append(labels.row % [level,current[level],mean[level],mean[level]-current[level]])
				await capture_case("PR13-B07.2-T01", clicked and text.contains(rows[2]) and text.contains(rows[4]) and text.contains(labels.warning), {"actual_gui_click":clicked,"level2_visible":text.contains(rows[2]),"level4_visible":text.contains(rows[4]),"weakening_warning_visible":text.contains(labels.warning)}, language, resolution, fps)
				await capture_case("PR13-B07.2-T02", text.contains(rows[1]) and text.contains(labels.warning) and text.contains(rows[2]) and text.contains(rows[4]), {"level1_improvement_visible":text.contains(rows[1]),"other_level_declines_retained":text.contains(rows[2]) and text.contains(rows[4]),"gain_does_not_mask_declines":text.contains(labels.warning)}, language, resolution, fps)
				var scroll_observation: Dictionary = await scroll_to_scope(dialog) if dialog != null else {}
				await capture_case("PR13-B07.2-T03", rows.all(func(row): return text.contains(row)) and text.contains(labels.scope) and bool(scroll_observation.get("last_line_visible",false)) and bool(scroll_observation.get("horizontal_scroll_disabled",false)), {"six_independent_level_rows_retained":rows.all(func(row): return text.contains(row)),"scope_limit_in_content":text.contains(labels.scope),"whole_pool_buff_not_claimed":text.contains(labels.warning),"actual_gui_scroll":scroll_observation}, language, resolution, fps)
				if dialog != null: dialog.queue_free()
				await get_tree().process_frame
	P.set_language(original_language)
	Game.hero_class = original_hero
	Engine.max_fps = original_fps
	Game.gateway = old_gateway
	gateway.free()
	var cases: Array = []
	for id in case_verdicts:
		cases.append({"case_id":id,"executed":true,"status":"Passed" if case_verdicts[id] else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":18,"all_rows_passed":case_verdicts[id]},"scope":"Actual X11 project UI and normal GUI pointer, localized per-level weapon mean and weakening disclosure. Survival/overflow intervals require the separately recorded real current experiment; FPS caps are not hardware performance claims."})
	var result := {"ok":cases.size()==3 and observations.size()==54 and not case_verdicts.values().has(false) and DisplayServer.get_name()!="headless","cases":cases,"observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name()}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
