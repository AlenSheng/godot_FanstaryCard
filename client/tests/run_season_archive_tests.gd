extends Node

func _ready() -> void:
	call_deferred("_run")

func _run() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	var result: Dictionary = await load("res://tests/test_season_archive.gd").new().run_test()
	var output := OS.get_environment("FANTASYCARD_ARCHIVE_NATIVE_OUTPUT")
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  ")); file.close()
	print(JSON.stringify(result))
	load("res://ui/palette.gd").clear_runtime_fonts()
	Sound.stop_all()
	get_tree().quit(0 if result.ok else 1)
