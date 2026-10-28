extends RefCounted

## Regression coverage for API/catalog item IDs and both language tables.
class SettlementHost extends Control:
	func _return_from_settlement() -> void:
		pass

func run_test() -> Dictionary:
	var P = load("res://ui/palette.gd")
	var languages: Dictionary = P.languages()
	var required_keys := [
		"word_equipment_fragments", "word_health_potion", "word_warrior_soul",
		"word_priest_soul", "word_mage_soul", "word_guardian_soul",
		"operation_success", "operation_done", "unknown_equipment_slot", "loadout_high_quality_limit", "bag", "use_health_potion",
		"temporary_bag_slots_used", "connected", "connecting_realtime", "restoring_connection"
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
	var remote_copy = load("res://ui/remote_copy.gd")
	var bilingual_notice := {"title": "测试服更新", "body": "中文正文", "titleEn": "Test Server Update", "bodyEn": "English body"}
	var codex = load("res://ui/codex_view.gd")
	var shop_view: Variant = load("res://ui/reference_ui.gd").new()
	var identifiers_ok: bool = P.word("equipment_fragments") == "装备碎片" and P.word("health_potion") == "生命药剂" and P.product_name("EquipmentFragments") == "装备碎片" and P.product_name("health_potion") == "生命药剂" and P.localized("equipment_fragments") == "装备碎片" and P.localized("health_potion") == "生命药剂" and shop_view._product_title("equipment_fragments", {}) == "装备碎片" and shop_view._product_title("health_potion", {}) == "生命药剂" and P.localized_text("warrior_soul") == "勇士之魂" and P.localized_text("背包") == "背包" and P.localized_text("使用生命药剂") == "使用生命药剂" and P.is_unlocalized_english_sentence("The server rejected this request.")
	identifiers_ok = identifiers_ok and P.localized("temporary_bag_slots_used") % [5, 20] == "已用 5 / 20 格" and P.localized_text("已连接") == "已连接"
	identifiers_ok = identifiers_ok and codex.filtered_count(13) == "    筛选结果 13 张" and codex.card_tooltip_suffix(1) == "\n持有 1 · 点击查看详情"
	identifiers_ok = identifiers_ok and remote_copy.field(bilingual_notice, "title") == "测试服更新" and remote_copy.field(bilingual_notice, "body") == "中文正文"
	shop_view.free()
	P.set_language("en")
	identifiers_ok = identifiers_ok and P.localized("bag") == "Bag" and P.localized_text("背包") == "Bag" and P.localized("use_health_potion") == "Use Health Potion" and P.localized_text("使用生命药剂") == "Use Health Potion"
	identifiers_ok = identifiers_ok and P.localized("temporary_bag_slots_used") % [5, 20] == "Used 5 / 20 slots" and P.localized_text("已连接") == "Connected" and P.localized_text("正在连接实时服务") == "Connecting to realtime service" and P.localized_text("正在恢复连接…") == "Restoring connection…"
	identifiers_ok = identifiers_ok and P.localized_text("背包 5 / 20 · 安全格 1") == "Bag 5 / 20 · Safe Slots 1" and P.localized_text("筛选结果 12 张") == "12 filtered cards" and P.localized_text("禁抽 1.5秒") == "Draw blocked 1.5s" and P.localized_text("本次结算暂无可展示的道具") == "No items to display in this settlement"
	identifiers_ok = identifiers_ok and codex.filtered_count(13) == "    13 filtered cards" and codex.card_tooltip_suffix(1) == "\nOwned 1 · Click for details" and P.localized("color_suffix").is_empty() and P.localized("codex_hero_class_tag") % P.localized("class_mage") == "Mage Class Card" and P.localized("codex_current_effect") == "Current: " and P.localized("codex_next_effect") == "Next: "
	identifiers_ok = identifiers_ok and remote_copy.field(bilingual_notice, "title") == "Test Server Update" and remote_copy.field(bilingual_notice, "body") == "English body" and remote_copy.field({"title": "系统通知"}, "title") == "System Mail"
	var previous_settlement: Dictionary = Game.settlement.duplicate(true)
	Game.settlement = {"result": "Dead", "details": {"items": []}}
	var host := SettlementHost.new()
	var settlement_ui: Control = load("res://ui/reference_ui.gd").new()
	load("res://ui/exploration_view.gd").build_settlement(settlement_ui, host)
	var visible_text: Array[String] = []
	for child in settlement_ui.get_children():
		if child is Label or child is Button: visible_text.append(child.text)
	identifiers_ok = identifiers_ok and visible_text.has("Expedition Failed") and visible_text.has("Run Rewards") and visible_text.has("No items to display in this settlement") and visible_text.has("Back") and not visible_text.any(func(value: String): return value.contains("暂无") or value.contains("None"))
	settlement_ui.free()
	host.free()
	Game.settlement = previous_settlement
	var previous_mail: Dictionary = Game.mail.duplicate(true)
	Game.mail = {"items": [{"id": "notice-1", "title": "系统通知", "titleEn": "System Notice", "body": "中文正文", "bodyEn": "English body", "read": true, "attachments": []}], "unreadCount": 0}
	var mail_view: Control = load("res://ui/reference_ui.gd").new()
	var mail_column := VBoxContainer.new()
	mail_view.add_child(mail_column)
	mail_view._build_mail_rows(mail_column)
	var mail_title: Label = mail_column.get_node_or_null("MailRow_notice-1/MailOpenArea/MailTitle")
	var mail_preview: Label = mail_column.get_node_or_null("MailRow_notice-1/MailOpenArea/MailPreviewText")
	identifiers_ok = identifiers_ok and mail_title != null and mail_title.text.contains("System Notice") and mail_preview != null and mail_preview.text == "English body"
	mail_view.free()
	Game.mail = previous_mail
	P.set_language(saved_language)
	return {"ok": missing.is_empty() and identifiers_ok, "message": "Localization tables and snake_case item IDs are covered" if missing.is_empty() and identifiers_ok else "Missing keys: %s" % ", ".join(missing)}
