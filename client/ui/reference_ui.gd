extends Control

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const Exploration = preload("res://ui/exploration_view.gd")
const BLUE := "UI/CardCodex/card_codex_action_button_blue.png"
const ORANGE := "UI/CardCodex/card_codex_action_button_orange.png"
var host: Control

func build(source: Control) -> void:
	host = source
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if not Game.settlement.is_empty():
		Exploration.build_settlement(self, host)
	elif not Game.room.is_empty():
		Exploration.build(self, host)
		if host.has_meta("pending_move"):
			if Game.allowed("room.move"):
				var move: Vector2i = host.get_meta("pending_move")
				Exploration.show_midlayer(self, host, move.x, move.y)
			else: host.remove_meta("pending_move")
	elif not Game.ready_prompt.is_empty():
		_ready_prompt()
	else:
		_header()
		if host.screen_loading:
			text("正在读取…", Rect2(700, 440, 520, 100), 40, P.GOLD)
			return
		match host.screen:
			"hall": _hall()
			"cards": _codex()
			"prep": _preparation()
			"gear": _gear()
			"enhance": _enhance()
			"shop": _shop()
			"market": _market()
	text(Game.connection, Rect2(1260, 1038, 620, 30), 18, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

func text(value: String, rect: Rect2, font_size: int = 24, color: Color = P.PAPER) -> Label:
	var label := Label.new()
	label.text = value
	label.add_theme_font_size_override("font_size", font_size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	label.clip_text = true
	add_child(label)
	label.position = rect.position
	label.size = rect.size
	return label

func picture(texture: Texture2D, rect: Rect2) -> TextureRect:
	var image := Art.image(self, texture, Vector2.ZERO)
	image.position = rect.position
	image.size = rect.size
	return image

func panel(rect: Rect2, key: String = "UI/CardCodex/card_codex_dialog_panel_normal.png") -> Control:
	var node := Panel.new()
	node.add_theme_stylebox_override("panel", Art.style(key))
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(node)
	node.position = rect.position
	node.size = rect.size
	return node

func button(value: String, rect: Rect2, action: Callable, disabled: bool = false, key: String = BLUE) -> Button:
	var node := Button.new()
	node.text = value
	node.disabled = disabled
	node.pressed.connect(action)
	Art.button(node, key)
	add_child(node)
	node.position = rect.position
	node.size = rect.size
	return node

func card(source: Control, id: String, rect: Rect2, action: Callable, selected: bool = false, disabled: bool = false) -> Button:
	var node: Button = source._card_button(self, id, action, selected, disabled)
	node.name = "Card_" + id
	node.position = rect.position
	node.size = Vector2(218, 376)
	node.scale = rect.size / Vector2(218, 376)
	return node

func _scroll(rect: Rect2, horizontal: bool = false) -> ScrollContainer:
	var node := ScrollContainer.new()
	node.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO if horizontal else ScrollContainer.SCROLL_MODE_DISABLED
	node.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED if horizontal else ScrollContainer.SCROLL_MODE_AUTO
	add_child(node)
	node.position = rect.position
	node.size = rect.size
	return node

func _header() -> void:
	panel(Rect2(24, 18, 1872, 82))
	var names := {"hall": "幻想牌域", "cards": "卡牌图鉴", "prep": "探索准备", "gear": "装备穿戴", "enhance": "碎片强化", "shop": "金币商店", "market": "金币市场"}
	if host.screen == "hall":
		picture(Art.texture("UI/Hall/logo.png"), Rect2(55, 29, 255, 58))
	else:
		button("返回营地", Rect2(40, 32, 170, 52), host._navigate.bind("hall"), Game.busy or not Game.ticket.is_empty())
		text(names.get(host.screen, "营地"), Rect2(240, 30, 500, 60), 38, P.GOLD)
	picture(_item("Gold"), Rect2(1490, 35, 44, 44))
	text("金币 %s" % Game.lobby.get("wallet", {}).get("gold", 0), Rect2(1546, 38, 310, 46), 28, P.GOLD)

func _item(kind: String) -> Texture2D:
	var names := {"Gold": "gold", "WarriorSoul": "warrior_soul", "EquipmentFragments": "fragments", "HealthPotion": "potion", "MageSoul": "mage_soul", "PriestSoul": "priest_soul", "GuardianSoul": "guardian_soul", "Helmet": "helmet", "Head": "helmet", "Chest": "chest", "Hands": "gauntlet", "Legs": "legs", "Feet": "boots"}
	return Art.texture("UI/Item/exploration_prep_item_icon_%s.png" % names[kind]) if names.has(kind) else null

func _hall() -> void:
	for i in range(3):
		var hero_class: String = ["Priest", "Mage", "Guardian"][i]
		var key := "UI/Hall/card_%s_%s.png" % [hero_class.to_lower(), "on" if hero_class == Game.hero_class else "off"]
		var node := button("", Rect2(42 + i * 310, 118, 295, 138), Game.select_class.bind(hero_class), Game.busy or not Game.preparation.is_empty())
		node.tooltip_text = "%s · 生命上限 %s" % [P.CLASSES[hero_class][0], P.CLASSES[hero_class][2]]
		picture(Art.texture(key), Rect2(42 + i * 310, 118, 295, 138))
	picture(Art.portrait(Game.hero_class), Rect2(310, 255, 570, 550)).name = "HeroPortrait"
	picture(Art.passive(Game.hero_class), Rect2(858, 275, 84, 84)).name = "HeroPassive"
	panel(Rect2(52, 320, 250, 435))
	text("专属武器", Rect2(90, 343, 180, 45), 26, P.GOLD)
	picture(Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % Game.hero_class.to_lower()), Rect2(80, 408, 200, 210))
	text(P.CLASSES[Game.hero_class][1] + "\n已锁定", Rect2(95, 650, 180, 90), 26, P.GOLD)
	picture(Art.texture("UI/Hall/portal_panel.png"), Rect2(990, 153, 835, 550))
	button("探索准备", Rect2(1140, 640, 520, 96), host._navigate.bind("prep"), Game.busy, ORANGE)
	var entries := [["cards", "codex"], ["gear", "gear"], ["cards", "deck"], ["shop", "shop"], ["market", "market"], ["prep", "prep"], ["enhance", "enhance"]]
	for i in range(entries.size()):
		var rect := Rect2(56 + i * 259, 802, 242, 223)
		var node := button("", rect, host._navigate.bind(entries[i][0]), Game.busy or not Game.ticket.is_empty())
		node.tooltip_text = entries[i][0]
		picture(Art.texture("UI/Hall/btn_%s.png" % entries[i][1]), rect)

func _codex() -> void:
	panel(Rect2(25, 115, 1378, 915))
	panel(Rect2(1425, 115, 470, 915))
	var search := LineEdit.new()
	search.placeholder_text = "按名称或卡牌 ID 搜索，回车确认"
	search.text = host._search
	search.text_submitted.connect(func(value): host._search = value.strip_edges(); host._render())
	add_child(search)
	search.position = Vector2(55, 142)
	search.size = Vector2(595, 60)
	var qualities := ["", "White", "Green", "Blue", "Purple", "Orange"]
	for i in range(qualities.size()):
		var quality: String = qualities[i]
		button("全部" if quality.is_empty() else P.word(quality), Rect2(684 + i * 111, 145, 100, 54), func(): host._quality = quality; host._render(), false, ORANGE if quality == host._quality else BLUE)
	var scroll := _scroll(Rect2(56, 230, 1320, 767))
	var grid := GridContainer.new()
	grid.columns = 5
	grid.add_theme_constant_override("h_separation", 40)
	grid.add_theme_constant_override("v_separation", 26)
	scroll.add_child(grid)
	var shown := 0
	for owned in host.owned:
		var id: String = owned.cardId
		var info: Dictionary = host.cards.get(id, {})
		var hero_class: Variant = owned.get("heroClass")
		if hero_class != null and hero_class != Game.hero_class: continue
		if not host._quality.is_empty() and info.get("quality") != host._quality: continue
		if not host._search.is_empty() and not (host._search.to_lower() in (id + str(info.get("name", ""))).to_lower()): continue
		var can_add: bool = owned.get("unlocked", false) and host.deck_draft.size() < 20 and host.deck_draft.count(id) < int(owned.get("copyCount", 0))
		if info.get("quality") == "Orange":
			for entry in host.deck_draft:
				var existing: Dictionary = host.cards.get(entry, {})
				if existing.get("quality") == "Orange" and (existing.get("hero_class") == null) == (hero_class == null): can_add = false
		var node: Button = host._card_button(grid, id, func(): host.deck_draft.append(id); host._render(), false, not can_add)
		node.tooltip_text += "\n已编入 %s · 持有 %s · 等级 %s" % [host.deck_draft.count(id), owned.copyCount, owned.level]
		shown += 1
	if shown == 0: text("没有符合条件的卡牌", Rect2(110, 330, 1000, 80), 32, P.MUTED)
	text("当前编组  %s / 20" % host.deck_draft.size(), Rect2(1460, 140, 400, 65), 34, P.GOLD)
	var deck_scroll := _scroll(Rect2(1455, 218, 405, 674))
	var rows := VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 4)
	deck_scroll.add_child(rows)
	for i in range(host.deck_draft.size()):
		var id: String = host.deck_draft[i]
		var info: Dictionary = host.cards.get(id, {})
		var row := Button.new()
		row.text = "%02d  %s    ×" % [i + 1, info.get("name", id)]
		row.alignment = HORIZONTAL_ALIGNMENT_LEFT
		row.custom_minimum_size = Vector2(395, 38)
		row.add_theme_font_size_override("font_size", 20)
		Art.button(row, "UI/Codex/deck_row_%s.png" % str(info.get("quality", "White")).to_lower())
		row.pressed.connect(func(): host.deck_draft.remove_at(i); host._render())
		rows.add_child(row)
	button("还原", Rect2(1460, 930, 165, 62), func(): host.deck_draft = Game.deck().get("cardIds", []).duplicate(); host._render())
	button("保存编组", Rect2(1642, 930, 200, 62), host._save_deck, Game.busy or host.deck_draft.size() != 20, ORANGE)

func _loadout(rect: Rect2, editable: bool, snapshot: Dictionary = {}) -> void:
	var hero_class: String = snapshot.get("heroClass", Game.hero_class)
	var equipment_ids: Array = snapshot.get("equipmentIds", host.gear_draft)
	var equipment_values: Array = snapshot.get("equipmentSnapshots") if snapshot.get("equipmentSnapshots") is Array else host.inventory.get("equipments", [])
	picture(Art.portrait(hero_class), Rect2(rect.position + Vector2(rect.size.x * 0.26, 105), Vector2(rect.size.x * 0.48, 535))).name = "HeroPortrait"
	text(P.CLASSES[hero_class][0], Rect2(rect.position + Vector2(45, 26), Vector2(400, 60)), 36, P.GOLD)
	var slots := ["Head", "Chest", "Hands", "Legs", "Feet"]
	var locations := [Vector2(40, 133), Vector2(40, 320), Vector2(40, 507), Vector2(rect.size.x - 165, 133), Vector2(rect.size.x - 165, 320)]
	for i in range(5):
		var id: Variant = equipment_ids[i] if i < equipment_ids.size() else null
		var item: Dictionary = {}
		for owned in equipment_values:
			if owned.instanceId == id: item = owned
		var point: Vector2 = rect.position + locations[i]
		var quality: String = str(item.get("quality", "common")).to_lower()
		var slot := button("", Rect2(point, Vector2(120, 120)), func(): host.gear_draft.resize(5); host.gear_draft[i] = null; host._render(), not editable or id == null, "UI/Prep/exploration_prep_equipment_slot_frame_%s.png" % quality)
		slot.tooltip_text = host._equipment_name(item) if not item.is_empty() else P.word(slots[i]) + " · 未穿戴"
		picture(_item(slots[i]), Rect2(point + Vector2(18, 12), Vector2(84, 84))).modulate.a = 1.0 if id != null else 0.35
		text(P.word(slots[i]) + (" +%s" % item.get("level", 0) if id != null else ""), Rect2(point + Vector2(2, 125), Vector2(148, 40)), 22, P.MUTED)
	var weapon_pos := rect.position + Vector2(rect.size.x - 165, 507)
	panel(Rect2(weapon_pos, Vector2(120, 120)), "UI/Prep/exploration_prep_equipment_slot_frame_orange.png")
	picture(Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % hero_class.to_lower()), Rect2(weapon_pos + Vector2(12, 12), Vector2(96, 96)))
	text("本命 +%s · 锁定" % snapshot.classWeaponLevel if snapshot.has("classWeaponLevel") else "本命 · 锁定", Rect2(weapon_pos + Vector2(-8, 127), Vector2(180, 40)), 21, P.GOLD)

func _preparation() -> void:
	var locked: bool = not Game.preparation.is_empty()
	var snap: Dictionary = Game.preparation.get("snapshot", {})
	panel(Rect2(28, 122, 752, 900))
	panel(Rect2(798, 122, 1094, 900))
	_loadout(Rect2(45, 140, 715, 720), false, snap)
	var card_ids: Array = snap.get("cardIds", Game.deck().get("cardIds", []))
	text("%s %s / 20    生命上限 %s" % ["已锁定编组" if locked else "编组", card_ids.size(), snap.get("maximumHp", P.CLASSES[Game.hero_class][2])], Rect2(85, 872, 640, 70), 26)
	text("卡牌与专属武器不占背包格", Rect2(85, 946, 650, 50), 22, P.MUTED)
	text("背包", Rect2(845, 145, 550, 65), 38, P.GOLD)
	var consumables: Dictionary = host.inventory.get("consumables", {})
	var stock := {"Advanced": int(consumables.get("advancedBagCount", 0)), "Top": int(consumables.get("topBagCount", 0))}
	if not locked and host.bag_tier != "Free" and stock.get(host.bag_tier, 0) <= 0:
		host.bag_tier = "Free"
	text("持有 高级 %s / 顶级 %s" % [stock.Advanced, stock.Top], Rect2(1390, 162, 440, 38), 23, P.MUTED)
	var tier: String = snap.get("backpackTier", host.bag_tier)
	var capacity: int = int(snap.get("backpackCapacity", {"Free": 20, "Advanced": 28, "Top": 36}.get(tier, 20)))
	var safe_slots: Array = snap.get("safeSlotIndexes", [] if tier == "Free" else ([27] if tier == "Advanced" else [33, 34, 35]))
	for i in range(3):
		var key: String = ["Free", "Advanced", "Top"][i]
		var title: String = ["免费包\n20 格 / 安全 0", "高级包\n28 格 / 安全 1", "顶级包\n36 格 / 安全 3"][i]
		var unavailable: bool = locked or (i > 0 and stock[key] <= 0)
		var tab := button(title if i == 0 else "", Rect2(845 + i * 328, 219, 307, 93), func(): host.bag_tier = key; host._render(), unavailable, ORANGE if tier == key else BLUE)
		tab.name = "Backpack_" + key
		if i > 0:
			picture(Art.product(key + "Bag"), Rect2(860 + i * 328, 226, 68, 78)).name = "BackpackIcon_" + key
			text(title.split("\n")[0], Rect2(937 + i * 328, 228, 202, 37), 25, P.MUTED if unavailable else P.PAPER)
			text(title.split("\n")[1], Rect2(937 + i * 328, 267, 202, 32), 20, P.GOLD if tier == key else P.MUTED)
			tab.tooltip_text = "持有 %s 个" % stock[key]
	for index in range(capacity):
		var point := Vector2(850 + (index % 6) * 163, 342 + (index / 6) * 82)
		panel(Rect2(point, Vector2(145, 73)), "UI/Prep/exploration_prep_backpack_cell_empty_normal.png")
		if index in safe_slots:
			picture(Art.texture("UI/Prep/icon_safe.png"), Rect2(point + Vector2(42, 5), Vector2(58, 58)))
		else: text(str(index + 1), Rect2(point + Vector2(8, 8), Vector2(110, 48)), 19, P.MUTED)
	picture(_item("HealthPotion"), Rect2(850, 853, 64, 74))
	text("生命药剂 · 持有 %s · 最多 2 瓶" % consumables.get("healthPotionCount", 0), Rect2(930, 850, 630, 45), 25)
	var count := SpinBox.new()
	count.max_value = mini(2, int(consumables.get("healthPotionCount", 0)))
	count.value = snap.get("potionCount", host.potion_count)
	count.editable = not locked
	count.value_changed.connect(func(value): host.potion_count = int(value))
	add_child(count)
	count.position = Vector2(1560, 847)
	count.size = Vector2(270, 66)
	if locked:
		button("取消匹配 / 准备", Rect2(850, 945, 410, 61), Game.cancel_preparation, Game.busy)
		button("正在匹配…" if not Game.ticket.is_empty() else "开始匹配", Rect2(1310, 945, 520, 61), Game.enqueue, Game.busy or not Game.gateway.online or not Game.ticket.is_empty(), ORANGE)
	else:
		button("确认探索准备", Rect2(1100, 945, 730, 61), func(): Game.prepare(host.bag_tier, host.potion_count), Game.busy, ORANGE)

func _gear() -> void:
	_loadout(Rect2(90, 135, 1030, 750), true)
	button("保存穿戴", Rect2(410, 939, 385, 68), func(): host._mutate("/loadouts/" + Game.hero_class, HTTPClient.METHOD_PUT, {"equipmentIds": host.gear_draft, "expectedVersion": Game.loadout().get("version", 0)}), Game.busy, ORANGE)
	panel(Rect2(1190, 136, 688, 886))
	text("仓库装备", Rect2(1235, 164, 520, 60), 36, P.GOLD)
	var scroll := _scroll(Rect2(1225, 255, 620, 625))
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	for item in host.inventory.get("equipments", []):
		var row := HBoxContainer.new()
		list.add_child(row)
		Art.image(row, _item(item.slot), Vector2(68, 70))
		var entry: Button = host._button(row, host._equipment_name(item), func(): host._equip(item), Game.busy or item.get("location") not in ["Inventory", "Equipped"])
		entry.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if list.get_child_count() == 0: text("仓库暂无装备\n探索撤离后可带回战利品", Rect2(1255, 362, 530, 160), 28, P.MUTED)
	button("碎片强化", Rect2(1260, 930, 530, 64), host._navigate.bind("enhance"))

func _enhance() -> void:
	panel(Rect2(30, 132, 470, 882))
	panel(Rect2(525, 130, 770, 884), "UI/Enhance/display_clean.png")
	panel(Rect2(1320, 132, 570, 882))
	text("选择强化物品", Rect2(70, 166, 390, 58), 34, P.GOLD)
	button("本命武器 · " + P.CLASSES[Game.hero_class][1], Rect2(66, 254, 393, 94), func(): host._enhance_item = ""; host._render(), false, ORANGE if host._enhance_item.is_empty() else BLUE)
	var scroll := _scroll(Rect2(64, 378, 405, 602))
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	var selected: Dictionary = {}
	for item in host.inventory.get("equipments", []):
		host._button(list, host._equipment_name(item), func(): host._enhance_item = item.instanceId; host._render(), item.get("location") not in ["Inventory", "Equipped"])
		if item.instanceId == host._enhance_item: selected = item
	var weapon: Dictionary = {}
	for entry in Game.lobby.get("classWeapons", []):
		if entry.heroClass == Game.hero_class: weapon = entry
	var level: int = int(selected.get("level", weapon.get("level", 0)))
	var title: String = host._equipment_name(selected) if not selected.is_empty() else P.CLASSES[Game.hero_class][1]
	text(title, Rect2(625, 178, 590, 68), 42, P.GOLD)
	var image: Texture2D = _item(selected.get("slot", "")) if not selected.is_empty() else Art.texture("UI/Item/exploration_prep_item_icon_weapon_%s.png" % Game.hero_class.to_lower())
	picture(image, Rect2(645, 290, 540, 540))
	text("+%s" % level, Rect2(810, 882, 290, 88), 58, P.GOLD)
	text("强化进度", Rect2(1375, 175, 450, 70), 38, P.GOLD)
	for i in range(5):
		var color := P.GOLD if i < level else P.MUTED
		text("+%s" % (i + 1), Rect2(1370 + i * 95, 300, 85, 72), 30, color)
	picture(_item("EquipmentFragments"), Rect2(1430, 439, 90, 108))
	text("装备碎片\n持有 %s" % Game.lobby.get("materials", {}).get("equipmentFragments", 0), Rect2(1535, 445, 300, 115), 30)
	text("本命武器只消耗碎片\n防具 +4 / +5 需同品质材料", Rect2(1370, 630, 470, 115), 26, P.MUTED)
	button("已达上限" if level >= 5 else "强化到 +%s" % (level + 1), Rect2(1380, 823, 440, 86), func():
		if not selected.is_empty(): host._enhance(selected)
		else: host._confirm("专属武器强化仅消耗装备碎片。", func(): host._mutate("/class-weapons/" + Game.hero_class + "/enhance", HTTPClient.METHOD_POST, {"expectedVersion": weapon.get("version", 0)})), Game.busy or level >= 5 or (not selected.is_empty() and selected.get("location") not in ["Inventory", "Equipped"]), ORANGE)

func _shop() -> void:
	panel(Rect2(28, 138, 1864, 864))
	var consumables: Dictionary = host.inventory.get("consumables", {})
	var paid_bags: int = int(consumables.get("advancedBagCount", 0)) + int(consumables.get("topBagCount", 0))
	var scroll := _scroll(Rect2(55, 210, 1810, 700), true)
	scroll.name = "ShopScroll"
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 20)
	scroll.add_child(row)
	for item in host.shop.get("products", []):
		var parsed: Variant = JSON.parse_string(item.get("payload", "{}"))
		var payload: Dictionary = parsed if parsed is Dictionary else {}
		var kind: String = item.get("kind", "")
		var product_title := _product_title(kind, payload)
		var item_panel := Panel.new()
		item_panel.name = "Product_" + str(item.productId)
		item_panel.custom_minimum_size = Vector2(240, 640)
		item_panel.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
		row.add_child(item_panel)
		var title := Label.new()
		title.text = product_title
		title.position = Vector2(20, 32)
		title.size = Vector2(200, 70)
		title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		title.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		title.mouse_filter = Control.MOUSE_FILTER_IGNORE
		item_panel.add_child(title)
		var image := Art.image(item_panel, _product_art(kind, payload), Vector2.ZERO)
		image.name = "ProductArt"
		image.position = Vector2(30, 127)
		image.size = Vector2(180, 230)
		var detail := Label.new()
		var amount: int = int(payload.get("amount", payload.get("count", 0)))
		detail.text = ("每份 ×%s\n" % amount if amount > 0 else "") + "今日 %s / %s\n\n%s 金币" % [item.purchased, item.limit, item.priceGold]
		detail.position = Vector2(20, 371)
		detail.size = Vector2(200, 160)
		detail.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		detail.mouse_filter = Control.MOUSE_FILTER_IGNORE
		item_panel.add_child(detail)
		var is_bag: bool = kind in ["AdvancedBag", "TopBag"]
		var stock_full: bool = is_bag and paid_bags + maxi(1, amount) > 3
		var stock_unknown: bool = is_bag and not host._shop_inventory_ready
		var buy_text := "刷新库存" if stock_unknown else ("库存已满" if stock_full else "购买")
		var buy: Button = host._button(item_panel, buy_text, func(): host._confirm("花费 %s 金币购买%s？" % [item.priceGold, product_title], func(): host._mutate("/shop/purchases", HTTPClient.METHOD_POST, {"productId": item.productId, "quantity": 1})), Game.busy or stock_unknown or stock_full or int(item.purchased) >= int(item.limit) or int(item.priceGold) > int(Game.lobby.get("wallet", {}).get("gold", 0)))
		buy.name = "Purchase"
		Art.button(buy, ORANGE)
		buy.position = Vector2(26, 546)
		buy.size = Vector2(188, 66)
	if row.get_child_count() == 0: text("暂无商品，请稍后刷新", Rect2(640, 440, 790, 95), 34, P.MUTED)
	text("高级与顶级背包合计上限 3 个 · %s" % ("持有 %s" % paid_bags if host._shop_inventory_ready else "请刷新库存"), Rect2(85, 937, 950, 45), 24, P.MUTED)
	button("刷新", Rect2(1630, 929, 190, 54), host._navigate.bind("shop"), Game.busy)

func _product_title(kind: String, payload: Dictionary) -> String:
	if kind == "Cards":
		if payload.has("cardId"): return host.cards.get(str(payload.cardId), {}).get("name", "卡牌 " + str(payload.cardId))
		return "卡包"
	if kind == "ClassSoul" and payload.get("heroClass", "") in P.CLASSES:
		return {"Mage": "法师之魂", "Priest": "牧师之魂", "Guardian": "盾卫之魂"}[payload.heroClass]
	return P.word(kind)

func _product_art(kind: String, payload: Dictionary) -> Texture2D:
	if kind == "Cards" and payload.has("cardId"):
		var illustration := Art.card(str(payload.cardId))
		if illustration != null: return illustration
	var dedicated := Art.product(kind)
	if dedicated != null: return dedicated
	if kind == "ClassSoul":
		var hero_class: String = payload.get("heroClass", "")
		return _item(hero_class + "Soul") if hero_class in P.CLASSES else null
	return _item(kind)

func _market() -> void:
	panel(Rect2(28, 135, 1300, 884))
	panel(Rect2(1344, 135, 546, 884))
	text("购买 / 我的挂单", Rect2(76, 164, 770, 57), 34, P.GOLD)
	text("物品                                     金币             操作", Rect2(76, 238, 1140, 50), 24, P.MUTED)
	var scroll := _scroll(Rect2(68, 316, 1210, 635))
	var list := VBoxContainer.new()
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(list)
	for listing in host.listings:
		var row := HBoxContainer.new()
		list.add_child(row)
		var name: Label = host._label(row, "装备 " + str(listing.equipmentId).left(8), 26)
		name.custom_minimum_size.x = 660
		host._label(row, "%s" % listing.priceGold, 30, P.GOLD).custom_minimum_size.x = 240
		if listing.sellerId == Game.lobby.get("player", {}).get("userId", ""):
			host._button(row, "下架", func(): host._mutate("/market/listings/" + listing.listingId, HTTPClient.METHOD_DELETE), Game.busy)
		else:
			host._button(row, "购买", func(): host._confirm("花费 %s 金币购买此装备？" % listing.priceGold, func(): host._mutate("/market/" + listing.listingId + "/purchase?expectedVersion=" + str(int(listing.version)), HTTPClient.METHOD_POST)), Game.busy or int(listing.priceGold) > int(Game.lobby.get("wallet", {}).get("gold", 0)))
	if list.get_child_count() == 0: text("集市暂时没有挂单", Rect2(356, 453, 730, 100), 32, P.MUTED)
	text("本次上架", Rect2(1390, 175, 440, 67), 34, P.GOLD)
	var choices := OptionButton.new()
	choices.add_item("选择仓库装备")
	var items: Array = []
	for item in host.inventory.get("equipments", []):
		if item.get("isBound", false) or item.get("location") != "Inventory": continue
		items.append(item)
		choices.add_item(host._equipment_name(item))
		if item.instanceId == host._market_item: choices.selected = items.size()
	if not items.any(func(item): return item.instanceId == host._market_item): host._market_item = ""
	choices.item_selected.connect(func(index): host._market_item = items[index - 1].instanceId if index > 0 else ""; host._render())
	add_child(choices)
	choices.position = Vector2(1385, 320)
	choices.size = Vector2(460, 66)
	text("上架单价", Rect2(1390, 449, 440, 50), 27)
	var price := SpinBox.new()
	price.min_value = 1
	price.max_value = 100000000
	price.value = host._market_price
	price.value_changed.connect(func(value): host._market_price = int(value))
	add_child(price)
	price.position = Vector2(1385, 515)
	price.size = Vector2(460, 72)
	text("手续费 10%（至少 1 金币）\n上架上限 8 件 · 最长 48 小时", Rect2(1390, 643, 455, 121), 25, P.MUTED)
	button("上架物品", Rect2(1400, 868, 435, 88), func():
		var selected_id: String = host._market_item
		var price_gold: int = host._market_price
		host._confirm("确认以 %s 金币上架？" % price_gold, func(): host._mutate("/market/listings", HTTPClient.METHOD_POST, {"equipmentId": selected_id, "priceGold": price_gold})), Game.busy or host._market_item.is_empty(), ORANGE)

func _ready_prompt() -> void:
	panel(Rect2(520, 245, 880, 600))
	text("旅人集结", Rect2(725, 312, 600, 90), 54, P.GOLD)
	text("已确认 %s / %s" % [Game.ready_prompt.get("ready_players", 0), Game.ready_prompt.get("required_players", 1)], Rect2(720, 455, 600, 80), 36)
	var deadline: float = float(Game.ready_prompt.get("deadline_unix_ms", 0)) / 1000.0
	var remaining := text("", Rect2(720, 552, 600, 60), 28, P.TEAL)
	var update_time: Callable = func(): remaining.text = "确认剩余 %s 秒" % maxi(0, int(deadline - Time.get_unix_time_from_system()))
	update_time.call()
	var timer := Timer.new()
	timer.wait_time = 0.25
	timer.timeout.connect(update_time)
	add_child(timer)
	timer.start()
	button("准备就绪", Rect2(690, 668, 540, 100), func(): Game.gateway.send("room.ready"), not Game.gateway.online, ORANGE)
