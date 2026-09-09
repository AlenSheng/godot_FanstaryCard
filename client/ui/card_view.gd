extends Button

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")

func configure(id: String, info: Dictionary, description: String, selected: bool) -> void:
	custom_minimum_size = Vector2(218, 376)
	clip_contents = true
	tooltip_text = description
	var monster: bool = info.get("source", "") == "Monster"
	var quality: String = str(info.get("quality", "White")).to_lower()
	var outline: Color = Color("8a3039") if monster else P.QUALITY.get(info.get("quality", "White"), P.GOLD)
	add_theme_stylebox_override("normal", P.box(Color("111b20"), P.GOLD if selected else outline, 4))
	add_theme_stylebox_override("disabled", P.box(Color("111b20"), outline, 2))
	add_theme_stylebox_override("hover", P.box(Color("21363e"), P.GOLD, 4))
	add_theme_stylebox_override("pressed", P.box(Color("21363e"), P.TEAL, 4))
	var illustration := Art.image(self, Art.card(id), Vector2.ZERO)
	illustration.name = "Illustration"
	illustration.position = Vector2(14, 58) if monster else Vector2(14, 12)
	illustration.size = Vector2(190, 177) if monster else Vector2(190, 280)
	if illustration.texture == null:
		_text("插画待补", Rect2(14, 112, 190, 60), 22, P.MUTED)
	var frame_key := "UI/Cards/card_frame_monster_clean.png" if monster else "UI/Codex/qframe_%s.png" % quality
	var frame := Art.image(self, Art.texture(frame_key), Vector2.ZERO)
	frame.name = "CardFrame"
	frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	frame.stretch_mode = TextureRect.STRETCH_SCALE
	if selected and not monster: frame.texture = Art.texture("UI/Codex/qframe_selected.png")
	var banner := ColorRect.new()
	banner.color = Color(0.03, 0.06, 0.08, 0.88)
	banner.position = Vector2(17, 28)
	banner.size = Vector2(184, 34)
	banner.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(banner)
	var badge := "怪" if monster else P.word(info.get("hero_class", ""))
	_text((badge + " " + info.get("name", id)).strip_edges(), Rect2(19, 28, 180, 34), 21, P.PAPER)
	var lines := description.split("\n\n", true, 1)
	_text(lines[1] if lines.size() > 1 else description, Rect2(21, 258 if monster else 287, 176, 82 if monster else 62), 17, P.PAPER)
	var footer: String = ("已选 · 本局怪物卡" if selected else "本局怪物卡") if monster else P.word(info.get("quality", ""))
	_text(footer, Rect2(24, 351, 170, 20), 14, (P.GOLD if selected else Color("d3b6ab")) if monster else outline)
	if selected and not monster:
		_text("已选", Rect2(72, 250, 74, 30), 22, P.GOLD)
	# Disabled cards remain readable in the codex even when the deck is full.
	if disabled: illustration.modulate = Color(0.72, 0.72, 0.72)

func _text(value: String, rect: Rect2, font_size: int, color: Color) -> void:
	var label := Label.new()
	label.text = value
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_ARBITRARY
	label.clip_text = true
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	add_child(label)
	label.position = rect.position
	label.size = rect.size
