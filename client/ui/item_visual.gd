extends RefCounted

const Art = preload("res://ui/art.gd")

## Builds a reusable layered equipment visual:
## common cell -> quality background -> equipment icon -> quality frame.
## Text, level and state badges deliberately remain outside the bitmap layers.
static func equipment(parent: Node, item: Dictionary, minimum: Vector2 = Vector2(140, 140)) -> Control:
	var gear: Dictionary = item.get("equipment", item) if item.get("equipment", item) is Dictionary else item
	var quality := str(gear.get("quality", "White")).capitalize()
	var root := Control.new()
	root.custom_minimum_size = minimum
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(root)

	var common := Panel.new()
	common.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	common.add_theme_stylebox_override("panel", Art.cell_style(Color("58646b")))
	common.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(common)

	var quality_background := ColorRect.new()
	quality_background.name = "QualityBackground"
	quality_background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	quality_background.offset_left = 13
	quality_background.offset_top = 13
	quality_background.offset_right = -13
	quality_background.offset_bottom = -13
	quality_background.color = Art.quality_color(quality).darkened(0.48)
	quality_background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(quality_background)

	var icon := TextureRect.new()
	icon.name = "EquipmentIcon"
	icon.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	icon.offset_left = 18
	icon.offset_top = 18
	icon.offset_right = -18
	icon.offset_bottom = -18
	icon.texture = Art.equipment_texture(item)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(icon)

	var quality_frame := TextureRect.new()
	quality_frame.name = "QualityFrame"
	quality_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	quality_frame.texture = Art.texture("UI/Prep/exploration_prep_equipment_slot_frame_%s.png" % quality.to_lower())
	quality_frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	quality_frame.stretch_mode = TextureRect.STRETCH_SCALE
	quality_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(quality_frame)
	return root

