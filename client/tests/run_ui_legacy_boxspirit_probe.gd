extends SceneTree

func _initialize() -> void:
	var palette = load("res://ui/palette.gd")
	palette.set_language("zh-CN")
	var result: Dictionary = load("res://tests/test_boxspirit_instances.gd").new().run_test()
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
