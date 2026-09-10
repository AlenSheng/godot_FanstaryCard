extends "res://tests/art_preview.gd"

var checks: Dictionary = {}

func _ready() -> void:
	output = "res://evidence/audio-fonts"
	get_window().gui_embed_subwindows = true
	Sound.persist_settings = false
	Sound.set_volume(0.65, false)
	Sound.set_muted(false)
	super._ready()
	Game.set_process(false)
	Game.gateway.reconnect_enabled = false

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	var mixer_checks: Dictionary = load("res://tests/sound_service_checks.gd").new().run_test()
	checks.merge(mixer_checks.checks)
	var rest_checks: Dictionary = await load("res://tests/rest_audio_session_checks.gd").new().run_test($UI)
	checks.merge(rest_checks.checks)
	await get_tree().create_timer(0.1).timeout
	for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
		get_window().size = resolution
		var suffix := "_%s" % resolution.x
		Game.room = {}
		$UI.screen = "hall"
		await _capture("hall" + suffix)
		var settings = $UI.get_node("AudioSettings")
		settings.show_settings()
		await _capture("sound_settings" + suffix, false)
		var popup: PopupPanel = settings._popup
		checks["Settings stay in window" + suffix] = Rect2(get_viewport().get_visible_rect()).encloses(Rect2(popup.position, popup.size))
		var slider: HSlider = popup.find_child("SoundVolume", true, false)
		slider.value = 42
		checks["Volume slider applies" + suffix] = is_equal_approx(Sound.volume, 0.42)
		var mute: CheckButton = popup.find_child("SoundMute", true, false)
		var shortcut := InputEventKey.new()
		shortcut.keycode = KEY_F10
		shortcut.pressed = true
		Input.parse_input_event(shortcut)
		await get_tree().process_frame
		checks["F10 works with popup slider focus" + suffix] = Sound.muted and mute.button_pressed
		shortcut = InputEventKey.new()
		shortcut.keycode = KEY_F10
		Input.parse_input_event(shortcut)
		mute.button_pressed = false
		mute.button_pressed = true
		checks["Mute applies" + suffix] = Sound.muted and not Sound.play_cue("card_play")
		mute.button_pressed = false
		checks["Unmute restores playback" + suffix] = Sound.play_cue("card_play")
		Sound.stop_all()
		popup.hide()
		await get_tree().process_frame
		Sound.set_volume(0.65, false)
	var report := {"ok": layout_errors.is_empty() and not checks.values().has(false), "checks": checks, "layout_errors": layout_errors, "fixture_only": true, "screenshots": screenshot_count}
	var file := FileAccess.open(output + "/report.json", FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if report.ok else 1)
