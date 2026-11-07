extends "res://tests/gameplay_ui_preview.gd"

const Palette = preload("res://ui/palette.gd")
const TextAudit = preload("res://tests/localization_text_audit.gd")
const SCENARIOS := ["login", "login_language", "login_notice", "login_notice_bottom", "hall", "hall_priest", "hall_guardian", "prep", "prep_locked", "gear", "gear_compare", "gear_compare_bottom", "gear_numbers", "enhance_numbers", "guardian_remainder", "enhance", "enhance_gear", "enhance_blocked", "shop", "shop_tail", "market", "cards", "cards_owned_details", "cards_unowned_details", "cards_unowned_known_details", "deck", "deck_full", "mail_empty", "mail_long", "mail_attachments", "mail_long_bottom", "settings", "settings_battle", "settings_bottom", "settings_battle_bottom", "confirm", "battle_status", "monster_pool", "monster_pool_full", "monster_pool_empty", "monster_pool_loot", "exploration", "map", "midlayer", "inventory", "inventory_details", "relic", "pve", "pvp", "pve_full_hand", "pvp_full_hand", "pve_priest", "pve_guardian", "pvp_priest", "pvp_guardian", "choice", "ready", "settlement_success", "settlement_death", "recovery", "notice", "mail_template_seed_gold", "mail_template_seed_souls", "mail_template_seed_white_fire", "mail_template_seed_green_water", "mail_template_seed_blue_earth", "mail_template_seed_purple_wood", "mail_template_seed_orange_metal", "mail_template_seed2_mixed_set", "mail_template_seed2_fragments", "mail_template_item_reclamation", "mail_template_item_reclamation_bottom", "login_notice_authored", "pvp_name_fallback", "relic_name_fallback"]
const SEASON_SCENARIOS := ["prep_season", "prep_season_borrowed", "prep_season_locked"]
const RED_SCENARIOS := ["c11_waiting","c11_pending","c11_pending_bottom","c11_replace","c11_replace_bottom","c11_confirm","c11_confirm_bottom"]
const MARKET_SCENARIOS := ["c12_gold","c12_diamond","c12_own","c12_sell","c12_relist","c12_confirm","c12_returns","c12_error","c12_hall"]
const SHOP_SCENARIOS := ["c13_shop","c13_tail","c13_shared","c13_closed","c13_copy","c13_copy_missing","c13_confirm","c13_copy_confirm","c13_upgrade_confirm"]
const ACTIVITY_SCENARIOS := ["c14_hall","c14_active","c14_spent","c14_upcoming","c14_late","c14_unavailable","c14_empty","c14_exchange_confirm","c14_claim_confirm"]
const JOURNEY_SCENARIOS := ["c15_entry","c15_active","c15_catchup","c15_complete","c15_upcoming","c15_archive","c15_disabled","c15_unavailable","c15_none","c15_error"]
const HISTORICAL_SCENARIOS := ["historical_gear_none","ready_removed_equipment","ready_removed_timeout"]
const REFRESH_SCENARIOS := ["refresh_original","refresh_exhausted","refresh_unavailable"]
const PREPARATION_SOURCE_SCENARIOS := ["prep_source_owned", "prep_source_borrowed", "prep_source_locked", "prep_source_unavailable", "prep_source_deck", "prep_source_deck_bottom", "prep_source_menu", "prep_current_d1"]
const THEME_SCENARIOS := ["c16_fire_info","c16_wood_info","c16_earth_info","c16_metal_info","c16_water_info","c16_wood_regen","c16_map","c16_action","c16_pvp","c16_choice"]
const EQUIPMENT_SCENARIOS := ["c05_gear","c05_prep","c05_enhance","c05_compare","c05_numbers","c05_inventory","c05_inventory_details","c05_relic","c06_armor","c06_weapon","c06_material","c06_confirm","c06_error","c07_entry","c07_make","c07_orange","c07_locked","c07_confirm","c07_notjoined","c07_error","c08_list","c08_learn","c08_preview","c08_confirm","c08_blocked","c08_numbers","c08_market","c08_preview_bottom","c09_default","c09_preference","c09_locked","c09_info"]
var review_frames: Array = []
var review_checks: Dictionary = {}
var _frame_log: FileAccess
var _initial_lobby: Dictionary = {}
var _text_auditor: TextAudit

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
	if Game.changed.is_connected(Sound._sync_context): Game.changed.disconnect(Sound._sync_context)
	if Game.sound_requested.is_connected(Sound._handle_sound_request): Game.sound_requested.disconnect(Sound._handle_sound_request)
	Sound.stop_music()
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
	var registry: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(Palette.LOCALE_REGISTRY_PATH))
	var chinese_pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(registry.languages["zh-CN"].path)))
	for locale in locales:
		await _reset_fixture()
		Game.lobby = {}
		await _render_base()
		var selector: Control = $UI.get_node("LoginLanguageSelector")
		selector.open()
		await get_tree().process_frame
		var choice: Button = selector.find_child("LanguageChoice_" + str(locale).replace("-", "_"), true, false)
		assert(choice != null)
		choice.pressed.emit()
		await get_tree().process_frame
		assert(Palette.language() == locale)
		var preferences := ConfigFile.new()
		assert(preferences.load(Palette.LANGUAGE_SETTINGS_PATH) == OK and str(preferences.get_value("ui", "language", "")) == locale)
		Game.lobby = _initial_lobby.duplicate(true)
		var target_pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(str(registry.languages[locale].path)))
		_text_auditor = TextAudit.new(locale, chinese_pack, target_pack)
		$UI.theme = Palette.theme()
		Game.changed.emit()
		await get_tree().process_frame
		for width in widths:
			get_window().size = Vector2i(width, roundi(width * 9.0 / 16.0))
			get_window().position = _review_window_position()
			await get_tree().process_frame
			for scenario in SCENARIOS + SEASON_SCENARIOS + EQUIPMENT_SCENARIOS + RED_SCENARIOS + MARKET_SCENARIOS + SHOP_SCENARIOS + ACTIVITY_SCENARIOS + JOURNEY_SCENARIOS + THEME_SCENARIOS + HISTORICAL_SCENARIOS + REFRESH_SCENARIOS + PREPARATION_SOURCE_SCENARIOS:
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
	Sound.stop_all(); Sound.stop_music()
	await get_tree().create_timer(0.15).timeout
	get_tree().quit(0 if layout_errors.is_empty() and not review_checks.values().has(false) else 1)

func _selected(scenario: String) -> bool:
	var selected := OS.get_environment("FANTASYCARD_REVIEW_SCREENS")
	if selected.is_empty(): return true
	for value in selected.split(","):
		if value.begins_with("="):
			if scenario == value.substr(1): return true
			continue
		if scenario == value or scenario.begins_with(value + "_"): return true
	return false

func _check_login_language(frame_name: String, on_login: bool) -> void:
	var selector: Control = $UI.get_node("LoginLanguageSelector")
	review_checks[frame_name + ": language selection only before login"] = selector.visible == on_login
	if on_login:
		var language_button: Button = selector.get_node("LoginLanguageButton")
		review_checks[frame_name + ": login language control within viewport"] = $UI.get_viewport_rect().grow(0.5).encloses(language_button.get_global_rect())
		review_checks[frame_name + ": login language clear of status"] = language_button.get_global_rect().position.y >= $UI.status_label.get_global_rect().end.y + 15
		if frame_name.ends_with("_login_language"):
			var panel: PanelContainer = selector.get_node("LoginLanguageListPanel")
			var scroll: ScrollContainer = panel.get_node("LoginLanguageListScroll")
			_check_content_insets(frame_name + ": login language list", panel, scroll)
			review_checks[frame_name + ": language list within viewport"] = $UI.get_viewport_rect().grow(0.5).encloses(panel.get_global_rect())
			review_checks[frame_name + ": all registered language choices"] = scroll.get_node("LoginLanguageChoices").get_child_count() == Palette.languages().size()
			for choice in scroll.get_node("LoginLanguageChoices").get_children():
				review_checks[frame_name + ": readable language choice " + str(choice.name)] = choice.get_theme_font_size("font_size") >= 24

func _check_shop_season_scene(frame_name: String) -> void:
	if frame_name.contains("_c13_copy") or frame_name.ends_with("_c13_upgrade_confirm"):
		var modal: Control=$UI._reference.get_node("CardDetails")
		var copy: Button=modal.get_node("CopyCard");var upgrade: Button=modal.get_node("UpgradeCard");var cost: Label=modal.get_node("UpgradeCopyCost")
		review_checks[frame_name+": permanent copy action visible and funded"]=copy.is_visible_in_tree() and not copy.disabled
		review_checks[frame_name+": material requirement visible"]=cost.is_visible_in_tree() and cost.text.contains("1")
		review_checks[frame_name+": missing material controls upgrade"]=upgrade.disabled==frame_name.ends_with("_missing")
		review_checks[frame_name+": copy action clears upgrade"]=copy.position.y>=upgrade.get_rect().end.y+8
		for node in [copy,upgrade,cost]:
			review_checks[frame_name+": copy controls inside detail panel "+str(node.name)]=modal.get_node("DetailsPanel").get_rect().encloses(node.get_rect())
		if frame_name.ends_with("_confirm"):review_checks[frame_name+": material or copy confirmation visible"]=$UI.get_node_or_null("ConfirmationModal")!=null
		return
	var rules: Label=$UI._reference.get_node("ShopRules")
	review_checks[frame_name+": business reset and shared soul note visible"]=rules.is_visible_in_tree() and rules.get_visible_line_count()==rules.get_line_count()
	if frame_name.ends_with("_c13_closed"):
		review_checks[frame_name+": closed catalog empty"]=$UI.shop.products.is_empty()
		review_checks[frame_name+": closed refresh disabled"]=$UI._reference.get_node("RefreshShopButton").disabled
		return
	for row in $UI._reference.get_node("ShopScroll/ShopProductRow").get_children():
		var id := str(row.name).trim_prefix("Product_");var button: Button=row.get_node("Purchase")
		if id in ["advanced_bag","top_bag"]:review_checks[frame_name+": bags have no artificial daily limit "+id]=not button.disabled
		if id.begins_with("daily_card_"):review_checks[frame_name+": owned daily cards remain purchasable "+id]=not button.disabled
		if frame_name.ends_with("_c13_shared") and id in ["priest_soul","mage_soul","guardian_soul"]:
			review_checks[frame_name+": shared class quota disabled "+id]=button.disabled

func _check_season_preparation(frame_name: String) -> void:
	var view: Control = $UI._reference
	var difficulty: OptionButton = view.get_node_or_null("SeasonDifficultySelector")
	var borrowed: CheckButton = view.get_node_or_null("SeasonBorrowedDeckToggle")
	if frame_name.ends_with("_locked"):
		review_checks[frame_name+": immutable selectors hidden"] = difficulty == null and borrowed == null
		var summary: Label = view.get_node("PreparationDeckSummary")
		review_checks[frame_name+": locked borrowed source visible"] = summary.text.contains(Palette.localized("season_borrowed_deck"))
		return
	review_checks[frame_name+": both selectors visible"] = difficulty != null and borrowed != null
	if difficulty == null or borrowed == null: return
	review_checks[frame_name+": six difficulties and selected cap"] = difficulty.item_count == 6 and difficulty.selected == 5
	review_checks[frame_name+": correct borrowed state"] = borrowed.button_pressed == frame_name.ends_with("_borrowed")
	for control in [difficulty,borrowed]:
		review_checks[frame_name+": inside canvas "+str(control.name)] = Rect2(0,0,1920,1080).encloses(control.get_rect())
		review_checks[frame_name+": clear of stock "+str(control.name)] = not control.get_rect().intersects(view.get_node("PreparationBagStockSummary").get_rect())
		review_checks[frame_name+": readable control "+str(control.name)] = control.get_theme_font_size("font_size") >= 24
	review_checks[frame_name+": selectors do not overlap"] = not difficulty.get_rect().intersects(borrowed.get_rect())
	var font: Font = borrowed.get_theme_font("font")
	var width := font.get_string_size(borrowed.text,HORIZONTAL_ALIGNMENT_LEFT,-1,borrowed.get_theme_font_size("font_size")).x
	review_checks[frame_name+": full localized toggle text"] = width + 64 <= borrowed.size.x

func _frame_checks(frame_name: String) -> Dictionary:
	var result: Dictionary = {}
	for key in review_checks:
		if str(key).begins_with(frame_name + ":"): result[key] = review_checks[key]
	return result

func _gear(id: String, slot: String = "Chest", quality: String = "Orange") -> Dictionary:
	return {"instanceId": id, "slot": slot, "quality": quality, "element": "Earth", "effectAffix": "Bulwark", "secondaryTrait": "DrawInterval", "level": 3, "version": 7, "location": "Inventory", "isBound": false}

func _owned(id: String) -> Dictionary:
	# Ownership fixtures describe the lobby, independently of the previous
	# room's archived or deliberately unavailable display catalog.
	var info: Dictionary = preload("res://data/catalog_index.gd").card(id)
	return {"cardId": id, "heroClass": info.get("hero_class"), "unlocked": true, "copyCount": 3, "level": 3, "version": 7, "currencyKind": "WarriorSoul" if info.get("hero_class") == null else str(info.hero_class) + "Soul", "craftCost": 12, "dismantleRefund": 3, "canDismantle": true, "canUpgrade": true, "upgradeCost": 80, "upgradeCopyCost": 0}

func _reset_fixture() -> void:
	$UI.get_node("LoginLanguageSelector").close()
	var audio: Node = $UI.get_node("AudioSettings")
	if is_instance_valid(audio._popup): audio._popup.hide()
	for child in $UI.get_children():
		if child is Window or child.name in ["EquipmentComparisonDialog", "ConfirmationModal", "BattleDetailsModal", "LootPreferenceInfo","SeasonThemeInfo"]:
			if child.has_method("dismiss"): child.dismiss()
			else: child.queue_free()
	await get_tree().process_frame
	Game.selected_cards = []; Game.combat_preview = {}
	Game.room = {}; Game.settlement = {}; Game.ready_prompt = {}; Game.preparation = {}; Game.relic_details = {}
	Game.preparation_loot_preference="";Game._loot_preference_scope=""
	Game._settlement_recovery_match_id = ""
	Game.gateway.recovering = false; Game.gateway.online = true
	Game.lobby = _initial_lobby.duplicate(true); Game.hero_class = "Mage"; Game.busy = false
	Game.configuration_error = ""; Game.connection = ""
	Game.preparation_configuration_error = ""
	$UI.screen = "hall"; $UI.screen_loading = false; $UI.mail_modal_lock = false
	$UI.market_controller.reset()
	$UI.activity_controller.reset()
	$UI.journey_controller.reset()
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
	if scenario in PREPARATION_SOURCE_SCENARIOS: return await _prepare_original_preparation_scene(scenario)
	if scenario in REFRESH_SCENARIOS: return await _prepare_refresh_scene(scenario)
	if scenario in HISTORICAL_SCENARIOS: return await _prepare_historical_equipment_scene(scenario,locale)
	if scenario.begins_with("c16_"):return await _prepare_theme_scene(scenario,locale)
	if scenario.begins_with("c15_"): return await _prepare_journey_scene(scenario)
	if scenario.begins_with("c14_"): return await _prepare_activity_scene(scenario)
	if scenario.begins_with("c13_"): return await _prepare_shop_scene(scenario)
	if scenario.begins_with("c12_"):return await _prepare_market_scene(scenario)
	if scenario.begins_with("c11_"):
		Game.room=_room_fixture()
		Game.room.config_version=Game.CATALOG.data.version
		Game.room["season"]={"season_id":"review","difficulty_id":"D2","ruleset_id":"season-v1","config_version":Game.CATALOG.data.version,"stats_version":"season-equipment-v1"}
		Game.room.player.phase="Choice"
		Game.room.player.equipped_items=[]
		Game.room.player.erase("monster_pool")
		Game.room.allowed_actions=["choice.read","choice.pick"]
		Game.room.player["red_evaluation_pending"]=scenario=="c11_waiting"
		if scenario!="c11_waiting":
			var item := _c05_item("reserved-red","Head",true,"Inferno")
			item.equipment.level=0
			Game.room.player["pending_red_item"]=item
		await _render_base()
		if scenario.begins_with("c11_replace") or scenario.begins_with("c11_confirm"):
			$UI.set_meta("red_reward_stage","confirm" if scenario.begins_with("c11_confirm") else "replace")
			$UI.set_meta("red_reward_replacement",str(Game.room.player.inventory[0].item_id))
			await _render_base()
		if scenario.ends_with("_bottom"):
			for child in $UI._reference.get_children():
				if child is ScrollContainer:
					child.set_deferred("scroll_vertical",100000)
			await get_tree().process_frame
			await get_tree().process_frame
			for child in $UI._reference.get_children():
				if child is ScrollContainer:
					var bar: VScrollBar=child.get_v_scroll_bar()
					review_checks[locale+"_"+str(get_window().size.x)+"_"+scenario+": bottom accessible "+str(child.name)]=is_equal_approx(bar.value,maxf(0,bar.max_value-bar.page))
		var frame: Control=$UI._reference.get_node("RedRewardPanel")
		for child in $UI._reference.get_children():
			if child is Control and child!=frame:
				if child is Label and child.text.is_empty(): continue
				review_checks[locale+"_"+str(get_window().size.x)+"_"+scenario+": content inside decorated panel "+str(child.name)]=frame.get_rect().grow(-16).encloses(child.get_rect())
		return false
	if scenario.begins_with("c09_"):
		await _prepare_equipment_scene("c05_prep")
		Game.season_loot_preference()
		if scenario!="c09_default":Game.preparation_loot_preference="Water"
		if scenario=="c09_locked":
			Game.preparation={"snapshot":{"heroClass":"Mage","maximumHp":70,"cardIds":Game.deck().get("cardIds",[]),"equipmentIds":Game.loadout().get("equipmentIds",[]),"equipmentSnapshots":$UI._equipped_items(),"classWeaponLevel":5,"backpackTier":"Free","backpackCapacity":20,"safeSlotIndexes":[],"potionCount":0,"lootPreferenceElement":"Water"}}
		await _render_base()
		if scenario=="c09_info":
			$UI._show_loot_preference_info()
			await get_tree().process_frame
			var frame: Panel=$UI.get_node("LootPreferenceInfo/LootPreferencePanel")
			for child in frame.get_children():
				if child is Control:
					review_checks[Palette.language()+"_"+str(get_window().size.x)+"_c09_info: content inside decorated panel "+str(child.name)]=frame.get_global_rect().grow(-16).encloses(child.get_global_rect())
		return false
	if scenario.begins_with("c05_"): return await _prepare_equipment_scene(scenario)
	if scenario.begins_with("c06_"): return await _prepare_enhancement_scene(scenario)
	if scenario.begins_with("c07_") or scenario.begins_with("c08_"): return await _prepare_crafting_scene(scenario)
	if scenario.begins_with("mail_template_"):
		var template_id := scenario.trim_prefix("mail_template_").trim_suffix("_bottom")
		var arguments: Array = []
		if template_id == "item_reclamation":
			arguments = [{"key": "kind", "value": "Gold"}, {"key": "amount", "value": "123456"}, {"key": "reason", "value": "Opaque reason {amount}: Fire / Gold. ".repeat(20)}]
		Game.mail = {"unreadCount": 1, "items": [{"id": "template-review", "template_id": template_id, "template_args": arguments, "sender_role": "admin" if template_id == "item_reclamation" else "system", "sender": "old sender", "title": "old title", "body": "old body", "read": true, "claimed": false, "attachments": []}]}
		await _render_base(); $UI.mail_modal_lock = true; $UI._reference._mail()
		$UI._reference._mail_select(Game.mail.items[0])
		if scenario.ends_with("_bottom"):
			await get_tree().process_frame
			await get_tree().process_frame
			var scroll: ScrollContainer = $UI._reference.get_node("MailModal").find_child("MailDetailScroll", true, false)
			scroll.set_deferred("scroll_vertical", 100000)
		return false
	match scenario:
		"prep_season", "prep_season_borrowed", "prep_season_locked":
			$UI.screen = "prep"
			Game.lobby["season"] = {"state":"Active","seasonId":"review-season","configVersion":Game.CATALOG.data.version,"highestOpenDifficulty":5,"highestUnlockedDifficulty":5}
			Game.preparation_difficulty = 5
			Game.use_borrowed_deck = scenario != "prep_season"
			if scenario == "prep_season_locked":
				var borrowed_rows: Array = Game.CATALOG.data.tables.SeasonBorrowedDecks.filter(func(row): return str(row.hero_class) == "Mage")
				Game.preparation = {"snapshot":{"heroClass":"Mage","maximumHp":70,"cardIds":borrowed_rows.map(func(row): return str(row.card_id)),"cardLevels":borrowed_rows.map(func(_row): return 5),"equipmentIds":[null,null,null,null,null],"equipmentSnapshots":[],"classWeaponLevel":5,"backpackTier":"Free","backpackCapacity":20,"safeSlotIndexes":[],"potionCount":0,"borrowedTemplateId":"loan-mage","configVersion":Game.CATALOG.data.version,"difficulty":"D5","season":{"seasonId":"review-season","difficultyId":"D5","rulesetId":"season-v1","configVersion":Game.CATALOG.data.version,"statsVersion":"season-equipment-v1"}}}
		"login": Game.lobby = {}
		"login_language":
			Game.lobby = {}
			await _render_base()
			$UI.get_node("LoginLanguageSelector").open()
			return false
		"login_notice", "login_notice_bottom", "login_notice_authored":
			Game.lobby = {}
			Game.authentication_reason = Palette.localized("login_timeout")
			Game.server_info["announcement"] = {"title": "Relicbound Test Server Update and Traveler Notices" if locale == "en" else "遗境行者测试服更新与旅人公告", "body": ("Dear Travelers,\n\nThe test server has recently been updated:\n\n1. After extraction, wait for server settlement and the run results.\n2. Results include the items earned during the run and equipped gear.\n3. Log Out returns to the login screen.\n4. Common panels leave clear space inside their decorative borders.\n\nThank you for playing!" if locale == "en" else "亲爱的旅人：\n\n测试服近期已更新：\n\n1. 撤离后等待服务器结算并显示本局结果。\n2. 结算包含本局获得的物品和穿戴装备。\n3. 切换账号后返回登录界面。\n4. 通用框的内容与装饰边框之间保留留白。\n\n感谢参与测试！")}
			if locale not in ["zh-CN", "en"]:
				Game.server_info["announcement"] = {"translations": {locale: {"title": Palette.localized("game_title") + " · " + Palette.localized("ui_announcement_title"), "body": (Palette.localized("ui_room_hint") + "\n\n" + Palette.localized("ui_safe_slot_hint") + "\n\n").repeat(8)}}}
			if scenario == "login_notice_authored":
				Game.server_info["announcement"] = {"title": "Equipment / Priest / Gold", "body": "Authored announcement text remains verbatim."}
				var authored_title := OS.get_environment("FANTASYCARD_REVIEW_AUTHORED_TITLE")
				if not authored_title.is_empty(): Game.server_info["announcement"].title = authored_title
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
				if locale not in ["zh-CN", "en"]:
					title = (Palette.localized("run_reward") + " / " + Palette.localized("ui_announcement_title") + " · ").repeat(3)
					body = Palette.localized("ui_room_hint") + " " + Palette.localized("ui_safe_slot_hint") + " "
				var authored_title := OS.get_environment("FANTASYCARD_REVIEW_AUTHORED_TITLE")
				for index in range(12): Game.mail.items.append({"id": "review-mail-%s" % index, "title": title + " %s" % index if authored_title.is_empty() else authored_title, "body": body.repeat(16), "sender": "System" if locale == "en" else "系统", "read": true, "claimed": false, "attachments": [{"kind": "Gold", "amount": 123456}, {"kind": "EquipmentFragments", "amount": 25}, {"kind": "HealthPotion", "amount": 2}]})
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
		"settings", "settings_battle", "settings_bottom", "settings_battle_bottom":
			if scenario.begins_with("settings_battle"): Game.room = _room_fixture(); Game.room.player.phase = "Pve"; Game.room.allowed_actions.append("battle.abandon")
			await _render_base(); $UI.get_node("AudioSettings").show_settings()
			if scenario.ends_with("_bottom"):
				await get_tree().process_frame
				await get_tree().process_frame
				$UI.get_node("AudioSettings")._popup.find_child("AudioSettingsScroll", true, false).set_deferred("scroll_vertical", 100000)
			return false
		"confirm":
			await _render_base(); $UI._confirm(Palette.localized("battle_abandon_warning"), func(): pass, {"title": "battle_abandon_title", "confirm_text": "battle_abandon_confirm", "tall": true}); return false
		"battle_status":
			Game.room = _room_fixture(); await _render_base(); $UI._show_battle_details(_status_fixture()); return false
		"exploration", "map", "midlayer", "inventory", "inventory_details", "relic", "pve", "pvp", "pve_full_hand", "pvp_full_hand", "pve_priest", "pve_guardian", "pvp_priest", "pvp_guardian", "pvp_name_fallback", "relic_name_fallback", "choice", "notice":
			Game.room = _room_fixture()
			if scenario in ["map", "midlayer"]:
				Game.room.map = []
				for y in range(6):
					for x in range(6): Game.room.map.append({"row": y, "column": x, "has_spring": y == 0 and x == 3, "is_boss": y == 2 and x == 2})
				Game.room.legal_moves = [{"row": 2, "column": 2}, {"row": 3, "column": 3}]; Game.room.allowed_actions.append("room.move")
			if scenario.begins_with("pve") or scenario.begins_with("pvp"):
				Game.room.player.phase = "Pve" if scenario.begins_with("pve") else "Pvp"; Game.room.allowed_actions += ["battle.play_cards", "battle.select_target", "duel.leave", "duel.escape"]
				Game.room.pve = {"battle_id": "review-battle", "current_target_id": "fire-bat", "monsters": [{"monster_id": "fire-bat", "maximum_hp": 44, "hp": 31, "shield": 8, "intent_kind": "Attack", "intent_element": "Fire", "intent_value": 5}]}
				if scenario.begins_with("pve"): Game.room.player.combat = {"hp": 80, "maximum_hp": 70, "shield": 6}
				else: Game.room.duel = {"duel_id": "review-duel", "opponent_id": "review-opponent", "opponent_class": "Guardian", "opponent": {"hero_class": "Guardian", "hp": 60, "maximum_hp": 100, "shield": 8}, "escape_remaining_ms": 0}
				if scenario.ends_with("full_hand"):
					Game.room.player.hand = []
					for card_id in ["MAG-10", "GW19", "GP07", "GO04", "M-BOXSPIRIT"]:
						var instance_id := "full-hand-" + str(Game.room.player.hand.size())
						Game.room.player.hand.append({"instance_id": instance_id, "card_id": card_id, "level": 10})
						Game.selected_cards.append(instance_id)
				if scenario in ["pve_priest", "pvp_priest"]:
					Game.room.player.hero_class = "Priest"; Game.room.player.battle_status = _status_fixture("LinYuan")
				elif scenario in ["pve_guardian", "pvp_guardian"]:
					Game.room.player.hero_class = "Guardian"; Game.room.player.battle_status = _status_fixture("ZaiYue")
			if scenario == "pvp_name_fallback":
				Game.room.duel.opponent_name = "旅人"; Game.room.duel.opponent_name_is_fallback = true
			if scenario == "relic_name_fallback":
				Game.room.current_cell.relic_piles[0].owner_name = "旅人"
				Game.room.current_cell.relic_piles[0].owner_name_is_fallback = true
			if scenario == "choice":
				Game.room.player.phase = "Choice"; Game.room.allowed_actions = ["choice.pick", "choice.refresh"]
				Game.room.reward_choice = {"refresh_count": 0, "options": [{"option_id": "equipment", "kind": 1, "quantity": 1}, {"option_id": "fragments", "kind": 2, "quantity": 18}, {"option_id": "heal", "kind": 3, "quantity": 1, "heal_percent": 14}]}
			await _render_base()
			if scenario in ["inventory", "inventory_details", "relic", "relic_name_fallback"]: $UI.set_meta("inventory_open", true)
			if scenario == "inventory_details": $UI.set_meta("inventory_selected", "pack-35")
			if scenario in ["relic", "relic_name_fallback"]:
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

func _c05_gear(id: String, slot: String, red: bool = false, unique: String = "") -> Dictionary:
	return {"instanceId":id,"slot":slot,"quality":"Red" if red else "Purple","element":"Fire","effectAffix":"Piercing","secondaryTrait":"DrawInterval","level":5,"version":7,"location":"Equipped","isBound":false,"statsVersion":"season-equipment-v1","uniqueAffix":unique if red else null,"uniqueElement":"Fire" if red and unique=="Inferno" else null}

func _c05_item(id: String,slot: String,red: bool=false,unique: String="") -> Dictionary:
	return {"item_id":id,"kind":"Equipment","quantity":1,"slot_index":0,"is_safe":false,"equipment":{"slot":slot,"quality":"Red" if red else "Purple","element":"Fire","effect_affix":"Piercing","secondary_trait":"DrawInterval","level":5,"stats_version":"season-equipment-v1","unique_affix":unique if red else null,"unique_element":"Fire" if red and unique=="Inferno" else null}}

func _market_item_fixture(id: String,quality: String="Orange",slot: String="Head",source: String="NaturalDrop") -> Dictionary:
	return {"instanceId":id,"slot":slot,"quality":quality,"element":"Fire","effectAffix":"Piercing","secondaryTrait":"DrawInterval","level":0,"version":7,
		"location":"Inventory","isBound":false,"originSeasonId":"market-review","seasonId":"market-review","assetScope":"ActiveSeason","statsVersion":"season-equipment-v1",
		"sourceKind":source,"recipeExtracted":source=="TemplateReforge","uniqueAffix":"Inferno" if quality=="Red" else null,"uniqueElement":"Fire" if quality=="Red" else null}

func _market_listing_fixture(id: String,item: Dictionary,currency: String,price: int,owner: bool=false) -> Dictionary:
	var gear: Dictionary=item.duplicate(true);gear.location="MarketListed"
	return {"listingId":id,"equipmentId":item.instanceId,"sellerId":Game.lobby.get("player",{}).get("userId") if owner else "other-market-owner",
		"currency":currency,"price":price,"priceGold":price if currency=="Gold" else 0,"version":9,"status":"Active","createdAt":"2026-11-04T00:00:00Z",
		"expiresAt":"2099-12-31T00:00:00Z","seasonId":"market-review","seasonEndsAt":"2099-12-31T00:00:00Z","fee":maxi(1,int(price/10.0)),
		"sellerNet":price-maxi(1,int(price/10.0)),"equipment":gear}

var _theme_review_indices: Dictionary={}

func _prepare_theme_scene(scenario: String,_locale: String) -> bool:
	var element := "Wood" if scenario=="c16_wood_regen" else scenario.split("_")[1].capitalize() if scenario.ends_with("_info") else "Fire"
	Game.room=_room_fixture()
	if scenario=="c16_map":
		Game.room.map=[]
		for y in 6:
			for x in 6:Game.room.map.append({"row":y,"column":x,"has_spring":y==0 and x==3,"is_boss":y==2 and x==2})
		Game.room.legal_moves=[{"row":2,"column":2},{"row":3,"column":3}];Game.room.allowed_actions.append("room.move");$UI.set_meta("exploration_map_open",true)
	if scenario in ["c16_wood_regen","c16_pvp"]:
		Game.room.player.phase="Pve" if scenario=="c16_wood_regen" else "Pvp"
		Game.room.allowed_actions+=["battle.play_cards","battle.select_target","duel.leave","duel.escape"]
		if scenario=="c16_wood_regen":
			Game.room.player.combat={"hp":80,"maximum_hp":70,"shield":6}
			Game.room.pve={"battle_id":"theme-visual","current_target_id":"annihilation-core","monsters":[{"monster_id":"annihilation-core","maximum_hp":280,"hp":187,"shield":0,"intent_kind":"Regenerate","intent_element":"None","intent_value":5,"windup_remaining_ms":900,"boss_phase":1}]}
		else:Game.room.duel={"duel_id":"review-duel","opponent_id":"review-opponent","opponent_class":"Guardian","opponent":{"hero_class":"Guardian","hp":60,"maximum_hp":100,"shield":8},"escape_remaining_ms":0}
	if scenario=="c16_choice":
		Game.room.player.phase="Choice";Game.room.allowed_actions=["choice.pick","choice.refresh"]
		Game.room.reward_choice={"refresh_count":0,"options":[{"option_id":"equipment","kind":1,"quantity":1},{"option_id":"fragments","kind":2,"quantity":18},{"option_id":"heal","kind":3,"quantity":1,"heal_percent":14}]}
	var version := "c16-visual-"+element.to_lower()
	if not _theme_review_indices.has(element):
		var data: Dictionary=Game.CATALOG.data.duplicate(true)
		data.version=version;data.tables.SeasonThemeRules[0].selected_theme=element;data.tables.SeasonLootPreference[0].default_element=element
		var index: Dictionary=preload("res://data/catalog_index.gd").from_data(data);index["_origin"]=Game.gateway.base_url;_theme_review_indices[element]=index
	Game._room_catalogs[version]=_theme_review_indices[element]
	Game.room.config_version=version;Game.room["season"]={"season_id":"theme-visual","difficulty_id":"D0","ruleset_id":"season-v1","config_version":version,"stats_version":"season-equipment-v1"}
	await _render_base()
	if scenario.ends_with("_info"):
		$UI._reference.get_node("SeasonThemeInfoButton").pressed.emit();await get_tree().process_frame
	return false

func _check_theme_scene(frame_name: String) -> void:
	var button: Button=$UI._reference.get_node("SeasonThemeInfoButton")
	review_checks[frame_name+": pinned theme badge visible"]=button.is_visible_in_tree() and not button.disabled
	if frame_name.ends_with("_info"):
		var panel: Panel=$UI.get_node("SeasonThemeInfo/ThemeInfoPanel")
		for child in panel.get_children():
			if child is Control:review_checks[frame_name+": info content inside frame "+str(child.name)]=panel.get_global_rect().grow(-16).encloses(child.get_global_rect())
	if frame_name.ends_with("_c16_wood_regen"):
		var intent: Label=$UI._reference.get_node("MonsterIntent_0")
		review_checks[frame_name+": regeneration label not None"]=Palette.without_bidi_isolates(intent.text).contains(Palette.localized("season_theme_regenerate"))
		review_checks[frame_name+": actual bounded5HP shown"]=Palette.without_bidi_isolates(intent.text).contains("5") and not intent.text.contains("200")

func _prepare_journey_scene(scenario: String) -> bool:
	if scenario=="c15_entry":return await _prepare_activity_scene("c14_active")
	$UI.screen="journey"
	var c=$UI.journey_controller;c.attach($UI)
	var inputs=preload("res://tests/test_season_journey.gd")
	var state: Dictionary=inputs.snapshot()
	match scenario:
		"c15_catchup":state=inputs.snapshot(48)
		"c15_complete":state=inputs.snapshot(12525)
		"c15_upcoming":
			state=inputs.snapshot(0,"Upcoming");state.startsAt="2027-01-01T00:00:00+08:00";state.endsAt="2027-02-12T00:00:00+08:00"
			state.seasons[0]=state.seasons[0].merged({"state":"Upcoming","startsAt":state.startsAt,"endsAt":state.endsAt},true)
		"c15_archive":state=inputs.snapshot(3200,"Ended","old")
		"c15_disabled":state=inputs.snapshot(0,"Disabled")
		"c15_unavailable":state=inputs.snapshot(3200,"Unavailable")
		"c15_none":state=inputs.snapshot(0,"None");state.seasons=[]
		"c15_error":state={};c.failed=true
	c.state=state;c.seasons=state.get("seasons",[]);c.next_offset=50 if scenario in ["c15_active","c15_complete","c15_archive"] else null
	await _render_base()
	if scenario=="c15_complete":
		$UI._reference.get_node("JourneyLevelsScroll").scroll_vertical=10000
		$UI._reference.get_node("JourneyContractsScroll").scroll_vertical=10000
		await get_tree().process_frame
		await _render_base()
	return false

func _check_journey_scene(frame_name: String) -> void:
	var view: Control=$UI._reference
	if frame_name.ends_with("_c15_entry"):
		review_checks[frame_name+": activity entry leads to journey"]=view.get_node("ActivityJourney").is_visible_in_tree() and not view.get_node("ActivityJourney").disabled
		return
	if frame_name.ends_with("_c15_none") or frame_name.ends_with("_c15_disabled") or frame_name.ends_with("_c15_unavailable") or frame_name.ends_with("_c15_error"):
		review_checks[frame_name+": unavailable has no invented level bar"]=view.get_node_or_null("JourneyProgress")==null
		review_checks[frame_name+": unavailable state shown"]=view.get_node("JourneyState").is_visible_in_tree()
		return
	review_checks[frame_name+": complete original30level track"]=$UI.journey_controller.state.levels.size()==30
	review_checks[frame_name+": original progress bar"]=view.get_node("JourneyProgress").value==$UI.journey_controller.state.experience
	review_checks[frame_name+": original season selector visible"]=view.get_node("JourneySeason").is_visible_in_tree()
	if frame_name.ends_with("_c15_active"):
		var scroll: Control=view.get_node("JourneyLevelsScroll")
		var row: Control=scroll.find_child("JourneyLevel20",true,false)
		review_checks[frame_name+": current level is fully in view"]=row!=null and scroll.get_global_rect().encloses(row.get_global_rect())
		if Palette.language()=="ar":
			review_checks[frame_name+": current total fraction isolated"]=view.get_node("JourneySummary").text.contains(String.chr(0x2066)+"7000 / 12525"+String.chr(0x2069))
			review_checks[frame_name+": current next fraction isolated"]=view.get_node("JourneyNext").text.contains(String.chr(0x2066)+"150 / 500"+String.chr(0x2069))
	if frame_name.ends_with("_c15_complete"):
		review_checks[frame_name+": final level reachable"]=view.get_node("JourneyLevelsScroll").scroll_vertical>0
		review_checks[frame_name+": final weekly row reachable"]=view.get_node("JourneyContractsScroll").scroll_vertical>0
	if Palette.language()=="ar":review_checks[frame_name+": date range remains chronological"]=view.get_node("JourneyWindow").text.contains(String.chr(0x2066))

func _prepare_activity_scene(scenario: String) -> bool:
	if scenario=="c14_hall":
		$UI.screen="hall";await _render_base();return false
	$UI.screen="activities"
	var c=$UI.activity_controller
	c.attach($UI)
	var event: Dictionary=preload("res://tests/test_season_activity_model.gd").event()
	event.accountVersion=4;event.configVersion=Game.CATALOG.data.version
	event.startsAt="2026-11-12T00:00:00+08:00";event.endsAt="2026-11-15T00:00:00+08:00"
	event.options.insert(1,{"ruleId":"event-warrior","costTokens":3,"rewardKind":"bound_warrior_soul","rewardCount":6,"eventLimit":4,"used":0})
	if scenario=="c14_upcoming":event.state="Upcoming";event.canExchange=false;event.earned=0;event.available=0
	if scenario in ["c14_spent","c14_late","c14_claim_confirm"]:
		event.spent=12;event.available=0;event.state="Ended" if scenario!="c14_spent" else "Active"
		for index in 4:
			var option: Dictionary=event.options[index%3]
			var claimed: bool=scenario=="c14_spent" or index==3
			event.rewards.append({"rewardId":"original-reward-"+str(index),"seasonId":event.seasonId,"eventId":event.eventId,"configVersion":event.configVersion,"ruleId":option.ruleId,"rewardKind":option.rewardKind,"rewardAmount":option.rewardCount,"heroClass":"Priest" if option.rewardKind=="bound_class_soul" else null,"tokenCost":3,"quantity":1,"state":"Claimed" if claimed else "Pending","canClaim":not claimed})
		for option in event.options:
			option.used=event.rewards.filter(func(reward):return reward.ruleId==option.ruleId).size()
	if scenario=="c14_unavailable":
		event.state="Unavailable";event.canExchange=false;event.options=[];c.failed=true;c.notice=Palette.localized("activity_unavailable")
	c.events=[event];c.selected=preload("res://ui/season_activity_model.gd").key(event);c.next_offset=50
	if scenario=="c14_empty":c.events=[];c.next_offset=null
	await _render_base()
	if scenario=="c14_exchange_confirm":c.confirm_exchange(event.options[2]);await get_tree().process_frame
	if scenario=="c14_claim_confirm":c.confirm_claim(event.rewards[0]);await get_tree().process_frame
	return false

func _check_activity_scene(frame_name: String) -> void:
	var view: Control=$UI._reference
	if frame_name.ends_with("_c14_hall"):
		review_checks[frame_name+": camp activity entry"] = view.get_node("ActivityEntry").is_visible_in_tree()
		return
	if frame_name.ends_with("_c14_empty"):
		review_checks[frame_name+": empty original-event list"]=$UI.activity_controller.events.is_empty()
		return
	review_checks[frame_name+": original event selector"]=view.get_node("ActivitySelector").is_visible_in_tree()
	review_checks[frame_name+": shared budget visible"]=view.get_node("ActivityBudget").is_visible_in_tree()
	if Palette.language()=="ar":review_checks[frame_name+": chronological range isolated from RTL sentence"]=view.get_node("ActivityWindow").text.contains(String.chr(0x2066)+"2026-11-12 00:00 → 2026-11-15 00:00 · UTC+8"+String.chr(0x2069))
	review_checks[frame_name+": original-source late claim hint"]=view.get_node("ActivitySourceHint").is_visible_in_tree()
	if frame_name.ends_with("_c14_spent") or frame_name.ends_with("_c14_upcoming"):
		for index in 4:review_checks[frame_name+": no exchange without current budget "+str(index)]=view.get_node("ActivityExchange"+str(index)).disabled
	if frame_name.ends_with("_c14_late"):
		for index in 4:review_checks[frame_name+": original pending claim "+str(index)]=view.get_node("ActivityClaim"+str(index)).disabled==(index==3)
	if frame_name.ends_with("_confirm"):review_checks[frame_name+": original event confirmation"]=$UI.get_node_or_null("ConfirmationModal")!=null

func _prepare_shop_scene(scenario: String) -> bool:
	$UI._shop_scroll=0
	var products: Array=[]
	for row in [["card_pack","Cards",250,5,3],["warrior_soul","WarriorSoul",180,3,20],["equipment_fragments","EquipmentFragments",120,3,20],
		["priest_soul","ClassSoul",400,1,12],["mage_soul","ClassSoul",400,1,12],["guardian_soul","ClassSoul",400,1,12],
		["health_potion","HealthPotion",100,4,1],["advanced_bag","AdvancedBag",800,0,1],["top_bag","TopBag",2200,0,1]]:
		var payload := {"count":int(row[4])} if row[1]=="Cards" else {"amount":int(row[4])}
		if row[1]=="ClassSoul": payload["heroClass"]={"priest_soul":"Priest","mage_soul":"Mage","guardian_soul":"Guardian"}[str(row[0])]
		products.append({"productId":str(row[0]),"kind":str(row[1]),"priceGold":int(row[2]),"limit":int(row[3]),"purchased":1 if scenario=="c13_shared" and row[1]=="ClassSoul" else 0,"payload":payload})
	for index in 3:
		products.append({"productId":"daily_card_"+str(index+1),"kind":"Cards","priceGold":80,"limit":1,"purchased":0,"alreadyOwned":true,"payload":{"cardId":["C01","MAG-01","GP01"][index],"count":1}})
	$UI.shop={"resetKey":"2098-12-31","rotationKey":"2098-12-31~0","refreshesUsed":1,"refreshLimit":3,"products":products,
		"policy":{"state":"Active","canPurchase":true,"grantsPermanentCopies":true,"seasonId":"review","configVersion":Game.CATALOG.data.version,
			"catalogVersion":Game.CATALOG.data.version,"wallet":{"gold":5000,"diamond":500},"resetsAt":"2099-01-01T20:00:00Z","seasonEndsAt":"2099-02-01T00:00:00Z"}}
	if scenario=="c13_closed":
		$UI.shop.policy.state="Closed";$UI.shop.policy.canPurchase=false;$UI.shop.products=[]
	Game.lobby.shop=$UI.shop;Game.lobby.wallet={"gold":5000,"diamond":500}
	$UI.inventory["consumables"]={"advancedBagCount":1,"topBagCount":0};Game.lobby.inventory=$UI.inventory
	$UI._shop_inventory_ready=true;$UI.screen="shop"
	if scenario in ["c13_copy","c13_copy_missing","c13_copy_confirm","c13_upgrade_confirm"]:
		var quote := _owned("MAG-01");quote["permanentCopies"]=true;quote.copyCount=1 if scenario=="c13_copy_missing" else 2
		quote.upgradeCopyCost=1;quote.canUpgrade=scenario!="c13_copy_missing";quote.upgradeCost=64
		quote.dismantleRefund=17 if quote.copyCount==1 else 3
		for index in $UI.owned.size():
			if $UI.owned[index].cardId=="MAG-01": $UI.owned[index]=quote
		Game.lobby.cards=$UI.owned;$UI._owned_index_ready=false;$UI._owned_by_id.clear();$UI.screen="cards"
		await _render_base()
		load("res://ui/codex_view.gd")._open_details($UI._reference,$UI,"MAG-01",$UI._reference.get_node("CodexScroll"))
		if scenario in ["c13_copy_confirm","c13_upgrade_confirm"]:
			var modal: Control=$UI._reference.get_node("CardDetails")
			modal.get_node("CopyCard" if scenario=="c13_copy_confirm" else "UpgradeCard").pressed.emit()
			await get_tree().process_frame
		return false
	await _render_base()
	if scenario in ["c13_tail","c13_shared"]:
		$UI._reference.get_node("ShopScroll").scroll_horizontal=10000 if scenario=="c13_tail" else 3*314
		await get_tree().process_frame;await get_tree().process_frame
	if scenario=="c13_confirm":$UI._purchase_shop_item(products[0],$UI._reference._product_title("Cards",products[0].payload));await get_tree().process_frame
	return false

func _prepare_market_scene(scenario: String) -> bool:
	Game.lobby["season"]={"state":"Active","seasonId":"market-review","hasJoined":true,"configVersion":Game.CATALOG.data.version,"statsVersion":"season-equipment-v1","wallet":{"seasonId":"market-review","gold":120000,"version":7}}
	Game.lobby.wallet={"gold":120000,"diamond":10000}
	if scenario=="c12_hall":$UI.screen="hall";return true
	var controller=$UI.market_controller
	controller.reset();controller.attach($UI);$UI.screen="market"
	var red := _market_item_fixture("market-red","Red")
	var orange := _market_item_fixture("market-orange")
	var reforged := _market_item_fixture("market-reforge","Purple","Chest","TemplateReforge")
	var policy := {"state":"Active","seasonId":"market-review","configVersion":Game.CATALOG.data.version,"seasonEndsAt":"2099-12-31T00:00:00Z","canTrade":true,
		"wallet":Game.lobby.wallet,"sharedSlots":8,"listingHours":48,"taxBasisPoints":1000,"minimumFee":1,
		"currencies":[{"currency":"Gold","orangePriceCap":99999,"redPriceCap":99999},{"currency":"Diamond","orangePriceCap":2000,"redPriceCap":8000}]}
	controller.state={"policy":policy,"inventory":{"equipments":[red,orange,reforged],"summary":{"capacity":50,"equipmentCount":3,"freeSlots":47}},
		"listings":[_market_listing_fixture("market-orange-list",orange,"Gold",99999),_market_listing_fixture("market-red-list",red,"Gold",99999),_market_listing_fixture("market-reforge-list",reforged,"Gold",250)],"ownListings":[],"returns":[]}
	if scenario in ["c12_diamond","c12_confirm"]:
		controller.filters.currency="Diamond";controller.state.listings=[_market_listing_fixture("market-orange-diamond",orange,"Diamond",2000),_market_listing_fixture("market-red-diamond",red,"Diamond",8000)]
	elif scenario=="c12_own":
		controller.tab="own"
		for index in 8:
			var original: Dictionary=(red if index%2==0 else orange).duplicate(true)
			original.instanceId="own-original-"+str(index)
			controller.state.ownListings.append(_market_listing_fixture("own-list-"+str(index),original,"Gold" if index%2==0 else "Diamond",99999 if index%2==0 else 2000,true))
		review_checks[Palette.language()+"_"+str(get_window().size.x)+"_"+scenario+": eight distinct held originals"]=controller.state.ownListings.map(func(row):return row.equipmentId).size()==8 and controller.state.ownListings.all(func(row):return controller.state.ownListings.filter(func(other):return other.equipmentId==row.equipmentId).size()==1)
	elif scenario in ["c12_sell","c12_relist"]:
		controller.tab="sell";controller.listing_currency="Diamond";controller.listing_price=2000;controller.selected_item=orange.instanceId
		if scenario=="c12_relist":
			controller.relist_target=_market_listing_fixture("relist-original",red,"Gold",99999,true);controller.listing_price=8000
			controller.state.ownListings=[controller.relist_target.duplicate(true)]
	elif scenario=="c12_returns":
		controller.tab="returns"
		var old: Dictionary=red.duplicate(true);old.seasonId="old-market-season";old.originSeasonId="old-market-season";old.assetScope="ArchivedSeason";old.location="MarketReturnPending"
		var current: Dictionary=orange.duplicate(true);current.location="MarketReturnPending"
		controller.state.returns=[{"returnId":"old-return","listingId":"expired-old","equipment":old,"canClaim":false},{"returnId":"current-return","listingId":"cancelled-current","equipment":current,"canClaim":true}]
		controller.state["returnsNextOffset"]=32
	elif scenario=="c12_error":controller.state={"error":true}
	await _render_base()
	if scenario=="c12_confirm":controller.confirm_buy(controller.state.listings[1]);await get_tree().process_frame
	if scenario in ["c12_own","c12_returns"]:
		var scroll: ScrollContainer=$UI._reference.get_node("MarketReturnsScroll" if scenario=="c12_returns" else "MarketListingsScroll")
		scroll.set_deferred("scroll_vertical",100000)
		await get_tree().process_frame;await get_tree().process_frame
		review_checks[Palette.language()+"_"+str(get_window().size.x)+"_"+scenario+": bottom accessible"]=is_equal_approx(scroll.get_v_scroll_bar().value,maxf(0,scroll.get_v_scroll_bar().max_value-scroll.get_v_scroll_bar().page))
	return false

func _prepare_equipment_scene(scenario: String) -> bool:
	var armor: Array=[]
	for slot in ["Head","Chest","Hands","Legs","Feet"]:
		armor.append(_c05_gear("c05-"+str(slot),str(slot),slot=="Head","Inferno"))
	$UI.inventory.equipments=armor
	Game.lobby.inventory=$UI.inventory
	Game.lobby["equippedLoadouts"]=[{"heroClass":"Mage","equipmentIds":armor.map(func(item):return item.instanceId),"version":7}]
	$UI.gear_draft=armor.map(func(item):return item.instanceId)
	Game.lobby["season"]={"state":"Active","seasonId":"review","highestOpenDifficulty":5,"highestUnlockedDifficulty":5,"statsVersion":"season-equipment-v1","configVersion":Game.CATALOG.data.version}
	Game.preparation_difficulty=5
	match scenario:
		"c05_gear": $UI.screen="gear"
		"c05_prep": $UI.screen="prep"
		"c05_enhance":
			$UI.screen="enhance";$UI._enhance_item="c05-Head"
		"c05_compare":
			$UI.screen="gear";await _render_base()
			$UI._show_equipment_details(_c05_gear("c05-selected","Head",true,"RapidDraw"))
			return false
		"c05_numbers":
			$UI.screen="gear";await _render_base()
			load("res://ui/numerical_details.gd").show_compare($UI,armor,_c05_gear("c05-selected","Head",true,"RapidDraw"))
			return false
		"c05_inventory","c05_inventory_details","c05_relic":
			Game.room=_room_fixture()
			Game.room["config_version"]=Game.CATALOG.data.version
			Game.room["season"]={"season_id":"review","difficulty_id":"D5","ruleset_id":"season-v1","config_version":Game.CATALOG.data.version,"stats_version":"season-equipment-v1"}
			Game.room.player.equipped_items=[]
			for slot in ["Head","Chest","Hands","Legs","Feet"]: Game.room.player.equipped_items.append(_c05_item("worn-"+str(slot),str(slot),slot=="Head","Inferno"))
			Game.room.player.inventory[35]=_c05_item("pack-35","Feet",true,"GoldenCicada")
			Game.room.player.inventory[35].slot_index=35
			await _render_base()
			$UI.set_meta("inventory_open",true)
			if scenario=="c05_inventory_details":$UI.set_meta("inventory_selected","pack-35")
			if scenario=="c05_relic":
				Game.relic_details={"pile-a":{"pile_id":"pile-a","owner_name":"Traveler","version":7,"items":[_c05_item("relic-1","Head",true,"ChainDraw"),_c05_item("relic-2","Chest",true,"Scavenge")]}}
				$UI.set_meta("relic_pile","pile-a")
				$UI.set_meta("relic_selected","relic-1")
	return true

func _prepare_enhancement_scene(scenario: String) -> bool:
	$UI.screen="enhance"
	var target:=_c05_gear("c06-target","Chest")
	target["level"]=3
	target["location"]="Inventory"
	target["seasonId"]="review"
	target["assetScope"]="ActiveSeason"
	var material:=target.duplicate(true)
	material["instanceId"]="c06-material"
	material["level"]=0
	var old:=material.duplicate(true)
	old["instanceId"]="c06-old"
	old["seasonId"]="archive"
	var bot:=material.duplicate(true)
	bot["instanceId"]="c06-bot"
	bot["sourceKind"]="BotReward"
	$UI.inventory.equipments=[target,material,old,bot]
	Game.lobby.inventory=$UI.inventory
	Game.lobby.materials={"equipmentFragments":99999}
	Game.lobby.classWeapons=[{"heroClass":"Mage","level":0,"version":1}]
	Game.lobby.season={"seasonId":"review","state":"Active","wallet":{"seasonId":"review","equipmentFragments":500,"version":10},"fragmentWallets":[{"seasonId":"review","equipmentFragments":500,"version":10}]}
	var weapon:=scenario=="c06_weapon"
	$UI._enhance_item="" if weapon else "c06-target"
	$UI._enhancement_quote_key="Mage:1" if weapon else "c06-target:7"
	$UI._enhancement_quote={"targetKind":"ClassWeapon" if weapon else "Equipment","expectedVersion":1 if weapon else 7,"currentLevel":0 if weapon else 3,"nextLevel":1 if weapon else 4,"fragmentCost":8 if weapon else 40,"materialCount":0 if weapon else 1,"availableMaterialCount":0 if weapon else 1,"availableFragments":99999 if weapon else 500,"canEnhance":true,"fragmentSourceSeasonId":null if weapon else "review","fragmentWalletVersion":null if weapon else 10}
	if scenario=="c06_error":$UI._enhancement_quote={"error":true}
	await _render_base()
	var cost: String=(Palette.localized("enhance_cost_confirm") % [40,4])+"\n"+$UI.EnhancementWallets.source_text($UI._enhancement_quote)
	if scenario=="c06_material":$UI._show_enhance_material_dialog(target,{"expectedVersion":7},cost)
	if scenario=="c06_confirm":$UI._confirm(Palette.localized("enhance_material_confirm") % [cost,$UI._equipment_name(material)],Callable())
	return false

func _prepare_crafting_scene(scenario: String) -> bool:
	if scenario=="c07_entry":return await _prepare_equipment_scene("c05_gear")
	$UI.screen="crafting"
	var sample:=_c05_gear("sample","Head")
	sample["level"]=3
	sample["location"]="Inventory"
	sample["seasonId"]="review"
	sample["assetScope"]="ActiveSeason"
	sample["sourceKind"]="NaturalDrop"
	sample["recipeExtracted"]=false
	var extracted:=sample.duplicate(true)
	extracted["instanceId"]="extracted"
	extracted["recipeExtracted"]=true
	var reforged:=sample.duplicate(true)
	reforged["instanceId"]="reforged"
	reforged["sourceKind"]="TemplateReforge"
	var body:=sample.duplicate(true)
	body["instanceId"]="body"
	body["slot"]="Feet"
	body["level"]=5
	body["isBound"]=true
	body["secondaryTrait"]="ForcedEscape"
	var recipe:={"recipeId":"recipe","seasonId":"review","quality":"Purple","slot":"Head","element":"Water","effectAffix":"Vitality","secondaryTrait":"DrawInterval","statsVersion":"season-equipment-v1","sourceItemId":"sample"}
	var after:=body.duplicate(true)
	after["slot"]="Head"
	after["element"]="Water"
	after["effectAffix"]="Vitality"
	after["level"]=0
	after["secondaryTrait"]="DrawInterval"
	after["sourceKind"]="TemplateReforge"
	$UI.inventory.equipments=[sample,extracted,reforged,body]
	Game.lobby.inventory=$UI.inventory
	Game.lobby.season={"state":"Active","seasonId":"review","hasJoined":true}
	$UI._crafting_selection={"quality":"Purple","slot":"Hands","element":"Water","wishedEffect":"Vitality"}
	$UI._crafting_state={"season":{"seasonId":"review"},"wallet":{"seasonId":"review","version":10,"blueprintMarks":5,"orangeBlueprintMarks":14,"equipmentFragments":80},"maximumDifficulty":5,
		"offers":[{"quality":"Purple","minimumDifficulty":1,"markKind":"Blueprint","markCost":4,"reforgeFragmentCost":1,"wishAttempts":3},{"quality":"Orange","minimumDifficulty":2,"markKind":"OrangeBlueprint","markCost":14,"reforgeFragmentCost":2,"wishAttempts":3}],
		"wishes":[{"quality":"Purple","slot":"Hands","element":"Water","wishedEffect":"Vitality","failures":2}],"recipes":[recipe]}
	$UI._crafting_tab="recipes" if scenario.begins_with("c08_") else "craft"
	$UI._craft_recipe="recipe" if scenario in ["c08_preview","c08_preview_bottom","c08_confirm","c08_blocked","c08_numbers"] else ""
	$UI._craft_body="body" if not $UI._craft_recipe.is_empty() else ""
	$UI._craft_quote={}
	if scenario=="c07_orange":$UI._crafting_selection.quality="Orange"
	if scenario=="c07_locked":$UI._crafting_state.maximumDifficulty=0
	if scenario=="c07_notjoined":$UI._crafting_state={"notJoined":true}
	if scenario=="c07_error":$UI._crafting_state={"error":true}
	if scenario=="c08_learn":sample["effectAffix"]=null
	if not $UI._craft_recipe.is_empty():$UI._craft_quote={"recipe":recipe,"before":body,"after":after,"fragmentCost":1,"availableFragments":80,"expectedWalletVersion":10,"canReforge":scenario!="c08_blocked"}
	if scenario=="c08_market":
		$UI.screen="market"
		$UI.listings=[]
		for item in [sample,extracted,reforged]:
			$UI.listings.append({"listingId":"listing-"+item.instanceId,"sellerId":"other-review-player","priceGold":123,"version":7,"equipment":item})
	await _render_base()
	if scenario=="c07_confirm":$UI._confirm_craft()
	if scenario=="c08_learn":$UI._confirm_learn(sample)
	if scenario=="c08_confirm":$UI._confirm_reforge()
	if scenario=="c08_numbers":load("res://ui/numerical_details.gd").show_compare($UI,[body],after)
	if scenario=="c08_preview_bottom":
		var scroll: ScrollContainer=$UI._reference.get_node("CraftingPreviewScroll")
		scroll.scroll_vertical=int(scroll.get_v_scroll_bar().max_value)
		await get_tree().process_frame
		var warning: Label=scroll.get_child(0).get_child(2)
		review_checks[Palette.language()+"_"+str(get_viewport().get_visible_rect().size.x)+": reforge warning reachable in preview"]=scroll.get_global_rect().grow(1).encloses(warning.get_global_rect())
	return false

func _review_window_position() -> Vector2i:
	return Vector2i.ZERO if OS.get_environment("FANTASYCARD_REVIEW_ISOLATED_DESKTOP") == "1" else Vector2i(-32000, -32000)

func _review_capture(frame_name: String, rebuild: bool = true) -> void:
	var on_login := frame_name.ends_with("_login") or frame_name.ends_with("_login_language") or frame_name.contains("_login_notice")
	if on_login:
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
	_check_login_language(frame_name, on_login)
	if frame_name.contains("_c13_"): _check_shop_season_scene(frame_name)
	if frame_name.contains("_c14_"): _check_activity_scene(frame_name)
	if frame_name.contains("_c15_"): _check_journey_scene(frame_name)
	if frame_name.contains("_c16_"): _check_theme_scene(frame_name)
	if "_refresh_" in frame_name: _check_refresh_scene(frame_name)
	if "_prep_source_" in frame_name or frame_name.ends_with("_prep_current_d1"): _check_original_preparation_scene(frame_name)
	if frame_name.contains("_prep_season"): _check_season_preparation(frame_name)
	var texts: Array = []
	_collect_text($UI, texts)
	for entry in texts:
		review_checks[frame_name + ": glyphs " + str(entry.path)] = entry.missing_glyphs.is_empty()
		if entry.type == "Button":
			review_checks[frame_name + ": complete button text " + str(entry.path)] = float(entry.max_line_width) <= float(entry.available_text_width) + 1.0
		if entry.type == "Label" and int(entry.max_lines_visible) < 0:
			review_checks[frame_name + ": complete label lines " + str(entry.path)] = int(entry.visible_lines) >= int(entry.lines)
			if int(entry.autowrap_mode) == TextServer.AUTOWRAP_OFF:
				review_checks[frame_name + ": complete fixed label width " + str(entry.path)] = float(entry.max_line_width) <= float(entry.available_text_width) + 1.0
		if entry.type == "LineEdit" and bool(entry.is_placeholder):
			review_checks[frame_name + ": complete input hint " + str(entry.path)] = float(entry.max_line_width) <= float(entry.available_text_width) + 1.0
		if bool(entry.battle_primary_text):
			review_checks[frame_name + ": readable battle primary " + str(entry.path)] = float(entry.effective_font_size) >= 12.0 - 0.01
		if str(entry.path).get_file().begins_with("ClassMaximumHp_"):
			review_checks[frame_name + ": integer class health " + str(entry.path)] = str(entry.text).is_valid_int()
		if Palette.language() not in ["zh-CN", "zh-TW"] and (entry.type != "LineEdit" or bool(entry.is_placeholder)):
			var checked_text: String = entry.text
			var authored_title := OS.get_environment("FANTASYCARD_REVIEW_AUTHORED_TITLE")
			if not authored_title.is_empty() and (str(entry.text) == authored_title or str(entry.path).get_file() == "MailTitle"):
				checked_text = checked_text.replace(authored_title, "")
			for player_name in ["逐风者", "长夜归来的盾卫", "一位来自漫长旅途的探索者"]:
				checked_text = checked_text.replace(player_name, "")
			for language_config in Palette.languages().values(): checked_text = checked_text.replace(str(language_config.get("name", "")), "")
			var unexpected_source_han: Array = _text_auditor.unexpected_han(checked_text)
			entry["unexpected_source_han"] = unexpected_source_han
			review_checks[frame_name + ": localized copy " + str(entry.path)] = unexpected_source_han.is_empty()
		if str(entry.path).get_file().begins_with("EquippedCaption_"):
			review_checks[frame_name + ": readable " + str(entry.path).get_file()] = float(entry.effective_font_size) >= 12.0
		if str(entry.path).begins_with("EquipmentComparisonDialog/") and entry.type == "Label" and not str(entry.path).ends_with("/Quantity"):
			review_checks[frame_name + ": comparison text " + str(entry.path)] = float(entry.effective_font_size) >= 12.0
		if str(entry.path).contains("Slot_C01/") and str(entry.path).ends_with("/CardName"):
			review_checks[frame_name + ": readable common-card name"] = float(entry.effective_font_size) >= 12.0
		if str(entry.path).contains("Slot_C01/") and str(entry.path).ends_with("/CardEffect"):
			review_checks[frame_name + ": readable common-card effect"] = float(entry.effective_font_size) >= 12.0
	if on_login:
		var title: Label = $UI._game_title
		review_checks[frame_name + ": readable login title"] = title.get_theme_font_size("font_size") >= 20 and title.get_visible_line_count() > 0
		for panel_name in ["LoginPanel", "AnnouncementPanel"]:
			var panel: PanelContainer = $UI.find_child(panel_name, true, false)
			_check_content_insets(frame_name + ": " + panel_name, panel, panel.get_child(0))
		var announcement_title: Label = $UI.find_child("AnnouncementTitle", true, false)
		review_checks[frame_name + ": complete announcement title"] = announcement_title.get_visible_line_count() == announcement_title.get_line_count()
		if frame_name.ends_with("_login_notice_authored"):
			var authored_title := OS.get_environment("FANTASYCARD_REVIEW_AUTHORED_TITLE")
			review_checks[frame_name + ": authored announcement title stays verbatim"] = announcement_title.text == ("Equipment / Priest / Gold" if authored_title.is_empty() else authored_title)
	var authored_mail_title := OS.get_environment("FANTASYCARD_REVIEW_AUTHORED_TITLE")
	if not authored_mail_title.is_empty() and frame_name.ends_with("_mail_long"):
		review_checks[frame_name + ": authored mail detail title stays verbatim"] = texts.any(func(entry): return str(entry.path).contains("MailDetailScroll") and str(entry.text) == authored_mail_title)
		review_checks[frame_name + ": authored mail list title stays verbatim"] = texts.any(func(entry): return str(entry.path).get_file() == "MailTitle" and str(entry.text).ends_with("  " + authored_mail_title))
	if frame_name.contains("_settings"):
		var popup: PopupPanel = $UI.get_node("AudioSettings")._popup
		if is_instance_valid(popup):
			review_checks[frame_name + ": no language selection in settings"] = popup.find_children("*", "OptionButton", true, false).is_empty()
			var settings_scroll: ScrollContainer = popup.find_child("AudioSettingsScroll", true, false)
			_check_content_insets(frame_name + ": settings", popup, settings_scroll)
			var settings_content: Control = popup.find_child("SettingsContent", true, false)
			var scrollbar := settings_scroll.get_v_scroll_bar()
			review_checks[frame_name + ": scrollbar stays clear of settings controls"] = settings_content.get_global_rect().end.x + 15.0 <= scrollbar.get_global_rect().position.x
	if frame_name.ends_with("_shop") or frame_name.ends_with("_shop_tail") or frame_name.ends_with("_c13_tail") or frame_name.ends_with("_c13_shared"):
		_check_shop()
		for product in $UI._reference.get_node("ShopScroll/ShopProductRow").get_children():
			var detail: Label = product.get_node("ShopDetail")
			var purchase: Button = product.get_node("Purchase")
			review_checks[frame_name + ": shop details clear purchase " + str(product.name)] = detail.get_rect().end.y + 4.0 <= purchase.position.y and detail.get_visible_line_count() == detail.get_line_count()
	if (frame_name.ends_with("_cards") and $UI.screen == "cards") or (frame_name.ends_with("_deck") and $UI.screen == "deck"):
		var grid_name := "CardGrid" if frame_name.ends_with("_cards") else "DeckOwnedGrid"
		var grid: Control = $UI._reference.find_child(grid_name, true, false)
		review_checks[frame_name + ": populated visible cards"] = grid != null and not grid.find_children("*", "Button", true, false).is_empty()
		for node in $UI._reference.find_children("*", "Button", true, false):
			if not str(node.name).begins_with("Filter_") and not str(node.name).begins_with("DeckFilter_"): continue
			var style: StyleBox = node.get_theme_stylebox("normal")
			var available: float = node.size.x - style.get_content_margin(SIDE_LEFT) - style.get_content_margin(SIDE_RIGHT)
			var text_width: float = node.get_theme_font("font").get_string_size(node.text, HORIZONTAL_ALIGNMENT_LEFT, -1, node.get_theme_font_size("font_size")).x
			review_checks[frame_name + ": complete " + str(node.name)] = text_width <= available
	for passive_frame in $UI.find_children("PlayerPassive_*", "Panel", true, false):
		var content: Control = passive_frame.get_node_or_null("PassiveContent")
		review_checks[frame_name + ": passive has padded content " + str(passive_frame.name)] = content != null
		if content != null:
			_check_content_insets(frame_name + ": " + str(passive_frame.name), passive_frame, content)
			var style: StyleBox = passive_frame.get_theme_stylebox("panel")
			var padding := Vector4(style.get_content_margin(SIDE_LEFT), style.get_content_margin(SIDE_TOP), style.get_content_margin(SIDE_RIGHT), style.get_content_margin(SIDE_BOTTOM))
			review_checks[frame_name + ": passive uses shared border padding " + str(passive_frame.name)] = padding == ART.COMMON_PANEL_PADDING
			for control in content.get_children():
				if control is Control:
					review_checks[frame_name + ": passive control inside content " + str(control.name)] = Rect2(Vector2.ZERO, content.size).encloses(control.get_rect())
		review_checks[frame_name + ": passive frame within viewport " + str(passive_frame.name)] = get_viewport().get_visible_rect().encloses(passive_frame.get_global_rect())
		for control_name in ["DrawChargeIcon", "DrawChargeLabel", "DrawChargeBar", "DrawChargePercent", "LibraryDiscardLabel"]:
			var control: Control = $UI.find_child(control_name, true, false)
			if control == null: continue
			review_checks[frame_name + ": draw control stays in viewport " + control_name] = get_viewport().get_visible_rect().encloses(control.get_global_rect())
			review_checks[frame_name + ": passive clear of draw control " + control_name] = not passive_frame.get_global_rect().intersects(control.get_global_rect())
	if frame_name.ends_with("full_hand"):
		var hand_cards: Array[Control] = []
		for control in $UI._reference.find_children("*", "Button", true, false):
			if control.has_meta("battle_hand_index"): hand_cards.append(control)
		review_checks[frame_name + ": five hand cards visible"] = hand_cards.size() == 5
		var action: Control = $UI._reference.find_child("PlayCardsButton", true, false)
		for card in hand_cards:
			var card_rect := card.get_global_rect()
			review_checks[frame_name + ": hand inside viewport " + str(card.get_meta("battle_hand_index"))] = get_viewport().get_visible_rect().encloses(card_rect)
			review_checks[frame_name + ": play clear of hand " + str(card.get_meta("battle_hand_index"))] = action != null and not action.get_global_rect().intersects(card_rect)
			var panel: Control = card.get_node("BattleTextPanel")
			var illustration: Control = card.get_node("Illustration")
			review_checks[frame_name + ": original card illustration " + str(card.get_meta("battle_hand_index"))] = illustration.get_rect().is_equal_approx(Rect2(14, 14, 190, 285))
			review_checks[frame_name + ": text above illustration " + str(card.get_meta("battle_hand_index"))] = panel.get_index() > illustration.get_index()
			for child in card.get_children():
				if not child.get_meta("battle_primary_text", false): continue
				review_checks[frame_name + ": battle panel encloses " + str(card.get_meta("battle_hand_index")) + "/" + str(child.name)] = panel.get_rect().encloses(child.get_rect())
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
	var collected_value := ""
	if root is Label or root is Button: collected_value = root.text
	elif root is LineEdit: collected_value = root.placeholder_text if root.text.is_empty() else root.text
	if not collected_value.is_empty():
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
			var value: String = collected_value
			var max_line_width := 0.0
			for line in value.split("\n"):
				max_line_width = maxf(max_line_width, typeface.get_string_size(line, HORIZONTAL_ALIGNMENT_LEFT, -1.0, font_size).x)
			var available_text_width: float = root.size.x
			if root is Button or root is LineEdit:
				var style: StyleBox = root.get_theme_stylebox("normal")
				available_text_width -= style.get_content_margin(SIDE_LEFT) + style.get_content_margin(SIDE_RIGHT)
				if root is LineEdit and root.right_icon != null: available_text_width -= root.right_icon.get_width()
			var missing_glyphs: Array[int] = []
			for index in value.length():
				var codepoint := value.unicode_at(index)
				if codepoint > 32 and not Palette.is_bidi_isolate(codepoint) and not typeface.has_char(codepoint) and not missing_glyphs.has(codepoint): missing_glyphs.append(codepoint)
			rows.append({"path": str($UI.get_path_to(root)), "type": root.get_class(),
				"text": value, "missing_glyphs": missing_glyphs, "max_line_width": max_line_width, "available_text_width": available_text_width, "tooltip": root.tooltip_text, "rect": [rect.position.x, rect.position.y, rect.size.x, rect.size.y],
				"visible_rect": [visible_rect.position.x, visible_rect.position.y, visible_rect.size.x, visible_rect.size.y],
				"font_size": font_size, "effective_font_size": font_size * absf(scale.y) * pixel_scale,
				"single_line_width": typeface.get_string_size(value, HORIZONTAL_ALIGNMENT_LEFT, -1, font_size).x,
				"font_color": root.get_theme_color("font_disabled_color" if root is Button and root.disabled else "font_color").to_html(),
				"disabled": root.disabled if root is Button else false,
				"is_placeholder": root is LineEdit and root.text.is_empty(),
				"autowrap_mode": root.autowrap_mode if root is Label else TextServer.AUTOWRAP_OFF,
				"battle_primary_text": bool(root.get_meta("battle_primary_text", false)),
				"lines": root.get_line_count() if root is Label else 1,
				"max_lines_visible": root.max_lines_visible if root is Label else -1,
				"visible_lines": root.get_visible_line_count() if root is Label else 1})
	for child in root.get_children():
		_collect_text(child, rows)


var _preparation_review_cases: Array = []
var _preparation_review_index: Dictionary = {}

func _preparation_fixture_value(name: String, path: String, method: int = HTTPClient.METHOD_GET) -> Dictionary:
	var folder: String = OS.get_environment("FANTASYCARD_PREPARATION_REVIEW_INPUT")
	assert(not folder.is_empty())
	var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("input-manifest.json")))
	assert(FileAccess.get_sha256(folder.path_join(name)) == manifest[name])
	var http = preload("res://network/http_protocol.gd")
	var response: Dictionary = http.decode_response(http.route(path, method), 200, PackedStringArray(["Content-Type: application/protobuf"]), FileAccess.get_file_as_bytes(folder.path_join(name)))
	assert(response.ok)
	return response.data

func _prepare_original_preparation_scene(scenario: String) -> bool:
	if scenario == "prep_current_d1":
		Game.lobby["season"] = {"state": "Active", "seasonId": "formal-current", "configVersion": Game.CATALOG.data.version, "highestOpenDifficulty": 5, "highestUnlockedDifficulty": 5}
		Game.preparation_difficulty = 1
		Game.use_borrowed_deck = true
		$UI.screen = "prep"
		await _render_base()
		return false
	var folder: String = OS.get_environment("FANTASYCARD_PREPARATION_REVIEW_INPUT")
	if _preparation_review_cases.is_empty():
		var manifest: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("input-manifest.json")))
		assert(FileAccess.get_sha256(folder.path_join("cases.json")) == manifest["cases.json"])
		_preparation_review_cases = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("cases.json")))
	var borrowed: bool = scenario in ["prep_source_borrowed", "prep_source_deck", "prep_source_deck_bottom"]
	var entry: Dictionary = _preparation_review_cases.filter(func(row): return row.borrowed == borrowed)[0]
	if _preparation_review_index.is_empty():
		var config: Dictionary = _preparation_fixture_value("original.configuration.envelope", "/api/v1/config/" + str(entry.sourceVersion))
		var data: Dictionary = preload("res://data/config_bundle.gd").new().decode(config.bundle, str(entry.sourceVersion), str(entry.originalHash))
		assert(not data.is_empty())
		_preparation_review_index = preload("res://data/catalog_index.gd").from_data(data)
	var index: Dictionary = _preparation_review_index.duplicate(true)
	index["_origin"] = Game.gateway.base_url
	Game._room_catalogs[index.version] = index
	var locked: bool = scenario in ["prep_source_locked", "prep_source_unavailable"]
	Game.lobby = _preparation_fixture_value(str(entry.name) + (".locked" if locked else ".draft") + ".bootstrap.envelope", "/api/v1/bootstrap").duplicate(true)
	Game.preparation = Game.lobby.activePreparation if Game.lobby.get("activePreparation") is Dictionary else {}
	Game.use_borrowed_deck = borrowed
	Game.preparation_difficulty = 1
	Game.hero_class = "Guardian" if locked else "Mage"
	if scenario == "prep_source_unavailable":
		Game._room_catalogs.erase(index.version)
		Game.preparation_configuration_error = Palette.message("config_archive_unavailable", [])
	$UI._sync_account_session()
	$UI.screen = "prep"
	$UI.bag_tier = "Free"
	$UI._owned_index_ready = false
	$UI._owned_by_id.clear()
	$UI._card_pool.set_process(false)
	await _render_base()
	if scenario == "prep_source_menu":
		$UI._reference.get_node("SeasonDifficultySelector").show_popup()
		await get_tree().process_frame
	if scenario in ["prep_source_deck", "prep_source_deck_bottom"]:
		$UI._show_preparation_deck()
		await get_tree().process_frame
		await get_tree().process_frame
		if scenario == "prep_source_deck_bottom":
			for child in $UI.get_children():
				if child is AcceptDialog and child.title == Palette.localized("preparation_deck_preview"):
					child.get_node("PreparationDeckScroll").set_deferred("scroll_vertical", 100000)
			await get_tree().process_frame
			await get_tree().process_frame
	return false

func _check_original_preparation_scene(frame_name: String) -> void:
	var model = preload("res://ui/preparation_model.gd")
	var view: Control = $UI._reference
	if frame_name.ends_with("_prep_current_d1"):
		var selector: OptionButton = view.get_node("SeasonDifficultySelector")
		review_checks[frame_name + ": formal D1 remains Purple"] = selector.get_item_text(1).contains(Palette.word("Purple"))
		return
	var unavailable: bool = frame_name.ends_with("_unavailable")
	var locked: bool = frame_name.ends_with("_locked") or unavailable
	review_checks[frame_name + ": original catalog readiness"] = Game.preparation_catalog_ready() != unavailable
	if unavailable:
		review_checks[frame_name + ": original missing is explicit"] = view.get_node("PreparationConfigurationUnavailable").is_visible_in_tree()
		review_checks[frame_name + ": queue disabled and cancel available"] = view.get_node("PreparationStartMatch").disabled and not view.get_node("PreparationCancel").disabled
		return
	var source: Dictionary = Game.preparation_catalog_index()
	review_checks[frame_name + ": original backpack exactly21"] = view.get_node("PreparationBackpackScroll/PreparationBackpackGrid").get_child_count() == 21
	review_checks[frame_name + ": original Wood preference"] = view.get_node("LootPreferenceSelector").selected == 0
	if locked:
		review_checks[frame_name + ": locked original hero wins over profile selection"] = $UI.display_hero_class() == "Mage"
		review_checks[frame_name + ": selectors remain immutable"] = view.get_node_or_null("SeasonDifficultySelector") == null and view.get_node_or_null("SeasonBorrowedDeckToggle") == null
	else:
		var selector: OptionButton = view.get_node("SeasonDifficultySelector")
		review_checks[frame_name + ": original D1 control cap Green"] = selector.selected == 1 and selector.get_item_text(1).contains(Palette.word("Green"))
		var loan: CheckButton = view.get_node("SeasonBorrowedDeckToggle")
		review_checks[frame_name + ": original template identity"] = loan.get_meta("template_id") == "archive-loan-mage"
		if frame_name.ends_with("_menu"):
			var popup: PopupMenu = selector.get_popup()
			review_checks[frame_name + ": original selector popup visible"] = popup.visible and popup.item_count == 6
			for tier in 6: review_checks[frame_name + ": original menu cap " + str(tier)] = popup.get_item_text(tier).contains(Palette.word(model.difficulty(tier, source).entry_quality))
	if frame_name.contains("_prep_source_deck"):
		var found := false
		for child in $UI.get_children():
			if child is AcceptDialog and child.title == Palette.localized("preparation_deck_preview"):
				found = true
				var scroll: ScrollContainer = child.get_node("PreparationDeckScroll")
				var label: Label = scroll.get_node("PreparationDeckText")
				review_checks[frame_name + ": real original damage visible"] = label.text.contains(str(int(_preparation_review_cases[0].originalDamage)))
				review_checks[frame_name + ": original loan has all20 slots"] = Game.preparation_deck_preview().card_ids.size() == 20 and Game.preparation_deck_preview().card_ids[12] == "C30"
				if frame_name.ends_with("_bottom"): review_checks[frame_name + ": full deck end reachable"] = scroll.scroll_vertical > 0
		review_checks[frame_name + ": deck preview dialog visible"] = found

var _refresh_review_index: Dictionary = {}

func _prepare_refresh_scene(scenario: String) -> bool:
	if _refresh_review_index.is_empty():
		var folder: String = OS.get_environment("FANTASYCARD_REFRESH_REVIEW_INPUT")
		assert(not folder.is_empty())
		var cases: Array = JSON.parse_string(FileAccess.get_file_as_string(folder.path_join("cases.json")))
		var entry: Dictionary = cases.filter(func(row): return row.name == "seven")[0]
		var http = preload("res://network/http_protocol.gd")
		var envelope: Dictionary = http.decode_response(http.route("/api/v1/config/" + str(entry.version), HTTPClient.METHOD_GET), 200, PackedStringArray(["Content-Type: application/protobuf"]), FileAccess.get_file_as_bytes(folder.path_join("seven.envelope")))
		assert(envelope.ok)
		var reader := preload("res://data/config_bundle.gd").new()
		var data: Dictionary = reader.decode(envelope.data.bundle, str(entry.version), str(entry.hash))
		assert(not data.is_empty())
		_refresh_review_index = preload("res://data/catalog_index.gd").from_data(data)
	Game.room = _room_fixture()
	Game.room.config_version = _refresh_review_index.version
	Game.room.player.phase = "Choice"
	Game.room.allowed_actions = ["choice.pick", "choice.refresh"]
	Game.room.reward_choice = {"refresh_count": 3 if scenario == "refresh_exhausted" else 0, "options": [{"option_id": "equipment", "kind": 1, "quantity": 1}, {"option_id": "fragments", "kind": 2, "quantity": 18}, {"option_id": "heal", "kind": 3, "quantity": 1, "heal_percent": 14}]}
	var index: Dictionary = _refresh_review_index.duplicate(true)
	index["_origin"] = "http://wrong-origin.example" if scenario == "refresh_unavailable" else Game.gateway.base_url
	Game._room_catalogs[index.version] = index
	await _render_base()
	return false

func _check_refresh_scene(frame_name: String) -> void:
	if not "_refresh_" in frame_name: return
	var button: Button = $UI.find_child("RewardRefresh", true, false)
	var heading: Label = $UI.find_child("RewardChoiceTitle", true, false)
	var plate: TextureRect = $UI.find_child("RewardChoicePlate", true, false)
	var exhausted: bool = frame_name.ends_with("_refresh_exhausted")
	var unavailable: bool = frame_name.ends_with("_refresh_unavailable")
	var expected: String = Palette.localized("refresh_exhausted") if exhausted else Palette.localized("quote_unavailable_short") if unavailable else Palette.localized("exploration_refresh_cost") % 7
	review_checks[frame_name + ": original exact localized price or state"] = button.text == expected
	review_checks[frame_name + ": unavailable and exhausted disabled"] = button.disabled == (exhausted or unavailable)
	review_checks[frame_name + ": visible price button"] = button.is_visible_in_tree()
	review_checks[frame_name + ": heading clear of plate ornaments"] = Rect2(190, 22, 360, 112).grow(0.5).encloses(heading.get_rect())
	var source_aspect: float = float(plate.texture.get_width()) / plate.texture.get_height()
	review_checks[frame_name + ": title plate retains aspect and clears reward panel"] = is_equal_approx(plate.size.x / plate.size.y, source_aspect) and plate.get_rect().end.y <= 160
	var breaks: int = TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND | TextServer.BREAK_ADAPTIVE
	var measured: Vector2 = heading.get_theme_font("font").get_multiline_string_size(heading.text, HORIZONTAL_ALIGNMENT_CENTER, heading.size.x, heading.get_theme_font_size("font_size"), -1, breaks)
	review_checks[frame_name + ": complete localized heading"] = heading.text == Palette.localized("loot_three_choices") and heading.get_line_count() <= 2 and heading.get_visible_line_count() >= heading.get_line_count() and measured.x <= heading.size.x + 0.5 and measured.y <= heading.size.y + 0.5
	review_checks[frame_name + ": readable heading"] = heading.get_theme_font_size("font_size") * float(get_window().size.y) / get_viewport().get_visible_rect().size.y >= 12.0
	if unavailable: review_checks[frame_name + ": original config failure tooltip"] = button.tooltip_text == Palette.localized("config_archive_unavailable")

func _prepare_historical_equipment_scene(scenario: String,locale: String) -> bool:
	var key: String=locale+"_"+str(get_window().size.x)+"_"+scenario
	if scenario=="historical_gear_none":
		var gear: Dictionary=_c05_gear("historical-no-trait","Head")
		gear.quality="Green";gear.level=0;gear.effectAffix=null;gear.secondaryTrait=null;gear.element="Wood"
		$UI.inventory.equipments=[gear];Game.lobby.inventory=$UI.inventory
		$UI.gear_draft=[gear.instanceId,null,null,null,null];$UI.screen="gear"
		Game.lobby["season"]={"state":"Active","seasonId":"review","statsVersion":"season-equipment-v1","configVersion":Game.CATALOG.data.version}
		await _render_base();$UI._show_equipment_details(gear)
		var text: String=preload("res://ui/equipment_details.gd").description(gear)
		review_checks[key+": absent trait stays absent"]=gear.secondaryTrait==null
		review_checks[key+": no invented draw label"]=not text.contains(Palette.localized("battle_draw_interval_seconds"))
		return false
	$UI.screen="hall";await _render_base()
	Game.ready_prompt={"match_id":"fixture-match"};Game.ticket={"ticket_id":"fixture-ticket"};Game.preparation={"preparation_id":"fixture-preparation"}
	Game.lobby["activePreparation"]=Game.preparation
	var captured: Array[String]=[]
	var record := func(value: String): captured.append(value)
	Game.notice.connect(record)
	var token: String=Game.gateway.token;Game.gateway.token=""
	Game._on_event("room.ready_removed",{"reason":"equipment_unavailable" if scenario=="ready_removed_equipment" else "ready_timeout"})
	Game.gateway.token=token;Game.notice.disconnect(record)
	var expected: String=Palette.localized("state_changed" if scenario=="ready_removed_equipment" else "ready_timeout")
	review_checks[key+": reason uses correct localized text"]=captured.size()==1 and captured[0]==expected
	review_checks[key+": cancelled preparation state cleared"]=Game.ready_prompt.is_empty() and Game.ticket.is_empty() and Game.preparation.is_empty() and Game.lobby.activePreparation==null
	$UI._toast(expected)
	return false
