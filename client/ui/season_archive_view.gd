extends RefCounted

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const Model = preload("res://ui/season_archive_model.gd")
const Details = preload("res://ui/equipment_details.gd")
const Dates = preload("res://ui/season_activity_model.gd")
const Display = preload("res://ui/season_journey_model.gd")
const BLUE := "UI/CardCodex/card_codex_action_button_blue.png"
const ORANGE := "UI/CardCodex/card_codex_action_button_orange.png"

static func _label(host: Control, parent: Node, value: String, font_size: int = 24, color: Color = P.PAPER) -> Label:
	return host._label(parent, Display.display_text(value), font_size, color, false)

static func _column(ui: Control, rect: Rect2, name: String) -> VBoxContainer:
	var panel := PanelContainer.new()
	panel.name = name
	panel.position = rect.position
	panel.size = rect.size
	panel.add_theme_stylebox_override("panel", P.box(Color("10272e"), P.GOLD, 1))
	ui.add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 24)
	panel.add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 12)
	margin.add_child(column)
	# Container minima can temporarily include the complete scrolling list.
	panel.minimum_size_changed.connect(func(): panel.set_deferred("size", rect.size))
	return column

static func _scroll(parent: Node, name: String) -> VBoxContainer:
	var scroll := ScrollContainer.new()
	scroll.name = name
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	parent.add_child(scroll)
	var list := VBoxContainer.new()
	list.name = name + "Items"
	list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	list.add_theme_constant_override("separation", 16)
	scroll.add_child(list)
	return list

static func _date(value: Variant) -> String:
	return Dates.date_label(str(value)) if value is String and not str(value).is_empty() else P.localized("archive_unknown")

static func _source_title(row: Dictionary) -> String:
	return P.localized("archive_legacy") if row.get("rulesetId") == "legacy" else str(row.get("seasonId", ""))

static func build(ui: Control, host: Control) -> void:
	var controller = host.archive_controller
	var left := _column(ui, Rect2(56, 136, 450, 886), "ArchiveSourcePanel")
	_label(host, left, P.localized("archive_sources"), 32, P.GOLD)
	_label(host, left, P.localized("archive_readonly_hint"), 24, P.MUTED)
	var sources := _scroll(left, "ArchiveSourcesScroll")
	for row in controller.seasons:
		var caption := _source_title(row) + "\n" + _date(row.get("endsAt"))
		var index: int = controller.seasons.find(row)
		host._button(sources, caption, controller.choose.bind(index), controller.loading, ORANGE if row.get("seasonId") == controller.selected.get("seasonId") else BLUE).set_meta("archive_source", row.seasonId)
	if controller.seasons.is_empty(): _label(host, sources, P.localized("loading" if controller.loading else "archive_empty"), 26, P.MUTED)
	var source_actions := HBoxContainer.new()
	left.add_child(source_actions)
	host._button(source_actions, "‹", controller.reload.bind(maxi(0, controller.list_offset - 20)), controller.loading or controller.list_offset == 0, BLUE).tooltip_text = P.localized("archive_previous")
	host._button(source_actions, "›", controller.reload.bind(int(controller.list_next) if controller.list_next != null else 0), controller.loading or controller.list_next == null, BLUE).tooltip_text = P.localized("archive_next")
	host._button(left, P.localized("refresh"), controller.reload.bind(controller.list_offset), controller.loading, BLUE)
	var right := _column(ui, Rect2(532, 136, 1332, 886), "ArchiveDetailPanel")
	if controller.selected.is_empty():
		_label(host, right, P.localized("archive_select_source"), 32, P.GOLD)
		if controller.failed: _label(host, right, P.localized("archive_load_failed"), 26, P.PAPER)
		return
	var source: Dictionary = controller.selected
	_label(host, right, P.localized("archive_source") % _source_title(source), 32, P.GOLD).name = "ArchiveOriginalSource"
	_label(host, right, _date(source.get("startsAt")) + " — " + _date(source.get("endsAt")), 22, P.MUTED)
	var wallet: Dictionary = source.wallet if source.get("wallet") is Dictionary else {}
	if not wallet.is_empty():
		_label(host, right, P.localized("archive_wallet") % [str(wallet.gold), str(wallet.equipmentFragments)], 26, P.GOLD)
		_label(host, right, P.localized("archive_marks") % [str(wallet.get("challengeMarks", 0)), str(wallet.get("blueprintMarks", 0)), str(wallet.get("orangeBlueprintMarks", 0))], 24)
	_label(host, right, P.localized("archive_status") % P.localized("archive_status_" + str(source.get("status", "Pending")).to_lower()), 24)
	_label(host, right, P.localized("archive_versions") % [source.get("configVersion") if source.get("configVersion") is String else P.localized("archive_unknown"), source.get("statsVersion") if source.get("statsVersion") is String else P.localized("archive_unknown")], 22, P.MUTED)
	var tabs := HBoxContainer.new()
	tabs.add_theme_constant_override("separation", 14)
	right.add_child(tabs)
	for section in Model.SECTIONS:
		var button: Button = host._button(tabs, P.localized("archive_tab_" + section), controller.choose_section.bind(section), controller.loading, ORANGE if controller.section == section else BLUE)
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		button.name = "ArchiveTab_" + section
	var catalog_label := "archive_catalog_loading" if controller.catalog_loading else "archive_catalog_verified" if controller.catalog_ready else "archive_catalog_unavailable"
	_label(host, right, P.localized(catalog_label), 22, P.TEAL if controller.catalog_ready else P.MUTED).name = "ArchiveCatalogStatus"
	var list := _scroll(right, "ArchiveContentScroll")
	if controller.loading: _label(host, list, P.localized("loading"), 28)
	elif controller.failed: _label(host, list, P.localized("archive_load_failed"), 26)
	else:
		var rows := Model.entries(controller.state, controller.section)
		for item in rows: _entry(host, list, item, controller)
		if rows.is_empty(): _label(host, list, P.localized("archive_section_empty"), 26, P.MUTED)
	var actions := HBoxContainer.new()
	actions.add_theme_constant_override("separation", 20)
	right.add_child(actions)
	host._button(actions, "‹", controller.load_page.bind(maxi(0, controller.page_offset - 20)), controller.loading or controller.page_offset == 0, BLUE).tooltip_text = P.localized("archive_previous")
	host._button(actions, "›", controller.load_page.bind(int(controller.page_next) if controller.page_next != null else 0), controller.loading or controller.page_next == null, BLUE).tooltip_text = P.localized("archive_next")
	var refresh: Button = host._button(actions, P.localized("refresh"), controller.load_page.bind(controller.page_offset), controller.loading, BLUE)
	refresh.size_flags_horizontal = Control.SIZE_EXPAND_FILL

static func _entry(host: Control, parent: Node, item: Dictionary, controller: RefCounted) -> void:
	var panel := PanelContainer.new()
	panel.add_theme_stylebox_override("panel", P.box(Color("17343b"), Color("8c6943"), 1))
	parent.add_child(panel)
	var lines := VBoxContainer.new()
	lines.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	lines.add_theme_constant_override("separation", 10)
	panel.add_child(lines)
	match controller.section:
		"equipment":
			_label(host, lines, Details.title(item), 28, P.GOLD)
			_label(host, lines, P.localized("archive_location") % P.localized("archive_location_" + str(item.get("location", ""))), 24)
			if controller.catalog_ready:
				_label(host, lines, Details.description(item, controller.catalog_index), 24)
			else:
				_label(host, lines, P.localized("archive_raw_equipment") % [P.word(item.get("slot")), P.word(item.get("element")), P.word(item.get("effectAffix")), str(item.get("level", 0))], 24)
		"recipes":
			_label(host, lines, P.word(item.get("quality")) + " · " + P.word(item.get("slot")), 28, P.GOLD)
			var secondary_label: String = P.localized("battle_draw_interval_seconds") if item.get("secondaryTrait") == "DrawInterval" else P.localized("force_escape") if item.get("secondaryTrait") == "ForcedEscape" else P.localized("archive_unknown")
			_label(host, lines, P.word(item.get("element")) + " · " + P.word(item.get("effectAffix")) + " · " + secondary_label, 24)
		"wishes":
			_label(host, lines, P.word(item.get("quality")) + " · " + P.word(item.get("slot")) + " · " + P.word(item.get("element")), 28, P.GOLD)
			_label(host, lines, P.localized("archive_wish_counter") % [P.word(item.get("wishedEffect")), str(item.get("failures", 0))], 24)
		"loadouts":
			_label(host, lines, P.localized({"Priest": "class_priest", "Mage": "class_mage", "Guardian": "class_guardian"}.get(str(item.get("heroClass", "")), "archive_unknown")), 28, P.GOLD)
			var names := ["Head", "Chest", "Hands", "Legs", "Feet"]
			var ids: Array = item.get("equipmentIds", [])
			for index in range(5):
				var id: Variant = ids[index] if index < ids.size() else null
				var title := P.localized("not_equipped")
				if id != null:
					title = P.localized("archive_item_unavailable")
					for equipment in controller.state.get("referencedEquipments", []):
						if equipment.get("instanceId") == id: title = Details.title(equipment)
				_label(host, lines, P.word(names[index]) + " · " + title, 24)
