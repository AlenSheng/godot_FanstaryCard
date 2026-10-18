extends SceneTree

func _initialize() -> void:
	var sequence: Dictionary = load("res://tests/test_session_sequence.gd").new().run_test()
	var replay: Dictionary = load("res://tests/test_gateway_replay.gd").new().run_test()
	var result := {"ok": sequence.ok and replay.ok, "sequence": sequence, "connection_replay": replay}
	print(JSON.stringify(result))
	quit(0 if result.ok else 1)
