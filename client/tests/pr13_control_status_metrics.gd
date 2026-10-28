extends "res://tests/pr13_control_native_render.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(output)
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	Game.gateway = CodecGateway.new()
	Game.gateway.persist_session = false
	var data: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(NATIVE_VECTORS))
	var vector: Dictionary = data.vectors[0]
	var room := native_room(vector,vector.assertions[2].returned_room_state_sha256)
	get_window().mode = Window.MODE_WINDOWED
	Engine.max_fps = 60
	for language in ["zh-CN","en"]:
		P.set_language(language)
		for resolution in [Vector2i(1920,1080),Vector2i(1280,720),Vector2i(960,540)]:
			get_window().size = resolution
			await project_room(room,vector,"target-a")
			var actual: Array = []
			for elapsed in [0,2000,5000]:
				$UI._set_battle_status_label("PlayerStatus",1500,2500,elapsed,3500,4500)
				await get_tree().process_frame
				await RenderingServer.frame_post_draw
				var label: Label = $UI._reference.get_node("PlayerStatus")
				var font: Font = label.get_theme_font("font")
				var size: int = label.get_theme_font_size("font_size")
				actual.append({"elapsed_ms":elapsed,"text":label.text,"font_size":size,"font_height":font.get_height(size),"label_size":[label.size.x,label.size.y],"minimum_size":[label.get_minimum_size().x,label.get_minimum_size().y],"line_count":label.get_line_count(),"visible_line_count":label.get_visible_line_count(),"line_spacing":label.get_theme_constant("line_spacing"),"visible":label.is_visible_in_tree()})
				if language=="en" and resolution.x==960 and elapsed==0:
					assert(get_viewport().get_texture().get_image().save_png(output+"/DEV_status_metrics.png")==OK)
			observations.append({"language":language,"resolution":[resolution.x,resolution.y],"actual":actual,"passed":true,"scope":"Collected layout metrics only; not canonical acceptance."})
	var result := {"ok":observations.size()==6 and DisplayServer.get_name()!="headless","observations":observations,"display_driver":DisplayServer.get_name(),"adapter":RenderingServer.get_video_adapter_name(),"scope":"Diagnostic only; readable flags must be assessed separately."}
	FileAccess.open(output+"/native-result.json",FileAccess.WRITE).store_string(JSON.stringify(result))
	get_tree().quit(0 if result.ok else 1)
