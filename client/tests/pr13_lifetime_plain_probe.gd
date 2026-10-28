extends Node

func _ready() -> void:
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.socket.close()
	await get_tree().process_frame
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().process_frame
	print("PR13_LIFETIME_PLAIN_PROBE_COMPLETED")
	get_tree().quit()
