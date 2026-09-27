extends RefCounted

const P = preload("res://ui/palette.gd")
const CATALOG = preload("res://data/catalog.json")
const CatalogIndex = preload("res://data/catalog_index.gd")
const NAMES = preload("res://data/card_names.json")

const QUALITY_ORDER := {"White": 0, "Green": 1, "Blue": 2, "Purple": 3, "Orange": 4}
const CLASS_ORDER := {"Priest": 0, "Mage": 1, "Guardian": 2}
static var _catalog_order: Array = []

static func sorted_ids(ids: Array, cards: Dictionary) -> Array:
	# The codex always sorts the full static catalog. Reuse that order instead
	# of comparing every pair again on each rebuild.
	if is_same(cards, CatalogIndex.cards()) and ids.size() == cards.size():
		if _catalog_order.is_empty():
			var ordered := ids.duplicate()
			ordered.sort_custom(func(left, right): return card_before(str(left), str(right), cards))
			_catalog_order = ordered
		return _catalog_order.duplicate()
	var result := ids.duplicate()
	result.sort_custom(func(left, right): return card_before(str(left), str(right), cards))
	return result

static func card_before(left_id: String, right_id: String, cards: Dictionary) -> bool:
	var left: Dictionary = cards.get(left_id, {})
	var right: Dictionary = cards.get(right_id, {})
	var left_quality := int(QUALITY_ORDER.get(str(left.get("quality", "")), 99))
	var right_quality := int(QUALITY_ORDER.get(str(right.get("quality", "")), 99))
	if left_quality != right_quality: return left_quality < right_quality
	var left_class: Variant = left.get("hero_class", null)
	var right_class: Variant = right.get("hero_class", null)
	var left_is_class := left_class != null
	var right_is_class := right_class != null
	if left_is_class != right_is_class: return not left_is_class
	if left_is_class:
		var left_rank := int(CLASS_ORDER.get(str(left_class), 99))
		var right_rank := int(CLASS_ORDER.get(str(right_class), 99))
		if left_rank != right_rank: return left_rank < right_rank
	return left_id < right_id

static func localized_name(id: String, card: Dictionary = {}) -> String:
	var fallback := str(card.get("name", id))
	var names: Dictionary = NAMES.data.get(P.language(), {})
	return str(names.get(id, fallback))

static func at_level(card: Dictionary, level: int) -> Dictionary:
	# Catalog rows are flat scalars, so a shallow copy keeps the source row intact.
	var effect := card.duplicate()
	var growth := CatalogIndex.card_level(str(card.get("id", "")), level)
	if growth.is_empty(): return effect
	for key in ["elemental_damage", "secondary_elemental_damage", "direct_damage", "heal", "shield"]:
		if int(effect.get(key, 0)) > 0: effect[key] += int(growth.value_bonus)
	for key in ["stun_seconds", "draw_block_seconds", "draw_speed_seconds"]:
		if float(effect.get(key, 0)) > 0: effect[key] += float(growth.duration_bonus)
	return effect

static func with_element(card: Dictionary, element_override: String) -> Dictionary:
	if card.get("id", "") != "M-BOXSPIRIT" or element_override.is_empty(): return card
	var result := card.duplicate(true)
	var damage: int = int(card.get("elemental_damage", 7)) + int(card.get("direct_damage", 0))
	result.element = element_override
	result.elemental_damage = 0 if element_override == "None" else damage
	result.direct_damage = damage if element_override == "None" else 0
	return result

static func face_description(id: String, level: int = 0, overrides: Dictionary = {}) -> String:
	var card := CatalogIndex.card(id).duplicate()
	card.merge(overrides, true)
	card["id"] = id
	var effect := at_level(card, level)
	var english := P.language() == "en"
	var parts: Array[String] = []
	var damage := float(effect.get("elemental_damage", 0))
	if damage > 0:
		var element := P.word(effect.get("element", "None"))
		var tuning: bool = effect.get("category", "") == "ElementTune"
		parts.append(("%s tune %s" if tuning else "%s %s") % [element, _number(damage)] if english else ("%s调伤%s" if tuning else "%s伤%s") % [element, _number(damage)])
	var secondary := float(effect.get("secondary_elemental_damage", 0))
	if secondary > 0:
		parts.append(("%s %s" if english else "%s伤%s") % [P.word(effect.get("secondary_element", "None")), _number(secondary)])
	var labels := {
		"health_cost": "Self -%s" if english else "自损%s",
		"direct_damage": "Damage %s" if english else "直伤%s",
		"heal": "Heal %s" if english else "治疗%s",
		"shield": "Shield %s" if english else "盾%s",
		"immediate_draw": "Draw %s" if english else "抽%s",
		"draw_charge": "Charge +%s%%" if english else "蓄能+%s%%",
		"stun_seconds": "Stun %ss" if english else "晕%s秒",
		"draw_block_seconds": "Draw lock %ss" if english else "封抽%s秒",
		"same_element_bonus": "Same element +%s" if english else "同系+%s",
		"resonance_bonus": "Combo tier +%s" if english else "连放倍率+%s档",
		"conflict_cancel_bonus": "Conflict cancel +%s%%" if english else "向反抵消+%s%%",
		"conflict_heal_coefficient": "Conflict heal x%s" if english else "向反回复×%s",
	}
	for key in labels:
		var value := float(effect.get(key, 0))
		if is_zero_approx(value): continue
		if key in ["draw_charge", "conflict_cancel_bonus"]: value *= 100.0
		parts.append(str(labels[key]) % _number(value))
	var speed := float(effect.get("draw_speed_modifier", 0))
	if not is_zero_approx(speed):
		var duration := _number(float(effect.get("draw_speed_seconds", 0)))
		parts.append("Draw interval %s%%/%ss" % [_number(speed * 100.0), duration] if english else "抽牌%s%s%%/%s秒" % ["加快" if speed < 0 else "减慢", _number(absf(speed) * 100.0), duration])
	if effect.get("is_class_reveal", false):
		parts.append("Class damage x1.3" if english else "本职业伤害×1.3")
	return (" · " if english else "·").join(parts)

static func _number(value: float) -> String:
	return str(int(value)) if is_equal_approx(value, round(value)) else ("%.2f" % value).trim_suffix("0").trim_suffix(".")

static func effect_text(effect: Dictionary) -> String:
	var lines: Array[String] = []
	var secondary_damage: int = int(effect.get("secondaryElementalDamage", effect.get("secondary_elemental_damage", 0)))
	if secondary_damage > 0:
		var secondary_element := P.word(effect.get("secondaryElement", effect.get("secondary_element", "None")))
		lines.append("Deal %s %s elemental damage" % [secondary_damage, secondary_element] if P.language() == "en" else "追加%s系伤害%s点" % [secondary_element, secondary_damage])
	for key in ["elementalDamage", "directDamage", "heal", "shield", "drawCharge", "immediateDraw", "drawSpeedModifier", "stunSeconds", "drawBlockSeconds", "healthCost", "sameElementBonus", "resonanceBonus", "conflictCancelBonus", "conflictHealCoefficient"]:
		var value: float = float(effect.get(key, effect.get(key.to_snake_case(), 0)))
		if is_zero_approx(value): continue
		var suffix := P.localized("seconds") if key.ends_with("Seconds") else ""
		if key in ["drawCharge", "drawSpeedModifier", "conflictCancelBonus", "conflictHealCoefficient"]: value *= 100; suffix = "%"
		var number := str(int(value)) if is_equal_approx(value, round(value)) else ("%.2f" % value).trim_suffix("0").trim_suffix(".")
		var text: String
		if key == "elementalDamage":
			var element := P.word(effect.get("element", "None"))
			text = "Deal %s %s elemental damage" % [number, element] if P.language() == "en" else "造成%s系伤害%s点" % [element, number]
		elif key == "directDamage":
			text = "Deal %s direct damage" % number if P.language() == "en" else "造成直接伤害%s点" % number
		elif key == "heal":
			text = "Heal %s" % number if P.language() == "en" else "治疗%s点" % number
		elif key == "shield":
			text = "Gain %s shield" % number if P.language() == "en" else "获得%s点护盾" % number
		else:
			var title: String = {"drawCharge": P.localized("battle_draw_charge"), "immediateDraw": P.localized("battle_immediate_draw"), "drawSpeedModifier": P.localized("draw_interval"), "stunSeconds": P.localized("stun"), "drawBlockSeconds": P.localized("draw_lock"), "healthCost": P.localized("self_damage"), "sameElementBonus": P.localized("battle_same_element"), "resonanceBonus": P.localized("battle_resonance"), "conflictCancelBonus": P.localized("battle_conflict_cancel"), "conflictHealCoefficient": P.localized("battle_conflict_heal")}[key]
			text = title + " " + number + suffix
		if key == "drawSpeedModifier": text += " / %s%s" % [effect.get("drawSpeedSeconds", effect.get("draw_speed_seconds", 0)), P.localized("seconds")]
		lines.append(text)
	if effect.get("isClassReveal", effect.get("is_class_reveal", false)): lines.append(P.localized("battle_class_reveal"))
	return " · ".join(lines)
