extends RefCounted

const P = preload("res://ui/palette.gd")
const CATALOG = preload("res://data/catalog.json")

static func at_level(card: Dictionary, level: int) -> Dictionary:
	var effect := card.duplicate(true)
	for growth in CATALOG.data.tables.CardLevels:
		if growth.card_id != card.get("id", "") or int(growth.level) != level: continue
		for key in ["elemental_damage", "secondary_elemental_damage", "direct_damage", "heal", "shield"]:
			if int(effect.get(key, 0)) > 0: effect[key] += int(growth.value_bonus)
		for key in ["stun_seconds", "draw_block_seconds", "draw_speed_seconds"]:
			if float(effect.get(key, 0)) > 0: effect[key] += float(growth.duration_bonus)
		break
	return effect

static func with_element(card: Dictionary, element_override: String) -> Dictionary:
	var result := card.duplicate(true)
	if card.get("id", "") != "M-BOXSPIRIT" or element_override.is_empty(): return result
	var damage: int = int(card.get("elemental_damage", 7)) + int(card.get("direct_damage", 0))
	result.element = element_override
	result.elemental_damage = 0 if element_override == "None" else damage
	result.direct_damage = damage if element_override == "None" else 0
	return result

static func effect_text(effect: Dictionary) -> String:
	var lines: Array[String] = []
	var secondary_damage: int = int(effect.get("secondaryElementalDamage", effect.get("secondary_elemental_damage", 0)))
	if secondary_damage > 0: lines.append(P.localized("battle_damage_segment") % [P.word(effect.get("secondaryElement", effect.get("secondary_element", "None"))), secondary_damage])
	for key in ["elementalDamage", "directDamage", "heal", "shield", "drawCharge", "immediateDraw", "drawSpeedModifier", "stunSeconds", "drawBlockSeconds", "healthCost", "sameElementBonus", "resonanceBonus", "conflictCancelBonus", "conflictHealCoefficient"]:
		var value: float = float(effect.get(key, effect.get(key.to_snake_case(), 0)))
		if is_zero_approx(value): continue
		var title: String = {"elementalDamage": P.word(effect.get("element", "None")) + P.localized("battle_secondary_damage"), "directDamage": P.localized("direct_damage"), "heal": P.localized("healing"), "shield": P.localized("shield_gain"), "drawCharge": P.localized("battle_draw_charge"), "immediateDraw": P.localized("battle_immediate_draw"), "drawSpeedModifier": P.localized("draw_interval"), "stunSeconds": P.localized("stun"), "drawBlockSeconds": P.localized("draw_lock"), "healthCost": P.localized("self_damage"), "sameElementBonus": P.localized("battle_same_element"), "resonanceBonus": P.localized("battle_resonance"), "conflictCancelBonus": P.localized("battle_conflict_cancel"), "conflictHealCoefficient": P.localized("battle_conflict_heal")}[key]
		var suffix := P.localized("seconds") if key.ends_with("Seconds") else ""
		if key in ["drawCharge", "drawSpeedModifier", "conflictCancelBonus", "conflictHealCoefficient"]: value *= 100; suffix = "%"
		var text := title + " " + ("%.2f" % value).trim_suffix("0").trim_suffix("0").trim_suffix(".") + suffix
		if key == "drawSpeedModifier": text += " / %s%s" % [effect.get("drawSpeedSeconds", effect.get("draw_speed_seconds", 0)), P.localized("seconds")]
		lines.append(text)
	if effect.get("isClassReveal", effect.get("is_class_reveal", false)): lines.append(P.localized("battle_class_reveal"))
	return " · ".join(lines)
