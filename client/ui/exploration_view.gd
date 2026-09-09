extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const PANEL := "UI/CardCodex/card_codex_dialog_panel_normal.png"
const SLOT := "UI/Prep/exploration_prep_backpack_cell_empty_normal.png"
const ITEM := "UI/Item/exploration_prep_item_icon_"

static func build(ui: Control, host: Control) -> void:
	var state: Dictionary = Game.room
	var phase: String = state.get("player", {}).get("phase", "")
	if phase in ["Pve", "Pvp"]:
		_battle(ui, host, state)
	elif state.has("reward_choice"):
		_rewards(ui, host, state.reward_choice)
	elif host.get_meta("exploration_map_open", false):
		_map(ui, host, state)
	else:
		_actions(ui, host, state)
	ui.button("同步", Rect2(1702, 985, 140, 56), func(): Game.gateway.send("room.snapshot.read"))
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

static func _bar(ui: Control, rect: Rect2, value: float, maximum: float, fill: String, track: String) -> void:
	var bar := ProgressBar.new()
	bar.position = rect.position
	bar.size = rect.size
	bar.show_percentage = false
	bar.max_value = maxf(1, maximum)
	bar.value = value
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar.add_theme_stylebox_override("background", Art.style(track))
	bar.add_theme_stylebox_override("fill", Art.style(fill))
	ui.add_child(bar)

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
	var frame: Control = ui.panel(rect)
	frame.name = "PlayerPassive_" + hero_class
	frame.mouse_filter = Control.MOUSE_FILTER_PASS
	frame.tooltip_text = "本命 · %s\n%s" % [names[hero_class], descriptions[hero_class]]
	var icon: TextureRect = _picture(ui, Art.passive(hero_class), Rect2(rect.position + Vector2(12, 9), Vector2(66, rect.size.y - 18)))
	icon.name = "PlayerPassiveIcon_" + hero_class
	ui.text("本命 · " + names[hero_class], Rect2(rect.position + Vector2(89, 8), Vector2(rect.size.x - 100, 36)), 25, P.GOLD)
	ui.text(descriptions[hero_class], Rect2(rect.position + Vector2(89, 44), Vector2(rect.size.x - 103, rect.size.y - 49)), 20, P.MUTED)

static func _battle(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.get("player", {})
	var pvp: bool = state.has("duel")
	_title(ui, "遭遇战" if pvp else "混沌战斗", true)
	if pvp:
		_duel(ui, host, state)
	else:
		var hero: Control = _picture(ui, Art.portrait(player.get("hero_class", Game.hero_class)), Rect2(80, 120, 515, 488))
		host._combat_panels[player.get("player_id", "")] = hero
		ui.text(P.CLASSES.get(player.get("hero_class", Game.hero_class), P.CLASSES.Mage)[0], Rect2(80, 615, 350, 48), 34, P.GOLD)
		_health(ui, player.get("combat", {}), Rect2(80, 670, 310, 115))
		_passive(ui, player.get("hero_class", ""), Rect2(621, 443, 317, 122))
		var monsters: Array = state.get("pve", {}).get("monsters", [])
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
				_center(ui.text("已击败", Rect2(x + 24, 126, 315, 58), 32, P.MUTED))
			_health(ui, monster, Rect2(x + 24, 190, 315, 114), true)
			var name: String = host._monster_name(monster.get("monster_id", ""))
			if monster.get("monster_id", "") == "annihilation-core": name += " · %s阶段" % ("二" if boss_phase == 2 else "一")
			var button: Button = ui.button(name + (" · 目标" if selected else ""), Rect2(x + 10, 550, 350, 58), func(): Game.command("battle.select_target", {"battle_id": state.pve.battle_id, "target_id": monster.monster_id}), not Game.allowed("battle.select_target") or not alive)
			if selected: button.add_theme_color_override("font_disabled_color", P.GOLD)
			if alive and int(monster.get("stun_remaining_ms", 0)) > 0:
				_center(ui.text("眩晕 %.1f 秒" % (float(monster.stun_remaining_ms) / 1000), Rect2(x + 15, 502, 340, 45), 25, P.TEAL))
			elif alive and int(monster.get("windup_remaining_ms", 0)) > 0:
				_center(ui.text("即将行动 %.1f 秒" % (float(monster.windup_remaining_ms) / 1000), Rect2(x + 15, 502, 340, 45), 25, P.GOLD))
	_hand(ui, host, state)

static func _hand(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.get("player", {})
	var hand: Array = player.get("hand", [])
	var origin := Vector2(458, 622)
	for index in range(5):
		var rect := Rect2(origin + Vector2(index * 232, 0), Vector2(218, 376))
		if index < hand.size():
			var card: Dictionary = hand[index]
			ui.card(host, card.get("card_id", ""), rect, func(): Game.toggle_card(card.instance_id), card.get("instance_id", "") in Game.selected_cards, not Game.allowed("battle.play_cards"))
		else:
			ui.panel(rect, "UI/Codex/qframe_common.png")
	ui.button("放", Rect2(1650, 822, 194, 142), Game.play_cards, Game.selected_cards.is_empty() or not Game.allowed("battle.play_cards"), "UI/Battle/battle_play_button.png")
	ui.picture(Art.texture("UI/Battle/battle_energy_ring.png"), Rect2(77, 843, 84, 84))
	ui.text("抽牌", Rect2(170, 838, 230, 43), 26, P.TEAL)
	_bar(ui, Rect2(171, 889, 225, 22), clampf(float(player.get("draw_charge", "0")), 0, 1), 1, "UI/Battle/battle_energy_cell_lit.png", "UI/Battle/battle_energy_cell_unlit.png")
	ui.text("牌库 %s · 弃牌 %s" % [player.get("library_count", 0), player.get("discard_count", 0)], Rect2(79, 940, 330, 32), 21, P.MUTED)
	_center(ui.text("已选 %s 张    1–5 选牌 / 空格放出" % Game.selected_cards.size(), Rect2(573, 1005, 765, 36), 23, P.PAPER))

static func _duel(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.player
	var duel: Dictionary = state.duel
	var hero: Control = _picture(ui, Art.portrait(player.get("hero_class", Game.hero_class)), Rect2(80, 139, 285, 420))
	host._combat_panels[player.get("player_id", "")] = hero
	ui.text(P.CLASSES.get(player.get("hero_class", Game.hero_class), P.CLASSES.Mage)[0], Rect2(372, 161, 422, 53), 38, P.GOLD)
	_health(ui, player.get("combat", {}), Rect2(370, 229, 409, 120))
	ui.picture(Art.texture("UI/Encounter/encounter_vs_emblem_normal.png"), Rect2(855, 153, 216, 193))
	var opponent: Control = _picture(ui, Art.texture("UI/Encounter/encounter_enemy_frame_normal.png"), Rect2(1516, 142, 268, 308))
	host._combat_panels[duel.get("opponent_id", "")] = opponent
	_center(ui.text("同格旅人", Rect2(1535, 242, 233, 72), 34, P.GOLD))
	ui.text("对手", Rect2(1129, 161, 340, 53), 38, P.GOLD)
	_health(ui, duel.get("opponent", {}), Rect2(1128, 229, 358, 120), true)
	var seconds: float = maxf(0, (float(duel.get("leave_window_ends_at_unix_ms", 0)) - Time.get_unix_time_from_system() * 1000) / 1000)
	ui.button("已请求离开" if duel.get("self_requested_leave", false) else "双方离开", Rect2(400, 398, 350, 66), func(): Game.command("duel.leave", {"duel_id": duel.duel_id}), not Game.allowed("duel.leave"))
	if seconds > 0: _center(ui.text("离开窗口 %.1f 秒" % seconds, Rect2(400, 480, 350, 44), 26, P.GOLD))
	ui.button("强制逃脱", Rect2(803, 395, 310, 70), func(): Game.command("duel.escape", {"duel_id": duel.duel_id}), not Game.allowed("duel.escape"))
	if duel.has("escape_remaining_ms"):
		_center(ui.text("逃脱中 %.1f 秒" % (float(duel.escape_remaining_ms) / 1000), Rect2(803, 480, 310, 44), 27, P.TEAL))
	if not Game.allowed("battle.play_cards"):
		ui.picture(Art.texture("UI/Encounter/encounter_lock_icon_normal.png"), Rect2(1290, 443, 47, 48))
		ui.text("等待行动", Rect2(1350, 443, 330, 48), 26, P.GOLD)
	# The opponent's class and hand are private in the current snapshot.
	ui.text("自己的手牌", Rect2(80, 622, 330, 54), 34, P.GOLD)
	_passive(ui, player.get("hero_class", ""), Rect2(80, 703, 330, 117))

static func _map(ui: Control, host: Control, state: Dictionary) -> void:
	_title(ui, "混沌领域")
	var origin := Vector2(424, 144)
	var stride := Vector2(145, 126)
	var colors: Array = [Color("79909c"), Color("a3a575"), Color("c6aa81")]
	for row in range(6):
		for column in range(6):
			var layer: int = mini(mini(row, column), mini(5 - row, 5 - column))
			var current: bool = int(state.get("self", {}).get("row", -1)) == row and int(state.get("self", {}).get("column", -1)) == column
			var legal: bool = state.get("legal_moves", []).any(func(move): return int(move.row) == row and int(move.column) == column)
			var rect := Rect2(origin + Vector2(column * stride.x, row * stride.y), Vector2(137, 118))
			var cell := {}
			for candidate in state.get("map", []):
				if int(candidate.row) == row and int(candidate.column) == column: cell = candidate; break
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
	ui.button("返回当前格", Rect2(80, 985, 262, 56), func(): host.set_meta("exploration_map_open", false); host._schedule_render())

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
	ui.text("临时行囊", Rect2(1268, 182, 480, 54), 34, P.GOLD)
	ui.text("已用 %s 格" % inventory.size(), Rect2(1268, 240, 466, 40), 25, P.PAPER)
	for index in range(mini(6, inventory.size())):
		var item: Dictionary = inventory[index]
		var x: float = 1268 + index % 3 * 162
		var y: float = 291 + int(index / 3) * 99
		ui.panel(Rect2(x, y, 137, 83), SLOT)
		ui.picture(_item_icon(item), Rect2(x + 7, y + 8, 64, 60))
		ui.text("×%s" % item.get("quantity", 0), Rect2(x + 75, y + 27, 59, 37), 23, P.GOLD if item.get("is_safe", false) else P.PAPER)
	var actions: Array = []
	for action in ["action.spring", "action.potion", "action.extract"]:
		if Game.allowed(action): actions.append(action)
	var piles: Array = state.get("current_cell", {}).get("relic_pile_ids", [])
	if not piles.is_empty(): actions.append("relic")
	actions.append("map")
	ui.panel(Rect2(80, 571, 1758, 393))
	_center(ui.text("选择接下来的行动", Rect2(610, 539, 680, 82), 43, P.GOLD))
	var start: float = 960 - actions.size() * 286.0 / 2
	for index in range(actions.size()):
		var action: String = actions[index]
		var rect := Rect2(start + index * 286, 639, 264, 278)
		var title: String = {"action.spring": "饮用生命泉水", "action.potion": "使用生命药剂", "action.extract": "撤离", "map": "走邻格", "relic": "遗物 %s 堆" % piles.size()}[action]
		var callback: Callable = func(): Game.command(action)
		if action == "map": callback = func(): host.set_meta("exploration_map_open", true); host._schedule_render()
		var action_name: String = action.trim_prefix("action.")
		var action_button: Button = ui.button("", rect, callback, action == "relic", SLOT)
		action_button.name = "Action_" + action_name
		var key: String = {"action.spring": "UI/Action/spring_clean.png", "action.potion": ITEM + "potion.png", "action.extract": "UI/Action/extract_gate_clean.png", "relic": "UI/Action/relic_pile_clean.png"}.get(action, "")
		if key.is_empty():
			_center(ui.text("→", Rect2(rect.position + Vector2(55, 27), Vector2(154, 149)), 96, P.TEAL))
		else:
			var icon: TextureRect = _picture(ui, Art.texture(key), Rect2(rect.position + Vector2(42, 20), Vector2(180, 160)))
			icon.name = "ActionIcon_" + action_name
		_center(ui.text(title, Rect2(rect.position + Vector2(12, 183), Vector2(240, 44)), 28, P.PAPER))
		if action == "relic": _center(ui.text("暂不可拾取", Rect2(rect.position + Vector2(12, 230), Vector2(240, 35)), 21, P.MUTED))
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
		var rect := Rect2(285 + index * 458, 226, 424, 564)
		ui.panel(rect)
		if index >= options.size():
			_center(ui.text("等待战利品", Rect2(rect.position + Vector2(24, 220), Vector2(376, 70)), 32, P.MUTED))
			continue
		var option: Dictionary = options[index]
		var kind: int = int(option.get("kind", 0))
		var title: String = {1: "装备", 2: "碎片堆", 3: "即时回血"}.get(kind, "战利品")
		_center(ui.text(title, Rect2(rect.position + Vector2(24, 28), Vector2(376, 62)), 42, P.PAPER))
		var key: String = {1: "UI/Enhance/armor_chest_art.png", 2: ITEM + "fragments.png"}.get(kind, "")
		if kind == 3: _center(ui.text("+", Rect2(rect.position + Vector2(67, 114), Vector2(290, 259)), 156, P.TEAL))
		else: ui.picture(Art.texture(key), Rect2(rect.position + Vector2(67, 114), Vector2(290, 259)))
		var description: String = "%s%% 生命" % option.get("heal_percent", 0) if kind == 3 else "数量 ×%s" % option.get("quantity", 0)
		_center(ui.text(description, Rect2(rect.position + Vector2(25, 382), Vector2(374, 63)), 33, P.TEAL))
		ui.button("选择", Rect2(rect.position + Vector2(59, 460), Vector2(306, 69)), func(): host._claim(option), not Game.allowed("reward.choice.claim"))
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
	ui.button("收下结算，返回营地", Rect2(649, 754, 625, 81), Game.acknowledge_settlement, Game.busy)

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
		label.text = entry[0]
		label.position = Vector2(583, entry[2])
		label.size = Vector2(754, 76)
		label.add_theme_font_size_override("font_size", entry[1])
		label.add_theme_color_override("font_color", P.GOLD if entry[1] == 54 else P.PAPER)
		_center(label)
		overlay.add_child(label)
	var confirm := Button.new()
	confirm.text = "确认进入"
	confirm.position = Vector2(735, 758)
	confirm.size = Vector2(450, 87)
	confirm.add_theme_font_size_override("font_size", 35)
	Art.button(confirm, "UI/CardCodex/card_codex_action_button_blue.png")
	confirm.pressed.connect(func():
		host.remove_meta("pending_move")
		host._midlayer_seen[Game.room.get("room_id", "")] = true
		overlay.queue_free()
		Game.command("room.move", {"row": row, "column": column}))
	overlay.add_child(confirm)
	var cancel := Button.new()
	cancel.text = "暂不进入"
	cancel.position = Vector2(750, 861)
	cancel.size = Vector2(420, 60)
	Art.button(cancel, "UI/CardCodex/card_codex_action_button_blue.png")
	cancel.pressed.connect(func(): host.remove_meta("pending_move"); overlay.queue_free())
	overlay.add_child(cancel)
