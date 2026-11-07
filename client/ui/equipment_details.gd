extends RefCounted

const P = preload("res://ui/palette.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")

static func equipment(item: Dictionary) -> Dictionary:
	if not item.has("kind"): return item
	var gear: Variant = item.get("equipment")
	return gear if gear is Dictionary else {}

static func stats_version(item: Dictionary) -> String:
	var gear := equipment(item)
	var value: Variant = gear.get("stats_version",gear.get("statsVersion"))
	return "" if value == null else str(value)

static func unique_key(gear: Dictionary) -> String:
	var value: Variant = gear.get("unique_affix",gear.get("uniqueAffix"))
	return "" if value == null else str(value)

static func unique_name(gear: Dictionary) -> String:
	var keys := {"Inferno":"equipment_unique_inferno","RapidDraw":"equipment_unique_rapid_draw","ChainDraw":"equipment_unique_chain_draw","Scavenge":"equipment_unique_scavenge","GoldenCicada":"equipment_unique_golden_cicada"}
	return P.localized(keys[unique_key(gear)]) if keys.has(unique_key(gear)) else ""

static func unique_description(item: Dictionary, index: Dictionary = {}) -> String:
	var gear := equipment(item)
	var policy := CatalogIndex.equipment_rules(stats_version(item),index)
	match unique_key(gear):
		"Inferno":
			var value: Variant = gear.get("unique_element",gear.get("uniqueElement",gear.get("element","Fire")))
			var element := str(gear.get("element","Fire")) if not policy.is_empty() or value == null else str(value)
			return P.localized("equipment_unique_inferno_hint") % [P.word(element),percent(float(policy.get("inferno_bonus",.35)))]
		"RapidDraw": return P.localized("equipment_unique_rapid_draw_hint") % [percent(float(policy.get("rapid_draw_reduction",.25))),str(policy.get("rapid_draw_floor_seconds",1.5))]
		"ChainDraw": return P.localized("equipment_unique_chain_draw_hint") % percent(float(policy.get("chain_draw_chance",.20)))
		"Scavenge": return P.localized("equipment_unique_scavenge_hint") % str(int(policy.get("opening_draw_count",1)))
		"GoldenCicada": return P.localized("equipment_unique_golden_cicada_hint") % percent(float(policy.get("golden_cicada_bonus",.15)))
	return ""

static func title(item: Dictionary) -> String:
	var gear: Dictionary = equipment(item)
	if gear.is_empty(): return P.word(item.get("kind", P.localized("item")))
	var affix: String = str(gear.get("effect_affix", gear.get("effectAffix", "")))
	var attributes := ("" if P.language() == "zh-CN" else " ").join([P.word(gear.get("quality", "")), P.word(gear.get("element", "")), P.word(gear.get("slot", P.localized("word_equipment")))])
	if affix not in ["", "<null>"]:
		return "%s%s%s +%s" % [P.word(affix), "·" if P.language() == "zh-CN" else " · ", attributes, gear.get("level", 0)]
	if P.language() == "zh-CN":
		return "%s%s %s +%s" % [P.word(gear.get("quality", "")), P.word(gear.get("element", "")), P.word(gear.get("slot", P.localized("word_equipment"))), gear.get("level", 0)]
	return "%s +%s" % [attributes, gear.get("level", 0)]

static func description(item: Dictionary, index: Dictionary = {}) -> String:
	var gear: Dictionary = equipment(item)
	if gear.is_empty(): return "%s ×%s" % [title(item), item.get("quantity", 1)]
	var quality: Dictionary = CatalogIndex.quality(str(gear.get("quality", "")), index, stats_version(item))
	var lines: Array[String] = [title(item)]
	if quality.is_empty(): return "\n".join([title(item),P.localized("config_archive_unavailable")])
	var level: int = int(gear.get("level", 0))
	if not quality.is_empty():
		var attributes: Array[String] = []
		var damage: float = float(quality.damage_percent) + level * float(quality.damage_per_level)
		var resistance: float = float(quality.resistance_percent) + level * float(quality.resistance_per_level)
		if not is_zero_approx(damage): attributes.append("%s +%s%%" % [P.element_stat("damage", gear.get("element", "")), percent(damage)])
		if not is_zero_approx(resistance): attributes.append("%s +%s%%" % [P.element_stat("resistance", gear.get("element", "")), percent(resistance)])
		if not attributes.is_empty(): lines.append(" · ".join(attributes))
		var secondary_trait: String = str(gear.get("secondary_trait", gear.get("secondaryTrait", "")))
		var secondary_value := 0.0
		if secondary_trait == "DrawInterval": secondary_value = float(quality.draw_interval_percent) + level * float(quality.draw_interval_per_level)
		elif secondary_trait == "ForcedEscape": secondary_value = float(quality.forced_escape_percent)
		if not is_zero_approx(secondary_value):
			lines.append("%s %s%%" % [P.localized("battle_draw_interval_seconds"), percent(secondary_value)] if secondary_trait == "DrawInterval" else "%s +%s%%" % [P.localized("force_escape"), percent(secondary_value)])
	var affix: String = str(gear.get("effect_affix", gear.get("effectAffix", "")))
	if affix not in ["", "<null>"]:
		lines.append("%s%s" % [P.word(affix), P.localized("equipment_set_hint")])
		var fields: Array = {"Piercing": [["piercing_percent", P.localized("penetration")]], "Bulwark": [["bulwark_reduction_percent", P.localized("damage_reduction")], ["bulwark_shield_percent", P.localized("shield_gain")]], "Vitality": [["vitality_heal_percent", P.localized("healing")], ["vitality_overcap_percent", P.localized("equipment_health_overcap")]]}.get(affix, [])
		for field in fields:
			var contribution: float = float(quality.get(field[0], 0)) + level * float(quality.get("affix_per_level", 0))
			if not is_zero_approx(contribution): lines.append("%s: %s +%s%%" % [P.localized("set_contribution"), field[1], percent(contribution)])
		if affix == "Bulwark": lines.append(P.localized("bulwark_hint"))
	if gear.get("is_bound", gear.get("isBound", false)): lines.append(P.localized("bound_unlisted"))
	var unique := unique_name(gear)
	if not unique.is_empty():
		lines.append(unique)
		lines.append(unique_description(item,index))
	return P.localized_text("\n".join(lines))

static func percent(value: float) -> String:
	return ("%.2f" % (value * 100)).trim_suffix("0").trim_suffix("0").trim_suffix(".")

static func enhancement_text(item: Dictionary, index: Dictionary = {}) -> String:
	var gear := equipment(item)
	var level: int = int(gear.get("level", 0))
	var quality: Dictionary = CatalogIndex.quality(str(gear.get("quality", "")), index, stats_version(item))
	if quality.is_empty(): return ""
	var lines: Array[String] = [P.localized("battle_current") + " +%s → +%s" % [level, mini(level + 1, 5)]]
	var fields: Array = [["damage_percent", "damage_per_level", P.element_stat("damage", gear.get("element", ""))], ["resistance_percent", "resistance_per_level", P.element_stat("resistance", gear.get("element", ""))]]
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
