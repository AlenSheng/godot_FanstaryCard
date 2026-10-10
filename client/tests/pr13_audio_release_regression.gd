extends "res://tests/art_preview.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	Game.gateway.reconnect_enabled = false
	var mixer: Dictionary = load("res://tests/sound_service_checks.gd").new().run_test()
	var sessions: Dictionary = await load("res://tests/rest_audio_session_checks.gd").new().run_test($UI)
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(0.1).timeout
	var result := {"ok":mixer.ok and sessions.ok,"mixer":mixer,"sessions":sessions,"scope":"Actual native mixer state, bounded voices, stop/restart and session transitions with Dummy audio output; no audible listening claim."}
	FileAccess.open(output + "/audio-regression.json", FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
