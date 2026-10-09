extends SceneTree

func _initialize() -> void:
	var script: Script = load("res://tests/gameplay_load_client.gd")
	if script == null or not script.can_instantiate():
		printerr("Gameplay load client failed to parse")
		quit(1)
		return
	var probe: Node = script.new()
	for value in ["", "240", "600", "601", "1200"]:
		if probe._cycle_limit(value) != (240 if value.is_empty() else int(value)):
			printerr("Gameplay cycle observation limit differs from declared budget")
			probe.free()
			quit(1)
			return
	for value in ["59", "1201", "-1", "NaN", "invalid"]:
		if probe._cycle_limit(value) != 0:
			printerr("Invalid gameplay cycle observation limit was accepted")
			probe.free()
			quit(1)
			return
	probe.free()
	var transport: Script = load("res://network/reusable_http_client.gd")
	if transport == null or not transport.can_instantiate():
		printerr("Reusable HTTP transport failed to parse")
		quit(1)
		return
	print("Gameplay load client parses")
	quit(0)
