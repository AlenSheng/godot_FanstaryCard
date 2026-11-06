extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var cases := {}
    var failures: Array[String] = []
    var count := 0
    for name in ["test_journey_reward_claims.gd"]:
        var script = load("res://tests/" + name)
        if script == null or not script.can_instantiate():
            failures.append(name + ":parse")
            continue
        var result: Dictionary = script.new().run_test()
        cases[name] = result
        for key in result.get("checks", {}):
            count += 1
            if not result.checks[key]: failures.append(name + ":" + key)
        if not result.get("ok", false): failures.append(name + ":suite")
    var result := {"ok": failures.is_empty(), "checks": count, "failures": failures, "cases": cases}
    var output := FileAccess.open("res://case-results.json", FileAccess.WRITE)
    output.store_string(JSON.stringify(result))
    output.close()
    print(JSON.stringify(result))
    quit(0 if failures.is_empty() else 1)
