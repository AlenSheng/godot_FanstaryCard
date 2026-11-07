extends "res://tests/ui_visual_review.gd"

const LegacySettings = preload("res://ui/settings_panel.gd")

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	_frame_log = FileAccess.open(output.path_join("frames.original.jsonl"), FileAccess.WRITE)
	_initial_lobby = Game.lobby.duplicate(true)
	var chinese_pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/locales/zh-CN.json"))
	for locale in Palette.languages():
		var target_pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/locales/%s.json" % locale))
		_text_auditor = TextAudit.new(locale, chinese_pack, target_pack)
		I18n.set_language(locale)
		$UI.theme = Palette.theme()
		for child in $UI.get_children():
			if child is CanvasItem: child.hide()
		for width in [960, 1280, 1920]:
			get_window().size = Vector2i(width, width * 9 / 16)
			get_window().position = _review_window_position()
			var panel := LegacySettings.new()
			panel.name = "RetainedLegacySettings"
			$UI.add_child(panel)
			panel.show_settings()
			await get_tree().process_frame
			await get_tree().process_frame
			var popup := panel.get_node("SettingsPopup") as PopupPanel
			var selector := popup.find_child("LanguageSelector", true, false) as OptionButton
			var name_tag := "%s_%d_retained_panel" % [locale, width]
			var logical_size := get_viewport().get_visible_rect().size
			review_checks[name_tag + ": panel fits viewport"] = popup.position.x >= 0 and popup.position.y >= 0 and popup.position.x + popup.size.x <= logical_size.x and popup.position.y + popup.size.y <= logical_size.y
			review_checks[name_tag + ": eleven language options"] = selector.item_count == Palette.languages().size()
			review_checks[name_tag + ": selected locale"] = str(selector.get_item_metadata(selector.selected)) == locale
			await _review_capture(name_tag, false)
			popup.hide()
			panel.queue_free()
			await get_tree().process_frame
	_frame_log.close()
	var report := {"ok": screenshot_count == 33 and layout_errors.is_empty() and not review_checks.values().has(false), "frames": review_frames, "checks": review_checks, "layout_errors": layout_errors, "screenshots": screenshot_count, "actual_game_matches": 0, "scope": "Main retained settings, eleven locales and three resolutions"}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	Sound.stop_all()
	Sound.stop_music()
	await get_tree().create_timer(0.35).timeout
	get_tree().quit(0 if report.ok else 1)
