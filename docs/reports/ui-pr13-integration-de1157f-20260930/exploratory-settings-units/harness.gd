extends "res://tests/ui_style_audit.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().create_timer(0.5).timeout
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			_reset()
			$UI.screen = "hall"
			$UI._render()
			var settings = $UI.get_node("AudioSettings")
			for iteration in range(2):
				settings.show_settings()
				await get_tree().process_frame
				await get_tree().process_frame
				var popup: PopupPanel = settings._popup
				var scroll: ScrollContainer = popup.get_node("AudioSettingsScroll")
				scroll.scroll_vertical = 10000
				var suffix := "%s_%s_%s" % [iteration, locale, resolution.x]
				await _take("settings_bottom_" + suffix, false)
				var column: VBoxContainer = scroll.get_child(0)
				var account: Button = column.get_node("SwitchAccountButton")
				var back: Button = column.get_child(column.get_child_count() - 1)
				_check_audit(scroll.get_global_rect().grow(1).encloses(account.get_global_rect()), "account reachable " + suffix)
				_check_audit(scroll.get_global_rect().grow(1).encloses(back.get_global_rect()), "back reachable " + suffix)
				_check_audit(scroll.scroll_vertical > 0, "scroll reaches lower actions " + suffix)
				_check_audit(popup.size.x <= get_window().size.x and popup.size.y <= get_window().size.y, "popup bounded " + suffix)
				back.pressed.emit()
				await get_tree().process_frame
				await get_tree().process_frame
				_check_audit(settings._popup == null and not is_instance_valid(popup), "back closes popup " + suffix)
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"), "captures": captures, "screenshots": captures.size(), "checks": checks, "errors": audit_errors, "text_observations": text_observations, "fixture_only": true, "limitations": "Focused native scroll/reopen supplement with external hashed fixture. Does not execute account logout or actual audio output."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "checks": checks.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)
