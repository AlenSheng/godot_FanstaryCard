extends Control

const P = preload("res://ui/palette.gd")
const LegacySettings = preload("res://ui/settings_panel.gd")

func _ready() -> void:
	get_window().mode = Window.MODE_WINDOWED
	get_window().set_flag(Window.FLAG_NO_FOCUS, true)
	get_window().gui_embed_subwindows = true
	Game.set_process(false)
	Game.gateway.end_session("", false)
	Game.gateway.set_process(false)
	Sound.persist_settings = false
	Sound.stop_all()
	Sound.set_music_context("")
	Sound.stop_music()
	Sound._headless_runtime = true
	Sound.set_process(false)
	call_deferred("_run")

func _run() -> void:
	var output := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	assert(not output.is_empty() and DisplayServer.get_name() != "headless")
	var background := ColorRect.new()
	background.color = P.INK
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var frames := []
	var checks := {}
	for locale_code in ["zh-CN", "en"]:
		I18n.set_language("en" if locale_code == "en" else "zh")
		for width in [960, 1280, 1920]:
			get_window().size = Vector2i(width, width * 9 / 16)
			get_window().position = Vector2i.ZERO
			await get_tree().process_frame
			var panel := LegacySettings.new()
			add_child(panel)
			panel.show_settings()
			await get_tree().create_timer(0.15).timeout
			await RenderingServer.frame_post_draw
			var popup := panel.get_node("SettingsPopup") as PopupPanel
			var name_tag := "%s_%d_legacy_settings" % [locale_code, width]
			var logical_size := get_viewport().get_visible_rect().size
			checks[name_tag + " window bounds"] = popup.position.x >= 0 and popup.position.y >= 0 and popup.position.x + popup.size.x <= logical_size.x and popup.position.y + popup.size.y <= logical_size.y
			var image := get_viewport().get_texture().get_image()
			checks[name_tag + " capture"] = image.save_png(output.path_join(name_tag + ".png")) == OK and image.get_width() == width
			frames.append({"locale": locale_code, "width": width, "popup_size": popup.size, "file": name_tag + ".png"})
			popup.hide()
			panel.queue_free()
			await get_tree().process_frame
	var report := {"ok": not checks.values().has(false), "checks": checks, "frames": frames, "actual_game_matches": 0, "scope": "Rendered retained settings across two languages and three resolutions"}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	P.clear_runtime_fonts()
	await get_tree().process_frame
	get_tree().quit(0 if report.ok else 1)
