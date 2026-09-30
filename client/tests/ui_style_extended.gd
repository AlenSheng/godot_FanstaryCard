extends "res://tests/ui_style_audit.gd"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().create_timer(0.5).timeout
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540), Vector2i(1440, 1080), Vector2i(1920, 810)]:
			get_window().size = resolution
			await get_tree().process_frame
			await _extended("%s_%sx%s" % [locale, resolution.x, resolution.y])
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "fixture_only": true,
		"source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"),
		"captures": captures, "screenshots": captures.size(), "checks": checks,
		"errors": audit_errors, "text_observations": text_observations,
		"limitations": "Actual Godot rendering and offline local UI actions, no server transaction or delivery verification."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)

func _extended(suffix: String) -> void:
	_reset()
	$UI.screen = "hall"
	Game.mail = {"unreadCount": 0, "items": [
		{"id": "fixture-long-mail", "title": "Long runtime mail title · 云端奖励内容", "body": "这是一段很长的运行时邮件正文，附件和操作按钮应该始终可达。\nA long runtime message must wrap and scroll without covering its actions.\n".repeat(15), "sender": "System", "read": true, "claimed": false, "attachments": [{"kind": "Gold", "amount": 500}, {"kind": "EquipmentFragments", "amount": 20}, {"kind": "HealthPotion", "amount": 2}]},
		{"id": "fixture-claimed-mail", "title": "Claimed · 已领取", "body": "Reward already claimed.", "sender": "System", "read": true, "claimed": true, "attachments": [{"kind": "Gold", "amount": 100}]}
	]}
	$UI._render()
	$UI._reference._mail()
	await _take("mail_long_" + suffix, false)
	var detail_scroll: ScrollContainer = $UI._reference.find_child("MailDetailScroll", true, false)
	if detail_scroll != null:
		detail_scroll.scroll_vertical = 100000
		await _take("mail_bottom_" + suffix, false)
		_check_audit(detail_scroll.scroll_vertical > 0, "mail_long_scroll_" + suffix)
		var actions: HBoxContainer = detail_scroll.get_parent().get_child(1)
		_check_audit(detail_scroll.get_parent().get_global_rect().encloses(actions.get_global_rect()), "mail_actions_inside_" + suffix)
	elif OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
		audit_errors.append("Missing mail detail scroll " + suffix)
	if detail_scroll == null: await _take("mail_bottom_" + suffix, false)
	$UI.set_meta("mail_selected_id", "fixture-claimed-mail")
	$UI._reference._refresh_mail_detail($UI._reference.get_node("MailModal"))
	await _take("mail_claimed_" + suffix, false)
	$UI._render()
	$UI._reference._mail()
	await _take("mail_reopen_" + suffix, false)
	_check_audit($UI._reference.find_children("MailModal", "Control", true, false).size() == 1, "mail_reopen_single_" + suffix)
	$UI.screen = "gear"
	var current := _fixture_gear("current", "Head", "Purple", "Fire", "Bulwark")
	var selected := _fixture_gear("selected", "Head", "Orange", "Water", "Piercing")
	$UI.inventory.equipments = [current, selected]
	$UI._render()
	for iteration in range(2):
		var comparison := Comparison.new()
		$UI.add_child(comparison)
		comparison.open(selected, current, [current], func(): action_calls += 1, Palette.localized("confirm"))
		await get_tree().process_frame
		await get_tree().process_frame
		await get_tree().create_timer(0.15).timeout
		var scroll: ScrollContainer = comparison.find_child("ComparisonScroll", true, false)
		if scroll != null:
			scroll.scroll_vertical = 100000
			await _take("compare_bottom_%s_%s" % [iteration, suffix], false)
			_check_audit(scroll.scroll_vertical > 0, "comparison_scroll_%s_%s" % [iteration, suffix])
			var confirm: Control = comparison.find_child("ConfirmEquip", true, false)
			_check_audit(comparison.get_node("ComparisonShell").get_global_rect().encloses(confirm.get_global_rect()), "comparison_action_inside_%s_%s" % [iteration, suffix])
		else:
			await _take("compare_bottom_%s_%s" % [iteration, suffix], false)
			if OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1": audit_errors.append("Missing comparison scroll " + suffix)
		comparison.find_child("CancelEquip", true, false).pressed.emit()
		await get_tree().process_frame
		_check_audit(action_calls == 0 and not is_instance_valid(comparison), "comparison_cancel_%s_%s" % [iteration, suffix])
	$UI.screen = "enhance"
	selected.location = "Inventory"
	selected.version = 7
	selected.level = 3
	$UI._enhance_item = "selected"
	$UI._enhancement_quote_key = "selected:7"
	$UI._enhancement_quote = {"fragmentCost": 125, "materialCount": 1, "availableMaterialCount": 2, "canEnhance": true, "nextLevel": 4, "expectedVersion": 7}
	await _take("enhancement_quote_" + suffix)
	$UI._enhancement_quote = {"error": true}
	await _take("enhancement_error_" + suffix)
	selected.level = 5
	$UI.inventory.equipments = [selected]
	await _take("enhancement_max_" + suffix)
	$UI.screen = "market"
	$UI.listings = [
		{"listingId": "fixture-sale", "sellerId": "another-player", "priceGold": 888, "version": 1, "equipment": selected},
		{"listingId": "fixture-own", "sellerId": "ui-audit", "priceGold": 99999999, "version": 1, "equipment": current}
	]
	await _take("market_populated_" + suffix)
	var choices: OptionButton = $UI._reference.find_children("*", "OptionButton", true, false)[0]
	var popup := choices.get_popup()
	popup.position = Vector2i(choices.get_global_rect().position + Vector2(0, choices.size.y))
	popup.popup()
	await _take("market_dropdown_" + suffix, false)
	_check_audit(popup.visible, "dropdown_visible_" + suffix)
	popup.hide()
	for hero in ["Priest", "Mage", "Guardian"]:
		Game.room = _room_fixture()
		Game.room.player.hero_class = hero
		Game.room.player.phase = "Pve"
		Game.room.player.battle_status = _status_fixture({"Priest": "LinYuan", "Mage": "FenXian", "Guardian": "ZaiYue"}[hero])
		Game.room.player.battle_status.combo = 5
		Game.room.player.battle_status.charge_level = 5
		Game.room.player.battle_status.bonuses.append_array([{"key": "passive_heal", "value": "0.36"}, {"key": "passive_control", "value": "0.27"}])
		Game.room.allowed_actions += ["battle.play_cards", "battle.select_target"]
		Game.room.player.hand = []
		Game.selected_cards = []
		for id in ["C01", "C06", "C09", "C15", {"Priest": "PRI-06", "Mage": "MAG-06", "Guardian": "GUA-06"}[hero]]:
			Game.room.player.hand.append({"instance_id": id, "card_id": id})
			Game.selected_cards.append(id)
		Game.room.pve = {"battle_id": "full-passive-preview", "current_target_id": "metal-guard", "monsters": [{"monster_id": "metal-guard", "hp": 24, "maximum_hp": 200, "shield": 8, "intent_kind": "Shield", "intent_element": "None", "intent_value": 12}]}
		Game.combat_preview = Game._calculate_combat_preview(Game.selected_cards)
		Game.combat_preview.damage_segments = []
		for kind in ["Fire", "Water", "Wood", "Earth", "Metal", "Direct"]: Game.combat_preview.damage_segments.append({"kind": kind, "amount": 19})
		Game.combat_preview.heal = 9
		Game.combat_preview.shield_gain = 8
		await _take("passive_six_" + hero.to_lower() + "_" + suffix)
		if OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
			var passive_panel: Control = $UI._reference.get_node("PlayerPassive_" + hero)
			var preview_panel: Control = $UI._reference.get_node("CombatPreview")
			_check_audit(not passive_panel.get_global_rect().intersects(preview_panel.get_global_rect()), "passive_preview_separate_" + hero + "_" + suffix)
			for node_name in ["PlayerPassivePrefix", "PlayerPassiveTitle", "PlayerPassiveDescription"]:
				var label: Label = $UI._reference.get_node(node_name)
				_check_audit(not label.text.is_empty() and label.get_line_count() == label.get_visible_line_count() and label.get_theme_font_size("font_size") >= 16 and passive_panel.get_global_rect().encloses(label.get_global_rect()), node_name + "_" + hero + "_" + suffix)
