extends "res://tests/pr13_element_marginal_render.gd"

func _run() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.socket.close()
	var mode := "empty"
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--probe-mode="): mode = argument.trim_prefix("--probe-mode=")
	var original: Node = Game.gateway
	var gateway: Node = null
	if mode != "empty":
		gateway = CodecGateway.new()
		gateway.persist_session = false
		Game.gateway = gateway
	if mode == "reset":
		reset_cards([], "Mage", 70, 35)
	elif mode in ["state", "variant"]:
		var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(ELEMENT_NATIVE_VECTORS))
		var vector: Dictionary = data.rows[0]
		if mode == "state": await observe_marginal(vector, vector.arms[1].events[0].after_state_sha256, "lifetime-isolation")
		else: await run_marginal_vector(vector)
	Game.gateway = original
	if gateway != null: gateway.free()
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().process_frame
	print("PR13_LIFETIME_INHERITED_PROBE_COMPLETED mode=" + mode)
	get_tree().quit()
