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
		"FenXian": return "%s核 · 连携 %s\n本命充能 +%s%%" % [P.word(status.get("core_element", "None")), status.get("combo", 0), Details.percent(values.get("weapon_bonus", 0))]
		"LinYuan": return "治疗 +%s%% · 控场 +%s%%\n本命治疗 +%s%%" % [Details.percent(values.get("passive_heal", 0)), Details.percent(values.get("passive_control", 0)), Details.percent(values.get("weapon_bonus", 0))]
		"ZaiYue": return "上盾 +%s%%\n本命额外盾 +%s" % [Details.percent(values.get("passive_shield", 0)), int(values.get("shield_flat", 0))]
	return ""

static func description(status: Dictionary) -> String:
	var lines: Array[String] = [passive_text(status), "抽牌间隔 %.2f 秒" % float(status.get("draw_interval_seconds", "0"))]
	for set in status.get("sets", []):
		lines.append("%s %s / %s 件 · %s" % [P.word(set.kind), set.count, set.required, "已生效" if set.active else "未激活"])
	var names := {"piercing": "破击直伤", "bulwark_reduction": "载壁减伤（仅盾卫）", "bulwark_shield": "载壁上盾", "vitality_heal": "生息治疗", "vitality_overcap": "生息超上限", "draw_interval": "装备抽牌间隔", "forced_escape": "装备逃脱"}
	for stat in status.get("bonuses", []):
		var key: String = stat.key
		var title: String = names.get(key, "")
		if key.begins_with("damage_"): title = P.word(key.trim_prefix("damage_")) + "增伤"
		elif key.begins_with("resistance_"): title = P.word(key.trim_prefix("resistance_")) + "抗性"
		if not title.is_empty(): lines.append("%s %s%%" % [title, Details.percent(float(stat.value))])
	return "\n".join(lines)
