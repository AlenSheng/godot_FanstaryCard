extends "res://tests/pr13_dual_pool_boundaries_render.gd"

func _run() -> void:
	output = OS.get_environment("PR13_DUAL_RENDER_OUTPUT")
	assert(not output.is_empty())
	DirAccess.make_dir_recursive_absolute(output)
	var rows: Array = []
	var file := FileAccess.open(OS.get_environment("PR13_DUAL_RENDER_VECTORS"), FileAccess.READ)
	assert(file != null)
	while not file.eof_reached():
		var line := file.get_line()
		if line.is_empty(): continue
		var row: Dictionary = JSON.parse_string(line)
		assert(str(row.source) == "2a1d7e649f61aa1dc04bf50899f7cc32bb553d26")
		rows.append(row)
	file.close()
	var matches := rows.filter(func(row): return int(row.seed) == 484001 and int(row.capacity) == 3 and str(row.operation) == "pvp-state")
	assert(matches.size() == 1)
	Game.set_process(false)
	$UI.set_process(false)
	var old_gateway: Node = Game.gateway
	old_gateway.set_process(false)
	old_gateway.socket.close()
	var gateway := NaturalGateway.new()
	gateway.persist_session = false
	Game.gateway = gateway
	gateway.event_received.connect(Game._on_event)
	get_window().mode = Window.MODE_WINDOWED
	for locale in ["en", "zh-CN"]:
		P.set_language(locale)
		for size in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = size
			await get_tree().process_frame
			await get_tree().process_frame
			var boundary: Dictionary = await boundary_witness(matches[0], observations.size(), locale, size)
			var title: Label = null
			for label in $UI._reference.find_children("*", "Label", true, false):
				if label.text == P.localized("current_cell_action"): title = label
			assert(title != null)
			var font: Font = title.get_theme_font("font")
			var font_size: int = title.get_theme_font_size("font_size")
			var glyph_width: float = font.get_string_size(title.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, font_size).x
			var reference: Control = $UI._reference
			var titles: Array = []
			for words in ["遭遇战", "混沌战斗", "混沌领域", "当前格行动", "战利品三选一"]:
				preload("res://ui/exploration_view.gd")._title(reference, words)
				var extra: Label = reference.get_child(reference.get_child_count() - 1) as Label
				assert(extra != null)
				var glyphs: float = extra.get_theme_font("font").get_string_size(extra.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, extra.get_theme_font_size("font_size")).x
				titles.append({"text": extra.text, "glyph_width": glyphs, "font_size": extra.get_theme_font_size("font_size"), "label_rect": [extra.position.x, extra.position.y, extra.size.x, extra.size.y], "fits": glyphs <= 336.0 and extra.position == Vector2(116, 37) and extra.size == Vector2(344, 73)})
				var plate: Node = reference.get_child(reference.get_child_count() - 2)
				extra.free()
				plate.free()
			observations.append({"all_five_title_variants_fit": titles.all(func(row): return row.fits), "title_variants": titles, "boundary_passed": boundary.passed, "locale": locale, "resolution": [size.x, size.y], "title_text": title.text, "title_size": [title.size.x, title.size.y], "font_size": font_size, "actual_font_glyph_width": glyph_width, "fits_authored_title_width": glyph_width <= 336.0, "original_screenshot_names": boundary.screenshots})
	Game.gateway = old_gateway
	gateway.event_received.disconnect(Game._on_event)
	gateway.free()
	FileAccess.open(output + "/native-result.json", FileAccess.WRITE).store_string(JSON.stringify({"ok": observations.size() == 6 and observations.all(func(row): return row.boundary_passed and row.all_five_title_variants_fit and row.fits_authored_title_width and row.title_size == [344.0, 73.0]), "observations": observations, "diagnostic_only": false, "header_acceptance_claimed": true, "source_sha": OS.get_environment("PR13_DUAL_RENDER_SOURCE")}))
	Sound.set_process(false)
	Sound.stop_all()
	Sound.stop_music()
	$UI.queue_free()
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	await get_tree().create_timer(.25).timeout
	get_tree().quit()
