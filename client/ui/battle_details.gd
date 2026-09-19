extends RefCounted

const P = preload("res://ui/palette.gd")
const Details = preload("res://ui/equipment_details.gd")

static func bonuses(status: Dictionary) -> Dictionary:
	var result := {}
	for entry in status.get("bonuses", []): result[entry.key] = float(entry.value)
	return result

static func passive_text(status: Dictionary) -> String:
	var values := bonuses(status)
	match status.get("passive_kind", ""):
		"FenXian": return P.localized("battle_passive_mage") % [P.word(status.get("core_element", "None")), status.get("combo", 0), status.get("charge_level", 0), Details.percent(values.get("weapon_bonus", 0))]
		"LinYuan": return P.localized("battle_passive_priest") % [Details.percent(values.get("passive_heal", 0)), Details.percent(values.get("passive_control", 0)), Details.percent(values.get("weapon_bonus", 0))]
		"ZaiYue": return P.localized("battle_passive_guardian") % [Details.percent(values.get("passive_shield", 0)), int(values.get("shield_flat", 0))]
	return ""

static func description(status: Dictionary) -> String:
	var lines: Array[String] = [passive_text(status), P.localized("battle_draw_interval_summary") % float(status.get("draw_interval_seconds", "0"))]
	for set in status.get("sets", []):
		lines.append(P.localized("battle_set_summary") % [P.word(set.kind), set.count, set.required, P.localized("battle_active") if set.active else P.localized("battle_inactive")])
	var names := {"piercing": P.localized("battle_piercing_direct"), "bulwark_reduction": P.localized("battle_bulwark_reduction"), "bulwark_shield": P.localized("battle_bulwark_shield"), "vitality_heal": P.localized("battle_vitality_heal"), "vitality_overcap": P.localized("battle_vitality_overcap"), "draw_interval": P.localized("battle_equipment_draw_interval"), "forced_escape": P.localized("battle_equipment_escape")}
	for stat in status.get("bonuses", []):
		var key: String = stat.key
		var title: String = names.get(key, "")
		if key.begins_with("damage_"): title = P.word(key.trim_prefix("damage_")) + P.localized("battle_attack_bonus")
		elif key.begins_with("resistance_"): title = P.word(key.trim_prefix("resistance_")) + P.localized("resistance")
		if not title.is_empty(): lines.append("%s %s%%" % [title, Details.percent(float(stat.value))])
	return P.localized_text("\n".join(lines))
