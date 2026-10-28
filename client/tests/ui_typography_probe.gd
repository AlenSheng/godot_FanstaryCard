extends Control

const P = preload("res://ui/palette.gd")
var observations: Array = []

func _ready() -> void:
	get_window().mode = Window.MODE_WINDOWED
	get_window().set_flag(Window.FLAG_NO_FOCUS, true)
	get_window().gui_embed_subwindows = true
	Game.set_process(false)
	Game.gateway.set_process(false)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	Sound.persist_settings = false
	Sound.stop_all()
	Sound.set_music_context("")
	Sound.stop_music()
	Sound._headless_runtime = true
	Sound.set_process(false)
	call_deferred("_run")

func _run() -> void:
	var output := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	assert(not output.is_empty())
	var width := OS.get_environment("FANTASYCARD_REVIEW_WIDTHS").to_int()
	get_window().size = Vector2i(width, width * 9 / 16)
	get_window().position = Vector2i.ZERO
	await get_tree().process_frame
	await get_tree().process_frame
	var background := ColorRect.new()
	background.color = Color("07191f")
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	var variants := ["baseline", "full_hint", "oversample_2", "msdf_96"]
	for index in variants.size():
		var variant: String = variants[index]
		var body := _candidate("body", variant)
		var title := _candidate("title", variant)
		var left := 40.0 + 475.0 * index
		_label(variant, body, 30, Vector2(left, 25), P.GOLD)
		_label("正文 / Body 24", body, 24, Vector2(left, 90))
		_label("装备属性 / Armor", body, 24, Vector2(left, 135))
		_label("80 / 70 · Shield +27%", body, 24, Vector2(left, 180))
		_label("碎片强化 / Enhance", title, 24, Vector2(left, 240), P.GOLD)
		_label("撤离 / Extract", body, 32, Vector2(left, 310))
		_label("魔法 / Magic", title, 32, Vector2(left, 375), P.GOLD)
		_label("遗境 / Relics", body, 48, Vector2(left, 460))
		_label("卡牌 / Cards", title, 48, Vector2(left, 550), P.GOLD)
		_label("Card transform 1.514", body, 22, Vector2(left, 665), P.MUTED)
		_label("火斩 / Fire Slash", title, 18, Vector2(left, 710), P.GOLD, 1.514)
		_label("火伤11 / Fire 11", body, 16, Vector2(left, 765), P.PAPER, 1.514)
		observations.append({"variant": variant, "body": _properties(body), "title": _properties(title)})
	await get_tree().process_frame
	await get_tree().process_frame
	await RenderingServer.frame_post_draw
	var error := get_viewport().get_texture().get_image().save_png(output.path_join("font-comparison_%s.png" % get_window().size.x))
	var result := {"ok": error == OK and DisplayServer.get_name() != "headless", "width": get_window().size.x,
		"font_candidates": observations, "actual_game_matches": 0, "whole_visual_acceptance": false}
	FileAccess.open(output.path_join("report.json"), FileAccess.WRITE).store_string(JSON.stringify(result, "  "))
	for child in get_children(): child.queue_free()
	P.clear_runtime_fonts()
	await get_tree().process_frame
	get_tree().call_deferred("quit", 0 if result.ok else 1)

func _candidate(role: String, variant: String) -> FontFile:
	var source: FontFile = P.font(role)
	if variant == "baseline": return source
	var font := FontFile.new()
	font.data = source.data
	font.allow_system_fallback = false
	font.antialiasing = TextServer.FONT_ANTIALIASING_GRAY
	font.hinting = TextServer.HINTING_NORMAL
	font.force_autohinter = true
	font.subpixel_positioning = TextServer.SUBPIXEL_POSITIONING_ONE_QUARTER
	if variant == "oversample_2":
		font.oversampling = 2.0
		font.generate_mipmaps = true
	if variant == "msdf_96":
		font.multichannel_signed_distance_field = true
		font.msdf_size = 96
		font.msdf_pixel_range = 8
	return font

func _properties(font: FontFile) -> Dictionary:
	return {"hinting": font.hinting, "autohinter": font.force_autohinter,
		"subpixel": font.subpixel_positioning, "oversampling": font.oversampling,
		"msdf": font.multichannel_signed_distance_field, "msdf_size": font.msdf_size}

func _label(value: String, font: Font, size: int, point: Vector2, color: Color = P.PAPER, scale_factor: float = 1.0) -> void:
	var label := Label.new()
	label.text = value
	label.add_theme_font_override("font", font)
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	label.position = point
	label.size = Vector2(440.0 / scale_factor, 80)
	label.scale = Vector2.ONE * scale_factor
	add_child(label)
