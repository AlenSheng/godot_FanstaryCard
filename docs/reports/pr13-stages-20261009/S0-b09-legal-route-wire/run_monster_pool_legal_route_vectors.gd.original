extends SceneTree

# Cloud-only entry point; no server, product transport, or Godot UI is changed.
func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var game := root.get_node_or_null("Game")
	if game != null:
		game.set_process(false)
	var suite: RefCounted = load("res://tests/test_monster_pool_legal_route_vectors.gd").new()
	var result: Dictionary = suite.run_test()
	var result_path := OS.get_environment("PR13_LEGAL_ROUTE_GODOT_RESULT")
	if result_path.is_empty() or FileAccess.file_exists(result_path):
		print(JSON.stringify({"ok": false, "reason": "result path absent or already exists"}))
		quit(2)
		return
	var result_file := FileAccess.open(result_path, FileAccess.WRITE)
	if result_file == null:
		quit(2)
		return
	result_file.store_string(JSON.stringify(result))
	result_file.close()
	print(JSON.stringify(result))
	quit(0 if result.get("ok", false) else 1)
