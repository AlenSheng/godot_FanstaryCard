extends RefCounted

const P = preload("res://ui/palette.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")

static func equipment(item: Dictionary) -> Dictionary:
	return item.get("equipment", {}) if item.has("kind") else item

static func title(item: Dictionary) -> String:
	var gear: Dictionary = equipment(item)
	if gear.is_empty(): return P.word(item.get("kind", "物品"))
	return "%s%s %s +%s" % [P.word(gear.get("quality", "")), P.word(gear.get("element", "")), P.word(gear.get("slot", "装备")), gear.get("level", 0)]

static func description(item: Dictionary) -> String:
	var gear: Dictionary = equipment(item)
	if gear.is_empty(): return "%s ×%s" % [title(item), item.get("quantity", 1)]
	var quality: Dictionary = CatalogIndex.quality(str(gear.get("quality", "")))
	var lines: Array[String] = [title(item)]
	var level: int = int(gear.get("level", 0))
	if not quality.is_empty():
		lines.append("%s%s +%s%% · %s +%s%%" % [P.word(gear.get("element", "")), P.localized("battle_attack_bonus"), percent(float(quality.damage_percent) + level * float(quality.damage_per_level)), P.localized("resistance"), percent(float(quality.resistance_percent) + level * float(quality.resistance_per_level))])
		var secondary_trait: String = str(gear.get("secondary_trait", gear.get("secondaryTrait", "")))
		if secondary_trait == "DrawInterval": lines.append("%s %s%%" % [P.localized("battle_draw_interval_seconds"), percent(float(quality.draw_interval_percent) + level * float(quality.draw_interval_per_level))])
		elif secondary_trait == "ForcedEscape": lines.append("%s +%s%%" % [P.localized("force_escape"), percent(float(quality.forced_escape_percent))])
	var affix: String = str(gear.get("effect_affix", gear.get("effectAffix", "")))
	if affix not in ["", "<null>"]:
		lines.append("%s%s" % [P.word(affix), P.localized("equipment_set_hint")])
		var fields: Array = {"Piercing": [["piercing_percent", P.localized("penetration")]], "Bulwark": [["bulwark_reduction_percent", P.localized("damage_reduction")], ["bulwark_shield_percent", P.localized("shield_gain")]], "Vitality": [["vitality_heal_percent", P.localized("healing")], ["vitality_overcap_percent", P.localized("equipment_health_overcap")]]}.get(affix, [])
		for field in fields:
			lines.append("%s: %s +%s%%" % [P.localized("set_contribution"), field[1], percent(float(quality.get(field[0], 0)) + level * float(quality.get("affix_per_level", 0)))])
		if affix == "Bulwark": lines.append(P.localized("bulwark_hint"))
	if gear.get("is_bound", gear.get("isBound", false)): lines.append("绑定 · 不可上架")
	return P.localized_text("\n".join(lines))

static func percent(value: float) -> String:
	return ("%.2f" % (value * 100)).trim_suffix("0").trim_suffix("0").trim_suffix(".")

static func enhancement_text(item: Dictionary) -> String:
	var gear := equipment(item)
	var level: int = int(gear.get("level", 0))
	var quality: Dictionary = CatalogIndex.quality(str(gear.get("quality", "")))
	if quality.is_empty(): return ""
	var lines: Array[String] = [P.localized("battle_current") + " +%s → +%s" % [level, mini(level + 1, 5)]]
	var fields: Array = [["damage_percent", "damage_per_level", P.word(gear.get("element", "")) + P.localized("battle_attack_bonus")], ["resistance_percent", "resistance_per_level", P.localized("resistance")]]
	if gear.get("secondaryTrait", gear.get("secondary_trait", "")) == "DrawInterval": fields.append(["draw_interval_percent", "draw_interval_per_level", P.localized("battle_draw_interval_seconds")])
	var affix: String = str(gear.get("effectAffix", gear.get("effect_affix", "")))
	for field in {"Piercing": [["piercing_percent", P.localized("battle_piercing_direct")]], "Bulwark": [["bulwark_reduction_percent", P.localized("battle_bulwark_reduction")], ["bulwark_shield_percent", P.localized("battle_bulwark_shield")]], "Vitality": [["vitality_heal_percent", P.localized("battle_vitality_heal")], ["vitality_overcap_percent", P.localized("battle_vitality_overcap")]]}.get(affix, []):
		fields.append([field[0], "affix_per_level", field[1]])
	for field in fields:
		var current: float = float(quality.get(field[0], 0)) + level * float(quality.get(field[1], 0))
		var next: float = float(quality.get(field[0], 0)) + mini(level + 1, 5) * float(quality.get(field[1], 0))
		lines.append("%s %s%% → %s%%" % [field[2], percent(current), percent(next)])
	if affix not in ["", "<null>"]: lines.append(P.localized("affix_hint"))
	return P.localized_text("\n".join(lines))
