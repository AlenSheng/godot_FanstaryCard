extends RefCounted

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const Details = preload("res://ui/equipment_details.gd")
const Slot = preload("res://ui/inventory_slot.gd")
const ItemVisual = preload("res://ui/item_visual.gd")
const CELL := Art.COMMON_CELL_KEY

static func open(host: Control, pile_id: String = "") -> void:
	host.set_meta("inventory_open", true)
	host.set_meta("relic_pile", pile_id)
	host.set_meta("inventory_selected", "")
	host.set_meta("relic_selected", "")
	if not pile_id.is_empty(): Game.command("relic.read", {"pile_id": pile_id})
	host._schedule_render()

static func build(ui: Control, host: Control, state: Dictionary) -> void:
	var player: Dictionary = state.get("player", {})
	var items: Array = player.get("inventory", [])
	var capacity: int = int(player.get("inventory_capacity", 0))
	var safe_slots: Array = player.get("safe_slot_indexes", [])
	var pile_id: String = host.get_meta("relic_pile", "")
	var selected: Dictionary = find_item(items, host.get_meta("inventory_selected", ""))
	ui.text(P.localized("relic_search") if not pile_id.is_empty() else P.localized("explore_bag"), Rect2(90, 45, 710, 85), 44, P.GOLD)
	ui.panel(Rect2(75, 145, 845, 800))
	ui.panel(Rect2(955, 145, 900, 800))
	ui.text(P.localized("inventory_bag_summary") % [items.size(), capacity, safe_slots.size()], Rect2(999, 193, 790, 50), 31, P.GOLD)
	ui.text(P.localized("drag_inventory_hint"), Rect2(999, 247, 790, 36), 22, P.MUTED)
	var safe_slot_lookup: Dictionary = {}
	var slot_order: Array = []
	for value in safe_slots:
		var safe_index := int(value)
		if safe_index >= 0 and safe_index < capacity and not safe_slot_lookup.has(safe_index):
			safe_slot_lookup[safe_index] = true
			slot_order.append(safe_index)
	for slot_index in range(capacity):
		if not safe_slot_lookup.has(slot_index): slot_order.append(slot_index)
	var row_count := int(ceil(float(capacity) / 6.0))
	var slots_scroll: ScrollContainer = ui._scroll(Rect2(999, 294, 640, 384))
	slots_scroll.name = "InventorySlotsScroll"
	var slots_grid := Control.new()
	slots_grid.name = "InventorySlotsContent"
	slots_grid.custom_minimum_size = Vector2(616, maxi(0, row_count * 104 - Art.COMMON_CELL_GAP))
	slots_grid.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slots_grid.mouse_filter = Control.MOUSE_FILTER_PASS
	slots_scroll.add_child(slots_grid)
	for display_index in range(capacity):
		var slot_index: int = int(slot_order[display_index])
		var is_safe: bool = safe_slot_lookup.has(slot_index)
		var item: Dictionary = {}
		for candidate in items:
			if int(candidate.get("slot_index", -1)) == slot_index: item = candidate; break
		var slot := Slot.new()
		slot.name = "InventorySlot_%s" % slot_index
		slot.slot_index = slot_index
		slot.item_id = item.get("item_id", "")
		slot.position = Vector2((display_index % 6) * 104, int(display_index / 6) * 104)
		slot.size = Art.COMMON_CELL_DISPLAY_SIZE
		slot.custom_minimum_size = Art.COMMON_CELL_DISPLAY_SIZE
		slot.clip_contents = true
		var marker_text := "" if is_safe else str(slot_index + 1)
		slot.text = marker_text
		slot.add_theme_font_size_override("font_size", 16)
		slot.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		slot.tooltip_text = P.localized_text((P.localized("ui_safe_slot_prefix") if is_safe else "") + (Details.description(item) if not item.is_empty() else P.localized("empty_slot")))
		if not is_safe: Art.button(slot, CELL)
		if not item.is_empty():
			# All occupied slots use the configured quality background and frame.
			slot.text = ""
			var item_visual := ItemVisual.item(slot, item, Art.COMMON_CELL_DISPLAY_SIZE)
			item_visual.position = Vector2.ZERO
			item_visual.size = Art.COMMON_CELL_DISPLAY_SIZE
			if not is_safe:
				var marker := Label.new()
				marker.name = "SlotMarker"
				marker.text = marker_text
				marker.position = Vector2(6, 5)
				marker.size = Vector2(84, 22)
				marker.horizontal_alignment = HORIZONTAL_ALIGNMENT_LEFT
				marker.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
				marker.add_theme_font_override("font", P.font_for_text(marker.text, 16))
				marker.add_theme_font_size_override("font_size", 16)
				marker.add_theme_color_override("font_color", P.MUTED)
				marker.mouse_filter = Control.MOUSE_FILTER_IGNORE
				slot.add_child(marker)
		if is_safe: Art.apply_safe_slot_button(slot)
		if is_safe: slot.add_theme_color_override("font_color", P.GOLD)
		if item.get("item_id", "") == selected.get("item_id", "unused"):
			slot.add_theme_stylebox_override("normal", P.box(Color("29474a"), P.GOLD, 2))
		slot.pressed.connect(func():
			if not selected.is_empty() and selected.get("item_id", "") != item.get("item_id", ""):
				Game.command("inventory.move", {"item_id": selected.item_id, "target_slot_index": slot_index})
				host.set_meta("inventory_selected", "")
			else: host.set_meta("inventory_selected", "" if not selected.is_empty() else item.get("item_id", ""))
			host._schedule_render())
		slots_grid.add_child(slot)
	if pile_id.is_empty(): _equipment(ui, host, player, selected)
	else: _relic(ui, host, state, pile_id, selected)
	ui.button(P.localized("back"), Rect2(80, 983, 245, 58), func(): host.set_meta("inventory_open", false); host._schedule_render())
	ui.text(P.localized("safe_slot_hint"), Rect2(990, 704, 800, 60), 23, P.MUTED)

static func _equipment(ui: Control, host: Control, player: Dictionary, selected: Dictionary) -> void:
	ui.text(P.localized("equipped"), Rect2(115, 174, 690, 48), 32, P.GOLD)
	var worn: Array = player.get("equipped_items", [])
	for index in range(5):
		var slot: String = ["Head", "Chest", "Hands", "Legs", "Feet"][index]
		var item: Dictionary = {}
		for candidate in worn:
			if candidate.get("equipment") is Dictionary and candidate.equipment.get("slot", "") == slot: item = candidate; break
		var button: Button = ui.button(P.word(slot) + " · " + (Details.title(item) if not item.is_empty() else P.localized("not_equipped")), Rect2(112, 235 + index * 69, 586, 60), func(): host._confirm(P.localized("unequip_confirm"), func(): Game.command("inventory.unequip", {"slot": slot})), item.is_empty() or not Game.allowed("inventory.unequip"))
		button.add_theme_font_size_override("font_size", 24)
		button.tooltip_text = P.localized_text(Details.description(item) if not item.is_empty() else P.localized("not_equipped"))
	ui.text("%s +%s · %s" % [P.localized("signature_weapon"), player.get("weapon_level", 0), P.localized("locked")], Rect2(118, 598, 740, 44), 27, P.TEAL)
	if selected.is_empty():
		ui.text(P.localized("inventory_detail_hint"), Rect2(118, 670, 736, 102), 27, P.PAPER)
	else:
		_description(ui, host, selected, Rect2(118, 656, 730, 185))
		if selected.get("kind", "") == "Equipment":
			ui.button(P.localized("compare_equip"), Rect2(119, 850, 550, 62), func(): host._show_equipment_details(selected, func(): Game.command("inventory.equip", {"item_id": selected.item_id}), P.localized("equip_replace")), not Game.allowed("inventory.equip"))
		elif selected.get("kind", "") == "HealthPotion":
			ui.button(P.localized("use_health_potion"), Rect2(119, 850, 550, 62), func(): Game.command("action.potion"), not Game.allowed("action.potion"))

static func _relic(ui: Control, host: Control, state: Dictionary, pile_id: String, selected: Dictionary) -> void:
	var summary: Dictionary = {}
	for candidate in state.get("current_cell", {}).get("relic_piles", []):
		if candidate.get("pile_id", "") == pile_id: summary = candidate; break
	if summary.is_empty():
		ui.text(P.localized("relic_unavailable"), Rect2(117, 235, 725, 130), 30, P.MUTED)
		return
	ui.text(str(summary.get("owner_name", P.localized("traveler_default_name"))) + P.localized("relic_owner_suffix"), Rect2(115, 172, 730, 58), 31, P.GOLD, null, true, false)
	var pile: Dictionary = Game.relic_details.get(pile_id, {})
	var fresh: bool = not pile.is_empty() and int(pile.get("version", 0)) == int(summary.get("version", 0))
	ui.button(P.localized("refresh_relic"), Rect2(620, 236, 232, 53), func(): Game.command("relic.read", {"pile_id": pile_id}), not Game.allowed("relic.read"))
	if not fresh:
		ui.text(P.localized("relic_changed"), Rect2(115, 317, 730, 82), 27, P.MUTED)
		return
	var scroll: ScrollContainer = ui._scroll(Rect2(112, 312, 744, 364))
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(column)
	for item in pile.get("items", []):
		var button := Button.new()
		button.text = P.localized_text(Details.title(item) + " ×%s" % item.get("quantity", 1))
		button.tooltip_text = Details.description(item)
		button.custom_minimum_size.y = 63
		button.add_theme_font_size_override("font_size", 25)
		Art.button(button, "UI/CardCodex/card_codex_action_button_blue.png")
		button.pressed.connect(func(): host.set_meta("relic_selected", item.item_id); host._schedule_render())
		column.add_child(button)
	var item: Dictionary = find_item(pile.get("items", []), host.get_meta("relic_selected", ""))
	if item.is_empty(): return
	_description(ui, host, item, Rect2(117, 682, 727, 147))
	if item.get("kind", "") == "Equipment":
		ui.button(P.localized("compare_equipment_action"), Rect2(115, 236, 250, 53), func(): host._show_equipment_details(item))
	var fits: bool = can_add(state.player, item)
	var ready: bool = fits or not selected.is_empty()
	var action: String = "relic.take" if fits else "relic.replace"
	ui.button(P.localized("take") if fits else (P.localized("replace_then_take") if ready else P.localized("select_item_to_return")), Rect2(118, 847, 738, 63), func():
		var payload := {"pile_id": pile_id, "item_id": item.item_id, "pile_version": pile.version}
		if not fits: payload.replace_item_id = selected.item_id
		Game.command(action, payload), not ready or not Game.allowed(action))

static func _description(ui: Control, host: Control, item: Dictionary, rect: Rect2) -> void:
	var scroll: ScrollContainer = ui._scroll(rect)
	var label := Label.new()
	label.text = P.localized_text(Details.description(item))
	label.add_theme_font_override("font", P.font_for_text(label.text, 21))
	label.add_theme_font_size_override("font_size", 21)
	label.add_theme_color_override("font_color", P.PAPER)
	label.custom_minimum_size.x = rect.size.x - 28
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	scroll.add_child(label)
	var positions: Dictionary = host.get_meta("item_detail_scroll", {})
	var id: String = item.get("item_id", "")
	scroll.set_deferred("scroll_vertical", int(positions.get(id, 0)))
	scroll.get_v_scroll_bar().value_changed.connect(func(value): positions[id] = int(value); host.set_meta("item_detail_scroll", positions))

static func find_item(items: Array, id: String) -> Dictionary:
	for item in items:
		if item.get("item_id", "") == id: return item
	return {}

static func can_add(player: Dictionary, item: Dictionary) -> bool:
	var items: Array = player.get("inventory", [])
	if items.size() < int(player.get("inventory_capacity", 0)): return true
	if item.get("kind", "") not in ["Equipment", "HealthPotion"]:
		for current in items:
			if current.get("kind") == item.get("kind") and current.get("item_id") == item.get("item_id"): return true
	return false
