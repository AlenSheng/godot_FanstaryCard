extends SceneTree

func _initialize() -> void:
	var result: Dictionary = load("res://tests/test_session_sequence.gd").new().run_test()
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
