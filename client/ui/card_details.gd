extends RefCounted

const P = preload("res://ui/palette.gd")
const CATALOG = preload("res://data/catalog.json")
const CatalogIndex = preload("res://data/catalog_index.gd")

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
	var names: Dictionary = P.language_pack_section("card_names")
	return str(names.get(id, fallback))

static func localized_face_name(id: String, card: Dictionary = {}) -> String:
	return str(P.language_pack_section("card_face_names").get(id, localized_name(id, card)))

static func at_level(card: Dictionary, level: int) -> Dictionary:
	# Catalog rows are flat scalars, so a shallow copy keeps the source row intact.
	var effect := card.duplicate()
	effect["is_element_tuning"] = str(card.get("category", "")) == "ElementTune"
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
	if id == "M-BOXSPIRIT" and str(card.get("element", "None")) == "None": card = with_element(card, "None")
	return _translated_face_description(at_level(card, level))

static func _number(value: float) -> String:
	return str(int(value)) if is_equal_approx(value, round(value)) else ("%.2f" % value).trim_suffix("0").trim_suffix(".")

static func _translated_face_description(effect: Dictionary) -> String:
	var parts: Array[String] = []
	for pair in [["elemental_damage", "element"], ["secondary_elemental_damage", "secondary_element"]]:
		var damage := float(effect.get(pair[0], 0))
		if damage > 0:
			var key := "card_face_tune" if effect.get("category", "") == "ElementTune" else "card_face_element"
			parts.append(P.localized(key) % [P.word(effect.get(pair[1], "None")), _number(damage)])
	var labels := {"health_cost": "card_face_health_cost", "direct_damage": "card_face_direct_damage",
		"heal": "card_face_heal", "shield": "card_face_shield", "immediate_draw": "card_face_draw",
		"draw_charge": "card_face_draw_charge", "stun_seconds": "card_face_stun",
		"draw_block_seconds": "card_face_draw_block", "same_element_bonus": "card_face_same_element",
		"resonance_bonus": "card_face_resonance", "conflict_cancel_bonus": "card_face_conflict_cancel",
		"conflict_heal_coefficient": "card_face_conflict_heal"}
	for key in labels:
		var value := float(effect.get(key, 0))
		if is_zero_approx(value): continue
		if key in ["draw_charge", "conflict_cancel_bonus"]: value *= 100.0
		parts.append(P.localized(str(labels[key])) % _number(value))
	var speed := float(effect.get("draw_speed_modifier", 0))
	if not is_zero_approx(speed):
		var key := "card_face_draw_faster" if speed < 0 else "card_face_draw_slower"
		parts.append(P.localized(key) % [_number(absf(speed) * 100.0), _number(float(effect.get("draw_speed_seconds", 0)))])
	if effect.get("is_class_reveal", false): parts.append(P.localized("card_face_class_reveal"))
	return P.localized("card_face_separator").join(parts)

static func contract_text(card: Dictionary) -> String:
	var tuning: bool = str(card.get("category", "")) == "ElementTune" or card.get("isElementTuning", card.get("is_element_tuning", false)) == true
	return P.localized("card_tuning_contract") if tuning else ""

static func effect_text(effect: Dictionary) -> String:
	var lines: Array[String] = []
	var secondary_damage: int = int(effect.get("secondaryElementalDamage", effect.get("secondary_elemental_damage", 0)))
	if secondary_damage > 0:
		var element := P.word(effect.get("secondaryElement", effect.get("secondary_element", "None")))
		lines.append(P.localized("card_effect_secondary").format({"element": element, "value": secondary_damage}))
	for key in ["elementalDamage", "directDamage", "heal", "shield", "drawCharge", "immediateDraw", "drawSpeedModifier", "stunSeconds", "drawBlockSeconds", "healthCost", "sameElementBonus", "resonanceBonus", "conflictCancelBonus", "conflictHealCoefficient"]:
		var value: float = float(effect.get(key, effect.get(key.to_snake_case(), 0)))
		if is_zero_approx(value): continue
		var suffix := P.localized("seconds") if key.ends_with("Seconds") else ""
		if key in ["drawCharge", "drawSpeedModifier", "conflictCancelBonus", "conflictHealCoefficient"]: value *= 100; suffix = "%"
		var number := _number(value)
		var text: String
		if key == "elementalDamage":
			text = P.localized("card_effect_elemental").format({"element": P.word(effect.get("element", "None")), "value": number})
		elif key in ["directDamage", "heal", "shield"]:
			text = P.localized({"directDamage": "card_effect_direct", "heal": "card_effect_heal", "shield": "card_effect_shield"}[key]) % number
		else:
			var title: String = {"drawCharge": P.localized("battle_draw_charge"), "immediateDraw": P.localized("battle_immediate_draw"), "drawSpeedModifier": P.localized("draw_interval"), "stunSeconds": P.localized("stun"), "drawBlockSeconds": P.localized("draw_lock"), "healthCost": P.localized("self_damage"), "sameElementBonus": P.localized("battle_same_element"), "resonanceBonus": P.localized("battle_resonance"), "conflictCancelBonus": P.localized("battle_conflict_cancel"), "conflictHealCoefficient": P.localized("battle_conflict_heal")}[key]
			text = title + " " + number + suffix
		if key == "drawSpeedModifier": text += " / %s%s" % [effect.get("drawSpeedSeconds", effect.get("draw_speed_seconds", 0)), P.localized("seconds")]
		lines.append(text)
	if effect.get("isClassReveal", effect.get("is_class_reveal", false)): lines.append(P.localized("battle_class_reveal"))
	return " · ".join(lines)
