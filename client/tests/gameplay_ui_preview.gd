extends "res://tests/art_preview.gd"

var checks: Dictionary = {}

func _ready() -> void:
	output = "res://evidence/gameplay-completion"
	get_window().gui_embed_subwindows = true
	super._ready()
	Game.set_process(false)
	Game.gateway.reconnect_enabled = false
	Game.gateway.socket.close()
	Game.lobby.materials = {"equipmentFragments": 999, "warriorSoul": 300, "mageSoul": 300, "priestSoul": 300, "guardianSoul": 300}
	Game.lobby.decks = []
	Game.configuration_error = ""
	Game.busy = false
	$UI._codex_ready = true
	$UI._view_cell = "completion-room:3:2"

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720)]:
		get_window().size = resolution
		var suffix := "_%s" % resolution.x
		Game.room = _room_fixture()
		$UI.set_meta("inventory_open", true)
		$UI.set_meta("inventory_selected", "pack-35")
		$UI.set_meta("relic_pile", "")
		await _capture("inventory_36" + suffix)
		_check($UI._reference.find_children("InventorySlot_*", "Button", true, false).size() == 36, "36 slots" + suffix)
		for index in [33, 34, 35]:
			var slot: Button = $UI._reference.get_node("InventorySlot_%s" % index)
			_check(slot.text.begins_with("安全"), "Safe slot %s" % index + suffix)
			_check(slot._can_drop_data(Vector2.ZERO, {"room_id": "completion-room", "inventory_item_id": "pack-0"}), "Same-room inventory drag" + suffix)
			_check(not slot._can_drop_data(Vector2.ZERO, {"room_id": "different-room", "inventory_item_id": "pack-0"}), "Foreign-room drag rejected" + suffix)
		var description_scroll: ScrollContainer = _description_scroll()
		_check(description_scroll != null, "Long equipment details can scroll" + suffix)
		if description_scroll != null:
			description_scroll.scroll_vertical = 10000
			await _capture("inventory_details_bottom" + suffix, false)
			_check(description_scroll.scroll_vertical > 0, "Last equipment modifiers reachable" + suffix)
			$UI._render()
			await get_tree().process_frame
			await get_tree().process_frame
			_check(_description_scroll().scroll_vertical > 0, "Equipment detail scroll survives render" + suffix)
		$UI.set_meta("inventory_open", false)
		await _capture("relics_multiple" + suffix)
		_check($UI._reference.find_children("Action_relic", "Button", true, false).size() == 2, "Two independently selectable relic piles" + suffix)
		Game.relic_details = {"pile-a": {"pile_id": "pile-a", "owner_name": "逐风者", "version": 7, "items": [_item(90)]}, "pile-b": {"pile_id": "pile-b", "owner_name": "长夜归来的盾卫", "version": 4, "items": [_item(91), _item(92)]}}
		$UI.set_meta("inventory_open", true)
		$UI.set_meta("relic_pile", "pile-a")
		$UI.set_meta("relic_selected", "pack-90")
		await _capture("relic_replace" + suffix)
		_check(_has_button("放回选中物品，再拾取", true), "Full pack supports replacement" + suffix)
		$UI.set_meta("relic_pile", "pile-b")
		$UI.set_meta("relic_selected", "pack-91")
		await _capture("relic_other_owner" + suffix)
		_check(_all_text().contains("长夜归来的盾卫"), "Selected relic owner rendered" + suffix)
		Game.relic_details["pile-b"].version = 3
		await _capture("relic_stale" + suffix)
		_check(_all_text().contains("遗物内容已变化"), "Stale relic content blocked" + suffix)
		_check(not _has_button("放回选中物品，再拾取", true), "Stale relic has no active transfer" + suffix)
		Game.room = {}
		$UI.set_meta("inventory_open", false)
		$UI.screen = "cards"
		$UI.deck_draft = []
		$UI.owned = [{"cardId": "MAG-01", "unlocked": true, "copyCount": 2, "level": 3, "version": 7, "currencyKind": "MageSoul", "craftCost": 12, "dismantleRefund": 9, "canDismantle": true, "canUpgrade": true, "upgradeCost": 80, "upgradeCopyCost": 1, "currentEffect": {"element": "Fire", "elementalDamage": 11}, "nextEffect": {"element": "Fire", "elementalDamage": 12}}]
		$UI._codex_card = "MAG-01"
		Game.lobby.materials.mageSoul = 300
		await _capture("card_upgrade" + suffix)
		_check(not $UI._reference.find_child("UpgradeCard", true, false).disabled, "Affordable upgrade enabled" + suffix)
		_check(_all_text().contains("下一级：") and _all_text().contains("需额外同名卡"), "Upgrade effect and copy cost rendered" + suffix)
		var details: Control = $UI._reference.find_child("DetailsPanel", true, false)
		for name in ["UpgradeCard", "DismantleCard", "CloseCardDetails"]:
			_check(details.get_global_rect().encloses($UI._reference.find_child(name, true, false).get_global_rect()), name + " within modal" + suffix)
		var card: Control = $UI._reference.find_child("DetailCard", true, false)
		_check(not card.get_global_rect().intersects($UI._reference.find_child("UpgradeCard", true, false).get_global_rect()), "Upgrade control does not cover card" + suffix)
		for label in $UI._reference.find_children("*", "Label", true, false):
			if label.text.begins_with("需额外同名卡"):
				_check(not card.get_global_rect().intersects(label.get_global_rect()), "Copy cost does not cover card" + suffix)
		Game.lobby.materials.mageSoul = 0
		await _capture("card_upgrade_insufficient" + suffix)
		_check($UI._reference.find_child("UpgradeCard", true, false).disabled, "Insufficient upgrade disabled" + suffix)
		$UI._codex_card = ""
		$UI.screen = "enhance"
		$UI._enhance_item = "preview-gear"
		$UI.inventory.equipments = [{"instanceId": "preview-gear", "slot": "Chest", "quality": "Orange", "element": "Earth", "effectAffix": "Bulwark", "secondaryTrait": "DrawInterval", "level": 3, "version": 7, "location": "Inventory", "isBound": false}]
		$UI._enhancement_quote_key = "preview-gear:7"
		$UI._enhancement_quote = {"fragmentCost": 125, "materialCount": 1, "availableMaterialCount": 2, "canEnhance": true, "nextLevel": 4, "expectedVersion": 7}
		await _capture("enhancement_quote" + suffix)
		_check(_all_text().contains("所需碎片 125") and _all_text().contains("同品质材料 2 / 1 件"), "Authoritative enhancement quote rendered" + suffix)
		for label in $UI._reference.find_children("*", "Label", true, false):
			if label.text.begins_with("属性 +3"):
				_check(label.get_line_count() == 7 and label.get_visible_line_count() == 7, "All enhancement benefits visible" + suffix)
		$UI._enhancement_quote.canEnhance = false
		$UI._enhancement_quote.availableMaterialCount = 0
		await _capture("enhancement_blocked" + suffix)
		_check(not _has_button("强化到 +4", true), "Unavailable enhancement disabled" + suffix)
		Game.room = _room_fixture()
		Game.room.player.phase = "Pve"
		Game.room.allowed_actions += ["battle.play_cards", "battle.select_target"]
		Game.room.pve = {"battle_id": "completion-battle", "current_target_id": "fire-bat", "monsters": [{"monster_id": "fire-bat", "maximum_hp": 44, "hp": 31, "shield": 8, "intent_kind": "Attack", "intent_value": 5, "intent_element": "Fire"}]}
		Game.selected_cards = ["hand-0", "hand-1"]
		Game.combat_preview = {"core_element": "Fire", "core_count": 2, "damage_segments": [{"kind": "Fire", "amount": 51}, {"kind": "Direct", "amount": 3}], "heal": 7, "shield_gain": 8, "shield_damage": 8, "hp_damage": 46, "stun_seconds": "1.2", "draw_charge": "0.3", "resonance_multiplier": "1.2", "conflict_pair_count": 1, "conflict_cancellation": "0.2"}
		await _capture("combat_preview" + suffix)
		_check($UI._reference.get_node_or_null("CombatPreview") != null and _all_text().contains("火 51") and _all_text().contains("直伤 3") and _all_text().contains("实际 54（盾8/血46）"), "Final combat preview rendered" + suffix)
		_check($UI._reference.get_node_or_null("CombatPreview").tooltip_text.contains("相生 ×1.20") and $UI._reference.get_node_or_null("CombatPreview").tooltip_text.contains("相克 1组 · 抵消 20%"), "Combat preview formula details rendered" + suffix)
		Game._on_event("combat.hit", {"battle_id": "completion-battle", "source_id": "preview-player", "target_id": "fire-bat", "damage_segments": [{"kind": "Fire", "amount": 51}, {"kind": "Metal", "amount": 6}, {"kind": "Direct", "amount": 3}, {"kind": "Water", "amount": 0}], "heal": 7, "shield_gain": 8})
		await get_tree().create_timer(0.1).timeout
		_check($UI._combat_panels["preview-player"].scale.x > 1.0 and $UI._combat_panels["fire-bat"].scale.x < 1.0, "Attack and hit pulses survive event dispatch" + suffix)
		for entry in [["火 51", $UI.P.ELEMENT.Fire], ["金 6", $UI.P.ELEMENT.Metal], ["直 3", Color.WHITE], ["+7", $UI.P.TEAL], ["+8", Color("c4d2d4")]]:
			var found := false
			for child in $UI.get_children():
				if child is Label and child.text == entry[0] and child.get_theme_color("font_color").is_equal_approx(entry[1]): found = true
			_check(found, "Typed feedback color " + entry[0] + suffix)
		RenderingServer.force_draw(false)
		get_viewport().get_texture().get_image().save_png(output + "/combat_feedback" + suffix + ".png")
		screenshot_count += 1
		$UI._show_battle_details(Game.room.player.battle_status)
		await _capture("battle_status" + suffix, false)
		_check_dialog_bounds("self" + suffix)
		await _close_dialogs()
		Game.room.player.phase = "Pvp"
		Game.room.allowed_actions += ["duel.leave", "duel.escape"]
		Game.room.duel = {"duel_id": "completion-duel", "opponent_id": "other", "opponent_name": "归途很长的盾卫", "opponent_class": "Guardian", "opponent": {"hp": 87, "maximum_hp": 112, "effective_maximum_hp": 112, "shield": 18}, "escape_probability": "0.37", "opponent_status": _status_fixture("ZaiYue"), "leave_window_ends_at_unix_ms": int(Time.get_unix_time_from_system() * 1000) + 20000}
		await _capture("pvp_details" + suffix)
		_check(_all_text().contains("成功率 37%") and _all_text().contains("归途很长的盾卫"), "PVP identity and escape odds rendered" + suffix)
		$UI._show_battle_details(Game.room.duel.opponent_status)
		await _capture("opponent_status" + suffix, false)
		_check_dialog_bounds("opponent" + suffix)
		await _close_dialogs()
		Game.room.erase("duel")
		Game.room.player.phase = "Pve"
		Game.room.player.hand = [{"instance_id": "box-fire", "card_id": "M-BOXSPIRIT", "element_override": "Fire"}, {"instance_id": "box-direct", "card_id": "M-BOXSPIRIT", "element_override": "None"}]
		Game.room.pve = {"battle_id": "box-battle", "current_target_id": "treasure-box-spirit", "monsters": [{"monster_id": "treasure-box-spirit", "maximum_hp": 50, "hp": 50, "shield": 0, "intent_kind": "Attack", "intent_value": 7, "intent_element": "Fire"}]}
		Game.selected_cards = []
		Game.clear_combat_preview()
		await _capture("boxspirit_elements" + suffix)
		var badges: Array = $UI._reference.find_children("MonsterElement", "Label", true, false)
		_check(badges.size() == 2, "Both box spirit instances rendered" + suffix)
		for entry in [["火", "火伤 7", $UI.P.ELEMENT.Fire], ["直伤", "直伤 7", Color.WHITE]]:
			_check(badges.any(func(badge): return badge.text == entry[0] and badge.get_parent().tooltip_text.contains(entry[1]) and badge.get_theme_color("font_color").is_equal_approx(entry[2])), "Box spirit instance " + entry[0] + suffix)
		Game.room.player.hand = [{"instance_id": "speed-card", "card_id": "C18"}]
		Game.selected_cards = ["speed-card"]
		Game.combat_preview = {"draw_speed_seconds": "8", "draw_speed_modifier": "-0.15", "draw_block_speed_seconds": "4", "damage_segments": []}
		await _capture("support_preview" + suffix)
		_check(_all_text().contains("抽牌间隔 -15% / 8秒") and _all_text().contains("充能×2 / 4秒"), "Support preview shows speed effects" + suffix)
	var report := {"ok": layout_errors.is_empty() and checks.values().all(func(value): return value == true), "fixture_only": true, "screenshots": screenshot_count, "checks": checks, "layout_errors": layout_errors, "limitations": "Offline fixtures verify presentation and controls; no live purchases, card upgrades, relic transfers or PVP transaction outcomes are asserted."}
	FileAccess.open(output + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if report.ok else 1)

func _check(condition: bool, label: String) -> void:
	checks[label] = condition

func _all_text() -> String:
	var text := ""
	for node in $UI._reference.find_children("*", "Control", true, false):
		if node is Label or node is Button: text += node.text + "\n"
	return text

func _has_button(text: String, enabled: bool) -> bool:
	for node in $UI._reference.find_children("*", "Button", true, false):
		if node.text == text and (not enabled or not node.disabled): return true
	return false

func _check_dialog_bounds(suffix: String) -> void:
	for child in $UI.get_children():
		if child is AcceptDialog:
			_check(Rect2i(get_viewport().get_visible_rect()).encloses(Rect2i(child.position, child.size)), child.title + " fits window" + suffix)

func _close_dialogs() -> void:
	for child in $UI.get_children():
		if child is AcceptDialog: child.hide()
	await get_tree().process_frame
	for child in $UI.get_children():
		if child is AcceptDialog: child.queue_free()
	await get_tree().process_frame

func _description_scroll() -> ScrollContainer:
	for label in $UI._reference.find_children("*", "Label", true, false):
		if label.text.contains("套装激活后贡献") and label.get_parent() is ScrollContainer: return label.get_parent()
	return null

func _item(index: int) -> Dictionary:
	return {"item_id": "pack-%s" % index, "kind": "Equipment", "quantity": 1, "slot_index": index, "is_safe": index in [33, 34, 35], "equipment": {"slot": ["Head", "Chest", "Hands", "Legs", "Feet"][index % 5], "quality": "Orange" if index == 35 else "Purple", "element": "Earth", "effect_affix": "Bulwark", "secondary_trait": "DrawInterval", "level": 3}}

func _status_fixture(passive: String = "FenXian") -> Dictionary:
	return {"passive_kind": passive, "combo": 3, "core_element": "Fire", "draw_interval_seconds": "2.4", "bonuses": [{"key": "weapon_bonus", "value": "0.1"}, {"key": "passive_shield", "value": "0.18"}, {"key": "shield_flat", "value": "2"}, {"key": "damage_Fire", "value": "0.12"}, {"key": "resistance_Earth", "value": "0.15"}, {"key": "bulwark_reduction", "value": "0.06"}, {"key": "forced_escape", "value": "0.04"}], "sets": [{"kind": "Bulwark", "count": 3, "required": 3, "active": true}, {"kind": "Vitality", "count": 1, "required": 3, "active": false}]}

func _room_fixture() -> Dictionary:
	var inventory: Array = []
	for index in range(36): inventory.append(_item(index))
	return {"room_id": "completion-room", "room_revision": 8, "self": {"row": 3, "column": 2}, "player": {"player_id": "preview-player", "hero_class": "Mage", "phase": "ActionBar", "combat": {"hp": 48, "maximum_hp": 70, "effective_maximum_hp": 78, "shield": 6}, "inventory": inventory, "inventory_capacity": 36, "safe_slot_indexes": [33, 34, 35], "equipped_items": [_item(0), _item(1), _item(2), _item(3), _item(4)], "weapon_level": 2, "draw_charge": "0.55", "hand": [{"instance_id": "hand-0", "card_id": "MAG-01", "level": 3}, {"instance_id": "hand-1", "card_id": "C01", "level": 2}], "battle_status": _status_fixture()}, "current_cell": {"has_evacuation": true, "relic_piles": [{"pile_id": "pile-a", "owner_name": "逐风者", "version": 7}, {"pile_id": "pile-b", "owner_name": "长夜归来的盾卫", "version": 4}]}, "allowed_actions": ["inventory.move", "inventory.equip", "inventory.unequip", "relic.read", "relic.take", "relic.replace", "action.potion", "action.extract"]}
