extends RefCounted

const CompareModel = preload("res://ui/equipment_compare_model.gd")
const EquipmentCompareDialog = preload("res://ui/equipment_compare_dialog.gd")

func run_test() -> Dictionary:
	var current := _gear("head-current", "Head", "Purple", "Fire", "Bulwark")
	var loadout: Array = [
		current,
		_gear("chest-current", "Chest", "Purple", "Earth", "Bulwark"),
		_gear("hands-current", "Hands", "Purple", "Metal", "Bulwark"),
		_gear("legs-current", "Legs", "Purple", "Wood", "Piercing"),
	]
	var selected := _gear("head-selected", "Head", "Orange", "Water", "Piercing", "DrawInterval")
	var current_rows := CompareModel.attribute_rows(current)
	var selected_rows := CompareModel.attribute_rows(selected)
	var white_rows := CompareModel.attribute_rows(_gear("head-white", "Head", "White", "Fire", "", "DrawInterval"))
	var after := CompareModel.replace_slot(loadout, selected)
	var bulwark_before := CompareModel.set_state(loadout, "Bulwark")
	var bulwark_after := CompareModel.set_state(after, "Bulwark")
	var piercing_before := CompareModel.set_state(loadout, "Piercing")
	var piercing_after := CompareModel.set_state(after, "Piercing")
	var totals := CompareModel.aggregate_attributes(loadout)
	var visible_sets := CompareModel.present_set_states(loadout)
	var null_current := _gear("null-current", "Chest", "Blue", "Earth", "<null>")
	var null_selected := _gear("null-selected", "Chest", "Purple", "Fire", "<null>")
	var dialog := EquipmentCompareDialog.new()
	dialog.open(null_selected, null_current, [null_current])
	var has_title_close := dialog.find_child("CloseComparison", true, false) != null
	var shows_null_affix := _all_text(dialog).contains("<null>")
	dialog.free()
	var checks := {
		"Cross-element attributes stay separate": current_rows.map(func(row): return row.key) == ["damage_Fire", "resistance_Fire"] and selected_rows.map(func(row): return row.key) == ["damage_Water", "resistance_Water", "draw_interval"],
		"Zero attributes are omitted from equipment comparison": white_rows.map(func(row): return row.key) == ["damage_Fire", "resistance_Fire"],
		"GDD base values are used": is_equal_approx(current_rows[0].value, 0.15) and is_equal_approx(current_rows[1].value, 0.09) and is_equal_approx(selected_rows[0].value, 0.22) and is_equal_approx(selected_rows[1].value, 0.13) and is_equal_approx(selected_rows[2].value, -0.18),
		"Three purple Bulwark activates": bulwark_before.active and bulwark_before.count == 3 and bulwark_before.required == 3,
		"Bulwark totals follow GDD": is_equal_approx(bulwark_before.values.bulwark_shield_percent, 0.24) and is_equal_approx(bulwark_before.values.bulwark_reduction_percent, 0.12),
		"Replacing the head breaks Bulwark": not bulwark_after.active and bulwark_after.count == 2 and is_zero_approx(bulwark_after.values.bulwark_shield_percent),
		"Orange plus purple Piercing activates at two": not piercing_before.active and piercing_after.active and piercing_after.count == 2 and piercing_after.required == 2,
		"Piercing total follows GDD": is_equal_approx(piercing_after.values.piercing_percent, 0.27),
		"Current loadout attributes aggregate locally": is_equal_approx(totals.damage_Fire, 0.15) and is_equal_approx(totals.resistance_Earth, 0.09) and is_equal_approx(totals.damage_Wood, 0.15),
		"Inactive present sets remain visible": visible_sets.size() == 2 and visible_sets.any(func(state): return state.kind == "Piercing" and state.count == 1 and state.required == 3 and not state.active),
		"Null affix placeholders stay hidden": not shows_null_affix,
		"Comparison title has no close button": not has_title_close,
	}
	return {"ok": not checks.values().has(false), "checks": checks, "message": "Equipment comparison keeps elements separate and computes affix set changes"}

func _gear(id: String, slot: String, quality: String, element: String, affix: String, secondary: String = "") -> Dictionary:
	return {"instanceId": id, "slot": slot, "quality": quality, "element": element, "effectAffix": affix, "secondaryTrait": secondary, "level": 0}

func _all_text(root: Node) -> String:
	var result := ""
	for node in root.find_children("*", "Control", true, false):
		if node is Label or node is Button: result += node.text + "\n"
	return result
