extends "res://tests/gameplay_ui_preview.gd"

const Palette = preload("res://ui/palette.gd")
const SCENARIOS := ["login", "login_notice", "login_notice_bottom", "hall", "hall_priest", "hall_guardian", "prep", "prep_locked", "gear", "gear_compare", "gear_compare_bottom", "gear_numbers", "enhance_numbers", "guardian_remainder", "enhance", "enhance_gear", "enhance_blocked", "shop", "shop_tail", "market", "cards", "cards_owned_details", "cards_unowned_details", "cards_unowned_known_details", "deck", "deck_full", "mail_empty", "mail_long", "mail_attachments", "mail_long_bottom", "settings", "settings_language", "settings_battle", "settings_bottom", "settings_battle_bottom", "confirm", "battle_status", "monster_pool", "monster_pool_full", "monster_pool_empty", "monster_pool_loot", "exploration", "map", "midlayer", "inventory", "inventory_details", "relic", "pve", "pvp", "choice", "ready", "settlement_success", "settlement_death", "recovery", "notice"]
var review_frames: Array = []
var review_checks: Dictionary = {}
var _frame_log: FileAccess
var _initial_lobby: Dictionary = {}

func _ready() -> void:
	get_window().mode = Window.MODE_WINDOWED
	get_window().set_flag(Window.FLAG_NO_FOCUS, true)
	get_window().position = _review_window_position()
	Sound.persist_settings = false
	super._ready()
	Game.set_process(false)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	Game.connection = ""
	$UI._codex_ready = true
	if Game.notice.is_connected($UI._toast): Game.notice.disconnect($UI._toast)
	# This is a silent layout review, not audio playback validation.
	Sound.stop_all()
	Sound._headless_runtime = true
	Sound.set_process(false)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	var profile := OS.get_environment("APPDATA").replace("\\", "/").to_lower()
	assert(not profile.is_empty() and OS.get_user_data_dir().replace("\\", "/").to_lower().begins_with(profile))
	var widths: Array = []
	for item in OS.get_environment("FANTASYCARD_REVIEW_WIDTHS").split(","):
		if item.to_int() in [960, 1280, 1920]: widths.append(item.to_int())
	if widths.is_empty(): widths = [960, 1280, 1920]
	var locales: Array = ["zh-CN", "en"]
	var selected_locales := OS.get_environment("FANTASYCARD_REVIEW_LOCALES")
	if not selected_locales.is_empty():
		locales.clear()
		for code in selected_locales.split(","):
			assert(code in Palette.languages())
			locales.append(code)
	_frame_log = FileAccess.open(output.path_join("frames.original.jsonl"), FileAccess.WRITE)
	_initial_lobby = Game.lobby.duplicate(true)
	var expected := 0
	for locale in locales:
		await _reset_fixture()
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		Game.changed.emit()
		await get_tree().process_frame
		for width in widths:
			get_window().size = Vector2i(width, roundi(width * 9.0 / 16.0))
			get_window().position = _review_window_position()
			await get_tree().process_frame
			for scenario in SCENARIOS:
				if not _selected(scenario): continue
				expected += 1
				await _reset_fixture()
				var rebuild: bool = await _prepare_scene(scenario, locale)
				await _review_capture("%s_%s_%s" % [locale, width, scenario], rebuild)
	_frame_log.close()
	var report := {"fixture_only": true, "actual_game_matches": 0, "languages": locales, "widths": widths,
		"selected_screens": OS.get_environment("FANTASYCARD_REVIEW_SCREENS"), "expected_frames": expected,
		"screenshots": screenshot_count, "render_capture_complete": screenshot_count == expected,
		"legacy_layout_observations": layout_errors, "frames": review_frames, "checks": review_checks,
		"gateway_origin": Game.gateway.base_url, "persist_session": Game.gateway.persist_session,
		"isolated_user_directory": OS.get_user_data_dir(), "whole_visual_acceptance": false}
	report["typography"] = {"ui_oversampling": (Palette.font("body") as FontFile).oversampling,
		"ui_hinting": (Palette.font("body") as FontFile).hinting,
		"cards_msdf": (Palette.scaled_font("body") as FontFile).multichannel_signed_distance_field,
		"cards_msdf_size": (Palette.scaled_font("body") as FontFile).msdf_size}
	var file := FileAccess.open(output.path_join("review.json"), FileAccess.WRITE)
	file.store_string(JSON.stringify(report, "  ")); file.close()
	Sound.stop_all()
	await get_tree().process_frame
	await get_tree().create_timer(0.15).timeout
	get_tree().quit(0 if layout_errors.is_empty() and not review_checks.values().has(false) else 1)

func _selected(scenario: String) -> bool:
	var selected := OS.get_environment("FANTASYCARD_REVIEW_SCREENS")
	if selected.is_empty(): return true
	for value in selected.split(","):
		if scenario == value or scenario.begins_with(value + "_"): return true
	return false

func _frame_checks(frame_name: String) -> Dictionary:
	var result: Dictionary = {}
	for key in review_checks:
		if str(key).begins_with(frame_name + ":"): result[key] = review_checks[key]
	return result

func _gear(id: String, slot: String = "Chest", quality: String = "Orange") -> Dictionary:
	return {"instanceId": id, "slot": slot, "quality": quality, "element": "Earth", "effectAffix": "Bulwark", "secondaryTrait": "DrawInterval", "level": 3, "version": 7, "location": "Inventory", "isBound": false}

func _owned(id: String) -> Dictionary:
	var info: Dictionary = $UI.cards[id]
	return {"cardId": id, "heroClass": info.get("hero_class"), "unlocked": true, "copyCount": 3, "level": 3, "version": 7, "currencyKind": "WarriorSoul" if info.get("hero_class") == null else str(info.hero_class) + "Soul", "craftCost": 12, "dismantleRefund": 3, "canDismantle": true, "canUpgrade": true, "upgradeCost": 80, "upgradeCopyCost": 0}

func _reset_fixture() -> void:
	var audio: Node = $UI.get_node("AudioSettings")
	if is_instance_valid(audio._popup): audio._popup.hide()
	for child in $UI.get_children():
		if child is Window or child.name in ["EquipmentComparisonDialog", "ConfirmationModal", "BattleDetailsModal"]:
			if child.has_method("dismiss"): child.dismiss()
			else: child.queue_free()
	await get_tree().process_frame
	Game.room = {}; Game.settlement = {}; Game.ready_prompt = {}; Game.preparation = {}; Game.relic_details = {}
	Game._settlement_recovery_match_id = ""
	Game.gateway.recovering = false; Game.gateway.online = true
	Game.lobby = _initial_lobby.duplicate(true); Game.hero_class = "Mage"; Game.busy = false
	Game.configuration_error = ""; Game.connection = ""
	$UI.screen = "hall"; $UI.screen_loading = false; $UI.mail_modal_lock = false
	$UI._quality = ""; $UI._search = ""; $UI._codex_card = ""; $UI._codex_ready = true
	$UI._enhance_item = ""; $UI._enhancement_quote_key = ""; $UI._enhancement_quote = {}
	$UI._owned_index_ready = false; $UI._owned_by_id.clear()
	$UI.deck_draft = []; $UI.owned = []
	for id in ["MAG-01", "MAG-04", "GP01", "MAG-10", "C01", "GG01"]: $UI.owned.append(_owned(id))
	Game.lobby.cards = $UI.owned
	$UI.inventory = {"equipments": [_gear("review-head", "Head", "Purple"), _gear("review-chest"), _gear("review-hands", "Hands", "Blue")], "consumables": {"healthPotionCount": 2, "advancedBagCount": 1, "topBagCount": 1}}
	Game.lobby.inventory = $UI.inventory
	$UI.shop = _shop_fixture(); Game.lobby.shop = $UI.shop
	$UI._sync_account_session(); $UI.gear_draft = ["review-head", "review-chest", "review-hands", null, null]
	var needs_card_grid := OS.get_environment("FANTASYCARD_REVIEW_SCREENS").is_empty()
	for selected in OS.get_environment("FANTASYCARD_REVIEW_SCREENS").split(","):
		if selected.begins_with("cards") or selected.begins_with("deck"): needs_card_grid = true
	if not needs_card_grid: $UI._card_pool.set_process(false)
	$UI._shop_inventory_ready = true; $UI.listings = []
	$UI.tips_overlay.clear()
	for key in ["inventory_open", "inventory_selected", "relic_pile", "relic_selected", "exploration_map_open", "pending_move", "mail_selected_id"]:
		if $UI.has_meta(key): $UI.remove_meta(key)

func _render_base() -> void:
	$UI._render()
	await get_tree().process_frame
	await get_tree().process_frame

func _prepare_scene(scenario: String, locale: String) -> bool:
	match scenario:
		"login": Game.lobby = {}
		"login_notice", "login_notice_bottom":
			Game.lobby = {}
			Game.authentication_reason = Palette.localized("login_timeout")
			Game.server_info["announcement"] = {"title": "Relicbound Test Server Update and Traveler Notices" if locale == "en" else "遗境行者测试服更新与旅人公告", "body": ("Dear Travelers,\n\nThe test server has recently been updated:\n\n1. After extraction, wait for server settlement and the run results.\n2. Results include the items earned during the run and equipped gear.\n3. Log Out returns to the login screen.\n4. Common panels leave clear space inside their decorative borders.\n\nThank you for playing!" if locale == "en" else "亲爱的旅人：\n\n测试服近期已更新：\n\n1. 撤离后等待服务器结算并显示本局结果。\n2. 结算包含本局获得的物品和穿戴装备。\n3. 切换账号后返回登录界面。\n4. 通用框的内容与装饰边框之间保留留白。\n\n感谢参与测试！")}
		"hall_priest": Game.hero_class = "Priest"
		"hall_guardian": Game.hero_class = "Guardian"
		"prep", "gear", "shop", "cards", "deck": $UI.screen = scenario
		"market":
			$UI.screen = "market"
			for index in range(4): $UI.listings.append({"listingId": "review-listing-%s" % index, "sellerId": "preview-player" if index == 0 else "other-review-player", "priceGold": 123 + index, "version": 7, "equipment": _gear("market-%s" % index, ["Head", "Chest", "Hands", "Feet"][index])})
		"prep_locked":
			$UI.screen = "prep"
			var locked: Array = []; locked.resize(20); locked.fill("GUA-01")
			Game.preparation = {"snapshot": {"heroClass": "Guardian", "maximumHp": 100, "cardIds": locked, "equipmentIds": [], "equipmentSnapshots": [], "classWeaponLevel": 4, "backpackTier": "Top", "backpackCapacity": 36, "safeSlotIndexes": [33, 34, 35], "potionCount": 2}}
		"gear_compare", "gear_compare_bottom":
			$UI.screen = "gear"; await _render_base()
			$UI._show_equipment_details(_gear("review-selected", "Head"))
			if scenario.ends_with("_bottom"):
				await get_tree().process_frame
				await get_tree().process_frame
				$UI.get_node("EquipmentComparisonDialog").find_child("ComparisonContentScroll", true, false).set_deferred("scroll_vertical", 100000)
			return false
		"gear_numbers", "enhance_numbers", "guardian_remainder":
			Game.room = _room_fixture(); await _render_base()
			if scenario == "guardian_remainder":
				Game.room.player.numerical_state = {"guardian_policy": "FractionalRemainder", "guardian_remainder_tenths": 4}
				load("res://ui/numerical_details.gd").show_remainder($UI)
			else:
				load("res://ui/numerical_details.gd").show_compare($UI, Game.room.player.get("equipment", []), _gear("review-selected", "Head"), scenario == "enhance_numbers")
			return false
		"monster_pool", "monster_pool_full", "monster_pool_empty", "monster_pool_loot":
			Game.room = _room_fixture(); Game.room.allowed_actions.append("monster.choose")
			var active: Array = []
			for index in range(5 if scenario == "monster_pool_full" else 1): active.append({"instance_id": "active-%s" % index, "card_id": "M-FIREBAT", "level": 3})
			Game.room.player.monster_pool = {"capacity": 5, "active": active, "pending": [] if scenario == "monster_pool_empty" else [{"instance_id": "candidate", "card_id": "M-BOXSPIRIT", "level": 4}]}
			await _render_base()
			if scenario == "monster_pool_loot": load("res://ui/monster_pool_view.gd").loot($UI, [_item(90), _item(91)])
			else: load("res://ui/monster_pool_view.gd").open($UI)
			return false
		"enhance", "enhance_gear", "enhance_blocked":
			$UI.screen = "enhance"
			if scenario == "enhance_gear": $UI._enhance_item = "review-chest"
			var quote_id := "review-chest:7" if scenario == "enhance_gear" else "Mage:1"
			$UI._enhancement_quote_key = quote_id
			$UI._enhancement_quote = {"fragmentCost": 125, "materialCount": 1, "availableMaterialCount": 3, "canEnhance": scenario != "enhance_blocked", "nextLevel": 4 if scenario == "enhance_gear" else 3, "expectedVersion": 7 if scenario == "enhance_gear" else 1}
		"shop_tail":
			$UI.screen = "shop"; await _render_base()
			$UI._reference.get_node("ShopScroll").scroll_horizontal = 10000; return false
		"cards_owned_details", "cards_unowned_details", "cards_unowned_known_details":
			if scenario == "cards_unowned_known_details":
				var quote := _owned("MAG-02"); quote.unlocked = false; quote.copyCount = 0; quote.level = 0
				$UI.owned.append(quote); Game.lobby.cards = $UI.owned; $UI._owned_index_ready = false; $UI._owned_by_id.clear()
			$UI.screen = "cards"; await _render_base()
			load("res://ui/codex_view.gd")._open_details($UI._reference, $UI, "MAG-01" if scenario == "cards_owned_details" else "MAG-02", $UI._reference.get_node("CodexScroll")); return false
		"deck_full":
			$UI.screen = "deck"; $UI.owned = []
			for id in $UI.cards:
				var info: Dictionary = $UI.cards[id]
				if not info.get("is_codex", false) or info.get("hero_class") not in [null, "Mage"]: continue
				$UI.owned.append(_owned(id)); $UI.deck_draft.append(id)
				if $UI.deck_draft.size() == 20: break
			Game.lobby.cards = $UI.owned; $UI._owned_index_ready = false; $UI._owned_by_id.clear()
		"mail_empty", "mail_long", "mail_attachments", "mail_long_bottom":
			Game.mail = {"unreadCount": 0, "items": []}
			if scenario != "mail_empty":
				var title := "Expedition rewards, maintenance compensation and a very long announcement title" if locale == "en" else "探索奖励与维护补偿以及特别长的邮件标题排版验证"
				var body := "All earned equipment and materials are available below. Open each attachment to review its details. " if locale == "en" else "所有探索装备和材料均列于下方，请查看每项附件的详情。"
				for index in range(12): Game.mail.items.append({"id": "review-mail-%s" % index, "title": title + " %s" % index, "body": body.repeat(16), "sender": "System" if locale == "en" else "系统", "read": true, "claimed": false, "attachments": [{"kind": "Gold", "amount": 123456}, {"kind": "EquipmentFragments", "amount": 25}, {"kind": "HealthPotion", "amount": 2}]})
			await _render_base(); $UI.mail_modal_lock = true; $UI._reference._mail()
			if scenario != "mail_empty": $UI._reference._mail_select(Game.mail.items[0])
			if scenario in ["mail_attachments", "mail_long_bottom"]:
				await get_tree().process_frame
				await get_tree().process_frame
				var detail_scroll: ScrollContainer = $UI._reference.get_node("MailModal").find_child("MailDetailScroll", true, false)
				if detail_scroll != null:
					var attachment_grid: GridContainer = detail_scroll.find_children("*", "GridContainer", true, false)[0]
					detail_scroll.set_deferred("scroll_vertical", maxi(0, int(attachment_grid.position.y) - 80) if scenario == "mail_attachments" else 100000)
			return false
		"settings", "settings_language", "settings_battle", "settings_bottom", "settings_battle_bottom":
			if scenario.begins_with("settings_battle"): Game.room = _room_fixture(); Game.room.player.phase = "Pve"; Game.room.allowed_actions.append("battle.abandon")
			await _render_base(); $UI.get_node("AudioSettings").show_settings()
			if scenario == "settings_language":
				await get_tree().process_frame
				var choices: Array = $UI.get_node("AudioSettings")._popup.find_children("*", "OptionButton", true, false)
				if not choices.is_empty(): choices[0].show_popup()
			if scenario.ends_with("_bottom"):
				await get_tree().process_frame
				await get_tree().process_frame
				$UI.get_node("AudioSettings")._popup.find_child("AudioSettingsScroll", true, false).set_deferred("scroll_vertical", 100000)
			return false
		"confirm":
			await _render_base(); $UI._confirm(Palette.localized("battle_abandon_warning"), func(): pass, {"title": "battle_abandon_title", "confirm_text": "battle_abandon_confirm", "tall": true}); return false
		"battle_status":
			Game.room = _room_fixture(); await _render_base(); $UI._show_battle_details(_status_fixture()); return false
		"exploration", "map", "midlayer", "inventory", "inventory_details", "relic", "pve", "pvp", "choice", "notice":
			Game.room = _room_fixture()
			if scenario in ["map", "midlayer"]:
				Game.room.map = []
				for y in range(6):
					for x in range(6): Game.room.map.append({"row": y, "column": x, "has_spring": y == 0 and x == 3, "is_boss": y == 2 and x == 2})
				Game.room.legal_moves = [{"row": 2, "column": 2}, {"row": 3, "column": 3}]; Game.room.allowed_actions.append("room.move")
			if scenario in ["pve", "pvp"]:
				Game.room.player.phase = "Pve" if scenario == "pve" else "Pvp"; Game.room.allowed_actions += ["battle.play_cards", "battle.select_target", "duel.leave", "duel.escape"]
				Game.room.pve = {"battle_id": "review-battle", "current_target_id": "fire-bat", "monsters": [{"monster_id": "fire-bat", "maximum_hp": 44, "hp": 31, "shield": 8, "intent_kind": "Attack", "intent_element": "Fire", "intent_value": 5}]}
				if scenario == "pve": Game.room.player.combat = {"hp": 80, "maximum_hp": 70, "shield": 6}
				else: Game.room.duel = {"duel_id": "review-duel", "opponent_id": "review-opponent", "opponent": {"hero_class": "Guardian", "hp": 60, "maximum_hp": 100, "shield": 8}, "escape_remaining_ms": 0}
			if scenario == "choice":
				Game.room.player.phase = "Choice"; Game.room.allowed_actions = ["choice.pick", "choice.refresh"]
				Game.room.reward_choice = {"refresh_count": 0, "options": [{"option_id": "equipment", "kind": 1, "quantity": 1}, {"option_id": "fragments", "kind": 2, "quantity": 18}, {"option_id": "heal", "kind": 3, "quantity": 1, "heal_percent": 14}]}
			await _render_base()
			if scenario in ["inventory", "inventory_details", "relic"]: $UI.set_meta("inventory_open", true)
			if scenario == "inventory_details": $UI.set_meta("inventory_selected", "pack-35")
			if scenario == "relic":
				Game.relic_details = {"pile-a": {"pile_id": "pile-a", "owner_name": "A Very Long Expedition Traveler Name" if locale == "en" else "一位来自漫长旅途的探索者", "version": 7, "items": [_item(90), _item(91)]}}
				$UI.set_meta("relic_pile", "pile-a"); $UI.set_meta("relic_selected", "pack-90")
			if scenario in ["map", "midlayer"]: $UI.set_meta("exploration_map_open", true)
			if scenario == "midlayer": $UI.set_meta("pending_move", Vector2i(2, 2))
			if scenario == "notice": $UI._toast(Palette.localized("request_not_sent") + " " + Palette.localized("connection_interrupted")); return false
		"ready": Game.ready_prompt = {"ready_players": 2, "required_players": 4, "deadline_unix_ms": int(Time.get_unix_time_from_system() * 1000) + 30000}
		"settlement_success", "settlement_death":
			Game.settlement = {"result": "Extracted" if scenario == "settlement_success" else "Dead", "settlementId": "review-settlement", "details": {"items": [{"item": {"kind": "HealthPotion", "quantity": 2}}, {"item": {"kind": "EquipmentFragments", "quantity": 123456}}, {"item": _item(35)}]}}
		"recovery": Game._settlement_recovery_match_id = "review-recovery"
	return true

func _review_window_position() -> Vector2i:
	return Vector2i.ZERO if OS.get_environment("FANTASYCARD_REVIEW_ISOLATED_DESKTOP") == "1" else Vector2i(-32000, -32000)

func _review_capture(frame_name: String, rebuild: bool = true) -> void:
	if (frame_name.ends_with("_login") or frame_name.contains("_login_notice")):
		# Login uses the normal shell, rather than the in-game reference view.
		$UI._render()
		await get_tree().create_timer(0.4).timeout
		if frame_name.ends_with("_login_notice_bottom"):
			for scroll_name in ["LoginControlsScroll", "AnnouncementScroll"]:
				$UI.find_child(scroll_name, true, false).scroll_vertical = 100000
			await get_tree().process_frame
		RenderingServer.force_draw(false)
		var error := get_viewport().get_texture().get_image().save_png(output + "/" + frame_name + ".png")
		if error == OK: screenshot_count += 1
		else: layout_errors.append("Screenshot save failed: " + frame_name)
	else:
		await _capture(frame_name, rebuild)
	var texts: Array = []
	_collect_text($UI, texts)
	for entry in texts:
		if str(entry.path).get_file().begins_with("EquippedCaption_"):
			review_checks[frame_name + ": readable " + str(entry.path).get_file()] = float(entry.effective_font_size) >= 12.0
		if str(entry.path).begins_with("EquipmentComparisonDialog/") and entry.type == "Label" and not str(entry.path).ends_with("/Quantity"):
			review_checks[frame_name + ": comparison text " + str(entry.path)] = float(entry.effective_font_size) >= 12.0
		if str(entry.path).contains("Slot_C01/") and str(entry.path).ends_with("/CardName"):
			review_checks[frame_name + ": readable common-card name"] = float(entry.effective_font_size) >= 12.0
		if str(entry.path).contains("Slot_C01/") and str(entry.path).ends_with("/CardEffect"):
			review_checks[frame_name + ": readable common-card effect"] = float(entry.effective_font_size) >= 12.0
	if (frame_name.ends_with("_login") or frame_name.contains("_login_notice")):
		var title: Label = $UI._game_title
		review_checks[frame_name + ": readable login title"] = title.get_theme_font_size("font_size") >= 20 and title.get_visible_line_count() > 0
		for panel_name in ["LoginPanel", "AnnouncementPanel"]:
			var panel: PanelContainer = $UI.find_child(panel_name, true, false)
			_check_content_insets(frame_name + ": " + panel_name, panel, panel.get_child(0))
		var announcement_title: Label = $UI.find_child("AnnouncementTitle", true, false)
		review_checks[frame_name + ": complete announcement title"] = announcement_title.get_visible_line_count() == announcement_title.get_line_count()
	if frame_name.contains("_settings"):
		var popup: PopupPanel = $UI.get_node("AudioSettings")._popup
		if is_instance_valid(popup):
			var settings_scroll: ScrollContainer = popup.find_child("AudioSettingsScroll", true, false)
			_check_content_insets(frame_name + ": settings", popup, settings_scroll)
			var settings_content: Control = popup.find_child("SettingsContent", true, false)
			var scrollbar := settings_scroll.get_v_scroll_bar()
			review_checks[frame_name + ": scrollbar stays clear of settings controls"] = settings_content.get_global_rect().end.x + 15.0 <= scrollbar.get_global_rect().position.x
	if frame_name.ends_with("_shop") or frame_name.ends_with("_shop_tail"):
		_check_shop()
		for product in $UI._reference.get_node("ShopScroll/ShopProductRow").get_children():
			var detail: Label = product.get_node("ShopDetail")
			var purchase: Button = product.get_node("Purchase")
			review_checks[frame_name + ": shop details clear purchase " + str(product.name)] = detail.get_rect().end.y + 4.0 <= purchase.position.y and detail.get_visible_line_count() == detail.get_line_count()
	if frame_name.ends_with("_cards") or frame_name.ends_with("_deck"):
		var grid_name := "CardGrid" if frame_name.ends_with("_cards") else "DeckOwnedGrid"
		var grid: Control = $UI._reference.find_child(grid_name, true, false)
		review_checks[frame_name + ": populated visible cards"] = grid != null and not grid.find_children("*", "Button", true, false).is_empty()
		for node in $UI._reference.find_children("*", "Button", true, false):
			if not str(node.name).begins_with("Filter_") and not str(node.name).begins_with("DeckFilter_"): continue
			var style: StyleBox = node.get_theme_stylebox("normal")
			var available: float = node.size.x - style.get_content_margin(SIDE_LEFT) - style.get_content_margin(SIDE_RIGHT)
			var text_width: float = node.get_theme_font("font").get_string_size(node.text, HORIZONTAL_ALIGNMENT_LEFT, -1, node.get_theme_font_size("font_size")).x
			review_checks[frame_name + ": complete " + str(node.name)] = text_width <= available
	var frame := {"name": frame_name, "language": Palette.language(),
		"window_size": [get_window().size.x, get_window().size.y],
		"viewport_size": [get_viewport().get_visible_rect().size.x, get_viewport().get_visible_rect().size.y],
		"texts": texts, "checks": _frame_checks(frame_name)}
	review_frames.append(frame)
	_frame_log.store_line(JSON.stringify(frame))
	_frame_log.flush()
	print(JSON.stringify({"frame": frame_name, "screenshots": screenshot_count}))

func _check_content_insets(key: String, panel: Node, child: Control) -> void:
	var style: StyleBox = panel.get_theme_stylebox("panel")
	var padding := Vector4(style.get_content_margin(SIDE_LEFT), style.get_content_margin(SIDE_TOP), style.get_content_margin(SIDE_RIGHT), style.get_content_margin(SIDE_BOTTOM))
	var inner := Rect2(Vector2(padding.x, padding.y), Vector2(panel.size) - Vector2(padding.x + padding.z, padding.y + padding.w))
	review_checks[key + ": contents stay inside decorative border"] = inner.encloses(child.get_rect())

func _collect_text(root: Node, rows: Array) -> void:
	if root is Control and not root.is_visible_in_tree(): return
	if (root is Label or root is Button) and not root.text.is_empty():
		var rect: Rect2 = root.get_global_rect()
		var visible_rect := rect
		var ancestor := root.get_parent()
		while ancestor is Control:
			if ancestor.clip_contents:
				visible_rect = visible_rect.intersection(ancestor.get_global_rect())
			ancestor = ancestor.get_parent()
		if visible_rect.has_area():
			var typeface: Font = root.get_theme_font("font")
			var font_size: int = root.get_theme_font_size("font_size")
			var scale: Vector2 = root.get_global_transform().get_scale()
			var pixel_scale := float(get_window().size.y) / get_viewport().get_visible_rect().size.y
			var value: String = root.text
			rows.append({"path": str($UI.get_path_to(root)), "type": root.get_class(),
				"text": value, "rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y],
				"visible_rect": [visible_rect.position.x, visible_rect.position.y, visible_rect.size.x, visible_rect.size.y],
				"font_size": font_size, "effective_font_size": font_size * absf(scale.y) * pixel_scale,
				"single_line_width": typeface.get_string_size(value, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x,
				"font_color": root.get_theme_color("font_disabled_color" if root is Button and root.disabled else "font_color").to_html(),
				"disabled": root.disabled if root is Button else false,
				"lines": root.get_line_count() if root is Label else 1,
				"visible_lines": root.get_visible_line_count() if root is Label else 1})
	for child in root.get_children():
		_collect_text(child, rows)
