extends SceneTree

func _initialize() -> void:
	var result: Dictionary = load("res://tests/test_localization.gd").new().run_test()
	print(result)
	quit(0 if result.get("ok", false) else 1)
