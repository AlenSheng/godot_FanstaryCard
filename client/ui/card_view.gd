extends Button

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const CardDetails = preload("res://ui/card_details.gd")
const ElementRules = preload("res://state/element_rules.gd")
const CARD_SHADER = preload("res://ui/card_view.gdshader")
const DESCRIPTIONS = preload("res://data/card_descriptions.json")
const CLASS_NAMES := {"Priest": "牧师", "Mage": "法师", "Guardian": "守护者"}
static var _materials: Dictionary = {}

static func clear_material_cache() -> void:
	_materials.clear()

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
		backdrop.position = Vector2(14, 14)
		backdrop.size = Vector2(190, 285)
		backdrop.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	var illustration := Art.image(self, Art.card(id), Vector2.ZERO)
	illustration.name = "Illustration"
	illustration.position = Vector2(14, 14)
	illustration.size = Vector2(190, 285)
	if illustration.texture == null:
		_text("插画待补", Rect2(14, 112, 190, 60), 22, P.MUTED)
	if selected and options.get("selected_overlay", false):
		var selected_overlay := ColorRect.new()
		selected_overlay.name = "SelectedIllustrationOverlay"
		selected_overlay.color = Color(0.16, 0.18, 0.19, 0.62)
		selected_overlay.position = illustration.position
		selected_overlay.size = illustration.size
		selected_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
		selected_overlay.material = CanvasItemMaterial.new()
		add_child(selected_overlay)
	var quality: String = str(info.get("quality", "White")).to_lower()
	var frame_key := "UI/Cards/card_frame_monster_clean.png" if monster else "UI/Codex/qframe_%s.png" % quality
	var frame := Art.image(self, Art.texture(frame_key), Vector2.ZERO)
	frame.name = "CardFrame"
	frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	frame.stretch_mode = TextureRect.STRETCH_SCALE
	if monster: frame.material = _monster_frame_material()
	if not monster:
		if frame.texture == null: frame.texture = Art.texture("UI/Codex/qframe_common.png")
		if selected: frame.texture = Art.texture("UI/Codex/qframe_selected.png")
		frame.material = _card_material(unowned, true)
	var lines := description.split("\n\n", true, 1)
	var passed_effect: String = lines[1] if lines.size() > 1 else description
	# Build compact summaries from the catalog's effects and level growth so
	# upgraded cards cannot reuse the base-level numbers from the text table.
	var effect := _face_description(id, passed_effect) if monster else CardDetails.face_description(id, int(options.get("level", 0)), info)
	if effect.is_empty(): effect = _face_description(id, passed_effect)
	if monster:
		_monster_text(id, info, effect, selected, int(options.get("level", 0)))
	else:
		var level := int(options.get("level", 0))
		# card_view.gdshader moves the frame's text panel below the portrait:
		# its usable interior is y=303..357, not the source texture's y=256..348.
		var title := _text(CardDetails.localized_name(id, info), Rect2(24, 304, 170, 26), 18, P.GOLD, false)
		title.add_theme_font_override("font", P.font("title"))
		title.name = "CardName"
		title.max_lines_visible = 1
		title.autowrap_mode = TextServer.AUTOWRAP_OFF
		title.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		_fit_card_effect_font(title, 18)
		var effect_label := _text(effect.replace("\n", " "), Rect2(24, 331, 170, 24), 16, P.PAPER, false)
		effect_label.name = "CardEffect"
		effect_label.max_lines_visible = 1
		effect_label.autowrap_mode = TextServer.AUTOWRAP_OFF
		effect_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		_fit_card_effect_font(effect_label, 16)
		var hero_class: String = P.word(info.get("hero_class", ""))
		if not hero_class.is_empty(): _class_badge(str(info.get("hero_class")), hero_class)
		var battle_element_hint := _battle_element_hint(str(info.get("element", "None")), str(options.get("battle_target_element", "None")))
		if not battle_element_hint.is_empty(): _battle_element_badge(battle_element_hint)
		elif level > 0: _level_badge(level)
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
	var key := ("gray" if grayscale else "color") + ("_frame" if reframe else "_body")
	if not _materials.has(key):
		var result := ShaderMaterial.new()
		result.shader = CARD_SHADER
		result.set_shader_parameter("grayscale", grayscale)
		result.set_shader_parameter("reframe", reframe)
		_materials[key] = result
	return _materials[key]

func _monster_frame_material() -> ShaderMaterial:
	if not _materials.has("monster_frame"):
		var result := ShaderMaterial.new()
		result.shader = CARD_SHADER
		result.set_shader_parameter("monster_reframe", true)
		_materials["monster_frame"] = result
	return _materials["monster_frame"]

func _level_badge(level: int) -> void:
	var badge := Art.image(self, Art.texture("UI/Codex/mana_cost_badge.png"), Vector2.ZERO)
	badge.name = "CardLevelBadge"
	badge.position = Vector2(2, 3)
	badge.size = Vector2(37, 37)
	var value := _text(str(level), Rect2(4, 5, 33, 33), 20, P.PAPER)
	value.name = "CardLevel"

func _battle_element_hint(card_element: String, target_element: String) -> String:
	if card_element not in ["Fire", "Wood", "Water", "Metal", "Earth"]: return ""
	if target_element not in ["Fire", "Wood", "Water", "Metal", "Earth"]: return ""
	if ElementRules.counters(card_element, target_element): return "recommended"
	if ElementRules.counters(target_element, card_element): return "countered"
	return ""

func _battle_element_badge(kind: String) -> void:
	var badge := Panel.new()
	badge.name = "BattleElementHintBadge"
	badge.position = Vector2(2, 3)
	badge.size = Vector2(37, 37)
	badge.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var style := StyleBoxFlat.new()
	style.bg_color = Color("287db6") if kind == "recommended" else Color("a9433d")
	style.border_color = Color("8ed7f0") if kind == "recommended" else Color("f0aaa0")
	style.set_border_width_all(2)
	style.set_corner_radius_all(18)
	badge.add_theme_stylebox_override("panel", style)
	add_child(badge)
	var badge_key := "battle_card_recommended_badge" if kind == "recommended" else "battle_card_countered_badge"
	var tooltip_key := "battle_card_recommended_tooltip" if kind == "recommended" else "battle_card_countered_tooltip"
	var label := _text(P.localized(badge_key), Rect2(2, 2, 33, 33), 17, P.PAPER)
	label.name = "BattleElementHintText"
	badge.tooltip_text = P.localized(tooltip_key)

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

func _monster_text(id: String, info: Dictionary, effect: String, selected: bool, level: int = 0) -> void:
	var banner := ColorRect.new()
	banner.color = Color(0.03, 0.06, 0.08, 0.88)
	banner.position = Vector2(17, 28)
	banner.size = Vector2(184, 34)
	banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(banner)
	var title_text := P.localized("monster") + " " + CardDetails.localized_name(id, info)
	var title := _text(title_text, Rect2(19, 28, 180, 34), 21, P.PAPER)
	title.name = "MonsterName"
	title.add_theme_font_override("font", P.font("title"))
	_text(effect, Rect2(21, 304, 176, 38), 17, P.PAPER)
	if id == "M-BOXSPIRIT":
		var element: String = info.get("element", "None")
		_text(P.word(element), Rect2(135, 258, 61, 35), 23, P.ELEMENT.get(element, Color.WHITE)).name = "MonsterElement"
	_text("已选 · 本局怪物卡" if selected else "本局怪物卡", Rect2(24, 344, 170, 19), 13, P.GOLD if selected else Color("d3b6ab")).name = "MonsterFooter"

func _fit_card_effect_font(label: Label, requested_size: int) -> void:
	var typeface: Font = P.font_for_text(label.text, requested_size)
	var fitted_size: int = requested_size
	while fitted_size > 12:
		var text_size := typeface.get_string_size(label.text, HORIZONTAL_ALIGNMENT_CENTER, -1.0, fitted_size)
		if text_size.x <= label.size.x and typeface.get_height(fitted_size) <= label.size.y:
			break
		fitted_size -= 1
	label.add_theme_font_size_override("font_size", fitted_size)

func _text(value: String, rect: Rect2, font_size: int, color: Color, fit_to_rect: bool = true) -> Label:
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
	label.add_theme_font_size_override("font_size", P.fit_font_size(typeface, font_size, rect.size.y, rect.size.x - 8.0, display_text) if fit_to_rect else font_size)
	label.add_theme_color_override("font_color", color)
	add_child(label)
	label.position = rect.position
	label.size = rect.size
	if fit_to_rect: P.fit_control_font(label, typeface, font_size, 8.0)
	return label
