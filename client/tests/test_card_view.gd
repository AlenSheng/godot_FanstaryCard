extends RefCounted

func run_test() -> Dictionary:
	var CardView = load("res://ui/card_view.gd")
	var Art = load("res://ui/art.gd")
	var card := Button.new()
	card.set_script(CardView)
	card.theme = load("res://ui/palette.gd").theme()
	(Engine.get_main_loop() as SceneTree).root.add_child(card)
	card.size = Vector2(218, 376)
	var info := {"name": "火球", "quality": "White", "hero_class": "Mage", "source": "Class"}
	card.configure("MAG-01", info, "法 火球\n白\n\n火系伤害8点", false, {"collection": true, "copy_count": 0})
	var errors: Array[String] = []
	if card.disabled or card.get_node("CopyCount").text != "0": errors.append("Unowned card must show zero and remain clickable")
	if card.material == null or not card.material.get_shader_parameter("grayscale"): errors.append("Unowned card must be grayscale")
	if not card.get_node("Illustration").use_parent_material or not card.get_node("CardFrame").material.get_shader_parameter("grayscale"):
		errors.append("Grayscale must cover both illustration and frame")
	if card.get_node("Illustration").size != Vector2(190, 285): errors.append("Codex portrait must retain a 2:3 rectangle")
	if card.get_node("CardName").position.y < 294 or card.get_node("CardEffect").text != "火系伤害8点": errors.append("Name and effect must use the bottom panel")
	_check_text(card, ["CardName", "CardEffect", "ClassSymbol", "CopyCount"], errors)
	if card.get_node("ClassSymbol").text != "法" or not "仅法师" in card.get_node("ClassBadge").tooltip_text: errors.append("Class badge must explain its restriction")
	if card.get_node("ClassBadge").mouse_filter != Control.MOUSE_FILTER_PASS: errors.append("Class badge must pass clicks to the card")
	card.configure("MAG-01", info, "火系伤害8点", false, {"collection": true, "copy_count": 0, "preview": true})
	if card.material != null or card.get_node_or_null("CopyCount") != null or card.get_node("CardFrame").material.get_shader_parameter("grayscale"):
		errors.append("Unowned detail preview must stay colored and omit the quantity badge")
	card.configure("MAG-01", info, "火系伤害8点", false, {"collection": true, "copy_count": 12})
	if card.material != null or card.get_node("CopyCount").text != "12": errors.append("Owned collection card must show its current quantity in color")
	card.configure("MAG-01", info, "火系伤害8点", true, {"collection": true, "copy_count": 123, "level": 5})
	_check_text(card, ["CardName", "CardEffect", "ClassSymbol", "CopyCount", "CardLevel", "SelectedIndicator"], errors)
	var title: Label = card.get_node("CardName")
	var effect: Label = card.get_node("CardEffect")
	if title.position.y + title.size.y > effect.position.y: errors.append("Card name must not overlap its effect line")
	if card.get_node("CardLevel").get_rect().intersects(card.get_node("ClassBadge").get_rect()): errors.append("Upgrade level must not overlap the class badge")
	info.hero_class = null
	card.configure("C01", info, "火系伤害8点", true)
	_check_text(card, ["CardName", "CardEffect", "SelectedIndicator"], errors)
	if card.get_node_or_null("ClassBadge") != null or card.get_node_or_null("CopyCount") != null: errors.append("Legacy common-card call must not gain class or quantity badges")
	if card.get_node("CardFrame").texture != Art.texture("UI/Codex/qframe_selected.png"): errors.append("Selected hand card must retain its selected frame")
	card.disabled = true
	card.configure("C01", info, "火系伤害8点", false)
	if not card.disabled: errors.append("Configuration must preserve the caller's disabled state")
	info.source = "Monster"
	card.configure("M-FIREBAT", info, "火系伤害8点", true)
	_check_text(card, ["MonsterName", "MonsterFooter"], errors)
	if card.get_node("CardFrame").texture != Art.texture("UI/Cards/card_frame_monster_clean.png") or card.get_node("CardFrame").material != null:
		errors.append("Monster cards must retain their dedicated frame and layout")
	var backdrop := card.get_node_or_null("MonsterBackdrop") as TextureRect
	if backdrop == null or backdrop.texture != Art.texture("Cards/Art/monster_card_backdrop.png"):
		errors.append("Monster drops must share the generated illustration backdrop")
	elif backdrop.get_index() >= card.get_node("Illustration").get_index() or backdrop.stretch_mode != TextureRect.STRETCH_KEEP_ASPECT_COVERED:
		errors.append("Monster backdrop must cover the art window behind the species cutout")
	card.configure("M-BOXSPIRIT", {"name": "匣灵", "source": "Monster", "element": "None"}, "直伤7点", true)
	_check_text(card, ["MonsterName", "MonsterFooter", "MonsterElement"], errors)
	card.free()
	_check_fixed_hud_text(errors)
	return {"ok": errors.is_empty(), "message": "Card behavior and visible bundled-font labels, counters, badges, footers and fixed HUD text" if errors.is_empty() else "; ".join(errors)}

func _check_text(card: Control, names: Array, errors: Array[String]) -> void:
	for node_name in names:
		var label := card.get_node_or_null(str(node_name)) as Label
		if label == null or label.text.is_empty():
			errors.append("Expected nonempty card label: " + str(node_name))
			continue
		_check_label(label, errors)
		if not Rect2(Vector2.ZERO, card.size).encloses(label.get_rect()): errors.append(str(node_name) + " must stay inside the card")
		var typeface := label.get_theme_font("font")
		var text_width := typeface.get_string_size(label.text, HORIZONTAL_ALIGNMENT_LEFT, -1, label.get_theme_font_size("font_size")).x
		if text_width > label.size.x: errors.append(str(node_name) + " must fit without horizontal clipping")

func _check_label(label: Label, errors: Array[String]) -> void:
	if label.get_visible_line_count() < 1: errors.append(str(label.name) + " has no visible line")
	if label.get_visible_line_count() != label.get_line_count(): errors.append(str(label.name) + " clips text lines")
	if label.size.y < label.get_line_height(): errors.append(str(label.name) + " is shorter than its bundled font line")

func _check_fixed_hud_text(errors: Array[String]) -> void:
	var reference = load("res://ui/reference_ui.gd").new()
	reference.theme = load("res://ui/palette.gd").theme()
	(Engine.get_main_loop() as SceneTree).root.add_child(reference)
	var title: Label = reference.text("潮听 · 临", Rect2(0, 0, 300, 48), 34)
	title.name = "PlayerName"
	var hp: Label = reference.text("48 / 70", Rect2(0, 50, 300, 40), 30)
	hp.name = "PlayerHP"
	var monster_hp: Label = reference.text("24 / 44", Rect2(0, 90, 300, 40), 30)
	monster_hp.name = "MonsterHP"
	for label in [title, hp, monster_hp]: _check_label(label, errors)
	if title.size.y > 48 or hp.size.y > 40 or monster_hp.size.y > 40: errors.append("Fitted HUD text must preserve its assigned height")
	reference.free()
