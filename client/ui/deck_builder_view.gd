extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const DragScroll = preload("res://ui/drag_scroll.gd")
const PREFIX := "UI/CardCodex/card_codex_"
const ROW_PREFIX := "UI/Codex/deck_row_"
const DECK_SIZE := 20
const QUALITIES := ["", "White", "Green", "Blue", "Purple", "Orange"]

static func build(ui: Control, host: Control) -> void:
	var search := _search_and_filters(ui, host)
	var owned_nodes := _owned_cards(ui, host)
	search.text_changed.connect(func(value):
		host._search = value.strip_edges()
		host._deck_builder_scroll = 0
		owned_nodes.scroll.scroll_vertical = 0
		_fill_owned_grid(host, owned_nodes.grid, owned_nodes.scroll, owned_nodes.count))
	_deck_panel(ui, host)

static func _search_and_filters(ui: Control, host: Control) -> LineEdit:
	var search := LineEdit.new()
	search.name = "DeckBuilderSearch"
	search.placeholder_text = P.localized_text("搜索卡牌名称或效果")
	search.text = host._search
	var search_style := Art.style(PREFIX + "search_field_normal.png")
	search_style.set_content_margin(SIDE_LEFT, 76)
	search.add_theme_stylebox_override("normal", search_style)
	search.add_theme_stylebox_override("focus", search_style)
	search.add_theme_constant_override("minimum_character_width", 1)
	ui.add_child(search)
	search.position = Vector2(48, 130)
	search.size = Vector2(510, 66)
	ui.text("品质：", Rect2(590, 143, 85, 42), 22, P.GOLD)
	for i in range(QUALITIES.size()):
		var quality: String = QUALITIES[i]
		var selected: bool = host._quality == quality
		var key := "filter_button_selected.png" if quality.is_empty() else "filter_button_%s%s.png" % [quality.to_lower(), "_selected" if selected else ""]
		var filter: Button = ui.button("全部" if quality.is_empty() else P.word(quality), Rect2(676 + i * 94, 132, 86, 62), func(): host._quality = quality; host._deck_builder_scroll = 0; host._render(), false, PREFIX + key)
		filter.name = "DeckFilter_" + ("All" if quality.is_empty() else quality)
	return search

static func _owned_cards(ui: Control, host: Control) -> Dictionary:
	var count: Label = ui.text("", Rect2(48, 208, 1110, 35), 20, P.MUTED)
	count.name = "DeckOwnedCount"
	var scroll := _scroll(ui, Rect2(42, 257, 1182, 758))
	scroll.name = "DeckOwnedScroll"
	var grid := GridContainer.new()
	grid.name = "DeckOwnedGrid"
	grid.columns = 4
	grid.add_theme_constant_override("h_separation", 48)
	grid.add_theme_constant_override("v_separation", 42)
	scroll.add_child(grid)
	_fill_owned_grid(host, grid, scroll, count)
	scroll.set_deferred("scroll_vertical", host._deck_builder_scroll)
	scroll.get_v_scroll_bar().value_changed.connect(func(value): host._deck_builder_scroll = int(value))
	return {"grid": grid, "scroll": scroll, "count": count}

static func _fill_owned_grid(host: Control, grid: GridContainer, scroll: ScrollContainer, count: Label) -> void:
	for child in grid.get_children():
		grid.remove_child(child)
		child.queue_free()
	var shown := 0
	var side := 236.0
	for entry_value in host.owned:
		var entry: Dictionary = entry_value
		if not entry.get("unlocked", false) or int(entry.get("copyCount", 0)) <= 0: continue
		var id := str(entry.get("cardId", ""))
		var info: Dictionary = host.cards.get(id, {})
		if id.is_empty() or not info.get("is_codex", false): continue
		if not host._quality.is_empty() and str(info.get("quality", "")) != host._quality: continue
		if not host._search.is_empty() and not host._search.to_lower() in (id + " " + host._card_text(id, int(entry.get("level", 0)))).to_lower(): continue
		var reason := _add_reason(host, id, info)
		var slot := Control.new()
		slot.name = "OwnedSlot_" + id
		slot.custom_minimum_size = Vector2(side, side * 376.0 / 218.0)
		grid.add_child(slot)
		var card: Button = host._card_button(slot, id, _activate_owned.bind(host, id, scroll), false, not reason.is_empty(), {"collection": true, "copy_count": 1, "level": int(entry.get("level", 0))})
		card.name = "DeckCard_" + id
		card.size = Vector2(218, 376)
		card.scale = Vector2.ONE * side / 218.0
		card.tooltip_text = P.localized_text(reason if not reason.is_empty() else "加入编组")
		shown += 1
	count.text = P.localized("owned_cards_count").format({"count": shown})
	if shown == 0:
		var empty := Label.new()
		empty.text = P.localized_text("没有符合条件的卡牌")
		empty.custom_minimum_size = Vector2(1100, 180)
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		grid.add_child(empty)

static func _deck_panel(ui: Control, host: Control) -> void:
	ui.panel(Rect2(1250, 114, 650, 911)).name = "DeckBuilderPanel"
	ui.picture(Art.texture("UI/Codex/deck_title_bar.png"), Rect2(1266, 126, 618, 82)).name = "DeckTitleLayer"
	var title: Label = ui.text(P.localized("current_deck_count").format({"count": host.deck_draft.size(), "total": DECK_SIZE}), Rect2(1300, 142, 550, 48), 30, P.GOLD)
	title.name = "DeckCount"
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var limits := _orange_counts(host)
	var limit_text := P.localized("deck_orange_limits").format({"general": limits.general, "class": limits.class})
	var limit_label: Label = ui.text(limit_text, Rect2(1290, 211, 570, 32), 19, P.MUTED)
	limit_label.name = "DeckOrangeLimits"
	limit_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var rows_rect := Rect2(1280, 251, 590, 642)
	for index in range(DECK_SIZE):
		_deck_row(ui, host, index, Rect2(rows_rect.position + Vector2(0, index * 32), Vector2(rows_rect.size.x, 30)))
	var auto: Button = ui.button(P.localized("auto_build"), Rect2(1280, 920, 270, 68), auto_build.bind(host), Game.busy, ui.BLUE)
	auto.name = "AutoBuildDeck"
	var done: Button = ui.button(P.localized("finish_deck"), Rect2(1580, 920, 290, 68), host._save_deck, Game.busy or host.deck_draft.size() != DECK_SIZE, ui.ORANGE)
	done.name = "SaveDeck"
	done.tooltip_text = P.localized("deck_requires_twenty") if host.deck_draft.size() != DECK_SIZE else P.localized("save_deck")

static func _deck_row(ui: Control, host: Control, index: int, rect: Rect2) -> void:
	var filled: bool = index < host.deck_draft.size()
	var id := str(host.deck_draft[index]) if filled else ""
	var info: Dictionary = host.cards.get(id, {})
	var quality := str(info.get("quality", "White")).to_lower()
	var base := ColorRect.new()
	base.name = "DeckRowBackground_%02d" % (index + 1)
	base.color = Color("19201f") if filled else Color("303334")
	base.mouse_filter = Control.MOUSE_FILTER_IGNORE
	ui.add_child(base)
	base.position = rect.position
	base.size = rect.size
	var row: Button = ui.button("", rect, _remove_card.bind(host, index), Game.busy or not filled, ROW_PREFIX + (quality if filled else "white") + ".png")
	row.name = "DeckSlot_%02d" % (index + 1)
	row.modulate = Color.WHITE if filled else Color(0.48, 0.5, 0.5, 0.72)
	row.tooltip_text = P.localized("remove_from_deck") if filled else P.localized("deck_empty_slot")
	if not filled:
		var empty: Label = ui.text(P.localized("deck_empty_slot"), Rect2(rect.position + Vector2(54, 1), Vector2(rect.size.x - 108, rect.size.y - 2)), 17, Color("929898"))
		empty.name = "DeckEmpty_%02d" % (index + 1)
		empty.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		empty.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		return
	var name_label: Label = ui.text(str(info.get("name", id)), Rect2(rect.position + Vector2(28, 1), Vector2(205, rect.size.y - 2)), 18, P.PAPER)
	name_label.name = "DeckCardName_%02d" % (index + 1)
	name_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	name_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	name_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var effect: String = host.card_description(id, "face")
	if effect.is_empty():
		var parts: PackedStringArray = host._card_text(id).split("\n\n", true, 1)
		effect = parts[1] if parts.size() > 1 else host._card_text(id)
	var effect_label: Label = ui.text(effect.replace("\n", " "), Rect2(rect.position + Vector2(244, 1), Vector2(316, rect.size.y - 2)), 16, P.MUTED)
	effect_label.name = "DeckCardEffect_%02d" % (index + 1)
	effect_label.autowrap_mode = TextServer.AUTOWRAP_OFF
	effect_label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	effect_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	effect_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER

static func _activate_owned(host: Control, id: String, scroll: ScrollContainer) -> void:
	if not scroll.can_activate(): return
	var info: Dictionary = host.cards.get(id, {})
	var reason := _add_reason(host, id, info)
	if not reason.is_empty():
		host._toast(reason)
		return
	host.deck_draft.append(id)
	host._render()

static func _remove_card(host: Control, index: int) -> void:
	if index < 0 or index >= host.deck_draft.size(): return
	host.deck_draft.remove_at(index)
	host._render()

static func _add_reason(host: Control, id: String, info: Dictionary) -> String:
	if info.get("hero_class") != null and info.get("hero_class") != Game.hero_class:
		return P.localized("class_restriction") % P.word(info.get("hero_class"))
	if host.deck_draft.size() >= DECK_SIZE: return P.localized("deck_full")
	if id in host.deck_draft: return P.localized("card_already_in_deck")
	if info.get("quality") == "Orange":
		var is_general: bool = info.get("hero_class") == null
		for existing_id in host.deck_draft:
			var existing: Dictionary = host.cards.get(existing_id, {})
			if existing.get("quality") == "Orange" and (existing.get("hero_class") == null) == is_general:
				return P.localized("orange_limit_reached")
	return ""

static func auto_build(host: Control) -> void:
	var result: Array = []
	for existing_id in host.deck_draft:
		var id := str(existing_id)
		var info: Dictionary = host.cards.get(id, {})
		if id.is_empty() or id in result: continue
		if info.get("hero_class") != null and info.get("hero_class") != Game.hero_class: continue
		if info.get("quality") == "Orange" and _contains_orange_group(host, result, info.get("hero_class") == null): continue
		result.append(id)
		if result.size() >= DECK_SIZE: break
	for entry_value in host.owned:
		if result.size() >= DECK_SIZE: break
		var entry: Dictionary = entry_value
		if not entry.get("unlocked", false) or int(entry.get("copyCount", 0)) <= 0: continue
		var id := str(entry.get("cardId", ""))
		var info: Dictionary = host.cards.get(id, {})
		if id.is_empty() or id in result or not info.get("is_codex", false): continue
		if info.get("hero_class") != null and info.get("hero_class") != Game.hero_class: continue
		if info.get("quality") == "Orange" and _contains_orange_group(host, result, info.get("hero_class") == null): continue
		result.append(id)
	host.deck_draft = result
	if result.size() < DECK_SIZE: host._toast(P.localized("not_enough_deck_cards"))
	host._render()

static func _contains_orange_group(host: Control, ids: Array, general: bool) -> bool:
	for id in ids:
		var info: Dictionary = host.cards.get(id, {})
		if info.get("quality") == "Orange" and (info.get("hero_class") == null) == general: return true
	return false

static func _orange_counts(host: Control) -> Dictionary:
	var result := {"general": 0, "class": 0}
	for id in host.deck_draft:
		var info: Dictionary = host.cards.get(id, {})
		if info.get("quality") != "Orange": continue
		if info.get("hero_class") == null: result.general += 1
		else: result.class += 1
	return result

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
