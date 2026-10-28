extends "res://tests/pr13_target_wait_frames.gd"

func rect_values(rect: Rect2) -> Array:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]

func click_viewport(point: Vector2) -> String:
	# CanvasItem's transform supplies viewport-local coordinates. push_input
	# routes these through the normal Control hit test and _gui_input path.
	get_viewport().notify_mouse_entered()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	get_viewport().push_input(motion, true)
	await get_tree().process_frame
	var hovered: Control = get_viewport().gui_get_hovered_control()
	var hovered_path := str(hovered.get_path()) if hovered != null else ""
	var down := InputEventMouseButton.new()
	down.button_index = MOUSE_BUTTON_LEFT
	down.button_mask = MOUSE_BUTTON_MASK_LEFT
	down.pressed = true
	down.position = point
	down.global_position = point
	get_viewport().push_input(down, true)
	await get_tree().process_frame
	var up := InputEventMouseButton.new()
	up.button_index = MOUSE_BUTTON_LEFT
	up.position = point
	up.global_position = point
	get_viewport().push_input(up, true)
	await get_tree().process_frame
	return hovered_path

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway: Node = Fixture.RecordingGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	var old_language: String = P.language()
	get_window().mode = Window.MODE_WINDOWED
	for language in ["zh-CN", "en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080), Vector2i(1280,720), Vector2i(960,540)]:
			get_window().size = resolution
			for count in [2,3]:
				for selection_present in [false,true]:
					for click_point in ["center","lower_half"]:
						reset_battle()
						gateway.sent = []
						if count == 3:
							Game.room.pve.monsters.append({"monster_id":"rust-rat","hp":20,"maximum_hp":20})
						Game.selected_cards = ["card"] if selection_present else []
						if selection_present: Game.combat_preview = Game._calculate_combat_preview(Game.selected_cards)
						await present()
						var wanted := "murk-snail" if count == 2 else "rust-rat"
						var button: Button = $UI._reference.get_node_or_null("MonsterTarget_" + wanted)
						var preview: Control = $UI._reference.get_node_or_null("CombatPreview")
						var button_rect := button.get_global_rect() if button != null else Rect2()
						var preview_rect := preview.get_global_rect() if preview != null else Rect2()
						var overlap: bool = preview != null and button_rect.intersects(preview_rect)
						var selected_before: Array = Game.selected_cards.duplicate()
						var before_image := get_viewport().get_texture().get_image()
						var actual_window := get_window().size
						var actual_pixels := before_image.get_size()
						var screenshot := ""
						var screenshot_ok := true
						if language == "en" and resolution.x == 960:
							screenshot = "%s_targets_%s_%s.png" % [count, "selected" if selection_present else "empty", click_point]
							screenshot_ok = before_image.save_png(output + "/" + screenshot) == OK
						var input_point := Vector2.ZERO
						var hovered_path := ""
						var visible: bool = button != null and button.is_visible_in_tree() and not button.disabled
						if visible:
							var local_point := Vector2(button.size.x * .5, button.size.y * (.5 if click_point == "center" else .82))
							input_point = button.get_global_transform_with_canvas() * local_point
							hovered_path = await click_viewport(input_point)
						var command: Dictionary = Game._latest_commands.get("battle.select_target", {})
						var clicked_expected: bool = command.get("payload", {}).get("target_id", "") == wanted
						var selection_kept: bool = Game.selected_cards == selected_before
						var ok: bool = visible and not overlap and clicked_expected and selection_kept and screenshot_ok and actual_window == resolution and actual_pixels == resolution
						var row := {"language":language,"resolution":[resolution.x,resolution.y],"living_targets":count,"selection_present":selection_present,"click_point":click_point,
							"actual_window_size":[actual_window.x,actual_window.y],"actual_pixel_size":[actual_pixels.x,actual_pixels.y],"target_id":wanted,
							"target_button_rect":rect_values(button_rect),"preview_rect":rect_values(preview_rect),"overlap":overlap,
							"viewport_input_point":[input_point.x,input_point.y],"hovered_control":hovered_path,"button_visible_and_enabled":visible,
							"expected_target_command_received":clicked_expected,"selected_card_order_preserved":selection_kept,"input_route":"Viewport.push_input mouse motion/down/up; no direct pressed emit",
							"screenshot":screenshot,"passed":ok}
						observations.append(row)
						if not ok: frame_errors.append(row)
	P.set_language(old_language)
	Game.gateway = old_gateway
	gateway.free()
	var driver := DisplayServer.get_name()
	var result := {"ok":observations.size()==48 and frame_errors.is_empty() and driver!="headless","observations":observations,"errors":frame_errors,
		"display_driver":driver,"adapter":RenderingServer.get_video_adapter_name(),"frames_drawn":Engine.get_frames_drawn(),
		"scope":"Actual rendered controls and normal GUI hit-testing with simulated viewport-local mouse events; owned controlled gateway; no server LIVE, human, capacity or hardware FPS claim"}
	FileAccess.open(output + "/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify({"ok":result.ok,"observations":observations.size(),"failed":frame_errors.size(),"display_driver":driver}))
	get_tree().quit(0 if result.ok else 1)
