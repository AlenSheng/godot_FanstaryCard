extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var results := {}
    var failures: Array[String] = []
    var total := 0
    for name in ["test_config_archives.gd", "test_combat_preview_state.gd", "test_combat_action_ids.gd", "test_terminal_command_context.gd", "test_play_retry.gd", "test_room_store.gd", "test_rejected_command_state.gd", "test_gateway_bootstrap_context.gd"]:
        print("CASE_START "+name)
        var script = load("res://tests/" + name)
        if script == null or not script.can_instantiate():
            failures.append(name+":parse")
            continue
        var instance = script.new()
        if not instance.has_method("run_test"):
            failures.append(name+":entrypoint")
            continue
        var result: Dictionary = await instance.run_test()
        print("CASE_DONE "+name)
        results[name] = result
        var file := FileAccess.open("res://case-results.json",FileAccess.WRITE)
        file.store_string(JSON.stringify(results))
        file.close()
        var checks: Dictionary = result.get("checks", result)
        for label in checks:
            if checks[label] is bool:
                total += 1
                if not checks[label]: failures.append(name+":"+str(label))
        if result.has("ok") and not result.ok: failures.append(name+":suite")
    print(JSON.stringify({"ok":failures.is_empty(),"checks":total,"failures":failures,"cases":results}))
    quit(0 if failures.is_empty() else 1)
