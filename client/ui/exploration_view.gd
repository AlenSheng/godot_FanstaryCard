extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const BoundedBar = preload("res://ui/bounded_bar.gd")
const InventoryView = preload("res://ui/inventory_view.gd")
const Details = preload("res://ui/equipment_details.gd")
const BattleDetails = preload("res://ui/battle_details.gd")
const DragScroll = preload("res://ui/drag_scroll.gd")
const CellIndex = preload("res://ui/cell_index.gd")
const TemporaryBagItem = preload("res://ui/temporary_bag_item.gd")
const PANEL := "UI/CardCodex/card_codex_dialog_panel_normal.png"
const SLOT := Art.COMMON_CELL_KEY
const EMPTY_HAND_SLOT := "UI/Codex/qframe_empty_gray.png"
const ITEM := "UI/Item/exploration_prep_item_icon_"

static func build(ui: Control, host: Control) -> void:
	var state: Dictionary = Game.room
	var phase: String = state.get("player", {}).get("phase", "")
	if phase in ["Pve", "Pvp"]:
		_battle(ui, host, state)
	elif state.has("reward_choice"):
		_rewards(ui, host, state.reward_choice)
	elif host.get_meta("inventory_open", false) and phase == "ActionBar":
		InventoryView.build(ui, host, state)
	elif host.get_meta("exploration_map_open", false):
		_map(ui, host, state)
	else:
		_actions(ui, host, state)
	ui.text(Game.connection, Rect2(1450, 995, 236, 40), 20, P.MUTED)

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
	var pve: Dictionary = state.get("pve", {})
	var target_id := str(pve.get("current_target_id", ""))
	var fallback := ""
	for entry in pve.get("monsters", []):
		if not entry is Dictionary: continue
		var monster: Dictionary = entry
		if int(monster.get("hp", 0)) <= 0: continue
		var element := str(monster.get("intent_element", "None"))
		if element not in ["Fire", "Wood", "Water", "Metal", "Earth"]: continue
		if fallback.is_empty(): fallback = element
		if str(monster.get("monster_id", "")) == target_id: return element
	return fallback

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
		ui.text("护盾 %s" % combat.shield, Rect2(rect.position.x + 46, rect.position.y + 76, rect.size.x - 46, 40), 24, Color("c4d2d4"))

static func _passive(ui: Control, hero_class: String, rect: Rect2) -> void:
	var names := {"Mage": "焚弦", "Priest": "临渊", "Guardian": "载岳"}
	if not names.has(hero_class): return
	var descriptions := {"Mage": "同核连放，加快抽牌", "Priest": "生命越低，治疗与控场越强", "Guardian": "生命越高，上盾越厚"}
	var status: Dictionary = Game.room.get("player", {}).get("battle_status", {})
	if not status.is_empty(): descriptions[hero_class] = BattleDetails.passive_text(status)
	var frame: Control = ui.panel(rect)
	frame.name = "PlayerPassive_" + hero_class
	frame.mouse_filter = Control.MOUSE_FILTER_PASS
	frame.tooltip_text = "本命 · %s\n%s" % [names[hero_class], BattleDetails.description(status) if not status.is_empty() else descriptions[hero_class]]
	var icon: TextureRect = _picture(ui, Art.passive(hero_class), Rect2(rect.position + Vector2(12, 9), Vector2(66, rect.size.y - 18)))
	icon.name = "PlayerPassiveIcon_" + hero_class
	ui.text("本命 · " + names[hero_class], Rect2(rect.position + Vector2(89, 8), Vector2(rect.size.x - 100, 36)), 25, P.GOLD)
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
		_passive(ui, player.get("hero_class", ""), Rect2(621, 443, 317, 122))
		var monsters: Array = state.get("pve", {}).get("monsters", [])
		var alive_monster_count := 0
		for candidate in monsters:
			if int(candidate.get("hp", 0)) > 0:
				alive_monster_count += 1
		var can_select_target := alive_monster_count > 1
		for index in range(mini(monsters.size(), 2)):
			var monster: Dictionary = monsters[index]
			var x: float = 1020.0 + index * 415.0 if monsters.size() > 1 else 1200.0
			var alive: bool = int(monster.get("hp", 0)) > 0
			var selected: bool = alive and state.pve.get("current_target_id", "") == monster.get("monster_id", "")
			# Older snapshots have no phase field; HP does not indicate a completed boss transition.
			var boss_phase: int = maxi(1, int(monster.get("boss_phase", 1)))
			var texture: Texture2D = Art.monster(monster.get("monster_id", ""), boss_phase)
			var enemy: Control = _picture(ui, texture, Rect2(x - 45, 301, 430, 245))
			enemy.name = "Monster_" + str(monster.get("monster_id", ""))
			host._combat_panels[monster.get("monster_id", "")] = enemy
			if texture == null:
				ui.panel(Rect2(x + 45, 306, 250, 170), SLOT)
				_center(ui.text(host._monster_name(monster.get("monster_id", "")), Rect2(x + 55, 356, 230, 65), 36, P.MUTED))
			if not alive: enemy.modulate.a = 0.35
			var element: String = monster.get("intent_element", "None")
			if alive:
				var intent: String = {"Charge": "蓄力", "Empower": "强化", "Shield": "护盾"}.get(monster.get("intent_kind", ""), P.word(element))
				var number: String = str(monster.get("intent_value", 0)) if int(monster.get("intent_value", 0)) > 0 else ""
				if element != "None":
					ui.picture(Art.element(element), Rect2(x + 25, 121, 62, 62))
				ui.text("%s %s" % [intent, number], Rect2(x + 95, 126, 250, 58), 37, P.ELEMENT.get(element, P.PAPER))
			else:
				_center(ui.text(P.localized("defeated"), Rect2(x + 24, 126, 315, 58), 32, P.MUTED))
			_health(ui, monster, Rect2(x + 24, 190, 315, 114), true)
			var name: String = host._monster_name(monster.get("monster_id", ""))
			if monster.get("monster_id", "") == "annihilation-core": name += " · %s阶段" % ("二" if boss_phase == 2 else "一")
			if can_select_target:
				var button: Button = ui.button(name + (" · 目标" if selected else ""), Rect2(x + 10, 550, 350, 58), func(): Game.command("battle.select_target", {"battle_id": state.pve.battle_id, "target_id": monster.monster_id}), not Game.allowed("battle.select_target") or not alive)
				button.name = "MonsterTarget_" + str(monster.get("monster_id", ""))
				if selected: button.add_theme_color_override("font_disabled_color", P.GOLD)
			if alive and int(monster.get("stun_remaining_ms", 0)) > 0:
				_center(ui.text("眩晕 %.1f 秒" % (float(monster.stun_remaining_ms) / 1000), Rect2(x + 15, 502, 340, 45), 25, P.TEAL))
			elif alive and int(monster.get("windup_remaining_ms", 0)) > 0:
				_center(ui.text("即将行动 %.1f 秒" % (float(monster.windup_remaining_ms) / 1000), Rect2(x + 15, 502, 340, 45), 25, P.GOLD))
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
	ui.text("牌库 %s · 弃牌 %s" % [player.get("library_count", 0), player.get("discard_count", 0)], Rect2(79, 940, 330, 32), 21, P.MUTED)
	_center(ui.text(P.localized("battle_play_hint") % Game.selected_cards.size(), Rect2(573, 1005, 765, 36), 23, P.PAPER))

static func _preview(ui: Control) -> void:
	if Game.selected_cards.is_empty(): return
	var preview: Dictionary = Game.combat_preview
	var area := Rect2(460, 572, 1380, 47)
	var panel: Control = ui.panel(area)
	panel.name = "CombatPreview"
	if preview.is_empty():
		ui.text(P.localized("calculating_preview"), Rect2(479, 578, 1000, 33), 22, P.MUTED)
		return
	var x := 478.0
	var core: String = preview.get("core_element", "")
	var headline := "预览" + (" · %s核×%s" % [P.word(core), preview.get("core_count", 0)] if not core.is_empty() else "")
	ui.text(headline, Rect2(x, 578, 245, 34), 22, P.GOLD)
	x += 244
	for segment in preview.get("damage_segments", []):
		ui.text("%s %s" % ["直伤" if segment.kind == "Direct" else P.word(segment.kind), segment.amount], Rect2(x, 578, 140, 34), 25, P.ELEMENT.get(segment.kind, Color.WHITE))
		x += 140
	var shield_damage := int(preview.get("shield_damage", 0))
	var hp_damage := int(preview.get("hp_damage", 0))
	var actual_damage := shield_damage + hp_damage
	ui.text("实际 %s（盾%s/血%s）" % [actual_damage, shield_damage, hp_damage], Rect2(x, 578, 235, 34), 21, P.PAPER)
	x += 235
	for entry in [["heal", "回复", P.TEAL], ["shield_gain", "盾", Color("c4d2d4")]]:
		if int(preview.get(entry[0], 0)) > 0:
			ui.text("%s +%s" % [entry[1], preview[entry[0]]], Rect2(x, 578, 149, 34), 24, entry[2])
			x += 150
	var effects: Array[String] = []
	for entry in [["stun_seconds", "眩晕", "秒"], ["draw_block_seconds", "锁抽", "秒"], ["health_cost", "自损", ""], ["immediate_draw", "抽牌", "张"]]:
		if float(preview.get(entry[0], 0)) > 0: effects.append("%s %s%s" % [entry[1], preview[entry[0]], entry[2]])
	if float(preview.get("draw_charge", "0")) > 0: effects.append("充能 +%s%%" % Details.percent(float(preview.draw_charge)))
	if float(preview.get("draw_speed_seconds", "0")) > 0:
		effects.append("抽牌间隔 %s%% / %s秒" % [Details.percent(float(preview.get("draw_speed_modifier", "0"))), preview.draw_speed_seconds])
	if float(preview.get("draw_block_speed_seconds", "0")) > 0: effects.append("充能×2 / %s秒" % preview.draw_block_speed_seconds)
	var tail: Label = ui.text(" · ".join(effects), Rect2(x, 578, maxf(1, 1824 - x), 34), 20, P.PAPER)
	tail.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	panel.mouse_filter = Control.MOUSE_FILTER_PASS
	var formula: Array[String] = []
	var resonance := float(preview.get("resonance_multiplier", "1"))
	if resonance > 1.0: formula.append("主核增幅 ×%.2f" % resonance)
	var conflict_pairs := int(preview.get("conflict_pair_count", 0))
	var cancellation := float(preview.get("conflict_cancellation", "0"))
	if conflict_pairs > 0: formula.append("相克 %s组 · 抵消 %s" % [conflict_pairs, Details.percent(cancellation)])
	panel.tooltip_text = "最终伤害 %s（扣盾 %s · 扣血 %s）\n%s\n%s\n按当前战斗状态结算，状态变化后会重新计算" % [actual_damage, shield_damage, hp_damage, " · ".join(formula), " · ".join(effects)]

static func _duel(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.player
	var duel: Dictionary = state.duel
	var hero: Control = _picture(ui, Art.portrait(player.get("hero_class", Game.hero_class)), Rect2(80, 139, 285, 420))
	host._combat_panels[player.get("player_id", "")] = hero
	ui.text(P.CLASSES.get(player.get("hero_class", Game.hero_class), P.CLASSES.Mage)[0], Rect2(372, 161, 422, 53), 38, P.GOLD)
	_health(ui, player.get("combat", {}), Rect2(370, 229, 409, 120))
	ui.picture(Art.texture("UI/Encounter/encounter_vs_emblem_normal.png"), Rect2(855, 153, 216, 193))
	var opponent_class: String = duel.get("opponent_class", "")
	var opponent: Control = _picture(ui, Art.portrait(opponent_class) if P.CLASSES.has(opponent_class) else Art.texture("UI/Encounter/encounter_enemy_frame_normal.png"), Rect2(1516, 142, 268, 308))
	host._combat_panels[duel.get("opponent_id", "")] = opponent
	ui.text(duel.get("opponent_name", "同格旅人") + " · " + P.word(opponent_class), Rect2(1129, 161, 380, 53), 31, P.GOLD)
	ui.button(P.localized("opponent_stats"), Rect2(1534, 462, 252, 55), func(): host._show_battle_details(duel.get("opponent_status", {})))
	_health(ui, duel.get("opponent", {}), Rect2(1128, 229, 358, 120), true)
	var seconds: float = maxf(0, (float(duel.get("leave_window_ends_at_unix_ms", 0)) - Time.get_unix_time_from_system() * 1000) / 1000)
	ui.button("已请求离开" if duel.get("self_requested_leave", false) else "双方离开", Rect2(400, 398, 350, 66), func(): Game.command("duel.leave", {"duel_id": duel.duel_id}), not Game.allowed("duel.leave"))
	if seconds > 0: _center(ui.text("离开窗口 %.1f 秒" % seconds, Rect2(400, 480, 350, 44), 26, P.GOLD))
	ui.button("强制逃脱", Rect2(803, 395, 310, 70), func(): Game.command("duel.escape", {"duel_id": duel.duel_id}), not Game.allowed("duel.escape"))
	if not str(duel.get("escape_probability", "")).is_empty():
		ui.text("成功率 %s%%" % Details.percent(float(duel.escape_probability)), Rect2(812, 353, 308, 37), 23, P.MUTED)
	if duel.has("escape_remaining_ms"):
		_center(ui.text("逃脱中 %.1f 秒" % (float(duel.escape_remaining_ms) / 1000), Rect2(803, 480, 310, 44), 27, P.TEAL))
	if not Game.allowed("battle.play_cards"):
		ui.picture(Art.texture("UI/Encounter/encounter_lock_icon_normal.png"), Rect2(1290, 443, 47, 48))
	ui.text(P.localized("waiting_action"), Rect2(1350, 443, 330, 48), 26, P.GOLD)
	ui.text(P.localized("own_hand"), Rect2(80, 622, 330, 54), 34, P.GOLD)
	_passive(ui, player.get("hero_class", ""), Rect2(80, 703, 330, 117))

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
			var value := "自己" if current else ("首领" if cell.get("is_boss", false) else ("源泉" if cell.get("has_spring", false) else ""))
			var tile := ColorRect.new()
			tile.color = (Color("ad873c") if legal else colors[layer]).darkened(0.65)
			tile.position = rect.position
			tile.size = rect.size
			tile.mouse_filter = Control.MOUSE_FILTER_IGNORE
			ui.add_child(tile)
			var button: Button = ui.button(value, rect, func(): host._move(row, column), not legal or not Game.allowed("room.move"), SLOT)
			button.add_theme_font_size_override("font_size", 30)
			var tint: Color = colors[layer]
			button.add_theme_stylebox_override("normal", Art.style(SLOT, Color("e7bb66") if legal else tint))
			button.add_theme_stylebox_override("disabled", Art.style(SLOT, Color("f2d392") if current else tint))
			button.add_theme_color_override("font_disabled_color", P.GOLD if current else (Color("fa8c72") if cell.get("is_boss", false) else P.TEAL))
			button.tooltip_text = "%s层%s" % [["外", "中", "内"][layer], " · 可前往" if legal else ""]
			if cell.get("has_spring", false) and not current and not cell.get("is_boss", false):
				button.text = ""
				var spring: TextureRect = _picture(ui, Art.texture("UI/Action/spring_clean.png"), Rect2(rect.position + Vector2(39, 9), Vector2(59, 58)))
				spring.name = "MapSpring_%s_%s" % [row, column]
				_center(ui.text("源泉", Rect2(rect.position + Vector2(6, 65), Vector2(125, 40)), 29, P.TEAL))
	ui.panel(Rect2(1372, 241, 430, 548))
	_center(ui.text("图例", Rect2(1420, 274, 333, 65), 40, P.GOLD))
	for index in range(3):
		var tint: Color = [Color("fa8c72"), P.TEAL, P.GOLD][index]
		if index == 1:
			_picture(ui, Art.texture("UI/Action/spring_clean.png"), Rect2(1423, 377 + index * 114, 88, 83))
		else: ui.panel(Rect2(1423, 377 + index * 114, 88, 83), SLOT).modulate = tint
		ui.text(["首领", "源泉", "自己"][index], Rect2(1535, 394 + index * 114, 220, 55), 34, tint)
	ui.text("高亮邻格可前往", Rect2(1431, 725, 330, 38), 24, P.GOLD)
	ui.text("向内探索后无法返回外层。\n源泉常亮，可规划补给路线。", Rect2(80, 265, 293, 171), 26, P.MUTED)
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
	ui.text("已用 %s / %s 格" % [inventory.size(), player.get("inventory_capacity", 0)], Rect2(1268, 240, 466, 40), 25, P.PAPER)
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
		item_view.configure(item, _item_icon(item))
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
		var title: String = {"action.spring": "饮用生命泉水", "action.potion": "使用生命药剂", "action.extract": "撤离", "map": "走邻格"}.get(action, "")
		var callback: Callable = func(): Game.command(action)
		if action == "map": callback = func(): host.set_meta("exploration_map_open", true); host._schedule_render()
		if relic:
			var pile_id := action.trim_prefix("relic:")
			for pile in piles:
				if pile.pile_id == pile_id: title = str(pile.get("owner_name", "旅人")) + "的遗物"; break
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
			_center(ui.text(("撤离中 " if key.begins_with("extraction") else "饮用泉水 ") + "%.1f 秒" % (float(state[key]) / 1000), Rect2(615, 453, 560, 67), 36, P.TEAL))
	ui.button("查看地图", Rect2(80, 985, 244, 56), func(): host.set_meta("exploration_map_open", true); host._schedule_render())

static func _item_icon(item: Dictionary) -> Texture2D:
	var kind: String = item.get("kind", "")
	var suffix: String = {"Gold": "gold", "EquipmentFragments": "fragments", "WarriorSoul": "warrior_soul", "HealthPotion": "potion", "ClassSoul": Game.hero_class.to_lower() + "_soul"}.get(kind, "")
	if kind == "Equipment":
		suffix = {"Helmet": "helmet", "Head": "helmet", "Chest": "chest", "Body": "chest", "Hands": "gauntlet", "Gloves": "gauntlet", "Legs": "legs", "Feet": "boots", "Boots": "boots"}.get(item.get("equipment", {}).get("slot", ""), "")
	return Art.texture(ITEM + suffix + ".png") if not suffix.is_empty() else null

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
		var title: String = {1: "装备", 2: "碎片堆", 3: "即时回血"}.get(kind, "战利品")
		_center(ui.text(title, Rect2(rect.position + Vector2(24, 28), Vector2(376, 62)), 42, P.PAPER))
		var item := {"kind": "Equipment", "equipment": option.get("equipment", {})}
		if kind == 3: _center(ui.text("+", Rect2(rect.position + Vector2(112, 103), Vector2(200, 165)), 120, P.TEAL))
		else: ui.picture(_item_icon(item) if kind == 1 else Art.texture(ITEM + "fragments.png"), Rect2(rect.position + Vector2(127, 103), Vector2(170, 165)))
		var description: String = "数量 ×%s" % option.get("quantity", 0)
		if kind == 1: description = Details.description(item)
		elif kind == 3:
			var combat: Dictionary = Game.room.get("player", {}).get("combat", {})
			var maximum: int = int(combat.get("maximum_hp", 0))
			var amount: int = mini(maxi(0, int(combat.get("effective_maximum_hp", maximum)) - int(combat.get("hp", 0))), int(maximum * int(option.get("heal_percent", 0)) / 100.0))
			description = "%s%% 最大生命 · 预计回复 %s" % [option.get("heal_percent", 0), amount]
		ui.text(description, Rect2(rect.position + Vector2(25, 281), Vector2(374, 168)), 23, P.TEAL)
		ui.button("收入背包" if kind != 3 else "立即回复", Rect2(rect.position + Vector2(25, 459), Vector2(374, 61)), func(): host._claim(option), not Game.allowed("reward.choice.claim"))
		if kind == 1:
			ui.button("对比 / 直接穿戴", Rect2(rect.position + Vector2(25, 525), Vector2(374, 58)), func(): host._show_equipment_details(item, func(): host._claim(option, true), "直接穿戴（回收旧装）"), not Game.allowed("reward.choice.claim"))
	var count: int = clampi(int(reward.get("refresh_count", 0)), 0, 3)
	ui.text("本局刷新 %s / 3" % count, Rect2(311, 840, 370, 66), 31, P.GOLD)
	ui.button("刷新 %s 金币" % [60, 180, 450][mini(count, 2)] if count < 3 else "刷新已用尽", Rect2(746, 830, 425, 91), func(): Game.command("reward.choice.refresh"), count >= 3 or not Game.allowed("reward.choice.refresh"))
	ui.text("当前%s层" % ["外", "中", "内"][clampi(int(reward.get("layer", 0)), 0, 2)], Rect2(1275, 845, 334, 64), 29, P.MUTED)

static func build_settlement(ui: Control, _host: Control) -> void:
	ui.panel(Rect2(483, 196, 954, 690))
	_center(ui.text(P.word(Game.settlement.get("result", "旅程结束")), Rect2(545, 253, 830, 100), 64, P.GOLD))
	_center(ui.text("此行收获", Rect2(598, 380, 724, 65), 36, P.PAPER))
	var details: Dictionary = Game.settlement.get("details", {})
	var y := 469.0
	for key in ["gold", "goldEarned", "equipmentFragments", "warriorSoul"]:
		if not details.has(key): continue
		var title: String = {"gold": "金币", "goldEarned": "金币", "equipmentFragments": "装备碎片", "warriorSoul": "勇士之魂"}[key]
		ui.text(title, Rect2(633, y, 390, 52), 30, P.PAPER)
		ui.text(str(details[key]), Rect2(1113, y, 170, 52), 32, P.GOLD)
		y += 55
	ui.button("返回", Rect2(649, 754, 625, 81), Game.acknowledge_settlement, Game.busy)

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
