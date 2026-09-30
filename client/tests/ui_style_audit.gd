extends "res://tests/gameplay_ui_preview.gd"

## Real Godot rendering of isolated fixture states. No economic/room commands.
const Palette = preload("res://ui/palette.gd")
const Artwork = preload("res://ui/art.gd")
const Comparison = preload("res://ui/equipment_compare_dialog.gd")
const ConfirmScene = preload("res://ui/confirmation_modal.tscn")
var captures: Array[Dictionary] = []
var audit_errors: Array[String] = []
var text_observations: Array[Dictionary] = []
var action_calls := 0
var prior_language := "zh-CN"

func _ready() -> void:
	super._ready()
	output = OS.get_environment("FANTASYCARD_UI_EVIDENCE")
	if output.is_empty(): output = "res://evidence/ui-style"
	Sound.persist_settings = false
	Sound.set_muted(true)
	get_window().gui_embed_subwindows = true
	get_viewport().set_disable_input(true)
	prior_language = Palette.language()

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	await get_tree().create_timer(0.5).timeout
	for locale in ["zh-CN", "en"]:
		Palette.set_language(locale)
		$UI.theme = Palette.theme()
		for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720), Vector2i(960, 540)]:
			get_window().size = resolution
			await get_tree().process_frame
			await _matrix("%s_%s" % [locale, resolution.x])
	Palette.set_language(prior_language)
	var report := {"ok": audit_errors.is_empty(), "fixture_only": true,
		"source_sha": OS.get_environment("FANTASYCARD_SOURCE_SHA"),
		"rendering": "Godot 4.7.2 gl_compatibility on Xorg :93, viewport capture",
		"captures": captures, "screenshots": captures.size(), "checks": checks,
		"errors": audit_errors, "text_observations": text_observations,
		"limitations": "Offline state fixtures exercise production UI, signals and real rendering. They do not prove live server transactions, recovery or pressure/load outcomes. Audio output uses Dummy."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify({"ok": report.ok, "screenshots": captures.size(), "checks": checks.size(), "errors": audit_errors}))
	get_tree().quit(0 if report.ok else 1)

func _reset() -> void:
	Game.room = {}
	Game.settlement = {}
	Game.preparation = {}
	Game.ready_prompt = {}
	Game.ticket = {}
	Game.busy = false
	Game.configuration_error = ""
	Game.authentication_reason = ""
	Game.hero_class = "Mage"
	Game.selected_cards = []
	Game.clear_combat_preview()
	Game.connection = "UI AUDIT · OFFLINE FIXTURE"
	Game.lobby = {"player": {"userId": "ui-audit"}, "wallet": {"gold": 10000},
		"materials": {"equipmentFragments": 999, "warriorSoul": 300, "mageSoul": 300, "priestSoul": 300, "guardianSoul": 300},
		"decks": [{"heroClass": "Mage", "cardIds": ["MAG-01", "C01", "C02"]}],
		"classWeapons": [{"heroClass": "Mage", "level": 2, "version": 1}], "equippedLoadouts": []}
	$UI.screen_loading = false
	$UI._codex_ready = true
	$UI._shop_inventory_ready = true
	$UI._search = ""
	$UI._quality = ""
	$UI._codex_card = ""
	$UI.gear_draft = [null, null, null, null, null]
	$UI.inventory = {"equipments": [], "consumables": {"healthPotionCount": 2, "advancedBagCount": 1, "topBagCount": 1}}
	$UI.owned = []
	for id in $UI.cards:
		var info: Dictionary = $UI.cards[id]
		if not info.get("is_codex", false): continue
		var owned: bool = info.source == "Initial" or (info.source == "Class" and info.quality == "White")
		$UI.owned.append({"cardId": id, "heroClass": info.hero_class, "unlocked": owned, "copyCount": 1 if owned else 0,
			"level": 0, "version": 1, "craftCost": 12, "dismantleRefund": 3, "canDismantle": owned,
			"currencyKind": "WarriorSoul" if info.hero_class == null else str(info.hero_class) + "Soul"})
	$UI.listings = []
	$UI._enhance_item = ""
	$UI._enhancement_quote_key = "Mage:1"
	$UI._enhancement_quote = {}
	Game.mail = {"items": [], "unreadCount": 0}
	$UI._view_cell = "completion-room:3:2"
	for key in ["pending_move", "inventory_open", "relic_pile", "inventory_selected", "relic_selected", "mail_selected_id"]:
		if $UI.has_meta(key): $UI.remove_meta(key)
	$UI.tips_overlay.clear()

func _matrix(suffix: String) -> void:
	_reset()
	var lobby: Dictionary = Game.lobby.duplicate(true)
	Game.lobby = {}
	$UI.screen = "hall"
	Game.server_info = {"announcement": {"title": "云端验收公告 · Long announcement title", "body": "这是运行时长文案，用来检查换行、滚动和按钮边界。\nThis deliberately long announcement remains runtime text.\n".repeat(10)}}
	await _take("login_long_" + suffix)
	Game.busy = true
	Game.authentication_reason = Palette.localized("connecting")
	await _take("login_busy_" + suffix)
	Game.busy = false
	Game.authentication_reason = Palette.localized("operation_rejected")
	await _take("login_error_" + suffix)
	Game.authentication_reason = ""
	Game.lobby = lobby
	for hero in ["Priest", "Mage", "Guardian"]:
		Game.hero_class = hero
		$UI.screen = "hall"
		await _take("hall_" + hero.to_lower() + "_" + suffix)
		$UI.screen = "prep"
		$UI.bag_tier = "Free"
		await _take("prep_" + hero.to_lower() + "_" + suffix)
		_check_audit($UI._reference.get_node("HeroPortrait").texture == Artwork.portrait(hero), "portrait_" + hero + "_" + suffix)
		if OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
			_check_audit($UI._reference.get_node_or_null("SignatureWeaponFrame") != null, "signature_frame_" + hero + "_" + suffix)
	Game.hero_class = "Mage"
	$UI.screen = "prep"
	var frozen_cards: Array = []
	frozen_cards.resize(20)
	frozen_cards.fill("GUA-01")
	Game.preparation = {"snapshot": {"heroClass": "Guardian", "maximumHp": 99, "cardIds": frozen_cards, "equipmentIds": [], "equipmentSnapshots": [], "classWeaponLevel": 4, "backpackTier": "Top", "backpackCapacity": 36, "safeSlotIndexes": [33, 34, 35], "potionCount": 2}}
	await _take("prep_locked_" + suffix)
	if OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
		var frozen_summary: Label = $UI._reference.get_node_or_null("FrozenPreparationSummary")
		_check_audit(frozen_summary != null and frozen_summary.text == Palette.localized("locked_deck_summary") % [20, 99] and frozen_summary.get_visible_line_count() == 1, "frozen preparation deck and HP visible " + suffix)
	Game.ticket = {"ticketId": "fixture-ticket"}
	await _take("matching_" + suffix)
	Game.ticket = {}
	Game.preparation = {}
	Game.ready_prompt = {"ready_players": 1, "required_players": 2, "deadline_unix_ms": int(Time.get_unix_time_from_system() * 1000) + 30000}
	await _take("ready_" + suffix)
	Game.ready_prompt = {}
	$UI.screen = "shop"
	$UI.screen_loading = true
	await _take("loading_" + suffix)
	$UI.screen_loading = false
	$UI.shop = {"products": []}
	await _take("shop_empty_" + suffix)
	$UI.shop = _shop_fixture()
	for product in $UI.shop.products:
		if product.payload is String: product.payload = JSON.parse_string(product.payload)
	await _take("shop_" + suffix)
	$UI._reference.get_node("ShopScroll").scroll_horizontal = 100000
	await _take("shop_tail_" + suffix, false)
	for hero in ["Priest", "Mage", "Guardian"]:
		var product: Node = $UI._reference.find_child("Product_fixture-" + hero, true, false)
		_check_audit(product != null and product.get_node("ProductArt").texture != null, "shop_class_soul_" + hero + "_" + suffix)
	$UI.screen = "market"
	await _take("market_empty_" + suffix)
	$UI.screen = "gear"
	await _take("gear_empty_" + suffix)
	var current := _fixture_gear("head-current", "Head", "Purple", "Fire", "Bulwark")
	var selected := _fixture_gear("head-selected", "Head", "Orange", "Water", "Piercing")
	$UI.inventory.equipments = [current, selected]
	$UI.gear_draft = ["head-current", null, null, null, null]
	await _take("gear_" + suffix)
	var comparison := Comparison.new()
	$UI.add_child(comparison)
	comparison.open(selected, current, [current])
	await _take("compare_" + suffix, false)
	var shell: Control = comparison.get_node("ComparisonShell")
	_check_audit(Rect2(0, 0, 1920, 1080).encloses(shell.get_global_rect()), "comparison_bounds_" + suffix)
	comparison.queue_free()
	await get_tree().process_frame
	$UI.screen = "enhance"
	await _take("enhance_loading_" + suffix)
	$UI._enhancement_quote = {"fragmentCost": 25, "availableMaterialCount": 2, "materialCount": 1, "canEnhance": false}
	await _take("enhance_disabled_" + suffix)
	$UI.screen = "cards"
	await _take("codex_" + suffix)
	_check_audit($UI._reference.find_child("CardGrid", true, false).get_child_count() == 220, "codex_220_" + suffix)
	$UI._codex_card = "GW08"
	await _take("codex_detail_" + suffix)
	$UI._codex_card = ""
	$UI._search = "NO_MATCH_UI_AUDIT"
	await _take("codex_empty_" + suffix)
	$UI._search = ""
	$UI.screen = "deck"
	$UI.deck_draft = ["MAG-01", "C01", "C02"]
	await _take("deck_" + suffix)
	$UI.screen = "hall"
	$UI._render()
	$UI._reference._mail()
	await _take("mail_empty_" + suffix, false)
	Game.room = _room_fixture()
	$UI._view_cell = "completion-room:3:2"
	$UI.set_meta("inventory_open", true)
	$UI.set_meta("inventory_selected", "pack-35")
	await _take("inventory_full_" + suffix)
	_check_audit($UI._reference.find_children("InventorySlot_*", "Button", true, false).size() == 36, "inventory_36_" + suffix)
	$UI.set_meta("inventory_open", false)
	await _take("action_" + suffix)
	Game.room.map = []
	for y in range(6):
		for x in range(6): Game.room.map.append({"row": y, "column": x, "has_spring": y == 0 and x == 3, "is_boss": y == 2 and x == 2})
	Game.room.legal_moves = [{"row": 2, "column": 2}]
	Game.room.allowed_actions.append("room.move")
	$UI.set_meta("exploration_map_open", true)
	await _take("map_" + suffix)
	$UI.set_meta("pending_move", Vector2i(2, 2))
	await _take("midlayer_" + suffix)
	$UI.remove_meta("pending_move")
	$UI.set_meta("exploration_map_open", false)
	Game.relic_details = {"pile-b": {"pile_id": "pile-b", "owner_name": "长夜归来的盾卫 · A very long traveler name", "version": 4, "items": []}}
	$UI.set_meta("inventory_open", true)
	$UI.set_meta("relic_pile", "pile-b")
	await _take("relic_empty_" + suffix)
	Game.relic_details["pile-b"].version = 3
	await _take("relic_stale_" + suffix)
	Game.room.player.inventory = []
	$UI.set_meta("relic_pile", "")
	await _take("inventory_empty_" + suffix)
	$UI.set_meta("inventory_open", false)
	Game.room.player.phase = "Choice"
	Game.room.reward_choice = {"refresh_count": 0, "options": [{"option_id": "equipment", "kind": 1, "quantity": 1}, {"option_id": "fragments", "kind": 2, "quantity": 18}, {"option_id": "heal", "kind": 3, "quantity": 1, "heal_percent": 14}]}
	Game.room.allowed_actions = ["choice.pick", "choice.refresh"]
	await _take("choose_" + suffix)
	Game.room.erase("reward_choice")
	Game.room.player.phase = "Pve"
	Game.room.allowed_actions = ["battle.play_cards", "battle.select_target"]
	Game.room.player.hand = [{"instance_id": "spell", "card_id": "MAG-01"}, {"instance_id": "monster", "card_id": "M-FIREBAT"}]
	Game.room.pve = {"battle_id": "ui-audit-battle", "current_target_id": "fire-bat", "monsters": [{"monster_id": "fire-bat", "hp": 24, "maximum_hp": 44, "shield": 8, "intent_kind": "Attack", "intent_element": "Fire", "intent_value": 2}]}
	Game.selected_cards = ["monster"]
	await _take("battle_selected_" + suffix)
	var monster: Button = $UI._reference.get_node_or_null("Card_M-FIREBAT")
	_check_audit(monster != null and monster.get_node("CardFrame").texture != null, "monster_frame_loaded_" + suffix)
	if monster != null:
		monster.pressed.emit()
		_check_audit(not "monster" in Game.selected_cards, "card_toggle_" + suffix)
	Game.room.player.hand = []
	Game.selected_cards = []
	await _take("battle_empty_hand_" + suffix)
	Game.room.player.phase = "Pvp"
	Game.room.duel = {"duel_id": "ui-audit-duel", "opponent_id": "other", "opponent": {"hp": 60, "maximum_hp": 100, "shield": 8}, "escape_remaining_ms": 1000}
	await _take("pvp_" + suffix)
	Game.room = {}
	Game.settlement = {"result": "Dead", "settlementId": "ui-audit", "details": {"items": []}}
	await _take("settlement_empty_" + suffix)
	Game.settlement.result = "Extracted"
	await _take("settlement_success_" + suffix)
	Game.settlement = {}
	$UI.screen = "hall"
	$UI._render()
	await _control_states(suffix)
	await _confirm_reopen(suffix)
	var settings = $UI.get_node("AudioSettings")
	settings.show_settings()
	await _take("settings_" + suffix, false)
	var popup: PopupPanel = settings._popup
	_check_audit(Rect2(get_viewport().get_visible_rect()).encloses(Rect2(popup.position, popup.size)), "settings_bounds_" + suffix)
	popup.hide()
	await get_tree().process_frame
	settings.show_settings()
	_check_audit(settings._popup.visible and $UI.get_node("AudioSettings").find_children("AudioSettingsPopup", "PopupPanel", true, false).size() <= 2, "settings_reopen_" + suffix)
	await _take("settings_reopen_" + suffix, false)
	settings._popup.hide()
	await get_tree().process_frame
	$UI._toast("遗物内容已变化，请刷新后选择。")
	await _take("error_toast_" + suffix, false)
	$UI.tips_overlay.clear()

func _control_states(suffix: String) -> void:
	var sampler := Control.new()
	sampler.name = "UIControlSampler"
	$UI.add_child(sampler)
	var panel := Panel.new()
	panel.position = Vector2(490, 260)
	panel.size = Vector2(940, 470)
	panel.add_theme_stylebox_override("panel", Artwork.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	sampler.add_child(panel)
	var blue := Button.new()
	blue.text = Palette.localized("back")
	blue.position = Vector2(50, 50)
	blue.size = Vector2(350, 80)
	Artwork.button(blue, "UI/CardCodex/card_codex_action_button_blue.png")
	panel.add_child(blue)
	var orange := Button.new()
	orange.text = Palette.localized("confirm")
	orange.position = Vector2(490, 50)
	orange.size = Vector2(350, 80)
	Artwork.button(orange, "UI/CardCodex/card_codex_action_button_orange.png")
	panel.add_child(orange)
	var disabled := Button.new()
	disabled.text = Palette.localized("buy")
	disabled.disabled = true
	disabled.position = Vector2(50, 170)
	disabled.size = Vector2(350, 80)
	Artwork.button(disabled, "UI/CardCodex/card_codex_action_button_orange.png")
	panel.add_child(disabled)
	var field := LineEdit.new()
	field.text = "99999999 · 运行时输入"
	field.position = Vector2(490, 170)
	field.size = Vector2(350, 80)
	panel.add_child(field)
	await _take("controls_normal_disabled_" + suffix, false)
	get_viewport().set_disable_input(false)
	var motion := InputEventMouseMotion.new()
	motion.position = blue.get_global_rect().get_center()
	get_viewport().push_input(motion, true)
	await _take("controls_hover_" + suffix, false)
	_check_audit(blue.get_draw_mode() == BaseButton.DRAW_HOVER, "button_hover_" + suffix)
	var down := InputEventMouseButton.new()
	down.position = motion.position
	down.button_index = MOUSE_BUTTON_LEFT
	down.pressed = true
	get_viewport().push_input(down, true)
	await _take("controls_pressed_" + suffix, false)
	_check_audit(blue.get_draw_mode() == BaseButton.DRAW_PRESSED, "button_pressed_" + suffix)
	down = InputEventMouseButton.new()
	down.position = motion.position
	down.button_index = MOUSE_BUTTON_LEFT
	get_viewport().push_input(down, true)
	field.grab_focus()
	await _take("controls_input_focus_" + suffix, false)
	_check_audit(field.has_focus(), "input_focus_" + suffix)
	get_viewport().set_disable_input(true)
	sampler.queue_free()
	await get_tree().process_frame

func _confirm_reopen(suffix: String) -> void:
	for iteration in range(2):
		var modal = ConfirmScene.instantiate()
		$UI.add_child(modal)
		modal.configure("这是运行时长文案：确认后将执行所选操作，返回可以继续检查物品。\nThis long runtime description checks wrapping and readability without baking text into artwork.", func(): action_calls += 1, {"tall": true})
		await _take("confirm_%s_%s" % [iteration, suffix], false)
		var dialog: Control = modal.get_node("DialogPanel")
		_check_audit(dialog.get_global_rect().encloses(modal.get_node("DialogPanel/ConfirmButton").get_global_rect()), "confirm_inside_%s_%s" % [iteration, suffix])
		modal.get_node("DialogPanel/CancelButton").pressed.emit()
		await get_tree().process_frame
		_check_audit(action_calls == 0 and not is_instance_valid(modal), "cancel_reopen_%s_%s" % [iteration, suffix])

func _take(capture_name: String, rebuild: bool = true) -> void:
	if rebuild: $UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	await get_tree().create_timer(0.15).timeout
	if capture_name.begins_with("login_") and OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
		var brand: Label = $UI.find_child("GameTitle", true, false)
		_check_audit(brand != null and brand.get_line_count() == 1 and brand.get_visible_line_count() == 1, capture_name + ": localized brand stays on one visible line")
		var page: ScrollContainer = $UI.find_child("LoginPageScroll", true, false)
		for frame_name in ["LoginAuthFrame", "LoginAnnouncementFrame"]:
			var login_frame: Control = $UI.find_child(frame_name, true, false)
			_check_audit(login_frame != null and page.get_global_rect().encloses(login_frame.get_global_rect()), capture_name + ": " + frame_name + " fully inside page")
	$UI.tips_overlay.clear()
	if capture_name.begins_with("error_toast_"): $UI._toast("遗物内容已变化，请刷新后选择。")
	if is_instance_valid($UI._reference) and OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1":
		var preview: Control = $UI._reference.get_node_or_null("CombatPreview")
		if preview != null:
			var safe := Rect2(preview.get_global_rect().position + Vector2(64, 14), preview.size - Vector2(128, 28))
			for label in $UI._reference.find_children("CombatPreview*", "Label", true, false):
				_check_audit(safe.encloses(label.get_global_rect()), capture_name + ": " + str(label.name) + " inside painted rails")
	for bar in get_tree().get_nodes_in_group("bounded_progress"):
		if not bar.slot_rect().encloses(bar.fill_rect()): audit_errors.append(capture_name + ": bar escapes artwork slot")
	for node in $UI.find_children("*", "Label", true, false):
		if not node.is_visible_in_tree() or node.text.is_empty(): continue
		if node.get_visible_line_count() == 0: audit_errors.append(capture_name + ": invisible text " + str(node.name))
		if node.get_line_count() > node.get_visible_line_count() and node.clip_text and node.text_overrun_behavior == TextServer.OVERRUN_NO_TRIMMING:
			text_observations.append({"capture": capture_name, "node": str(node.name), "text": node.text.left(100), "lines": node.get_line_count(), "visible": node.get_visible_line_count(), "rect": str(node.get_rect()), "font_size": node.get_theme_font_size("font_size"), "font_height": node.get_theme_font("font").get_height(node.get_theme_font_size("font_size"))})
			if OS.get_environment("FANTASYCARD_UI_ASSERT_FIXES") == "1": audit_errors.append(capture_name + ": clipped text " + node.text.left(40))
	RenderingServer.force_draw(false)
	var frame := get_viewport().get_texture().get_image()
	var path := output + "/" + capture_name + ".png"
	if frame.save_png(path) != OK: audit_errors.append("Could not save " + capture_name)
	captures.append({"name": capture_name, "file": capture_name + ".png", "pixels": [frame.get_width(), frame.get_height()]})

func _check_audit(condition: bool, label: String) -> void:
	checks[label] = condition
	if not condition: audit_errors.append(label)

func _fixture_gear(id: String, slot: String, quality: String, element: String, affix: String) -> Dictionary:
	return {"instanceId": id, "slot": slot, "quality": quality, "element": element, "effectAffix": affix, "secondaryTrait": "DrawInterval", "level": 0, "location": "Warehouse", "version": 1}
