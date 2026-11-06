extends Button

const I18n = preload("res://ui/i18n.gd")


var item_id := ""
var slot_index := -1

func _get_drag_data(_position: Vector2) -> Variant:
	if item_id.is_empty() or not Game.allowed("inventory.move"): return null
	var preview := Label.new()
	preview.text = I18n.t(text)
	set_drag_preview(preview)
	return {"inventory_item_id": item_id, "room_id": Game.room.get("room_id", "")}

func _can_drop_data(_position: Vector2, data: Variant) -> bool:
	return data is Dictionary and data.get("room_id", "") == Game.room.get("room_id", "") and data.has("inventory_item_id") and Game.allowed("inventory.move")

func _drop_data(_position: Vector2, data: Variant) -> void:
	Game.command("inventory.move", {"item_id": data.inventory_item_id, "target_slot_index": slot_index})
