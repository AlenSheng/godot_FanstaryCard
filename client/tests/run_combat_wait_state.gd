extends SceneTree

func _initialize() -> void:
	var result: Dictionary = preload("res://tests/test_combat_wait_state.gd").new().run_test()
	var path := OS.get_environment("PR13_WAIT_REPORT")
	if not path.is_empty(): FileAccess.open(path, FileAccess.WRITE).store_string(JSON.stringify(result))
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
