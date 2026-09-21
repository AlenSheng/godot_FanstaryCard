extends RefCounted

## Regression coverage for API/catalog item IDs and both language tables.
func run_test() -> Dictionary:
	var P = load("res://ui/palette.gd")
	var languages: Dictionary = P.languages()
	var required_keys := [
		"word_equipment_fragments", "word_health_potion", "word_warrior_soul",
		"word_priest_soul", "word_mage_soul", "word_guardian_soul",
		"operation_success", "operation_done", "unknown_equipment_slot", "loadout_high_quality_limit"
	]
	var missing: Array[String] = []
	for language in ["zh-CN", "en"]:
		var strings: Dictionary = languages.get(language, {}).get("strings", {})
		for key in required_keys:
			if str(strings.get(key, "")).is_empty(): missing.append("%s:%s" % [language, key])
	var zh_strings: Dictionary = languages.get("zh-CN", {}).get("strings", {})
	var en_strings: Dictionary = languages.get("en", {}).get("strings", {})
	for key in zh_strings:
		if not en_strings.has(key): missing.append("en:%s" % key)
	for key in en_strings:
		if not zh_strings.has(key): missing.append("zh-CN:%s" % key)
	var saved_language: String = P.language()
	P.set_language("zh-CN")
	var shop_view := load("res://ui/reference_ui.gd").new()
	var identifiers_ok: bool = P.word("equipment_fragments") == "装备碎片" and P.word("health_potion") == "生命药剂" and P.product_name("EquipmentFragments") == "装备碎片" and P.product_name("health_potion") == "生命药剂" and P.localized("equipment_fragments") == "装备碎片" and P.localized("health_potion") == "生命药剂" and shop_view._product_title("equipment_fragments", {}) == "装备碎片" and shop_view._product_title("health_potion", {}) == "生命药剂" and P.localized_text("warrior_soul") == "勇士之魂" and P.is_unlocalized_english_sentence("The server rejected this request.")
	shop_view.free()
	P.set_language(saved_language)
	return {"ok": missing.is_empty() and identifiers_ok, "message": "Localization tables and snake_case item IDs are covered" if missing.is_empty() and identifiers_ok else "Missing keys: %s" % ", ".join(missing)}
