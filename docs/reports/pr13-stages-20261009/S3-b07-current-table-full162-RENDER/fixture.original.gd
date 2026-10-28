extends "res://tests/pr13_guardian_impact_render.gd"

var original_rows: Array = []
var failures: Array = []

func emit_row(id: String, passed: bool, actual: Dictionary, language: String, resolution: Vector2i, cap: int, delay: int) -> void:
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var pixels: Image = get_viewport().get_texture().get_image()
	passed = passed and pixels.get_size() == resolution
	var screenshot := ""
	if cap == 60 and delay == 100:
		screenshot = id + "_" + language + "_" + str(resolution.x) + ".png"
		passed = passed and pixels.save_png(output + "/" + screenshot) == OK
	var row := {"case_id":id,"passed":passed,"language":language,"resolution":[resolution.x,resolution.y],"fps_cap":cap,"controlled_response_delay_ms":delay,"screenshot":screenshot,"actual":actual}
	original_rows.append(row)
	if not passed: failures.append(row)
	var stream := FileAccess.open(output + "/rows.original.jsonl",FileAccess.READ_WRITE)
	stream.seek_end()
	stream.store_line(JSON.stringify(row))
	stream.close()

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	FileAccess.open(output + "/rows.original.jsonl",FileAccess.WRITE).close()
	Game.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := CodecGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	get_window().mode = Window.MODE_WINDOWED
	get_viewport().gui_embed_subwindows = true
	Game.hero_class = "Guardian"
	for language in ["zh-CN","en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = resolution
			for cap in [30,60,144]:
				Engine.max_fps = cap
				for delay in [0,100,300]:
					reset_cards(["C17"],"Guardian",100)
					Game.room.player.weapon_level = 2
					Game.room.player.numerical_state = {"guardian_policy":"FractionalRemainder","guardian_remainder_tenths":4}
					if delay > 0: await get_tree().create_timer(float(delay)/1000.0).timeout
					await present()
					var before := JSON.stringify(Game.room)
					var clicked: bool = await click_named("GuardianRemainder")
					await get_tree().process_frame
					var dialog: AcceptDialog = guardian_dialog()
					var content: String = dialog_text(dialog) if dialog != null else ""
					var labels: Dictionary = Details.GUARDIAN_IMPACT[language]
					var current := [1.0,1.0,2.0,2.0,3.0,3.0]
					var means := [1.0,1.4,1.8,2.2,2.6,3.0]
					var texts: Array = []
					for L in range(6): texts.append(labels.row % [L,current[L],means[L],means[L]-current[L]])
					var scope: Dictionary = await scroll_to_scope(dialog) if dialog != null else {}
					var all_rows: bool = texts.all(func(text):return content.contains(text))
					var common_ok: bool = clicked and dialog != null and all_rows and content.contains(labels.scope) and bool(scope.get("last_line_visible",false)) and bool(scope.get("horizontal_scroll_disabled",false)) and before == JSON.stringify(Game.room)
					await emit_row("PR13-B07.1-T01",common_ok and content.contains(texts[0]) and content.contains(texts[5]),{"normal_gui_click":clicked,"six_rows":texts,"content":content,"endpoint_rows_present":content.contains(texts[0]) and content.contains(texts[5]),"actual_scroll":scope,"room_unchanged":before==JSON.stringify(Game.room)},language,resolution,cap,delay)
					await emit_row("PR13-B07.1-T02",common_ok and content.contains(texts[1]) and content.contains(texts[3]),{"normal_gui_click":clicked,"middle_rows_present":content.contains(texts[1]) and content.contains(texts[3]),"actual_scroll":scope,"room_unchanged":before==JSON.stringify(Game.room)},language,resolution,cap,delay)
					if dialog != null: dialog.queue_free()
					await get_tree().process_frame
					var checks: Array = []
					var default_ok := true
					for L in range(6):
						reset_cards(["C17"],"Guardian",100)
						Game.room.player.weapon_level = L
						Game.room.player.numerical_state = {}
						var original := JSON.stringify(Game.room)
						await present()
						await click_named("Card_C17")
						await present()
						var preview: Dictionary = Game.combat_preview.duplicate(true)
						var expected_shield: int = 7 + int(current[L])
						var absent: bool = $UI._reference.get_node_or_null("GuardianRemainder") == null
						var visible_text: Array = preview_texts()
						var expected_text: String = "%s +%d" % [P.localized("battle_preview_shield"),expected_shield]
						var visible_shield: bool = visible_text.has(expected_text)
						var ok: bool = absent and visible_shield and not preview.is_empty() and int(preview.get("shield_gain",-1)) == expected_shield and int(preview.get("shield_overflow",-1)) == 0 and original == JSON.stringify(Game.room)
						checks.append({"level":L,"expected_current_step":current[L],"expected_shield":expected_shield,"actual_preview":preview,"visible_preview_text":visible_text,"expected_shield_text":expected_text,"actual_shield_text_visible":visible_shield,"candidate_entry_absent":absent,"room_unchanged":original==JSON.stringify(Game.room),"passed":ok})
						default_ok = default_ok and ok
					await emit_row("PR13-B07.1-T03",default_ok,{"six_actual_default_levels":checks,"candidate_flag_absent":true,"current_snapshot_controls":true},language,resolution,cap,delay)
	Game.gateway = old_gateway
	gateway.free()
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(0.25).timeout
	var result := {"ok":original_rows.size()==162 and failures.is_empty() and DisplayServer.get_name()!="headless","observations":original_rows,"failures":failures,"required_rows":162,"required_PNGs":18,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"source_sha":OS.get_environment("PR13_SOURCE_SHA"),"candidate_production_activation":false,"MAIN_accepted":false}
	FileAccess.open(output + "/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
