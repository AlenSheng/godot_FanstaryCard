extends SceneTree
func _initialize() -> void:
    call_deferred("run")
func run() -> void:
    var result: Dictionary = load("res://tests/test_inventory_discard_protocol.gd").new().run_test()
    var file := FileAccess.open("res://native-result.json",FileAccess.WRITE)
    file.store_string(JSON.stringify(result));file.close()
    print(JSON.stringify(result))
    quit(0 if result.ok else 1)
