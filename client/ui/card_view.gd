extends Button

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const CARD_SHADER = preload("res://ui/card_view.gdshader")
const DESCRIPTIONS = preload("res://data/card_descriptions.json")
const CLASS_NAMES := {"Priest": "牧师", "Mage": "法师", "Guardian": "守护者"}

func configure(id: String, info: Dictionary, description: String, selected: bool, options: Dictionary = {}) -> void:
	for child in get_children(): child.free()
	custom_minimum_size = Vector2(218, 376)
	clip_contents = true
	tooltip_text = P.localized_text(description)
	mouse_default_cursor_shape = Control.CURSOR_ARROW if disabled else Control.CURSOR_POINTING_HAND
	var monster: bool = info.get("source", "") == "Monster"
	var collection: bool = options.get("collection", false) and not options.get("preview", false) and not monster
	var copy_count: int = maxi(0, int(options.get("copy_count", 0)))
	var unowned: bool = collection and copy_count == 0
	material = _card_material(unowned) if unowned else null
	for state in ["normal", "disabled", "hover", "pressed"]:
		add_theme_stylebox_override(state, StyleBoxEmpty.new())
	add_theme_stylebox_override("focus", P.box(Color.TRANSPARENT, P.GOLD, 2))
	if monster:
		var backdrop := Art.image(self, Art.texture("Cards/Art/monster_card_backdrop.png"), Vector2.ZERO)
		backdrop.name = "MonsterBackdrop"
		backdrop.position = Vector2(14, 58)
		backdrop.size = Vector2(190, 177)
		backdrop.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	var illustration := Art.image(self, Art.card(id), Vector2.ZERO)
	illustration.name = "Illustration"
	illustration.position = Vector2(14, 58) if monster else Vector2(14, 14)
	illustration.size = Vector2(190, 177) if monster else Vector2(190, 285)
	if illustration.texture == null:
		_text("插画待补", Rect2(14, 112, 190, 60), 22, P.MUTED)
	var quality: String = str(info.get("quality", "White")).to_lower()
	var frame_key := "UI/Cards/card_frame_monster_clean.png" if monster else "UI/Codex/qframe_%s.png" % quality
	var frame := Art.image(self, Art.texture(frame_key), Vector2.ZERO)
	frame.name = "CardFrame"
	frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	frame.stretch_mode = TextureRect.STRETCH_SCALE
	if not monster:
		if frame.texture == null: frame.texture = Art.texture("UI/Codex/qframe_common.png")
		if selected: frame.texture = Art.texture("UI/Codex/qframe_selected.png")
		frame.material = _card_material(unowned, true)
	var lines := description.split("\n\n", true, 1)
	var passed_effect: String = lines[1] if lines.size() > 1 else description
	# The card face is configuration-owned. Do not trust a caller-provided summary:
	# older call sites used generated strings such as `火 8.0`, which caused the
	# collection to keep showing stale text even after the table was updated.
	var effect := _face_description(id, passed_effect)
	if monster:
		_monster_text(id, info, effect, selected)
	else:
		# Keep the codex/deck card name at the established bottom-panel position.
		# The two-line effect area grows below it without moving the name.
		var title := _text(str(info.get("name", id)), Rect2(24, 294, 170, 35), 20, P.GOLD)
		title.add_theme_font_override("font", P.font("title"))
		title.name = "CardName"
		var effect_label := _wrapped_text(effect, Rect2(24, 330, 170, 46), 14, P.PAPER)
		effect_label.name = "CardEffect"
		var hero_class: String = P.word(info.get("hero_class", ""))
		if not hero_class.is_empty(): _class_badge(str(info.get("hero_class")), hero_class)
		if collection: _copy_badge(copy_count)
		if int(options.get("level", 0)) > 0:
			_text("+%s" % options.level, Rect2(150, 50, 49, 34), 21, P.GOLD).name = "CardLevel"
		if selected:
			var selection := _text("已选", Rect2(75, 260, 68, 33), 18, P.GOLD)
			selection.name = "SelectedIndicator"
			var selection_style := P.box(Color("172d35"), P.GOLD, 1)
			for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]: selection_style.set_content_margin(side, 0)
			selection.add_theme_stylebox_override("normal", selection_style)
	for child in get_children():
		if child is CanvasItem and child.material == null: child.use_parent_material = true

func _face_description(id: String, fallback: String) -> String:
	var locale := P.language()
	var tables: Dictionary = DESCRIPTIONS.data
	var descriptions: Dictionary = tables.get(locale, tables.get("zh", {}))
	var configured := str(descriptions.get("card.face.desc." + id, "")).strip_edges()
	return configured if not configured.is_empty() else fallback

func _card_material(grayscale: bool, reframe: bool = false) -> ShaderMaterial:
	var result := ShaderMaterial.new()
	result.shader = CARD_SHADER
	result.set_shader_parameter("grayscale", grayscale)
	result.set_shader_parameter("reframe", reframe)
	return result

func _copy_badge(copy_count: int) -> void:
	var badge := Art.image(self, Art.texture("UI/Codex/mana_cost_badge.png"), Vector2.ZERO)
	badge.name = "CopyBadge"
	badge.position = Vector2(2, 3)
	badge.size = Vector2(37, 37)
	var count := _text(str(copy_count), Rect2(4, 5, 33, 33), 20 if copy_count < 100 else 15, P.PAPER)
	count.name = "CopyCount"

func _class_badge(hero_class: String, symbol: String) -> void:
	# The pad sits below the sprite so its 28x28 rectangle cannot cover the
	# decorative ring; the ring's opaque pixels mask the pad at the edges.
	var center_back := ColorRect.new()
	center_back.name = "ClassBadgeCenter"
	center_back.color = Color("080b0c")
	center_back.position = Vector2(171, 10)
	center_back.size = Vector2(28, 28)
	center_back.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(center_back)
	var badge := Art.image(self, Art.texture("UI/Codex/class_badge_%s.png" % hero_class.to_lower()), Vector2.ZERO)
	badge.name = "ClassBadge"
	badge.position = Vector2(156, -5)
	badge.size = Vector2(58, 58)
	badge.tooltip_text = P.localized_text("仅限%s职业编组" % P.localized_text(CLASS_NAMES.get(hero_class, symbol)))
	badge.mouse_filter = Control.MOUSE_FILTER_PASS
	var label := _text(symbol, Rect2(168, 7, 34, 34), 22, P.PAPER)
	label.name = "ClassSymbol"
	tooltip_text += "\n\n" + badge.tooltip_text

func _monster_text(id: String, info: Dictionary, effect: String, selected: bool) -> void:
	var banner := ColorRect.new()
	banner.color = Color(0.03, 0.06, 0.08, 0.88)
	banner.position = Vector2(17, 28)
	banner.size = Vector2(184, 34)
	banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(banner)
	var title := _text("怪 " + str(info.get("name", id)), Rect2(19, 28, 180, 34), 21, P.PAPER)
	title.name = "MonsterName"
	title.add_theme_font_override("font", P.font("title"))
	_text(effect, Rect2(21, 258, 176, 82), 17, P.PAPER)
	if id == "M-BOXSPIRIT":
		var element: String = info.get("element", "None")
		_text(P.word(element), Rect2(135, 216, 61, 35), 23, P.ELEMENT.get(element, Color.WHITE)).name = "MonsterElement"
	_text("已选 · 本局怪物卡" if selected else "本局怪物卡", Rect2(24, 345, 170, 27), 14, P.GOLD if selected else Color("d3b6ab")).name = "MonsterFooter"

func _text(value: String, rect: Rect2, font_size: int, color: Color) -> Label:
	var label := Label.new()
	var display_text := P.localized_text(value)
	label.text = display_text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	label.clip_text = true
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var typeface := P.font_for_text(display_text, font_size)
	label.add_theme_font_override("font", typeface)
	label.add_theme_font_size_override("font_size", P.fit_font_size(typeface, font_size, rect.size.y, rect.size.x - 8.0, display_text))
	label.add_theme_color_override("font_color", color)
	add_child(label)
	label.position = rect.position
	label.size = rect.size
	P.fit_control_font(label, typeface, font_size, 8.0)
	return label

func _wrapped_text(value: String, rect: Rect2, font_size: int, color: Color) -> Label:
	var label := Label.new()
	var display_text := P.localized_text(value)
	label.text = display_text
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	label.max_lines_visible = 2
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	label.clip_text = true
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var typeface := P.font_for_text(display_text, font_size)
	label.add_theme_font_override("font", typeface)
	label.add_theme_font_size_override("font_size", P.fit_font_size(typeface, font_size, rect.size.y / 2.0))
	label.add_theme_color_override("font_color", color)
	add_child(label)
	label.position = rect.position
	label.size = rect.size
	return label
