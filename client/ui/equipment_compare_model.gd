extends RefCounted

const CATALOG = preload("res://data/catalog.json")
const EquipmentDetails = preload("res://ui/equipment_details.gd")

const AFFIXES := ["Bulwark", "Piercing", "Vitality"]
const MULTIPLIERS := {2: 1.35, 3: 1.35, 4: 1.55, 5: 1.80}
const AFFIX_FIELDS := {
	"Piercing": ["piercing_percent"],
	"Bulwark": ["bulwark_shield_percent", "bulwark_reduction_percent"],
	"Vitality": ["vitality_heal_percent", "vitality_overcap_percent"],
}
const FIELD_CAPS := {
	"piercing_percent": [0.40, 0.45, 0.50],
	"bulwark_shield_percent": [0.40, 0.45, 0.50],
	"bulwark_reduction_percent": [0.35, 0.40, 0.45],
	"vitality_heal_percent": [0.50, 0.50, 0.50],
	"vitality_overcap_percent": [0.40, 0.40, 0.40],
}

static func gear(item: Dictionary) -> Dictionary:
	return EquipmentDetails.equipment(item)

static func quality_row(item: Dictionary) -> Dictionary:
	var quality := str(gear(item).get("quality", "")).capitalize()
	for row in CATALOG.data.tables.EquipmentQuality:
		if str(row.id) == quality: return row
	return {}

static func attribute_rows(item: Dictionary) -> Array[Dictionary]:
	var equipment := gear(item)
	var quality := quality_row(item)
	if equipment.is_empty() or quality.is_empty(): return []
	var level := int(equipment.get("level", 0))
	var element := str(equipment.get("element", "None"))
	var rows: Array[Dictionary] = [
		{"key": "damage_" + element, "kind": "damage", "element": element, "value": float(quality.damage_percent) + level * float(quality.damage_per_level)},
		{"key": "resistance_" + element, "kind": "resistance", "element": element, "value": float(quality.resistance_percent) + level * float(quality.resistance_per_level)},
	]
	var secondary := str(equipment.get("secondary_trait", equipment.get("secondaryTrait", "")))
	if secondary == "DrawInterval":
		rows.append({"key": "draw_interval", "kind": "draw_interval", "element": "None", "value": float(quality.draw_interval_percent) + level * float(quality.draw_interval_per_level)})
	elif secondary == "ForcedEscape":
		rows.append({"key": "forced_escape", "kind": "forced_escape", "element": "None", "value": float(quality.forced_escape_percent)})
	return rows

static func affix_contributions(item: Dictionary) -> Dictionary:
	var equipment := gear(item)
	var quality := quality_row(item)
	var kind := str(equipment.get("effect_affix", equipment.get("effectAffix", "")))
	if kind not in AFFIXES or quality.is_empty(): return {"kind": "", "values": {}}
	var level := int(equipment.get("level", 0))
	var values := {}
	for field in AFFIX_FIELDS[kind]:
		values[field] = float(quality.get(field, 0.0)) + level * float(quality.get("affix_per_level", 0.0))
	return {"kind": kind, "values": values}

static func replace_slot(loadout: Array, selected: Dictionary) -> Array:
	var selected_slot := str(gear(selected).get("slot", ""))
	var result: Array = []
	for item in loadout:
		if str(gear(item).get("slot", "")) != selected_slot: result.append(item)
	result.append(selected)
	return result

static func set_state(loadout: Array, kind: String) -> Dictionary:
	var matching: Array = []
	var highest_rank := 0
	for item in loadout:
		var contribution := affix_contributions(item)
		if contribution.kind != kind: continue
		matching.append(item)
		var quality := str(gear(item).get("quality", "")).capitalize()
		highest_rank = maxi(highest_rank, ["", "White", "Green", "Blue", "Purple", "Orange", "Red"].find(quality))
	var count := matching.size()
	var has_high_quality := highest_rank >= 5
	var required := 2 if has_high_quality else 3
	var active := count >= required
	var values := {}
	for field in AFFIX_FIELDS[kind]: values[field] = 0.0
	if active:
		var multiplier := float(MULTIPLIERS.get(clampi(count, 2, 5), 1.0))
		var cap_index := 2 if highest_rank >= 6 else (1 if highest_rank >= 5 else 0)
		for item in matching:
			var contribution := affix_contributions(item)
			for field in AFFIX_FIELDS[kind]: values[field] += float(contribution.values.get(field, 0.0))
		for field in AFFIX_FIELDS[kind]:
			values[field] = minf(floorf(float(values[field]) * multiplier * 100.0) / 100.0, float(FIELD_CAPS[field][cap_index]))
	return {"kind": kind, "count": count, "required": required, "active": active, "values": values, "has_high_quality": has_high_quality}

static func changed_sets(before: Array, after: Array) -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for kind in AFFIXES:
		var old_state := set_state(before, kind)
		var new_state := set_state(after, kind)
		if old_state.count != new_state.count or old_state.required != new_state.required or old_state.values != new_state.values:
			result.append({"kind": kind, "before": old_state, "after": new_state})
	return result

