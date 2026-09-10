extends RefCounted

const P = preload("res://ui/palette.gd")
const CATALOG = preload("res://data/catalog.json")

static func equipment(item: Dictionary) -> Dictionary:
	return item.get("equipment", {}) if item.has("kind") else item

static func title(item: Dictionary) -> String:
	var gear: Dictionary = equipment(item)
	if gear.is_empty(): return P.word(item.get("kind", "物品"))
	return "%s%s %s +%s" % [P.word(gear.get("quality", "")), P.word(gear.get("element", "")), P.word(gear.get("slot", "装备")), gear.get("level", 0)]

static func description(item: Dictionary) -> String:
	var gear: Dictionary = equipment(item)
	if gear.is_empty(): return "%s ×%s" % [title(item), item.get("quantity", 1)]
	var quality: Dictionary = {}
	for row in CATALOG.data.tables.EquipmentQuality:
		if row.id == gear.get("quality", ""): quality = row; break
	var lines: Array[String] = [title(item)]
	var level: int = int(gear.get("level", 0))
	if not quality.is_empty():
		lines.append("%s增伤 +%s%% · 抗性 +%s%%" % [P.word(gear.get("element", "")), percent(float(quality.damage_percent) + level * float(quality.damage_per_level)), percent(float(quality.resistance_percent) + level * float(quality.resistance_per_level))])
		var secondary_trait: String = str(gear.get("secondary_trait", gear.get("secondaryTrait", "")))
		if secondary_trait == "DrawInterval": lines.append("抽牌间隔 %s%%" % percent(float(quality.draw_interval_percent) + level * float(quality.draw_interval_per_level)))
		elif secondary_trait == "ForcedEscape": lines.append("强制逃脱 +%s%%" % percent(float(quality.forced_escape_percent)))
	var affix: String = str(gear.get("effect_affix", gear.get("effectAffix", "")))
	if affix not in ["", "<null>"]:
		lines.append("%s套 · 同效果3件生效，含橙/红时2件生效" % P.word(affix))
		var fields: Array = {"Piercing": [["piercing_percent", "穿透"]], "Bulwark": [["bulwark_reduction_percent", "减伤"], ["bulwark_shield_percent", "上盾"]], "Vitality": [["vitality_heal_percent", "治疗"], ["vitality_overcap_percent", "生命上限溢出"]]}.get(affix, [])
		for field in fields:
			lines.append("套装激活后贡献：%s +%s%%" % [field[1], percent(float(quality.get(field[0], 0)) + level * float(quality.get("affix_per_level", 0)))])
		if affix == "Bulwark": lines.append("上盾适用所有职业；减伤仅盾卫生效")
	if gear.get("is_bound", gear.get("isBound", false)): lines.append("绑定 · 不可上架")
	return "\n".join(lines)

static func percent(value: float) -> String:
	return ("%.2f" % (value * 100)).trim_suffix("0").trim_suffix("0").trim_suffix(".")

static func enhancement_text(item: Dictionary) -> String:
	var gear := equipment(item)
	var level: int = int(gear.get("level", 0))
	var quality: Dictionary = {}
	for row in CATALOG.data.tables.EquipmentQuality:
		if row.id == gear.get("quality", ""): quality = row; break
	if quality.is_empty(): return ""
	var lines: Array[String] = ["属性 +%s → +%s" % [level, mini(level + 1, 5)]]
	var fields: Array = [["damage_percent", "damage_per_level", P.word(gear.get("element", "")) + "增伤"], ["resistance_percent", "resistance_per_level", "抗性"]]
	if gear.get("secondaryTrait", gear.get("secondary_trait", "")) == "DrawInterval": fields.append(["draw_interval_percent", "draw_interval_per_level", "抽牌间隔"])
	var affix: String = str(gear.get("effectAffix", gear.get("effect_affix", "")))
	for field in {"Piercing": [["piercing_percent", "破击直伤"]], "Bulwark": [["bulwark_reduction_percent", "载壁减伤（仅盾卫）"], ["bulwark_shield_percent", "载壁上盾"]], "Vitality": [["vitality_heal_percent", "生息治疗"], ["vitality_overcap_percent", "生息超上限"]]}.get(affix, []):
		fields.append([field[0], "affix_per_level", field[1]])
	for field in fields:
		var current: float = float(quality.get(field[0], 0)) + level * float(quality.get(field[1], 0))
		var next: float = float(quality.get(field[0], 0)) + mini(level + 1, 5) * float(quality.get(field[1], 0))
		lines.append("%s %s%% → %s%%" % [field[2], percent(current), percent(next)])
	if affix not in ["", "<null>"]: lines.append("效果词缀为本件贡献，套装激活后生效")
	return "\n".join(lines)
