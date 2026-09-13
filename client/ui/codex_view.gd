extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const DragScroll = preload("res://ui/drag_scroll.gd")
const PREFIX := "UI/CardCodex/card_codex_"
const SOULS := ["PriestSoul", "MageSoul", "GuardianSoul", "WarriorSoul"]
const SOUL_NAMES := {"PriestSoul": "牧魂", "MageSoul": "法魂", "GuardianSoul": "盾魂", "WarriorSoul": "勇士之魂"}

static func header(ui: Control, host: Control) -> void:
	ui.panel(Rect2(20, 18, 1880, 82), PREFIX + "title_bar_normal.png")
	ui.button("返回", Rect2(56, 30, 136, 58), host._navigate.bind("hall"), Game.busy).name = "ReturnButton"
	ui.text("卡牌图鉴", Rect2(232, 30, 430, 60), 36, P.GOLD)
	for i in range(SOULS.size()):
		var kind: String = SOULS[i]
		var x := 1010 + i * 218
		ui.picture(ui._item(kind), Rect2(x, 31, 50, 56))
		var value: Label = ui.text(str(host._card_material(kind)), Rect2(x + 68, 41, 135, 40), 25, P.GOLD)
		value.name = "Material_" + kind
		value.mouse_filter = Control.MOUSE_FILTER_PASS
		value.tooltip_text = P.localized_text(SOUL_NAMES[kind])

static func build(ui: Control, host: Control) -> void:
	var search := LineEdit.new()
	search.name = "CodexSearch"
	search.placeholder_text = P.localized_text("搜索卡牌名称或效果")
	search.text = host._search
	var search_style := Art.style(PREFIX + "search_field_normal.png")
	search_style.set_content_margin(SIDE_LEFT, 76)
	search.add_theme_stylebox_override("normal", search_style)
	search.add_theme_stylebox_override("focus", search_style)
	search.add_theme_constant_override("minimum_character_width", 1)
	ui.add_child(search)
	search.position = Vector2(48, 130)
	search.size = Vector2(625, 66)
	ui.button("完成编组" if host.edit_mode else "编辑编组", Rect2(718, 134, 216, 58), func(): host.edit_mode = not host.edit_mode; host._codex_scroll = 0; host._render(), Game.busy).name = "ToggleDeck"
	ui.text("品质：", Rect2(997, 143, 85, 42), 22, P.GOLD)
	var qualities := ["", "White", "Green", "Blue", "Purple", "Orange"]
	for i in range(qualities.size()):
		var quality: String = qualities[i]
		var selected: bool = host._quality == quality
		var key := "filter_button_selected.png" if quality.is_empty() else "filter_button_%s%s.png" % [quality.to_lower(), "_selected" if selected else ""]
		var filter: Button = ui.button("全部" if quality.is_empty() else P.word(quality), Rect2(1090 + i * 132, 132, 116, 62), func(): host._quality = quality; host._codex_scroll = 0; host._render(), false, PREFIX + key)
		filter.name = "Filter_" + ("All" if quality.is_empty() else quality)
	var count: Label = ui.text("", Rect2(48, 208, 1050, 35), 20, P.MUTED)
	count.name = "CollectionCount"
	var scroll := _scroll(ui, Rect2(42, 257, 1342 if host.edit_mode else 1840, 758))
	scroll.name = "CodexScroll"
	scroll.interaction_enabled = host._codex_card.is_empty()
	var grid := GridContainer.new()
	grid.name = "CardGrid"
	grid.columns = 5 if host.edit_mode else 8
	grid.add_theme_constant_override("h_separation", 42 if host.edit_mode else 47)
	grid.add_theme_constant_override("v_separation", 42)
	scroll.add_child(grid)
	_fill_grid(host, grid, scroll, count)
	scroll.set_deferred("scroll_vertical", host._codex_scroll)
	scroll.get_v_scroll_bar().value_changed.connect(func(value): host._codex_scroll = int(value))
	search.text_changed.connect(func(value): host._search = value.strip_edges(); host._codex_scroll = 0; scroll.scroll_vertical = 0; _fill_grid(host, grid, scroll, count))
	ui.text("点击卡牌查看详情 · 按住拖拽或使用滚轮浏览", Rect2(480, 1037, 850, 30), 18, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if host.edit_mode: _deck(ui, host)
	if not host._codex_card.is_empty(): _details(ui, host)

static func _fill_grid(host: Control, grid: GridContainer, scroll: ScrollContainer, count: Label) -> void:
	for child in grid.get_children():
		grid.remove_child(child)
		child.queue_free()
	var collected := 0
	var total := 0
	var shown := 0
	var side: float = 218.0 if host.edit_mode else 184.0
	for id in host.cards:
		var info: Dictionary = host.cards[id]
		if not info.get("is_codex", false): continue
		total += 1
		var owned: Dictionary = host._owned_card(id)
		var copies := int(owned.get("copyCount", 0)) if owned.get("unlocked", false) else 0
		if copies > 0: collected += 1
		if not host._quality.is_empty() and info.get("quality") != host._quality: continue
		if not host._search.is_empty() and not host._search.to_lower() in (id + " " + host._card_text(id)).to_lower(): continue
		var slot := Control.new()
		slot.custom_minimum_size = Vector2(side, side * 376.0 / 218.0)
		slot.mouse_filter = Control.MOUSE_FILTER_PASS
		grid.add_child(slot)
		var node: Button = host._card_button(slot, id, func():
			if scroll.can_activate():
				host._codex_card = id
				host._render(), false, false, {"collection": true, "copy_count": copies})
		node.name = "Card_" + id
		node.size = Vector2(218, 376)
		node.scale = Vector2.ONE * side / 218.0
		node.tooltip_text = P.localized_text(node.tooltip_text + "\n持有 %s · %s" % [copies, "点击分解 / 编组" if copies > 0 else "点击合成"])
		shown += 1
	count.text = P.localized_text("已收集 %s / %s" % [collected, total])
	if shown != total: count.text += P.localized_text("    筛选结果 %s 张" % shown)
	if not host._codex_ready: count.text += P.localized_text("    持有数据未就绪，请重新进入图鉴刷新")
	if shown == 0:
		var empty := Label.new()
		empty.text = P.localized_text("没有符合条件的卡牌")
		empty.custom_minimum_size = Vector2(1000, 180)
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		grid.add_child(empty)

static func _scroll(ui: Control, rect: Rect2) -> ScrollContainer:
	var scroll := DragScroll.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	ui.add_child(scroll)
	scroll.position = rect.position
	scroll.size = rect.size
	var bar := scroll.get_v_scroll_bar()
	bar.custom_minimum_size.x = 18
	for state in ["scroll", "grabber", "grabber_highlight", "grabber_pressed"]:
		var style := Art.style(PREFIX + ("scroll_track_normal.png" if state == "scroll" else "scroll_thumb_normal.png"))
		for side in [SIDE_LEFT, SIDE_RIGHT]:
			style.set_content_margin(side, 0)
			style.set_texture_margin(side, 4)
		bar.add_theme_stylebox_override(state, style)
	return scroll

static func _deck(ui: Control, host: Control) -> void:
	ui.panel(Rect2(1410, 219, 487, 803))
	ui.text("当前编组  %s / 20" % host.deck_draft.size(), Rect2(1450, 244, 410, 60), 30, P.GOLD)
	var scroll := _scroll(ui, Rect2(1435, 324, 430, 570))
	scroll.name = "DeckScroll"
	scroll.interaction_enabled = host._codex_card.is_empty()
	var rows := VBoxContainer.new()
	rows.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	rows.add_theme_constant_override("separation", 6)
	scroll.add_child(rows)
	for i in range(host.deck_draft.size()):
		var id: String = host.deck_draft[i]
		var info: Dictionary = host.cards.get(id, {})
		var row := Button.new()
		row.disabled = Game.busy
		row.text = P.localized_text("%02d  %s    ×" % [i + 1, info.get("name", id)])
		row.alignment = HORIZONTAL_ALIGNMENT_LEFT
		row.custom_minimum_size = Vector2(397, 44)
		row.add_theme_font_size_override("font_size", 22)
		Art.button(row, "UI/Codex/deck_row_%s.png" % str(info.get("quality", "White")).to_lower())
		row.pressed.connect(func():
			if scroll.can_activate(): host.deck_draft.remove_at(i); host._render())
		rows.add_child(row)
	scroll.set_deferred("scroll_vertical", host._codex_deck_scroll)
	scroll.get_v_scroll_bar().value_changed.connect(func(value): host._codex_deck_scroll = int(value))
	ui.button("还原", Rect2(1440, 936, 172, 60), func(): host.deck_draft = Game.deck().get("cardIds", []).duplicate(); host._render(), Game.busy)
	ui.button("保存编组", Rect2(1630, 936, 230, 60), host._save_deck, Game.busy or host.deck_draft.size() != 20, ui.ORANGE)

static func _details(ui: Control, host: Control) -> void:
	var id: String = host._codex_card
	var info: Dictionary = host.cards.get(id, {})
	if info.is_empty(): return
	var entry: Dictionary = host._owned_card(id)
	var copies := int(entry.get("copyCount", 0)) if entry.get("unlocked", false) else 0
	var known: bool = host._codex_ready and entry.has("craftCost") and entry.has("dismantleRefund")
	var owned: bool = copies > 0
	var hero: Variant = info.get("hero_class")
	var kind: String = entry.get("currencyKind", "WarriorSoul" if hero == null else str(hero) + "Soul")
	var material: String = SOUL_NAMES.get(kind, kind)
	var cost := int(entry.get("craftCost", 0))
	var refund := int(entry.get("dismantleRefund", 0))
	var balance: int = host._card_material(kind)
	for control in ui.find_children("*", "Control", true, false):
		control.focus_mode = Control.FOCUS_NONE
	var modal: Control = ui.get_script().new()
	modal.host = host
	modal.name = "CardDetails"
	ui.add_child(modal)
	modal.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	modal.mouse_filter = Control.MOUSE_FILTER_STOP
	modal.focus_mode = Control.FOCUS_ALL
	modal.grab_focus()
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.78)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	shade.mouse_filter = Control.MOUSE_FILTER_STOP
	modal.add_child(shade)
	modal.panel(Rect2(340, 120, 1240, 876)).name = "DetailsPanel"
	modal.text("卡牌详情", Rect2(740, 150, 440, 58), 38).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	modal.button("返回", Rect2(1406, 146, 140, 64), func(): host._codex_card = ""; host._render(), host._codex_mutating).name = "CloseCardDetails"
	var preview: Button = host._card_button(modal, id, func(): pass, false, false, {"preview": true, "level": int(entry.get("level", 0))})
	preview.name = "DetailCard"
	preview.position = Vector2(411, 271) if owned else Vector2(390, 311)
	preview.size = Vector2(218, 376)
	preview.scale = Vector2.ONE * (1.23 if owned else 1.42)
	preview.mouse_filter = Control.MOUSE_FILTER_IGNORE
	preview.focus_mode = Control.FOCUS_NONE
	modal.text(info.get("name", id), Rect2(796, 242, 650, 64), 39)
	_tag(modal, P.word(info.get("quality", "White")) + "色", Rect2(798, 338, 155, 60), "tag_normal.png" if info.get("quality") == "White" else "tag_q_%s.png" % str(info.get("quality")).to_lower())
	_tag(modal, "通用卡" if hero == null else P.word(hero) + "职业卡", Rect2(974, 338, 170, 60), "tag_normal.png" if hero == null else "tag_orange.png")
	var category: String = P.word(info.get("category", "Support"))
	if category == "Assist": category = "辅助"
	var element: String = str(info.get("element")) if info.get("element") != null else "None"
	if category == "伤害": category = P.word(element) + "系伤害" if element != "None" else "直接伤害"
	_tag(modal, category, Rect2(1166, 338, 172, 60), "tag_%s.png" % element.to_lower() if element in ["Earth", "Metal", "Water", "Wood"] else "tag_normal.png")
	modal.text("等级 +%s · 已拥有 ×%s" % [entry.get("level", 0), copies] if owned else "未拥有 · 合成后获得 +0 " + str(info.get("name", id)), Rect2(798, 424, 690, 50), 27)
	var face: PackedStringArray = host._card_text(id, int(entry.get("level", 0))).split("\n\n", true, 1)
	var effect_text: String = face[1] if face.size() > 1 else host._card_text(id)
	if entry.get("currentEffect") is Dictionary: effect_text = "当前：" + host.CardDetails.effect_text(entry.currentEffect)
	if entry.get("nextEffect") is Dictionary: effect_text += "\n下一级：" + host.CardDetails.effect_text(entry.nextEffect)
	modal.text(effect_text, Rect2(798, 485, 690, 174), 23)
	var box := ColorRect.new()
	box.color = Color(0.005, 0.012, 0.013, 0.94)
	box.mouse_filter = Control.MOUSE_FILTER_IGNORE
	modal.add_child(box)
	box.position = Vector2(794, 672)
	box.size = Vector2(650, 168)
	if owned:
		_cost_row(modal, "升级消耗", kind, "%s %s" % [entry.get("upgradeCost", 0), material] if int(entry.get("level", 0)) < 5 else "已达 +5", 687)
		_cost_row(modal, "当前拥有", kind, "%s %s" % [balance, material], 735)
		_cost_row(modal, "分解返还", kind, "%s %s" % [refund, material] if known else "读取中", 783)
	else:
		_cost_row(modal, "合成消耗", kind, "%s %s" % [cost, material] if known else "读取中", 701)
		_cost_row(modal, "当前拥有", kind, "%s %s" % [balance, material], 756)
	var hint := "总投入的 25%，向下取整；优先分解未升级副本" if owned else "合成后可加入编组"
	if owned and not entry.get("canDismantle", false): hint = "已保存编组正在使用，请先调整并保存编组"
	var used_in_draft: bool = owned and host.deck_draft.count(id) >= copies
	if used_in_draft: hint = "当前编组正在使用，请先从编组移除并保存"
	if not known: hint = "暂未取得合成与分解报价，请重新进入图鉴刷新"
	if known and not owned and balance < cost: hint = "%s不足，还需 %s" % [material, cost - balance]
	modal.text(hint, Rect2(782, 845, 680, 45), 18, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var disabled: bool = Game.busy or not known or ((not entry.get("canDismantle", false) or used_in_draft) if owned else balance < cost)
	var title := "分解 ×1  +%s" % refund if owned else "合成 ×1  %s" % cost
	if not known: title = "报价暂不可用"
	if host._codex_mutating: title = "正在处理…"
	var action: Button = modal.button(title, Rect2(828, 902, 594, 72), host._card_action.bind(id, "dismantle" if owned else "craft"), disabled, ui.ORANGE if owned else ui.BLUE)
	action.name = "DismantleCard" if owned else "CraftCard"
	modal.picture(modal._item(kind), Rect2(856, 915, 36, 43))
	if owned:
		var copy_cost: int = int(entry.get("upgradeCopyCost", 0))
		var upgrade_cost: int = int(entry.get("upgradeCost", 0))
		var upgrade_ready: bool = entry.get("canUpgrade", false) and balance >= upgrade_cost and copies - copy_cost >= maxi(1, host.deck_draft.count(id))
		var upgrade_title := "升至 +%s" % (int(entry.get("level", 0)) + 1)
		if int(entry.get("level", 0)) >= 5: upgrade_title = "已达 +5"
		var upgrade: Button = modal.button(upgrade_title, Rect2(400, 795, 315, 67), func():
			host._confirm("消耗 %s %s%s，将此卡升级到 +%s？" % [upgrade_cost, material, "和 1 张额外同名卡" if copy_cost > 0 else "", int(entry.get("level", 0)) + 1], host._card_action.bind(id, "upgrade")), Game.busy or not upgrade_ready)
		upgrade.name = "UpgradeCard"
		upgrade.tooltip_text = P.localized_text("已达最高等级" if int(entry.get("level", 0)) >= 5 else ("需要额外同名卡，并保留各编组所用副本" if copy_cost > 0 else "只消耗魂材料"))
		modal.text("需额外同名卡 ×%s" % copy_cost, Rect2(397, 747, 321, 38), 21, P.MUTED)
	if host.edit_mode and owned:
		var reason := _add_reason(host, id, info, copies)
		var add: Button = modal.button("加入编组" if reason.is_empty() else reason, Rect2(400, 884, 315, 64), func(): host.deck_draft.append(id); host._codex_card = ""; host._render(), Game.busy or not reason.is_empty())
		add.name = "AddCardToDeck"

static func _tag(ui: Control, value: String, rect: Rect2, key: String) -> void:
	ui.panel(rect, PREFIX + key)
	ui.text(value, Rect2(rect.position + Vector2(8, 8), rect.size - Vector2(16, 16)), 21).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

static func _cost_row(ui: Control, label: String, kind: String, value: String, y: float) -> void:
	ui.text(label, Rect2(820, y, 248, 38), 20)
	ui.picture(ui._item(kind), Rect2(1095, y + 1, 30, 36))
	ui.text(value, Rect2(1136, y, 280, 38), 20).horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

static func _add_reason(host: Control, id: String, info: Dictionary, copies: int) -> String:
	if info.get("hero_class") != null and info.hero_class != Game.hero_class: return "仅限%s职业编组" % P.word(info.hero_class)
	if host.deck_draft.size() >= 20: return "编组已满"
	if host.deck_draft.count(id) >= copies: return "可用数量不足"
	if info.get("quality") == "Orange":
		for existing_id in host.deck_draft:
			var existing: Dictionary = host.cards.get(existing_id, {})
			if existing.get("quality") == "Orange" and (existing.get("hero_class") == null) == (info.get("hero_class") == null): return "已达到橙卡携带上限"
	return ""
