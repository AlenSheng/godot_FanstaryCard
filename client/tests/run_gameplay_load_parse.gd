extends SceneTree

func _initialize() -> void:
	var script: Script = load("res://tests/gameplay_load_client.gd")
	if script == null or not script.can_instantiate():
		printerr("Gameplay load client failed to parse")
		quit(1)
		return
	var transport: Script = load("res://network/reusable_http_client.gd")
	if transport == null or not transport.can_instantiate():
		printerr("Reusable HTTP transport failed to parse")
		quit(1)
		return
	print("Gameplay load client parses")
	quit(0)
