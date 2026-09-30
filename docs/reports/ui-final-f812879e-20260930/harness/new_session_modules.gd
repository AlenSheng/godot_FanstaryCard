extends SceneTree
func _initialize() -> void:
	_run.call_deferred()
func _run() -> void:
	var results: Dictionary = {}
	var ok := true
	for name in ["test_session_sequence", "test_settlement_polling"]:
		var value: Dictionary = await load("res://tests/" + name + ".gd").new().run_test()
		results[name] = value
		ok = ok and value.ok
	var report := {"ok": ok, "source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"), "tests": results}
	FileAccess.open(OS.get_environment("FANTASYCARD_SESSION_RESULTS"), FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	quit(0 if ok else 1)
