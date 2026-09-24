extends RefCounted

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const DragScroll = preload("res://ui/drag_scroll.gd")
const CardGridView = preload("res://ui/card_grid_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
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
		_fill_owned_grid(host, owned_nodes.grid, owned_nodes.scroll, owned_nodes.count)
		host._set_card_page_cache_key("deck"))
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
	var grid := CardGridView.new()
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
	var entries: Array = []
	var owned_entries: Array = host.owned.duplicate()
	owned_entries.sort_custom(func(left, right):
		return CardDetails.card_before(str(left.get("cardId", "")), str(right.get("cardId", "")), host.cards))
	for entry_value in owned_entries:
		var entry: Dictionary = entry_value
		if not entry.get("unlocked", false) or int(entry.get("copyCount", 0)) <= 0: continue
		var id := str(entry.get("cardId", ""))
		var info: Dictionary = host.cards.get(id, {})
		if id.is_empty() or not info.get("is_codex", false): continue
		if not host._quality.is_empty() and str(info.get("quality", "")) != host._quality: continue
		if not host._search.is_empty() and not host._search.to_lower() in (id + " " + host._card_text(id, int(entry.get("level", 0)))).to_lower(): continue
		var reason := _add_reason(host, id, info)
		var in_deck: bool = id in host.deck_draft
		entries.append({"id": id, "slot_name": "OwnedSlot_" + id, "card_name": "DeckCard_" + id,
			"callback": _activate_owned.bind(host, id, scroll), "selected": in_deck, "disabled": Game.busy,
			"options": {"collection": true, "copy_count": int(entry.get("copyCount", 0)), "level": int(entry.get("level", 0))},
			"tooltip": reason if not reason.is_empty() else "加入编组"})
	grid.configure(host, scroll, entries, 236.0)
	count.text = P.localized("owned_cards_count").format({"count": entries.size()})

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
	var done: Button = ui.button(P.localized("finish_deck"), Rect2(1580, 920, 290, 68), host._save_deck, Game.busy, ui.ORANGE)
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
	var name_label: Label = ui.text(CardDetails.localized_name(id, info), Rect2(rect.position + Vector2(28, 1), Vector2(205, rect.size.y - 2)), 18, P.PAPER)
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
	if Game.busy: return
	Game.busy = true
	host._render()
	if not Game.gateway.token.is_empty():
		var generation: int = Game.gateway.session_generation
		var response: Dictionary = await Game.gateway.request("/api/v1/cards", HTTPClient.METHOD_GET, null, [0, 400, 404, 409, 429, 500, 502, 503, 504])
		if not host._session_result_current(generation, response): return
		if not response.ok:
			Game.busy = false
			host._toast(P.localized("auto_build_failed"))
			host._render()
			return
		host.owned = response.data
	# Auto-build is an intentional rebuild. It scores every owned card against the
	# current loadout and class passive, then greedily picks the best legal set.
	# Inventory is loaded here because the deck screen can be opened without ever
	# visiting the equipment screen first.
	var inventory: Dictionary = {}
	if not Game.gateway.token.is_empty():
		var inventory_response: Dictionary = await Game.gateway.request("/api/v1/inventory", HTTPClient.METHOD_GET, null, [0, 404, 409, 429, 500, 502, 503, 504])
		if inventory_response.ok and inventory_response.data is Dictionary: inventory = inventory_response.data
	if inventory.is_empty() and host.get("inventory") is Dictionary: inventory = host.get("inventory")
	var result := _ranked_auto_deck(host, inventory)
	host.deck_draft = result
	if result.size() < DECK_SIZE: host._toast(P.localized("not_enough_deck_cards"))
	Game.busy = false
	host._render()

static func _ranked_auto_deck(host: Control, inventory: Dictionary = {}) -> Array:
	var candidates: Array = []
	var owned_by_id: Dictionary = {}
	for raw in host.owned:
		var entry: Dictionary = raw if raw is Dictionary else {}
		var id := str(entry.get("cardId", ""))
		if id.is_empty() or not entry.get("unlocked", false) or int(entry.get("copyCount", 0)) <= 0: continue
		owned_by_id[id] = entry
	for id in owned_by_id:
		var info: Dictionary = host.cards.get(id, {})
		if not info.get("is_codex", false): continue
		if info.get("hero_class") != null and info.get("hero_class") != Game.hero_class: continue
		candidates.append({"id": id, "info": info, "owned": owned_by_id[id]})
	if candidates.is_empty(): return []
	var preference := _equipment_element_preference(inventory)
	var weapon_level := _class_weapon_level()
	var selected: Array = []
	var element_counts: Dictionary = {}
	var class_count := 0
	var class_quota := mini(7, candidates.filter(func(value): return value.info.get("hero_class") != null).size())
	while selected.size() < DECK_SIZE and not candidates.is_empty():
		var best_index := -1
		var best_score := -INF
		var class_slots_left := class_quota - class_count
		var must_fill_class := class_slots_left > 0 and selected.size() >= DECK_SIZE - class_slots_left
		for index in candidates.size():
			var candidate: Dictionary = candidates[index]
			var info: Dictionary = candidate.info
			var id := str(candidate.id)
			var is_class := info.get("hero_class") != null
			if must_fill_class and not is_class: continue
			var is_general_orange: bool = info.get("quality") == "Orange" and not is_class
			var is_class_orange: bool = info.get("quality") == "Orange" and is_class
			if is_general_orange and _contains_orange_group(host, selected, true): continue
			if is_class_orange and _contains_orange_group(host, selected, false): continue
			var score := _auto_card_score(info, candidate.owned, preference, weapon_level, element_counts, class_count, selected.size())
			# Keep the result deterministic when two cards are otherwise equivalent.
			var wins_tie := best_index < 0 or id < str(candidates[best_index].id)
			if score > best_score or (is_equal_approx(score, best_score) and wins_tie):
				best_score = score
				best_index = index
		if best_index < 0: break
		var chosen: Dictionary = candidates[best_index]
		var chosen_info: Dictionary = chosen.info
		selected.append(str(chosen.id))
		var element := str(chosen_info.get("element", "None"))
		if element != "None" and not element.is_empty(): element_counts[element] = int(element_counts.get(element, 0)) + 1
		if chosen_info.get("hero_class") != null: class_count += 1
		candidates.remove_at(best_index)
	return selected

static func _auto_card_score(info: Dictionary, owned: Dictionary, preference: Dictionary, weapon_level: int, element_counts: Dictionary, class_count: int, selected_count: int) -> float:
	var quality_score := {"White": 0.0, "Green": 8.0, "Blue": 16.0, "Purple": 27.0, "Orange": 40.0}
	var score: float = quality_score.get(str(info.get("quality", "White")), 0.0)
	score += minf(8.0, float(int(owned.get("level", 0))) * 1.5)
	score += minf(4.0, float(int(owned.get("copyCount", 0))) * 0.5)
	var element := str(info.get("element", "None"))
	if preference.has(element): score += float(preference[element])
	var is_class := info.get("hero_class") != null
	if is_class:
		# High weapon levels make the class engine the primary reason to select a
		# class card. At ordinary levels, only cards that fit the current deck get
		# this extra weight, so a good general card can still win the slot.
		score += _class_synergy_score(info, Game.hero_class)
		if weapon_level >= 3: score += 12.0 + float(weapon_level - 2) * 5.0
		else: score += float(weapon_level) * 1.5
	else:
		score += _class_synergy_score(info, Game.hero_class)
	if element != "None" and not element.is_empty():
		var same := int(element_counts.get(element, 0))
		score += minf(12.0, float(same) * (2.5 if int(info.get("same_element_bonus", 0)) > 0 else 1.0))
	if int(info.get("resonance_bonus", 0)) > 0: score += 4.0 + float(element_counts.get(element, 0)) * 1.5
	if int(info.get("immediate_draw", 0)) > 0 or float(info.get("draw_charge", 0)) > 0.0: score += 3.0
	if float(info.get("stun_seconds", 0)) > 0.0: score += 2.5
	if int(info.get("heal", 0)) > 0: score += 2.0 if Game.hero_class == "Priest" else 0.5
	if int(info.get("shield", 0)) > 0: score += 2.0 if Game.hero_class == "Guardian" else 0.5
	# Reserve the early slots for the class engine when enough class cards exist.
	if selected_count < 7 and is_class: score += 14.0
	if selected_count >= 13 and not is_class and class_count < 7: score -= 18.0
	return score

static func _class_synergy_score(info: Dictionary, hero_class: String) -> float:
	var element := str(info.get("element", "None"))
	match hero_class:
		"Mage":
			return (7.0 if element == "Fire" else 0.0) + float(info.get("same_element_bonus", 0)) * 2.0 + float(info.get("resonance_bonus", 0)) * 2.0
		"Priest":
			return (6.0 if int(info.get("heal", 0)) > 0 else 0.0) + (2.0 if float(info.get("stun_seconds", 0)) > 0.0 else 0.0) + (1.5 if int(info.get("immediate_draw", 0)) > 0 else 0.0)
		"Guardian":
			return (7.0 if int(info.get("shield", 0)) > 0 else 0.0) + (3.0 if int(info.get("health_cost", 0)) > 0 else 0.0) + (2.0 if int(info.get("direct_damage", 0)) > 0 else 0.0)
	return 0.0

static func _equipment_element_preference(inventory: Dictionary) -> Dictionary:
	var weights := {"Fire": 0.0, "Wood": 0.0, "Earth": 0.0, "Metal": 0.0, "Water": 0.0}
	var equipped_ids: Array = Game.loadout().get("equipmentIds", [])
	for raw in inventory.get("equipments", []):
		var item: Dictionary = raw if raw is Dictionary else {}
		if item.get("instanceId", null) not in equipped_ids: continue
		var element := str(item.get("element", ""))
		if not weights.has(element): continue
		var quality_weight: float = float({"White": 1.0, "Green": 1.35, "Blue": 1.75, "Purple": 2.2, "Orange": 2.8, "Red": 3.3}.get(str(item.get("quality", "White")), 1.0))
		weights[element] += quality_weight + float(int(item.get("level", 0))) * 0.35
	var preferred := ""
	var top := 0.0
	for element in weights:
		if float(weights[element]) > top: top = float(weights[element]); preferred = element
	if preferred.is_empty(): return weights
	# GDD conflict ring: a preferred element and its opposed element should not
	# dominate the same auto-built deck, while the two adjacent elements remain viable.
	var opposed: String = str({"Wood": "Earth", "Earth": "Water", "Water": "Fire", "Fire": "Metal", "Metal": "Wood"}.get(preferred, ""))
	var attacks_preferred: String = str({"Wood": "Metal", "Earth": "Wood", "Water": "Earth", "Fire": "Water", "Metal": "Fire"}.get(preferred, ""))
	weights[preferred] = float(weights[preferred]) + 8.0
	if not opposed.is_empty(): weights[opposed] = float(weights[opposed]) - 5.0
	if not attacks_preferred.is_empty(): weights[attacks_preferred] = float(weights[attacks_preferred]) - 2.0
	return weights

static func _class_weapon_level() -> int:
	for weapon in Game.lobby.get("classWeapons", []):
		if weapon is Dictionary and str(weapon.get("heroClass", "")) == Game.hero_class: return int(weapon.get("level", 0))
	return 0

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
