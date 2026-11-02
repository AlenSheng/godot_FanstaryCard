extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var results := {}
    var failures: Array[String] = []
    var count := 0
    for name in ["test_combat_action_ids.gd", "test_terminal_command_context.gd", "test_play_retry.gd", "test_room_store.gd", "test_rejected_command_state.gd"]:
        var instance = load("res://tests/" + name).new()
        var checks: Dictionary = await instance.run_test()
        results[name] = checks
        for label in checks:
            count += 1
            if not checks[label]: failures.append(name + ":" + str(label))
    print(JSON.stringify({"ok": failures.is_empty(), "checks": count, "failures": failures, "cases": results}))
    quit(0 if failures.is_empty() else 1)
