extends Control

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const Details = preload("res://ui/equipment_details.gd")

var item_id := ""
var item: Dictionary = {}

func configure(value: Dictionary, icon: Texture2D) -> void:
	item = value.duplicate(true)
	item_id = str(item.get("item_id", ""))
	custom_minimum_size = Vector2(137, 83)
	size = custom_minimum_size
	mouse_default_cursor_shape = Control.CURSOR_DRAG
	tooltip_text = P.localized_text(Details.description(item))

	var frame := Panel.new()
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	frame.add_theme_stylebox_override("panel", Art.style(Art.COMMON_CELL_KEY))
	add_child(frame)

	if icon != null:
		var image := TextureRect.new()
		image.texture = icon
		image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		image.position = Vector2(7, 8)
		image.size = Vector2(64, 60)
		image.mouse_filter = Control.MOUSE_FILTER_IGNORE
		add_child(image)

	var quantity := Label.new()
	quantity.text = "×%s" % item.get("quantity", 0)
	quantity.position = Vector2(75, 27)
	quantity.size = Vector2(59, 37)
	quantity.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
	quantity.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	quantity.clip_text = true
	quantity.mouse_filter = Control.MOUSE_FILTER_IGNORE
	quantity.add_theme_font_override("font", P.font_for_text(quantity.text, 23))
	quantity.add_theme_font_size_override("font_size", 23)
	quantity.add_theme_color_override("font_color", P.GOLD if item.get("is_safe", false) else P.PAPER)
	add_child(quantity)

func _get_drag_data(_position: Vector2) -> Variant:
	if item_id.is_empty(): return null
	set_drag_preview(_make_drag_preview())
	# This payload is intentionally not an inventory slot payload. The compact
	# backpack is a preview/scroll surface; safe-slot exchanges are only handled
	# by the full inventory dialog.
	return {"temporary_item_id": item_id, "room_id": Game.room.get("room_id", "")}

func _can_drop_data(_position: Vector2, _data: Variant) -> bool:
	return false

func _make_drag_preview() -> Control:
	var preview := Panel.new()
	preview.custom_minimum_size = Vector2(137, 83)
	preview.size = preview.custom_minimum_size
	preview.add_theme_stylebox_override("panel", Art.style(Art.COMMON_CELL_KEY))
	preview.modulate = Color(1.0, 1.0, 1.0, 0.88)
	if item.get("kind", "") != "":
		var icon := Art.item_texture(item)
		if icon != null:
			var image := TextureRect.new()
			image.texture = icon
			image.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
			image.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			image.position = Vector2(7, 8)
			image.size = Vector2(64, 60)
			image.mouse_filter = Control.MOUSE_FILTER_IGNORE
			preview.add_child(image)
	var quantity := Label.new()
	quantity.text = "×%s" % item.get("quantity", 0)
	quantity.position = Vector2(75, 27)
	quantity.size = Vector2(59, 37)
	quantity.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	quantity.add_theme_font_override("font", P.font_for_text(quantity.text, 23))
	quantity.add_theme_font_size_override("font_size", 23)
	quantity.add_theme_color_override("font_color", P.GOLD if item.get("is_safe", false) else P.PAPER)
	preview.add_child(quantity)
	return preview
