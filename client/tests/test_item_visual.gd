extends RefCounted

func run_test() -> Dictionary:
	var Art = load("res://ui/art.gd")
	var ItemVisual = load("res://ui/item_visual.gd")
	var TemporaryBagItem = load("res://ui/temporary_bag_item.gd")
	var gear := {"kind": "Equipment", "item_id": "gear-1", "quantity": 1, "equipment": {"quality": "Green", "element": "Wood", "slot": "Chest"}}
	var gold := {"kind": "Gold", "item_id": "gold", "quantity": 10}
	var catalog = load("res://data/catalog.json")
	var checks := {
		"reward equipment uses its actual quality and element": Art.item_texture(gear) == Art.texture("Equipment/Green/chest_wood.png"),
		"class soul lookup matches its own id": Art.item_texture({"kind": "ClassSoul", "item_id": "class_soul:Mage"}) == Art.texture("UI/Item/exploration_prep_item_icon_mage_soul.png"),
		"every configured quality has a background and frame": true,
		"every configured item has an icon and initial quality art": true,
	}
	for row in catalog.data.tables.Items:
		var configured := {"kind": row.kind, "item_id": row.id}
		checks["every configured item has an icon and initial quality art"] = checks["every configured item has an icon and initial quality art"] and Art.item_texture(configured) != null and Art.texture(Art.item_background_key(configured)) != null and Art.texture(Art.item_frame_key(configured)) != null
	for quality in ["White", "Green", "Blue", "Purple", "Orange", "Red"]:
		var value := {"quality": quality}
		checks["every configured quality has a background and frame"] = checks["every configured quality has a background and frame"] and Art.texture(Art.item_background_key(value)) != null and Art.texture(Art.item_frame_key(value)) != null
	var parent := Control.new()
	var visual: Control = ItemVisual.item(parent, gold, Vector2(96, 96))
	visual.size = Vector2(96, 96)
	checks["gold keeps a 96 square visual"] = visual.size == Vector2(96, 96) and visual.get_node("ItemIcon").texture == Art.item_texture(gold) and visual.get_node("QualityFrame").texture == Art.texture(Art.item_frame_key(gold))
	checks["quality fill reaches the inner edge at every common size"] = true
	for width in [68, 76, 96, 165]:
		var sized: Control = ItemVisual.item(parent, gold, Vector2(width, width), false)
		sized.size = Vector2(width, width)
		var fill: ColorRect = sized.get_node("QualityBackground")
		var expected: float = float(width) * float(Art.QUALITY_FILL_INSET_RATIO)
		checks["quality fill reaches the inner edge at every common size"] = checks["quality fill reaches the inner edge at every common size"] and is_equal_approx(fill.offset_left, expected) and is_equal_approx(fill.offset_top, expected) and is_equal_approx(fill.offset_right, -expected) and is_equal_approx(fill.offset_bottom, -expected)
	var compact: Control = TemporaryBagItem.new()
	compact.call("configure", gold)
	checks["compact gold art stays square within its row"] = compact.get_child(0).size == Vector2(76, 76) and compact.custom_minimum_size == Vector2(137, 83)
	parent.free()
	compact.free()
	return {"ok": not checks.values().has(false), "message": "Equipment icons, item quality art and backpack cell sizing", "checks": checks}
