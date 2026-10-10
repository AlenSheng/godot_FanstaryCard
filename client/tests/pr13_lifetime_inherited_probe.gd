extends "res://tests/pr13_element_marginal_render.gd"

func _run() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.socket.close()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().process_frame
	print("PR13_LIFETIME_INHERITED_PROBE_COMPLETED")
	get_tree().quit()
