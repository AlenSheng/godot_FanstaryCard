extends SceneTree

func _initialize() -> void:
	var result: Dictionary = await load("res://tests/test_codex_open.gd").new().run_test()
	print(result)
	quit(0 if result.get("ok", false) else 1)
