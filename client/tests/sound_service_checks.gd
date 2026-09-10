extends RefCounted

# Run inside audio_font_preview so the mixer can retire stopped voices before exit.
func run_test() -> Dictionary:
	var service = load("res://audio/sound_service.gd").new()
	service.persist_settings = false
	service.bind_game_events = false
	service.bus_name = &"FantasyCard Test SFX"
	var tree := Engine.get_main_loop() as SceneTree
	tree.root.add_child(service)
	var heard: Array = []
	service.cue_started.connect(func(cue): heard.append(cue))
	var checks: Dictionary = {}
	checks["All 22 resources load"] = service.streams.size() == 22
	var durations_ok := true
	for stream in service.streams.values():
		durations_ok = durations_ok and stream.get_length() > 0.05 and stream.get_length() < 2.0
	checks["All cues are short nonempty clips"] = durations_ok
	checks["First cue plays"] = service.play_cue("ui_click")
	checks["Rapid duplicate is suppressed"] = not service.play_cue("ui_click") and heard.size() == 1
	checks["Unknown cue stays silent"] = not service.play_cue("missing")
	service.set_muted(true)
	checks["Mute suppresses sound"] = not service.play_cue("card_play")
	var stopped := true
	for voice in service._voices: stopped = stopped and not voice.playing
	checks["Mute stops current voices"] = stopped
	service.set_muted(false)
	service.set_volume(0.0)
	checks["Zero volume stays silent"] = not service.play_cue("card_play")
	service.set_volume(2.0)
	checks["Volume clamps and applies to dedicated bus"] = is_equal_approx(service.volume, 1.0) and is_equal_approx(AudioServer.get_bus_volume_db(AudioServer.get_bus_index(service.bus_name)), -3.0)
	service.stop_all()
	for cue in service.CUES: service.play_cue(cue)
	checks["Bursts keep a fixed eight-voice pool"] = service._voices.size() == 8 and service.get_child_count() == 8
	checks["Dedicated bus has a limiter"] = AudioServer.get_bus_effect_count(AudioServer.get_bus_index(service.bus_name)) == 1
	var button := Button.new()
	service.add_child(button)
	service.stop_all()
	heard.clear()
	service._bind_button(weakref(button))
	service._bind_button(weakref(button))
	button.pressed.emit()
	checks["Button hook binds only once"] = button.pressed.get_connections().size() == 1 and heard == ["ui_click"]
	button.disabled = true
	button.pressed.emit()
	checks["Disabled button does not play"] = heard.size() == 1
	button.disabled = false
	button.set_meta("sound_cue", "")
	button.pressed.emit()
	checks["Decorative preview buttons can be silent"] = heard.size() == 1
	service.settings_path = "user://sound-validation-%s.cfg" % Time.get_ticks_usec()
	service.persist_settings = true
	service.set_volume(0.42)
	service.set_muted(true)
	var restored = load("res://audio/sound_service.gd").new()
	restored.settings_path = service.settings_path
	restored._load_settings()
	checks["Volume and mute survive a new instance"] = is_equal_approx(restored.volume, 0.42) and restored.muted
	DirAccess.remove_absolute(ProjectSettings.globalize_path(service.settings_path))
	restored.free()
	service.free()
	checks["Private test bus is removed"] = AudioServer.get_bus_index(&"FantasyCard Test SFX") == -1
	return {"ok": not checks.values().has(false), "message": "Bundled sound playback, cooldown, bounded voices, mute/volume, limiter and button routing", "checks": checks}
