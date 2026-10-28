extends "res://tests/pr13_guardian_impact_render.gd"

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
		assert(P.language() == language)
		for resolution in [Vector2i(1920,1080), Vector2i(1280,720), Vector2i(960,540)]:
			get_window().size = resolution
			for fps in [30,60,144]:
				Engine.max_fps = fps
				reset_cards(["C09"], "Guardian", 100)
				Game.room.player.numerical_state = {"guardian_policy":"FractionalRemainder", "guardian_remainder_tenths":4}
				await present()
				var before: String = JSON.stringify(Game.room)
				var clicked: bool = await click_named("GuardianRemainder")
				await get_tree().process_frame
				var dialog := guardian_dialog()
				var content: String = dialog_text(dialog) if dialog != null else ""
				var rules: Array = Details.GUARDIAN_REMAINDER_RULES[language]
				var all_rules: bool = rules.all(func(rule): return content.contains(str(rule)))
				var remainder_displayed: bool = content.contains(Details.text("weapon") % 4)
				await capture_case("DEV-GUARDIAN-RULES-T01", clicked and all_rules and remainder_displayed and before==JSON.stringify(Game.room), {"normal_gui_click":clicked,"all_localized_rules_present":all_rules,"room_state_unchanged":before==JSON.stringify(Game.room),"remainder_displayed":remainder_displayed}, language,resolution,fps)
				var scroll: Dictionary = await scroll_to_scope(dialog) if dialog != null else {}
				await capture_case("DEV-GUARDIAN-RULES-T02", all_rules and bool(scroll.get("last_line_visible",false)) and bool(scroll.get("horizontal_scroll_disabled",false)) and before==JSON.stringify(Game.room), {"normal_gui_scroll":scroll,"rules_and_per_level_scope_retained":all_rules,"room_state_unchanged":before==JSON.stringify(Game.room)}, language,resolution,fps)
				if dialog != null: dialog.queue_free()
				await get_tree().process_frame
				Game.room.player.numerical_state = {}
				await present()
				# The same existing details entry is available programmatically when
				# legacy rooms hide the candidate-specific HUD button.
				before = JSON.stringify(Game.room)
				Details.show_remainder($UI)
				await get_tree().process_frame
				dialog = guardian_dialog()
				content = dialog_text(dialog) if dialog != null else ""
				var legacy_clean: bool = not content.contains(str(Details.GUARDIAN_IMPACT[language].title)) and rules.all(func(rule): return not content.contains(str(rule)))
				await capture_case("DEV-GUARDIAN-RULES-T03", dialog!=null and legacy_clean and before==JSON.stringify(Game.room), {"legacy_candidate_copy_absent":legacy_clean,"room_state_unchanged":before==JSON.stringify(Game.room),"default_room_policy_unchanged":not Game.room.player.numerical_state.has("guardian_policy")}, language,resolution,fps)
				if dialog != null: dialog.queue_free()
				await get_tree().process_frame
	P.set_language(original_language)
	Game.hero_class = original_hero
	Engine.max_fps = original_fps
	Game.gateway = old_gateway
	gateway.free()
	var cases: Array = []
	for id in case_verdicts:
		cases.append({"case_id":id,"executed":true,"status":"Passed" if case_verdicts[id] else "Failed","profiles_executed":["OFFLINE","RENDER"],"actual":{"matrix_rows":18,"all_rows_passed":case_verdicts[id]},"scope":"Development UI fixture only; actual backend preview/retry/cap/leave/PVP experiments remain separate canonical requirements."})
	var result := {"ok":cases.size()==3 and observations.size()==54 and not case_verdicts.values().has(false) and DisplayServer.get_name()!="headless","cases":cases,"observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name()}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
