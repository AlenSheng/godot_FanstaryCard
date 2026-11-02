extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var results := {}
    var failures: Array[String] = []
    var count := 0
    for name in ["test_combat_action_ids.gd", "test_terminal_command_context.gd", "test_play_retry.gd", "test_room_store.gd", "test_rejected_command_state.gd"]:
        var instance = load("res://tests/" + name).new()
        var result: Dictionary = await instance.run_test()
        results[name] = result
        var checks: Dictionary = result.get("checks", result)
        for label in checks:
            if checks[label] is bool:
                count += 1
                if not checks[label]: failures.append(name + ":" + str(label))
        if result.has("ok") and not result.ok: failures.append(name + ":suite")
    print(JSON.stringify({"ok": failures.is_empty(), "checks": count, "failures": failures, "cases": results}))
    quit(0 if failures.is_empty() else 1)
