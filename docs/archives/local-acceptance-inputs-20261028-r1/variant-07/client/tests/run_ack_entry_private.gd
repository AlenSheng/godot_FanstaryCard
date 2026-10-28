extends SceneTree
func _initialize() -> void:call_deferred("_run")
func _run() -> void:
 var result:Dictionary=await load("res://tests/test_ack_entry_observation.gd").new().run_test()
 FileAccess.open(OS.get_environment("PR13_GAP_RESULT"),FileAccess.WRITE).store_string(JSON.stringify(result))
 print(JSON.stringify(result))
 quit(0 if result.ok else 1)
