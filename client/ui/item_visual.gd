extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")

## Configured quality backing, fill, icon and frame for every inventory item.
static func item(parent: Node, item: Dictionary, minimum: Vector2 = Vector2(140, 140), show_quantity: bool = true) -> Control:
	var root := Control.new()
	root.custom_minimum_size = minimum
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(root)

	var common := Panel.new()
	common.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	common.add_theme_stylebox_override("panel", Art.style(Art.item_background_key(item)))
	common.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(common)

	var quality_background := ColorRect.new()
	quality_background.name = "QualityBackground"
	quality_background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	# The frame art has a 12 px rim in a 192 px source. Scale the fill inset
	# with the cell so compact and full-size common slots have no empty band.
	var fill_inset := minf(minimum.x, minimum.y) * Art.QUALITY_FILL_INSET_RATIO
	quality_background.offset_left = fill_inset
	quality_background.offset_top = fill_inset
	quality_background.offset_right = -fill_inset
	quality_background.offset_bottom = -fill_inset
	quality_background.color = Art.quality_color(Art.item_quality_name(item)).darkened(0.48)
	quality_background.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(quality_background)

	var icon := TextureRect.new()
	icon.name = "EquipmentIcon" if str(item.get("kind", "")) == "Equipment" or item.has("slot") else "ItemIcon"
	icon.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	icon.offset_left = 18
	icon.offset_top = 18
	icon.offset_right = -18
	icon.offset_bottom = -18
	icon.texture = Art.item_texture(item)
	icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	icon.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(icon)

	var quality_frame := TextureRect.new()
	quality_frame.name = "QualityFrame"
	quality_frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	quality_frame.texture = Art.texture(Art.item_frame_key(item))
	quality_frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	quality_frame.stretch_mode = TextureRect.STRETCH_SCALE
	quality_frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	root.add_child(quality_frame)

	var quantity := int(item.get("quantity", item.get("Quantity", 1)))
	if show_quantity and quantity > 0:
		var quantity_label := Label.new()
		quantity_label.name = "Quantity"
		quantity_label.text = "×%s" % quantity
		quantity_label.position = Vector2(maxf(4.0, minimum.x - 56.0), maxf(4.0, minimum.y - 31.0))
		quantity_label.size = Vector2(minimum.x - quantity_label.position.x - 5.0, 25)
		quantity_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
		quantity_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		quantity_label.add_theme_font_override("font", P.font_for_text(quantity_label.text, 20))
		quantity_label.add_theme_font_size_override("font_size", 20)
		quantity_label.add_theme_color_override("font_color", P.GOLD)
		quantity_label.add_theme_color_override("font_outline_color", Color("10191b"))
		quantity_label.add_theme_constant_override("outline_size", 5)
		quantity_label.mouse_filter = Control.MOUSE_FILTER_IGNORE
		root.add_child(quantity_label)
	return root

static func equipment(parent: Node, value: Dictionary, minimum: Vector2 = Vector2(140, 140)) -> Control:
	return item(parent, value, minimum)

