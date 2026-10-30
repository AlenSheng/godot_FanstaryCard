extends "res://tests/ui_visual_review.gd"

const GoogleCopy = preload("res://tests/test_google_localization.gd")

func _ready() -> void:
	super._ready()
	if Game.changed.is_connected(Sound._sync_context): Game.changed.disconnect(Sound._sync_context)
	if Game.sound_requested.is_connected(Sound._handle_sound_request): Game.sound_requested.disconnect(Sound._handle_sound_request)
	Sound.set_music_context("")
	Sound.stop_music()

func _selected(scenario: String) -> bool:
	return scenario in ["login", "login_notice", "login_notice_bottom", "settings_bottom", "confirm"]

func _reset_fixture() -> void:
	var dialog := $UI.get_node("AudioSettings").get_node_or_null("AccountDeletionConfirmation")
	if dialog != null: dialog.queue_free()
	await super._reset_fixture()

func _prepare_scene(scenario: String, locale: String) -> bool:
	if scenario in ["login_notice", "login_notice_bottom"]:
		Game.lobby = {}
		Game.authentication_reason = Palette.localized("google_token_invalid")
		Game.server_info["announcement"] = {}
		return true
	if scenario == "confirm":
		await super._prepare_scene("settings_bottom", locale)
		await get_tree().process_frame
		var audio := $UI.get_node("AudioSettings")
		var button := audio._popup.find_child("AccountDeletionRequestButton", true, false) as Button
		var check_prefix := "%s_%d_confirm:" % [locale, get_window().size.x]
		review_checks[check_prefix + " deletion entry is enabled"] = button != null and not button.disabled
		button.pressed.emit()
		await get_tree().process_frame
		review_checks[check_prefix + " actual account confirmation opens"] = audio.get_node_or_null("AccountDeletionConfirmation") != null
		var dialog := audio.get_node("AccountDeletionConfirmation")
		review_checks[check_prefix + " warning in selected language"] = dialog.description_label.text == Palette.localized("account_deletion_confirmation")
		review_checks[check_prefix + " title in selected language"] = dialog.title_label.text == Palette.localized("account_deletion_request")
		return false
	return await super._prepare_scene(scenario, locale)

func _review_capture(frame_name: String, rebuild: bool = true) -> void:
	await super._review_capture(frame_name, rebuild)
	for entry in review_frames.back().texts:
		for key in GoogleCopy.KEYS:
			if str(entry.text) != Palette.localized(key): continue
			review_checks[frame_name + ": readable Google copy " + str(entry.path)] = float(entry.effective_font_size) >= 12.0 - 0.01

func _run() -> void:
	OS.set_environment("FANTASYCARD_REVIEW_WIDTHS", "960,1280,1920")
	await super._run()
	var report := JSON.parse_string(FileAccess.get_file_as_string(output.path_join("review.json"))) as Dictionary
	report["ok"] = report.render_capture_complete and report.legacy_layout_observations.is_empty() and not report.checks.values().has(false)
	report["provider_scope"] = "Google UI policy is selected by a fixture subclass on the desktop; no native Google SDK, token or real sign-in was executed."
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
