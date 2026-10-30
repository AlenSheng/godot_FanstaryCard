"""Finish the one-time card-copy migration, preserving existing EN/ZH wording."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COPY = {
    "card_face_element": ["%s伤%s", "%s %s", "%s: daño %s"],
    "card_face_tune": ["%s调伤%s", "%s tune %s", "%s: ajuste %s"],
    "card_face_health_cost": ["自损%s", "Self -%s", "Vida -%s"],
    "card_face_direct_damage": ["直伤%s", "Damage %s", "Directo %s"],
    "card_face_heal": ["治疗%s", "Heal %s", "Cura %s"],
    "card_face_shield": ["盾%s", "Shield %s", "Escudo %s"],
    "card_face_draw": ["抽%s", "Draw %s", "Roba %s"],
    "card_face_draw_charge": ["蓄能+%s%%", "Charge +%s%%", "Carga +%s%%"],
    "card_face_stun": ["晕%s秒", "Stun %ss", "Aturde %ss"],
    "card_face_draw_block": ["封抽%s秒", "Draw lock %ss", "Robo bloqueado %ss"],
    "card_face_same_element": ["同系+%s", "Same element +%s", "Mismo elem. +%s"],
    "card_face_resonance": ["连放倍率+%s档", "Combo tier +%s", "Combo +%s nivel"],
    "card_face_conflict_cancel": ["向反抵消+%s%%", "Conflict cancel +%s%%", "Anulación opuesta +%s%%"],
    "card_face_conflict_heal": ["向反回复×%s", "Conflict heal x%s", "Cura opuesta ×%s"],
    "card_face_draw_faster": ["抽牌加快%s%%/%s秒", "Draw interval -%s%%/%ss", "Intervalo -%s%%/%ss"],
    "card_face_draw_slower": ["抽牌减慢%s%%/%s秒", "Draw interval %s%%/%ss", "Intervalo %s%%/%ss"],
    "card_face_class_reveal": ["本职业伤害×1.3", "Class damage x1.3", "Daño de clase ×1.3"],
    "card_face_separator": ["·", " · ", " · "],
    "card_effect_elemental": ["造成{element}系伤害{value}点", "Deal {value} {element} elemental damage", "Daño de {element}: {value}"],
    "card_effect_secondary": ["追加{element}系伤害{value}点", "Deal {value} {element} elemental damage", "Daño extra de {element}: {value}"],
    "card_effect_direct": ["造成直接伤害%s点", "Deal %s direct damage", "Inflige %s de daño directo"],
    "card_effect_heal": ["治疗%s点", "Heal %s", "Cura %s"],
    "card_effect_shield": ["获得%s点护盾", "Gain %s shield", "Gana %s de escudo"],
    "account_uid_inline": ["%s · UID %s", "%s · UID %s", "%s · ID %s"],
    "account_uid_multiline": ["%s\nUID %s", "%s\nUID %s", "%s\nID %s"]
}

FACE = '''static func face_description(id: String, level: int = 0, overrides: Dictionary = {}) -> String:
	var card := CatalogIndex.card(id).duplicate()
	card.merge(overrides, true)
	card["id"] = id
	return _translated_face_description(at_level(card, level))

'''
TRANSLATED_FACE = '''static func _translated_face_description(effect: Dictionary) -> String:
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

'''
CONTRACT = '''static func contract_text(card: Dictionary) -> String:
	var tuning: bool = str(card.get("category", "")) == "ElementTune" or card.get("isElementTuning", card.get("is_element_tuning", false)) == true
	return P.localized("card_tuning_contract") if tuning else ""

'''
EFFECT = '''static func effect_text(effect: Dictionary) -> String:
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
'''


def main():
    for index, code in enumerate(["zh-CN", "en", "es"]):
        path = ROOT / "client/data/locales" / (code + ".json")
        pack = json.loads(path.read_text(encoding="utf-8"))
        pack["strings"].update({key: values[index] for key, values in COPY.items()})
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path = ROOT / "client/ui/card_details.gd"
    text = path.read_text(encoding="utf-8")
    start, end = text.index("static func face_description"), text.index("static func _number")
    text = text[:start] + FACE + text[end:]
    start, end = text.index("static func _translated_face_description"), text.index("static func contract_text")
    text = text[:start] + TRANSLATED_FACE + text[end:]
    text = text[:text.index("static func contract_text")] + CONTRACT + EFFECT
    path.write_text(text, encoding="utf-8")
    for relative, old, key in [("client/ui/main.gd", '"%s · UID %s"', "account_uid_inline"),
                                ("client/ui/reference_ui.gd", '"%s\\nUID %s"', "account_uid_multiline")]:
        path = ROOT / relative
        text = path.read_text(encoding="utf-8").replace(old, 'P.localized("' + key + '")')
        path.write_text(text, encoding="utf-8")
    print(json.dumps({"localized_card_templates": len(COPY)}))


if __name__ == "__main__":
    main()
