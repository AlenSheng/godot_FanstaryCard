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
	if secondary_damage > 0: lines.append("%s伤 %s（独立分段）" % [P.word(effect.get("secondaryElement", effect.get("secondary_element", "None"))), secondary_damage])
	for key in ["elementalDamage", "directDamage", "heal", "shield", "drawCharge", "immediateDraw", "drawSpeedModifier", "stunSeconds", "drawBlockSeconds", "healthCost", "sameElementBonus", "resonanceBonus", "conflictCancelBonus", "conflictHealCoefficient"]:
		var value: float = float(effect.get(key, effect.get(key.to_snake_case(), 0)))
		if is_zero_approx(value): continue
		var title: String = {"elementalDamage": P.word(effect.get("element", "None")) + "伤", "directDamage": "直伤", "heal": "治疗", "shield": "护盾", "drawCharge": "抽牌充能", "immediateDraw": "立即抽牌", "drawSpeedModifier": "抽牌间隔", "stunSeconds": "眩晕", "drawBlockSeconds": "锁抽", "healthCost": "自损生命", "sameElementBonus": "同核加成", "resonanceBonus": "相生加成", "conflictCancelBonus": "相克抵消", "conflictHealCoefficient": "相克治疗系数"}[key]
		var suffix := "秒" if key.ends_with("Seconds") else ""
		if key in ["drawCharge", "drawSpeedModifier", "conflictCancelBonus", "conflictHealCoefficient"]: value *= 100; suffix = "%"
		var text := title + " " + ("%.2f" % value).trim_suffix("0").trim_suffix("0").trim_suffix(".") + suffix
		if key == "drawSpeedModifier": text += " / %s秒" % effect.get("drawSpeedSeconds", effect.get("draw_speed_seconds", 0))
		lines.append(text)
	if effect.get("isClassReveal", effect.get("is_class_reveal", false)): lines.append("职业显：本职业显示元素的基础伤害 ×1.3")
	return " · ".join(lines)
