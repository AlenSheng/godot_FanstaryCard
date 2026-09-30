extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const BoundedBar = preload("res://ui/bounded_bar.gd")
const InventoryView = preload("res://ui/inventory_view.gd")
const MonsterPool = preload("res://ui/monster_pool_view.gd")
const Details = preload("res://ui/equipment_details.gd")
const BattleDetails = preload("res://ui/battle_details.gd")
const DragScroll = preload("res://ui/drag_scroll.gd")
const CellIndex = preload("res://ui/cell_index.gd")
const BattleTargets = preload("res://state/battle_targets.gd")
const TemporaryBagItem = preload("res://ui/temporary_bag_item.gd")
const ItemVisual = preload("res://ui/item_visual.gd")
const PANEL := "UI/CardCodex/card_codex_dialog_panel_normal.png"
const SLOT := Art.COMMON_CELL_KEY
const EMPTY_HAND_SLOT := "UI/Codex/qframe_empty_gray.png"
const ITEM := "UI/Item/exploration_prep_item_icon_"
const MAP_BOSS_MARKER: Texture2D = preload("res://assets/generated/ui/map_boss_marker.png")
const MAP_SELF_MARKER: Texture2D = preload("res://assets/generated/ui/map_self_marker.png")

static func build(ui: Control, host: Control) -> void:
	var state: Dictionary = Game.room
	var phase: String = state.get("player", {}).get("phase", "")
	if phase in ["Pve", "Pvp"]:
		_battle(ui, host, state)
	elif phase in ["Extracted", "Dead"]:
		_settlement_pending(ui, phase)
	elif state.has("reward_choice"):
		_rewards(ui, host, state.reward_choice)
	elif host.get_meta("inventory_open", false) and phase == "ActionBar":
		InventoryView.build(ui, host, state)
	elif host.get_meta("exploration_map_open", false):
		_map(ui, host, state)
	else:
		_actions(ui, host, state)
	var pool: Dictionary = state.get("player", {}).get("monster_pool", {})
	if not pool.is_empty() and phase in ["ActionBar", "Choice"]:
		ui.button(MonsterPool.text("title") + " (%d)" % pool.get("pending", []).size(), Rect2(1210, 35, 340, 62), func(): MonsterPool.open(host))
	var numerics: Dictionary = state.get("player", {}).get("numerical_state", {})
	if numerics.get("guardian_policy", "") == "FractionalRemainder" and Game.hero_class == "Guardian":
		ui.button("%d / 10" % int(numerics.get("guardian_remainder_tenths", 0)), Rect2(1580, 35, 120, 62), func(): preload("res://ui/numerical_details.gd").show_remainder(host))
	var duel: Dictionary = state.get("duel", {})
	if phase == "Pvp" and bool(duel.get("separate_loot", false)):
		ui.button(P.localized("loot"), Rect2(1130, 49, 290, 61), func(): MonsterPool.loot(host, duel.get("searchable_loot", [])))

static func _title(ui: Control, value: String, battle: bool = false) -> void:
	ui.picture(Art.texture("UI/Encounter/encounter_title_plate_normal.png"), Rect2(50, 28, 480, 96))
	_center(ui.text(value, Rect2(74, 37, 426, 73), 44, P.PAPER))

static func _center(label: Label) -> Label:
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	return label

static func _picture(ui: Control, texture: Texture2D, rect: Rect2) -> TextureRect:
	var node := TextureRect.new()
	node.texture = texture
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(node)
	node.position = rect.position
	node.size = rect.size
	return node

static func _battle_target_element(state: Dictionary) -> String:
	var monster := BattleTargets.current(state.get("pve", {}))
	var element := str(monster.get("intent_element", "None"))
	return element if element in ["Fire", "Wood", "Water", "Metal", "Earth"] else ""

static func _nine_patch(ui: Control, texture: Texture2D, rect: Rect2, margins: Vector4) -> NinePatchRect:
	var node := NinePatchRect.new()
	node.texture = texture
	node.set_patch_margin(SIDE_LEFT, int(margins.x))
	node.set_patch_margin(SIDE_TOP, int(margins.y))
	node.set_patch_margin(SIDE_RIGHT, int(margins.z))
	node.set_patch_margin(SIDE_BOTTOM, int(margins.w))
	node.axis_stretch_horizontal = NinePatchRect.AXIS_STRETCH_MODE_STRETCH
	node.axis_stretch_vertical = NinePatchRect.AXIS_STRETCH_MODE_STRETCH
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(node)
	node.position = rect.position
	node.size = rect.size
	return node

static func _bar(ui: Control, rect: Rect2, value: float, maximum: float, fill: String, track: String) -> BoundedBar:
	var bar := BoundedBar.new()
	bar.configure(fill, track)
	bar.position = rect.position
	bar.size = rect.size
	bar.max_value = maxf(1, maximum)
	bar.value = value
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(bar)
	return bar

static func _health(ui: Control, combat: Dictionary, rect: Rect2, enemy: bool = false) -> void:
	var maximum: int = int(combat.get("effective_maximum_hp", combat.get("maximum_hp", 1)))
	_bar(ui, Rect2(rect.position.x, rect.position.y + 40, rect.size.x, 30), float(combat.get("hp", 0)), maximum, "UI/Encounter/encounter_hp_fill_normal.png", "UI/Encounter/encounter_hp_track_normal.png")
	_center(ui.text("%s / %s" % [combat.get("hp", 0), maximum], Rect2(rect.position, Vector2(rect.size.x, 40)), 30))
	if int(combat.get("shield", 0)) > 0:
		ui.picture(Art.texture("UI/Battle/battle_shield_badge.png"), Rect2(rect.position.x, rect.position.y + 76, 36, 40))
		ui.text(P.localized("exploration_shield_amount") % combat.shield, Rect2(rect.position.x + 46, rect.position.y + 76, rect.size.x - 46, 40), 24, Color("c4d2d4"))

static func _status(ui: Control, name: String, rect: Rect2) -> void:
	var label: Label = ui.text("", rect, 23, P.TEAL)
	label.name = name
	label.visible = false

static func _passive(ui: Control, hero_class: String, rect: Rect2) -> void:
	var names := {"Mage": P.localized("exploration_passive_mage_name"), "Priest": P.localized("exploration_passive_priest_name"), "Guardian": P.localized("exploration_passive_guardian_name")}
	if not names.has(hero_class): return
	var descriptions := {"Mage": "同核连放，加快抽牌", "Priest": "生命越低，治疗与控场越强", "Guardian": "生命越高，上盾越厚"}
	var status: Dictionary = Game.room.get("player", {}).get("battle_status", {})
	if not status.is_empty(): descriptions[hero_class] = BattleDetails.passive_text(status)
	var frame: Control = ui.panel(rect)
	frame.name = "PlayerPassive_" + hero_class
	frame.mouse_filter = Control.MOUSE_FILTER_PASS
	frame.tooltip_text = P.localized("exploration_passive_tooltip") % [names[hero_class], BattleDetails.description(status) if not status.is_empty() else P.localized_text(descriptions[hero_class])]
	var icon: TextureRect = _picture(ui, Art.passive(hero_class), Rect2(rect.position + Vector2(12, 9), Vector2(66, rect.size.y - 18)))
	icon.name = "PlayerPassiveIcon_" + hero_class
	ui.text(P.localized("signature_prefix") + names[hero_class], Rect2(rect.position + Vector2(89, 8), Vector2(rect.size.x - 100, 36)), 25, P.GOLD)
	ui.text(descriptions[hero_class], Rect2(rect.position + Vector2(89, 44), Vector2(rect.size.x - 103, rect.size.y - 49)), 20, P.MUTED)

static func _battle(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.get("player", {})
	var pvp: bool = state.has("duel")
	_title(ui, "遭遇战" if pvp else "混沌战斗", true)
	ui.button(P.localized("battle_stats_set"), Rect2(1452, 49, 375, 61), func(): host._show_battle_details(player.get("battle_status", {}))).name = "BattleStats"
	if pvp:
		_duel(ui, host, state)
	else:
		var hero: Control = _picture(ui, Art.portrait(player.get("hero_class", Game.hero_class)), Rect2(80, 120, 515, 488))
		host._combat_panels[player.get("player_id", "")] = hero
		ui.text(P.CLASSES.get(player.get("hero_class", Game.hero_class), P.CLASSES.Mage)[0], Rect2(80, 615, 350, 48), 34, P.GOLD)
		_health(ui, player.get("combat", {}), Rect2(80, 670, 310, 115))
		_status(ui, "PlayerStatus", Rect2(80, 785, 375, 32))
		_passive(ui, player.get("hero_class", ""), Rect2(621, 443, 317, 122))
		var monsters: Array = state.get("pve", {}).get("monsters", [])
		var can_select_target := BattleTargets.living(state.get("pve", {})).size() > 1
		var target_id := str(BattleTargets.current(state.get("pve", {})).get("monster_id", ""))
		var slot_scale := minf(1.0, 2.0 / float(maxi(1, monsters.size())))
		for index in range(monsters.size()):
			var monster: Dictionary = monsters[index]
			var x: float = 1020.0 + index * 415.0 * slot_scale if monsters.size() > 1 else 1200.0
			var alive: bool = int(monster.get("hp", 0)) > 0
			var selected: bool = alive and target_id == monster.get("monster_id", "")
			# Older snapshots have no phase field; HP does not indicate a completed boss transition.
			var boss_phase: int = maxi(1, int(monster.get("boss_phase", 1)))
			var texture: Texture2D = Art.monster(monster.get("monster_id", ""), boss_phase)
			var enemy: Control = _picture(ui, texture, Rect2(x - 45 * slot_scale, 301, 430 * slot_scale, 202 if can_select_target else 245))
			enemy.name = "Monster_" + str(monster.get("monster_id", ""))
			host._combat_panels[monster.get("monster_id", "")] = enemy
			if texture == null:
				ui.panel(Rect2(x + 45 * slot_scale, 306, 250 * slot_scale, 170), SLOT)
				_center(ui.text(host._monster_name(monster.get("monster_id", "")), Rect2(x + 55 * slot_scale, 356, 230 * slot_scale, 65), 36, P.MUTED))
			if not alive: enemy.modulate.a = 0.35
			var element: String = monster.get("intent_element", "None")
			if alive:
				var intent: String = {"Charge": "蓄力", "Empower": "强化", "Shield": "护盾"}.get(monster.get("intent_kind", ""), P.word(element))
				var number: String = str(monster.get("intent_value", 0)) if int(monster.get("intent_value", 0)) > 0 else ""
				if element != "None":
					ui.picture(Art.element(element), Rect2(x + 25 * slot_scale, 121, 62 * slot_scale, 62))
				ui.text("%s %s" % [intent, number], Rect2(x + 95 * slot_scale, 126, 250 * slot_scale, 58), 37, P.ELEMENT.get(element, P.PAPER))
			else:
				_center(ui.text(P.localized("defeated"), Rect2(x + 24 * slot_scale, 126, 315 * slot_scale, 58), 32, P.MUTED))
			_health(ui, monster, Rect2(x + 24 * slot_scale, 190, 315 * slot_scale, 114), true)
			_status(ui, "MonsterStatus_%d" % index, Rect2(x + 24 * slot_scale, 308, 350 * slot_scale, 32))
			var name: String = host._monster_name(monster.get("monster_id", ""))
			if monster.get("monster_id", "") == "annihilation-core": name += P.localized("exploration_boss_phase") % boss_phase
			if can_select_target and alive:
				var button: Button = ui.button(name + (P.localized("exploration_target_suffix") if selected else ""), Rect2(x + 10 * slot_scale, 512, 350 * slot_scale, 50), func(): Game.command("battle.select_target", {"battle_id": state.pve.battle_id, "target_id": monster.monster_id}), not Game.allowed("battle.select_target"))
				button.name = "MonsterTarget_" + str(monster.get("monster_id", ""))
				# Default button padding otherwise grows this row into the preview.
				for style_name in ["normal", "hover", "pressed", "disabled"]:
					var style: StyleBox = button.get_theme_stylebox(style_name).duplicate()
					style.set_content_margin(SIDE_TOP, 6)
					style.set_content_margin(SIDE_BOTTOM, 6)
					button.add_theme_stylebox_override(style_name, style)
				button.size = Vector2(350 * slot_scale, 50)
				if selected: button.add_theme_color_override("font_disabled_color", P.GOLD)
			if alive and int(monster.get("stun_remaining_ms", 0)) <= 0 and int(monster.get("windup_remaining_ms", 0)) > 0:
				_center(ui.text(P.localized("exploration_action_soon") % (float(monster.windup_remaining_ms) / 1000), Rect2(x + 15 * slot_scale, 472 if can_select_target else 502, 340 * slot_scale, 35 if can_select_target else 45), 25, P.GOLD))
	_hand(ui, host, state)

static func _hand(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.get("player", {})
	var hand: Array = player.get("hand", [])
	var target_element := _battle_target_element(state)
	_preview(ui)
	var origin := Vector2(458, 622)
	for index in range(5):
		var rect := Rect2(origin + Vector2(index * 232, 0), Vector2(218, 376))
		if index < hand.size():
			var card: Dictionary = hand[index]
			ui.card(host, card.get("card_id", ""), rect, func(): Game.toggle_card(card.instance_id), card.get("instance_id", "") in Game.selected_cards, not Game.allowed("battle.play_cards"), {"level": int(card.get("level", 0)), "element_override": str(card.get("element_override", "")), "battle_target_element": target_element, "selected_overlay": true})
			var play_index := Game.selected_cards.find(card.get("instance_id", ""))
			if play_index >= 0:
				var order_label: Label = ui.text(str(play_index + 1), Rect2(rect.position.x + 9, rect.position.y + 9, 34, 36), 28, P.GOLD)
				order_label.name = "PlayOrder_%s" % index
		else:
			var empty_slot := _picture(ui, Art.texture(EMPTY_HAND_SLOT), rect)
			empty_slot.name = "EmptyHandSlot_%s" % index
			empty_slot.stretch_mode = TextureRect.STRETCH_SCALE
	var play_label := P.localized("battle_play_button")
	var play_width := 220.0
	var play_font := P.font_for_text(play_label, 30)
	if play_font != null:
		play_width = clampf(play_font.get_string_size(play_label, HORIZONTAL_ALIGNMENT_LEFT, -1, 30).x + 72.0, 220.0, 300.0)
	var play_rect := Rect2(1860.0 - play_width, 845, play_width, 89)
	var play_art := _nine_patch(ui, Art.texture("UI/Battle/battle_play_button_generated.png"), play_rect, Vector4(34, 18, 34, 18))
	play_art.name = "PlayCardsButtonArt"
	var play_button: Button = ui.button(P.localized("battle_play_button"), play_rect, Game.play_cards, Game.selected_cards.is_empty() or not Game.allowed("battle.play_cards"), "")
	play_button.name = "PlayCardsButton"
	for state_name in ["normal", "hover", "pressed", "disabled"]:
		play_button.add_theme_stylebox_override(state_name, StyleBoxEmpty.new())
	play_button.add_theme_font_size_override("font_size", 30)
	play_button.add_theme_color_override("font_color", P.PAPER)
	play_button.add_theme_color_override("font_hover_color", P.PAPER)
	play_button.add_theme_color_override("font_pressed_color", P.PAPER)
	play_button.add_theme_color_override("font_disabled_color", P.MUTED)
	ui.picture(Art.texture("UI/Battle/battle_energy_ring_clean.png"), Rect2(83, 840, 72, 84))
	ui.text(P.localized("draw"), Rect2(170, 838, 230, 43), 26, P.TEAL)
	var charge_bar := _bar(ui, Rect2(171, 885, 225, 32), clampf(float(player.get("draw_charge", "0")), 0, 1), 1, "UI/Battle/battle_energy_cell_lit.png", "UI/Battle/battle_energy_cell_unlit.png")
	charge_bar.name = "DrawChargeBar"
	if host.has_method("_draw_charge_value"):
		charge_bar.value = host._draw_charge_value(float(player.get("draw_charge", "0")))
	ui.text("%d%%" % roundi(charge_bar.value * 100.0), Rect2(402, 880, 72, 38), 24, P.TEAL).name = "DrawChargePercent"
	ui.text(P.localized("exploration_library_discard") % [player.get("library_count", 0), player.get("discard_count", 0)], Rect2(79, 940, 330, 32), 21, P.MUTED)
	var waiting: Dictionary = Game.combat_wait_state()
	if waiting.reason != "available":
		var waiting_label: Label = ui.text(P.localized("battle_wait_" + str(waiting.reason)), Rect2(1390, 1005, 460, 38), 22, P.MUTED)
		waiting_label.name = "CombatWaitReason"
	_center(ui.text(P.localized("battle_play_hint") % Game.selected_cards.size(), Rect2(573, 1005, 765, 36), 23, P.PAPER))

static func _preview(ui: Control) -> void:
	if Game.selected_cards.is_empty(): return
	var preview: Dictionary = Game.combat_preview
	var area := Rect2(460, 528, 1380, 89)
	var panel: Control = ui.panel(area)
	panel.name = "CombatPreview"
	if preview.is_empty():
		ui.text(P.localized("calculating_preview"), Rect2(479, 578, 1000, 33), 22, P.MUTED)
		return
	var x := 478.0
	var core: String = preview.get("core_element", "")
	var headline := P.localized("exploration_preview_core") % [P.word(core), preview.get("core_count", 0)] if not core.is_empty() else P.localized("preview")
	headline = "%s · %s" % [P.localized("battle_preview_confirmed" if preview.get("authoritative", false) else "battle_preview_estimate"), headline]
	var heading: Label = ui.text(headline, Rect2(x, 542, 310, 34), 22, P.GOLD, null, false)
	heading.autowrap_mode = TextServer.AUTOWRAP_OFF
	heading.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	heading.tooltip_text = headline
	x = 478
	var segments: Array = preview.get("damage_segments", [])
	var segment_width := 780.0 / maxi(1, segments.size())
	for segment in segments:
		var segment_text := "%s %s" % [P.localized("battle_preview_direct") if segment.kind == "Direct" else P.word(segment.kind), segment.amount]
		var segment_label: Label = ui.text(segment_text, Rect2(x, 578, segment_width, 34), 22, P.ELEMENT.get(segment.kind, Color.WHITE), null, false)
		segment_label.autowrap_mode = TextServer.AUTOWRAP_OFF
		segment_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		segment_label.tooltip_text = segment_text
		x += segment_width
	var shield_damage := int(preview.get("shield_damage", 0))
	var hp_damage := int(preview.get("hp_damage", 0))
	var actual_damage := shield_damage + hp_damage
	x = 788
	var applied: Label = ui.text(P.localized("exploration_preview_actual" if preview.get("authoritative", false) else "battle_preview_applied_estimate") % [actual_damage, shield_damage, hp_damage], Rect2(x, 542, 350, 34), 22, P.PAPER, null, false)
	applied.autowrap_mode = TextServer.AUTOWRAP_OFF
	applied.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	x += 350
	for entry in [["heal", "battle_preview_heal", P.TEAL], ["shield_gain", "battle_preview_shield", Color("c4d2d4")]]:
		if int(preview.get(entry[0], 0)) > 0:
			ui.text("%s +%s" % [P.localized(entry[1]), preview[entry[0]]], Rect2(x, 542, 130, 34), 22, entry[2], null, false)
			x += 130
	var effects: Array[String] = []
	for entry in [["stun_seconds", "眩晕", "秒"], ["draw_block_seconds", "锁抽", "秒"], ["health_cost", "自损", ""], ["immediate_draw", "抽牌", "张"]]:
		if float(preview.get(entry[0], 0)) > 0: effects.append("%s %s%s" % [entry[1], preview[entry[0]], entry[2]])
	if float(preview.get("draw_charge", "0")) > 0: effects.append(P.localized("exploration_preview_charge") % Details.percent(float(preview.draw_charge)))
	if float(preview.get("draw_speed_seconds", "0")) > 0:
		effects.append(P.localized("exploration_preview_draw_speed") % [Details.percent(float(preview.get("draw_speed_modifier", "0"))), preview.draw_speed_seconds])
	if float(preview.get("draw_block_speed_seconds", "0")) > 0: effects.append(P.localized("exploration_preview_double_charge") % preview.draw_block_speed_seconds)
	var tail: Label = ui.text(" · ".join(effects), Rect2(1270, 578, 554, 34), 22, P.PAPER, null, false)
	tail.autowrap_mode = TextServer.AUTOWRAP_OFF
	tail.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	panel.mouse_filter = Control.MOUSE_FILTER_PASS
	var formula: Array[String] = []
	var resonance := float(preview.get("resonance_multiplier", "1"))
	if resonance > 1.0: formula.append(P.localized("exploration_preview_multiplier") % resonance)
	var conflict_pairs := int(preview.get("conflict_pair_count", 0))
	var cancellation := float(preview.get("conflict_cancellation", "0"))
	if conflict_pairs > 0: formula.append(P.localized("exploration_preview_conflict") % [conflict_pairs, Details.percent(cancellation)])
	panel.tooltip_text = P.localized("exploration_preview_tooltip") % [actual_damage, shield_damage, hp_damage, " · ".join(formula), " · ".join(effects)]
	if preview.get("control_estimated", false): panel.tooltip_text += "\n" + P.localized("battle_preview_control_estimate")
	if int(preview.get("heal_overflow", 0)) + int(preview.get("shield_overflow", 0)) > 0:
		panel.tooltip_text += "\n" + P.localized("battle_preview_overflow") % [int(preview.get("heal_overflow", 0)), int(preview.get("shield_overflow", 0))]

static func _duel(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.player
	var duel: Dictionary = state.duel
	var hero: Control = _picture(ui, Art.portrait(player.get("hero_class", Game.hero_class)), Rect2(80, 139, 285, 420))
	host._combat_panels[player.get("player_id", "")] = hero
	ui.text(P.CLASSES.get(player.get("hero_class", Game.hero_class), P.CLASSES.Mage)[0], Rect2(372, 161, 422, 53), 38, P.GOLD)
	_health(ui, player.get("combat", {}), Rect2(370, 229, 409, 120))
	_status(ui, "PlayerStatus", Rect2(370, 350, 410, 32))
	ui.picture(Art.texture("UI/Encounter/encounter_vs_emblem_normal.png"), Rect2(855, 153, 216, 193))
	var opponent_class: String = duel.get("opponent_class", "")
	var opponent: Control = _picture(ui, Art.portrait(opponent_class) if P.CLASSES.has(opponent_class) else Art.texture("UI/Encounter/encounter_enemy_frame_normal.png"), Rect2(1516, 142, 268, 308))
	host._combat_panels[duel.get("opponent_id", "")] = opponent
	ui.text(duel.get("opponent_name", "同格旅人") + " · " + P.word(opponent_class), Rect2(1129, 161, 380, 53), 31, P.GOLD)
	ui.button(P.localized("opponent_stats"), Rect2(1534, 462, 252, 55), func(): host._show_battle_details(duel.get("opponent_status", {})))
	_health(ui, duel.get("opponent", {}), Rect2(1128, 229, 358, 120), true)
	_status(ui, "OpponentStatus", Rect2(1128, 350, 390, 32))
	var seconds: float = maxf(0, (float(duel.get("leave_window_ends_at_unix_ms", 0)) - Time.get_unix_time_from_system() * 1000) / 1000)
	ui.button(P.localized("exploration_leave_requested") if duel.get("self_requested_leave", false) else P.localized("leave_duel"), Rect2(400, 398, 350, 66), func(): Game.command("duel.leave", {"duel_id": duel.duel_id}), not Game.allowed("duel.leave"))
	if seconds > 0: _center(ui.text(P.localized("exploration_leave_window") % seconds, Rect2(400, 480, 350, 44), 26, P.GOLD))
	ui.button("强制逃脱", Rect2(803, 395, 310, 70), func(): Game.command("duel.escape", {"duel_id": duel.duel_id}), not Game.allowed("duel.escape"))
	if not str(duel.get("escape_probability", "")).is_empty():
		ui.text(P.localized("exploration_escape_chance") % Details.percent(float(duel.escape_probability)), Rect2(812, 353, 308, 37), 23, P.MUTED)
	if duel.has("escape_remaining_ms"):
		_center(ui.text(P.localized("exploration_escaping") % (float(duel.escape_remaining_ms) / 1000), Rect2(803, 480, 310, 44), 27, P.TEAL))
	if not Game.allowed("battle.play_cards"):
		ui.picture(Art.texture("UI/Encounter/encounter_lock_icon_normal.png"), Rect2(1290, 443, 47, 48))
	ui.text(P.localized("waiting_action"), Rect2(1350, 443, 330, 48), 26, P.GOLD)
	ui.text(P.localized("own_hand"), Rect2(80, 622, 330, 54), 34, P.GOLD)
	_passive(ui, player.get("hero_class", ""), Rect2(80, 703, 330, 117))
	_hand(ui, host, state)

static func _map(ui: Control, host: Control, state: Dictionary) -> void:
	_title(ui, "混沌领域")
	var origin := Vector2(424, 144)
	var stride := Vector2(145, 126)
	var colors: Array = [Color("79909c"), Color("a3a575"), Color("c6aa81")]
	var cells := CellIndex.by_position(state.get("map", []))
	var moves := CellIndex.by_position(state.get("legal_moves", []))
	for row in range(6):
		for column in range(6):
			var layer: int = mini(mini(row, column), mini(5 - row, 5 - column))
			var pos := Vector2i(row, column)
			var current: bool = int(state.get("self", {}).get("row", -1)) == row and int(state.get("self", {}).get("column", -1)) == column
			var legal: bool = moves.has(pos)
			var rect := Rect2(origin + Vector2(column * stride.x, row * stride.y), Vector2(137, 118))
			var cell: Dictionary = cells.get(pos, {})
			var markers: Array[Dictionary] = []
			if cell.get("is_boss", false): markers.append({"label": P.localized("boss"), "texture": MAP_BOSS_MARKER, "tint": Color("fa8c72")})
			elif cell.get("has_spring", false): markers.append({"label": P.localized("spring"), "texture": Art.texture("UI/Action/spring_clean.png"), "tint": P.TEAL})
			if current: markers.append({"label": P.localized("self"), "texture": MAP_SELF_MARKER, "tint": P.GOLD})
			var tile := ColorRect.new()
			tile.color = (Color("ad873c") if legal else colors[layer]).darkened(0.65)
			tile.position = rect.position
			tile.size = rect.size
			tile.mouse_filter = Control.MOUSE_FILTER_IGNORE
			ui.add_child(tile)
			var button: Button = ui.button("", rect, func(): host._move(row, column), not legal or not Game.allowed("room.move"), SLOT)
			button.add_theme_font_size_override("font_size", 30)
			var tint: Color = colors[layer]
			button.add_theme_stylebox_override("normal", Art.style(SLOT, Color("e7bb66") if legal else tint))
			button.add_theme_stylebox_override("disabled", Art.style(SLOT, Color("f2d392") if current else tint))
			var layer_names := [P.localized("exploration_outer"), P.localized("exploration_middle"), P.localized("exploration_inner")]
			var tooltip := P.localized("exploration_map_layer") % layer_names[layer]
			if legal: tooltip += " · " + P.localized("exploration_map_reachable")
			if not markers.is_empty():
				var marker_names: Array[String] = []
				for marker in markers: marker_names.append(str(marker.label))
				tooltip += " · " + ", ".join(marker_names)
			button.tooltip_text = tooltip
			if markers.size() == 1:
				var marker: Dictionary = markers[0]
				_picture(ui, marker.texture, Rect2(rect.position + Vector2(39, 5), Vector2(59, 59)))
				_center(ui.text(marker.label, Rect2(rect.position + Vector2(6, 65), Vector2(125, 39)), 27, marker.tint))
			elif not markers.is_empty():
				var icon_size := 46.0 if markers.size() == 2 else 36.0
				var gap := 8.0 if markers.size() == 2 else 2.0
				var total_width := markers.size() * icon_size + (markers.size() - 1) * gap
				var start_x := (rect.size.x - total_width) * 0.5
				for marker_index in range(markers.size()):
					var marker: Dictionary = markers[marker_index]
					var marker_x := start_x + marker_index * (icon_size + gap)
					_picture(ui, marker.texture, Rect2(rect.position + Vector2(marker_x, 5), Vector2(icon_size, 48)))
					_center(ui.text(marker.label, Rect2(rect.position + Vector2(marker_x - 8, 70), Vector2(icon_size + 16, 31)), 18 if markers.size() == 2 else 14, marker.tint))
	ui.panel(Rect2(1372, 241, 430, 548))
	_center(ui.text(P.localized("exploration_map_legend"), Rect2(1420, 274, 333, 65), 40, P.GOLD))
	for index in range(3):
		var tint: Color = [Color("fa8c72"), P.TEAL, P.GOLD][index]
		_picture(ui, [MAP_BOSS_MARKER, Art.texture("UI/Action/spring_clean.png"), MAP_SELF_MARKER][index], Rect2(1423, 377 + index * 114, 88, 83))
		ui.text(["首领", "源泉", "自己"][index], Rect2(1535, 394 + index * 114, 220, 55), 34, tint)
	ui.text("高亮邻格可前往", Rect2(1431, 725, 330, 38), 24, P.GOLD)
	var map_player_count := int(state.get("map_player_count", 0))
	var population_text := P.localized("map_player_count_unavailable")
	if map_player_count > 0: population_text = P.localized("map_player_count") % [map_player_count]
	# Keep both descriptions at the same size and give wrapped lines their own space.
	ui.text(P.localized("map_encounter_hint"), Rect2(80, 265, 320, 120), 24, P.MUTED, null, false)
	ui.text(population_text, Rect2(80, 400, 320, 44), 24, P.GOLD, null, false)
	ui.text(P.localized("map_hint"), Rect2(80, 460, 320, 230), 24, P.MUTED, null, false)
	ui.button("返回", Rect2(80, 985, 262, 56), func(): host.set_meta("exploration_map_open", false); host._schedule_render())

static func _actions(ui: Control, host: Control, state: Dictionary) -> void:
	_title(ui, "当前格行动")
	var player: Dictionary = state.get("player", {})
	var hero: Control = _picture(ui, Art.portrait(player.get("hero_class", Game.hero_class)), Rect2(105, 135, 380, 405))
	host._combat_panels[player.get("player_id", "")] = hero
	ui.panel(Rect2(553, 165, 540, 252))
	ui.text(P.CLASSES.get(player.get("hero_class", Game.hero_class), P.CLASSES.Mage)[0], Rect2(594, 191, 450, 58), 37, P.GOLD)
	_health(ui, player.get("combat", {}), Rect2(596, 261, 449, 126))
	var inventory: Array = player.get("inventory", [])
	ui.panel(Rect2(1228, 158, 574, 363))
	ui.text(P.localized("temporary_bag"), Rect2(1268, 182, 480, 54), 34, P.GOLD)
	ui.text(P.localized("temporary_bag_slots_used") % [inventory.size(), player.get("inventory_capacity", 0)], Rect2(1268, 240, 466, 40), 25, P.PAPER)
	ui.button(P.localized("open_bag"), Rect2(1556, 180, 206, 52), func(): InventoryView.open(host), not Game.allowed("inventory.move")).name = "OpenInventory"
	# The compact view always shows two rows of three items. Keep the server's
	# inventory order (the acquisition order) instead of laying items out by
	# slot_index; the full bag is the only place where slot exchange is allowed.
	var bag_scroll := DragScroll.new()
	bag_scroll.name = "TemporaryBackpackScroll"
	bag_scroll.position = Vector2(1268, 291)
	bag_scroll.size = Vector2(500, 182)
	bag_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	bag_scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	bag_scroll.interaction_enabled = inventory.size() > 6
	ui.add_child(bag_scroll)
	# The compact backpack must not expose a second scrollbar affordance. Drag
	# inside the item area is the only scrolling control.
	var scrollbar := bag_scroll.get_v_scroll_bar()
	scrollbar.custom_minimum_size = Vector2.ZERO
	scrollbar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	scrollbar.modulate.a = 0.0
	var item_grid := GridContainer.new()
	item_grid.name = "TemporaryBackpackGrid"
	item_grid.columns = 3
	item_grid.add_theme_constant_override("h_separation", 25)
	item_grid.add_theme_constant_override("v_separation", 16)
	item_grid.custom_minimum_size = Vector2(461, 0)
	bag_scroll.add_child(item_grid)
	for index in range(inventory.size()):
		var item: Dictionary = inventory[index]
		var item_view := TemporaryBagItem.new()
		item_view.name = "TemporaryBagItem_%s" % str(item.get("item_id", index))
		item_view.configure(item)
		item_grid.add_child(item_view)
	var actions: Array = []
	for action in ["action.spring", "action.potion", "action.extract"]:
		if Game.allowed(action): actions.append(action)
	var piles: Array = state.get("current_cell", {}).get("relic_piles", [])
	actions.append("map")
	ui.panel(Rect2(80, 539, 1758, 425)).name = "ActionPanel"
	_center(ui.text(P.localized("choose_next_action"), Rect2(610, 558, 680, 62), 40, P.GOLD)).name = "ActionTitle"
	var scroll: ScrollContainer = ui._scroll(Rect2(107, 632, 1702, 300), true)
	var strip := HBoxContainer.new()
	strip.add_theme_constant_override("separation", 22)
	scroll.add_child(strip)
	for pile in piles: actions.append("relic:" + str(pile.pile_id))
	for index in range(actions.size()):
		var action: String = actions[index]
		var tile: Control = ui.get_script().new()
		tile.custom_minimum_size = Vector2(264, 278)
		strip.add_child(tile)
		var rect := Rect2(0, 0, 264, 278)
		var relic: bool = action.begins_with("relic:")
		var title: String = {"action.spring": P.localized("exploration_spring_action"), "action.potion": P.localized("use_health_potion"), "action.extract": P.localized("extract"), "map": P.localized("move_neighbor")}.get(action, "")
		var callback: Callable = func(): Game.command(action)
		if action == "map": callback = func(): host.set_meta("exploration_map_open", true); host._schedule_render()
		if relic:
			var pile_id := action.trim_prefix("relic:")
			for pile in piles:
				if pile.pile_id == pile_id: title = P.localized("exploration_relic_owner") % str(pile.get("owner_name", P.localized("same_cell_traveler"))); break
			callback = func(): InventoryView.open(host, pile_id)
		var action_name: String = "relic" if relic else action.trim_prefix("action.")
		var action_button: Button = tile.button("", rect, callback, relic and not Game.allowed("relic.read"), SLOT)
		action_button.name = "Action_" + action_name
		var key: String = {"action.spring": "UI/Action/spring_clean.png", "action.potion": ITEM + "potion.png", "action.extract": "UI/Action/extract_gate_clean.png"}.get(action, "UI/Action/relic_pile_clean.png" if relic else "")
		if key.is_empty():
			_center(tile.text("→", Rect2(rect.position + Vector2(55, 27), Vector2(154, 149)), 96, P.TEAL))
		else:
			var icon: TextureRect = _picture(tile, Art.texture(key), Rect2(rect.position + Vector2(42, 20), Vector2(180, 160)))
			icon.name = "ActionIcon_" + action_name
		_center(tile.text(title, Rect2(rect.position + Vector2(12, 183), Vector2(240, 75)), 26, P.PAPER))
	for key in ["extraction_remaining_ms", "spring_remaining_ms"]:
		if state.has(key):
			_center(ui.text(P.localized("exploration_extraction_progress" if key.begins_with("extraction") else "exploration_spring_progress") % (float(state[key]) / 1000), Rect2(615, 453, 560, 67), 36, P.TEAL))
	ui.button("查看地图", Rect2(80, 985, 244, 56), func(): host.set_meta("exploration_map_open", true); host._schedule_render())

static func _rewards(ui: Control, host: Control, reward: Dictionary) -> void:
	ui.panel(Rect2(218, 141, 1484, 818))
	_title(ui, "战利品三选一")
	var options: Array = reward.get("options", [])
	for index in range(3):
		var rect := Rect2(285 + index * 458, 226, 424, 588)
		ui.panel(rect)
		if index >= options.size():
			_center(ui.text("等待战利品", Rect2(rect.position + Vector2(24, 220), Vector2(376, 70)), 32, P.MUTED))
			continue
		var option: Dictionary = options[index]
		var kind: int = int(option.get("kind", 0))
		var title: String = {1: P.localized("exploration_equipment_reward"), 2: P.localized("exploration_fragment_reward"), 3: P.localized("exploration_heal_reward")}.get(kind, P.localized("loot"))
		_center(ui.text(title, Rect2(rect.position + Vector2(24, 28), Vector2(376, 62)), 42, P.PAPER))
		var item := {"kind": "Equipment", "equipment": option.get("equipment", {})}
		if kind == 3: _center(ui.text("+", Rect2(rect.position + Vector2(112, 103), Vector2(200, 165)), 120, P.TEAL))
		else:
			var reward_item: Dictionary = item if kind == 1 else {"kind": "EquipmentFragments", "item_id": "equipment_fragments", "quantity": option.get("quantity", 1)}
			var visual := ItemVisual.item(ui, reward_item, Vector2(165, 165), false)
			visual.position = rect.position + Vector2(129, 103)
			visual.size = Vector2(165, 165)
		var description: String = P.localized("exploration_reward_quantity") % option.get("quantity", 0)
		if kind == 1: description = Details.description(item)
		elif kind == 3:
			var combat: Dictionary = Game.room.get("player", {}).get("combat", {})
			var maximum: int = int(combat.get("maximum_hp", 0))
			var amount: int = mini(maxi(0, int(combat.get("effective_maximum_hp", maximum)) - int(combat.get("hp", 0))), int(maximum * int(option.get("heal_percent", 0)) / 100.0))
			description = P.localized("exploration_reward_heal") % [option.get("heal_percent", 0), amount]
		ui.text(description, Rect2(rect.position + Vector2(25, 281), Vector2(374, 168)), 23, P.TEAL)
		ui.button(P.localized("added_to_bag") if kind != 3 else P.localized("exploration_heal_now"), Rect2(rect.position + Vector2(25, 459), Vector2(374, 61)), func(): host._claim(option), not Game.allowed("reward.choice.claim"))
		if kind == 1:
			ui.button(P.localized("exploration_compare_equip_direct"), Rect2(rect.position + Vector2(25, 525), Vector2(374, 58)), func(): host._show_equipment_details(item, func(): host._claim(option, true), P.localized("exploration_equip_recycle")), not Game.allowed("reward.choice.claim"))
	var count: int = clampi(int(reward.get("refresh_count", 0)), 0, 3)
	ui.text(P.localized("exploration_refresh_count") % count, Rect2(311, 840, 370, 66), 31, P.GOLD)
	ui.button(P.localized("exploration_refresh_cost") % [60, 180, 450][mini(count, 2)] if count < 3 else P.localized("refresh_exhausted"), Rect2(746, 830, 425, 91), func(): Game.command("reward.choice.refresh"), count >= 3 or not Game.allowed("reward.choice.refresh"))
	ui.text(P.localized("exploration_current_layer") % [P.localized("exploration_outer"), P.localized("exploration_middle"), P.localized("exploration_inner")][clampi(int(reward.get("layer", 0)), 0, 2)], Rect2(1275, 845, 334, 64), 29, P.MUTED)

static func _settlement_pending(ui: Control, phase: String) -> void:
	ui.picture(Art.texture(PANEL), Rect2(480, 150, 960, 766))
	_center(ui.text(P.localized("settlement_pending_extract" if phase == "Extracted" else "settlement_pending_battle"), Rect2(545, 285, 830, 100), 64, P.GOLD))
	_center(ui.text(P.localized("settlement_query_failed" if Game.settlement_query_failed else "settlement_pending_message"), Rect2(598, 455, 724, 70), 34, P.PAPER))
	ui.button(P.localized("settlement_retry"), Rect2(716, 650, 488, 96), Game.retry_settlement)

static func build_settlement(ui: Control, host: Control) -> void:
	ui.picture(Art.texture(PANEL), Rect2(480, 150, 960, 766))
	var result: String = str(Game.settlement.get("result", ""))
	var result_title: String = P.localized("word_extracted") if result == "Extracted" else P.localized("word_pvp_death") if result == "PvpDeath" else P.localized("word_dead") if result in ["Dead", "Death", "Defeated", "PveDeath"] else P.localized("journey_end")
	_center(ui.text(result_title, Rect2(545, 253, 830, 100), 64, P.GOLD))
	_center(ui.text(P.localized("run_reward"), Rect2(598, 380, 724, 65), 36, P.PAPER))
	var items: Array = _settlement_items()
	if items.is_empty():
		_center(ui.text(P.localized("settlement_no_items"), Rect2(598, 521, 724, 62), 28, P.MUTED))
	else:
		var scroll: ScrollContainer = ui._scroll(Rect2(595, 460, 730, 274))
		scroll.name = "SettlementItemsScroll"
		var list := Control.new()
		list.custom_minimum_size = Vector2(690, items.size() * 82)
		scroll.add_child(list)
		for index in range(items.size()):
			var entry: Dictionary = items[index]
			var item: Dictionary = entry.get("item", {})
			var row := Control.new()
			row.name = "SettlementItem_%s" % index
			row.position = Vector2(0, index * 82)
			row.size = Vector2(690, 82)
			list.add_child(row)
			var backing := Panel.new()
			backing.position = Vector2(78, 5)
			backing.size = Vector2(612, 72)
			backing.mouse_filter = Control.MOUSE_FILTER_IGNORE
			var backing_style := StyleBoxFlat.new()
			backing_style.bg_color = Color("07171c")
			backing_style.border_color = Color("76664d")
			backing_style.set_border_width_all(1)
			backing.add_theme_stylebox_override("panel", backing_style)
			row.add_child(backing)
			var visual := ItemVisual.item(row, item, Vector2(68, 68), false)
			visual.position = Vector2(0, 7)
			visual.size = Vector2(68, 68)
			var title := Details.title(item)
			if entry.get("equipped", false): title += " · " + P.localized("settlement_equipped")
			ui.text(title, Rect2(96, 16, 472, 50), 25, P.PAPER, row)
			ui.text("×%s" % item.get("quantity", 1), Rect2(580, 16, 94, 50), 25, P.GOLD, row).horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	ui.button("返回", Rect2(716, 753, 488, 96), host._return_from_settlement, Game.busy)

static func _settlement_items() -> Array:
	var details: Dictionary = Game.settlement.details if Game.settlement.get("details") is Dictionary else {}
	var result: Array = []
	if details.get("items") is Array:
		for entry in details.items:
			if entry is Dictionary and entry.get("item") is Dictionary:
				result.append(entry)
		return result
	if Game.settlement.get("matchId", "") != Game.room.get("match_id", ""): return result
	var player: Dictionary = Game.room.get("player", {})
	var extracted: bool = Game.settlement.get("result", "") == "Extracted"
	for item in player.get("inventory", []):
		if item is Dictionary and (extracted or item.get("is_safe", false)):
			result.append({"item": item, "equipped": false})
	if extracted:
		for item in player.get("equipped_items", []):
			if item is Dictionary: result.append({"item": item, "equipped": true})
	return result

static func show_midlayer(ui: Control, host: Control, row: int, column: int) -> void:
	var overlay := Control.new()
	overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	ui.add_child(overlay)
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.72)
	shade.size = Vector2(1920, 1080)
	overlay.add_child(shade)
	var frame := Panel.new()
	frame.add_theme_stylebox_override("panel", Art.style(PANEL))
	frame.position = Vector2(534, 230)
	frame.size = Vector2(852, 720)
	overlay.add_child(frame)
	for entry in [["进入中层", 54, 285], ["进入后不能退回外层", 30, 433], ["随机撤离点不会显示在小地图", 30, 526], ["源泉常亮，可规划绕路回血", 30, 619]]:
		var label := Label.new()
		var display_text := P.localized_text(entry[0])
		label.text = display_text
		label.add_theme_font_override("font", P.font_for_text(display_text, entry[1]))
		label.position = Vector2(583, entry[2])
		label.size = Vector2(754, 76)
		var typeface := P.font_for_text(display_text, entry[1])
		label.add_theme_font_override("font", typeface)
		label.add_theme_font_size_override("font_size", P.fit_font_size(typeface, entry[1], label.size.y, label.size.x - 12.0, display_text))
		label.add_theme_color_override("font_color", P.GOLD if entry[1] == 54 else P.PAPER)
		_center(label)
		overlay.add_child(label)
		P.fit_control_font(label, typeface, entry[1], 12.0)
	var confirm := Button.new()
	confirm.text = P.localized_text("确认进入")
	confirm.position = Vector2(735, 758)
	confirm.size = Vector2(450, 87)
	confirm.add_theme_font_size_override("font_size", 35)
	confirm.clip_text = true
	confirm.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	Art.button(confirm, "UI/CardCodex/card_codex_action_button_blue.png")
	confirm.pressed.connect(func():
		host.remove_meta("pending_move")
		host._midlayer_seen[Game.room.get("room_id", "")] = true
		overlay.queue_free()
		Game.command("room.move", {"row": row, "column": column}))
	overlay.add_child(confirm)
	P.fit_control_font(confirm, P.font_for_text(confirm.text, 35), 35, 48.0)
	var cancel := Button.new()
	cancel.text = P.localized_text("暂不进入")
	cancel.position = Vector2(750, 861)
	cancel.size = Vector2(420, 60)
	Art.button(cancel, "UI/CardCodex/card_codex_action_button_blue.png")
	cancel.clip_text = true
	cancel.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	cancel.pressed.connect(func(): host.remove_meta("pending_move"); overlay.queue_free())
	overlay.add_child(cancel)
	P.fit_control_font(cancel, P.font_for_text(cancel.text, 24), 24, 48.0)
