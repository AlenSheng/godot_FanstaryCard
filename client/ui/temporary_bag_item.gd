extends Control

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const Details = preload("res://ui/equipment_details.gd")
const ItemVisual = preload("res://ui/item_visual.gd")

var item_id := ""
var item: Dictionary = {}

func configure(value: Dictionary) -> void:
	item = value.duplicate(true)
	item_id = str(item.get("item_id", ""))
	custom_minimum_size = Vector2(137, 83)
	size = custom_minimum_size
	mouse_default_cursor_shape = Control.CURSOR_DRAG
	tooltip_text = P.localized_text(Details.description(item))

	var visual := ItemVisual.item(self, item, Vector2(76, 76), false)
	visual.position = Vector2(2, 3)
	visual.size = Vector2(76, 76)

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
	preview.add_theme_stylebox_override("panel", StyleBoxEmpty.new())
	preview.modulate = Color(1.0, 1.0, 1.0, 0.88)
	var visual := ItemVisual.item(preview, item, Vector2(76, 76), false)
	visual.position = Vector2(2, 3)
	visual.size = Vector2(76, 76)
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
