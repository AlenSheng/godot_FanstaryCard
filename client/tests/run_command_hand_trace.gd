extends SceneTree

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var checks := {}
	for path in ["res://tests/test_command_state_hand_trace.gd","res://tests/test_command_state_observation.gd"]:
		var test = load(path).new()
		var result: Dictionary = await test.run_test()
		if not result.get("ok",false) or not result.get("checks") is Dictionary:
			push_error("Required trace suite failed: "+path)
			quit(1)
			return
		for key in result.checks:
			checks[path+":"+str(key)] = result.checks[key] is bool and result.checks[key]
		test = null
	var failed: Array = checks.keys().filter(func(key): return not checks[key])
	print(JSON.stringify({"checks":checks.size(),"failed":failed,"new_worlds":0}))
	quit(0 if failed.is_empty() else 1)
