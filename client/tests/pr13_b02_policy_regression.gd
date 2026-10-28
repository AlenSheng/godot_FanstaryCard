extends Node

func _ready() -> void:
	_run.call_deferred()

func _run() -> void:
	var checks: Array = []
	for path in ["res://tests/test_protobuf.gd", "res://tests/test_combat_preview_state.gd"]:
		var result: Dictionary = load(path).new().run_test()
		checks.append({"path": path, "passed": result.ok, "message": result.message})
	var ok: bool = checks.size() == 2 and checks.all(func(row): return row.passed)
	var file := FileAccess.open(OS.get_environment("PR13_B02_CLIENT_OUTPUT"), FileAccess.WRITE)
	file.store_string(JSON.stringify({"ok": ok, "checks": checks}) + "\n")
	file.close()
	get_tree().quit(0 if ok else 1)
