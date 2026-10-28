extends "res://tests/ui_visual_review.gd"

func _ready() -> void:
	super._ready()
	if Game.changed.is_connected(Sound._sync_context): Game.changed.disconnect(Sound._sync_context)
	if Game.sound_requested.is_connected(Sound._handle_sound_request): Game.sound_requested.disconnect(Sound._handle_sound_request)
	Sound.set_music_context("")
	Sound.stop_music()

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	_frame_log = FileAccess.open(output.path_join("frames.original.jsonl"), FileAccess.WRITE)
	_initial_lobby = Game.lobby.duplicate(true)
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		Game.changed.emit()
		await get_tree().process_frame
		for width in [960, 1280, 1920]:
			get_window().size = Vector2i(width, width * 9 / 16)
			get_window().position = _review_window_position()
			for ready in [true, false]:
				await _reset_fixture()
				Game.lobby = {}
				$UI.fixture_ready = ready
				await _render_base()
				var name_tag := "%s_%d_steam_%s_login" % [locale, width, "ready" if ready else "unavailable"]
				var buttons: Array = $UI.content.find_children("*", "Button", true, false)
				review_checks[name_tag + ": only one entry action"] = buttons.size() == 1 and buttons[0].name == "EnterGameButton"
				review_checks[name_tag + ": no account input"] = $UI.content.find_children("*", "LineEdit", true, false).is_empty()
				review_checks[name_tag + ": entry caption"] = buttons[0].text == ("Enter" if locale == "en" else "进入")
				review_checks[name_tag + ": public title locale"] = $UI._game_title.text == Palette.localized("game_title")
				review_checks[name_tag + ": readiness state"] = buttons[0].disabled == not ready
				await _review_capture(name_tag, false)
	_frame_log.close()
	var report := {"ok": screenshot_count == 12 and layout_errors.is_empty() and not review_checks.values().has(false), "frames": review_frames, "checks": review_checks, "layout_errors": layout_errors, "screenshots": screenshot_count, "actual_game_matches": 0, "scope": "Steam ready/unavailable UI fixtures; no Steam SDK or real authentication"}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	Sound.stop_all()
	Sound.stop_music()
	await get_tree().create_timer(0.35).timeout
	get_tree().quit(0 if report.ok else 1)
