extends Control

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const Model = preload("res://ui/inventory_management_model.gd")
const EquipmentDetails = preload("res://ui/equipment_details.gd")

var _host: Control
var _panel: PanelContainer
var _list: VBoxContainer
var _count: Label
var _submit: Button
var _quality := ""
var _protect_samples := true
var _selection := {}

func open(host: Control) -> void:
	_host = host
	name = "InventoryManagement"
	z_index = 4096
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	var shade := ColorRect.new()
	shade.color = Color(0, 0, 0, 0.76)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(shade)
	_panel = PanelContainer.new()
	_panel.name = "InventoryManagementPanel"
	_panel.add_theme_stylebox_override("panel", P.box(Color("10272e"), P.GOLD, 2))
	add_child(_panel)
	_panel.minimum_size_changed.connect(func(): _layout.call_deferred())
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 24)
	_panel.add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 18)
	margin.add_child(column)
	var header := HBoxContainer.new()
	column.add_child(header)
	var title: Label = _host._label(header, P.localized("inventory_manage"), 34, P.GOLD, false)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_host._button(header, P.localized("archive_title"), func():
		var source := _host
		queue_free()
		source._navigate("archive"), Game.busy, "UI/CardCodex/card_codex_action_button_blue.png").name = "SeasonArchiveEntry"
	_host._button(header, P.localized("close"), queue_free)
	_host._label(column, P.localized("inventory_manage_hint"), 24, P.MUTED, false)
	var filters := HBoxContainer.new()
	filters.add_theme_constant_override("separation", 16)
	column.add_child(filters)
	var quality := OptionButton.new()
	quality.name = "InventoryQualityFilter"
	quality.add_item(P.localized("inventory_manage_all"))
	for value in Model.QUALITIES: quality.add_item(P.word(value))
	quality.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	quality.custom_minimum_size.y = 58
	quality.add_theme_font_override("font", P.font("ui"))
	quality.add_theme_font_size_override("font_size", 26)
	quality.get_popup().theme = P.theme()
	P.apply_text_direction(quality)
	quality.item_selected.connect(func(index): _quality = "" if index == 0 else Model.QUALITIES[index - 1]; _rebuild())
	filters.add_child(quality)
	var protect := CheckButton.new()
	protect.name = "InventoryProtectSamples"
	protect.text = P.localized("inventory_manage_protect_samples")
	protect.button_pressed = true
	protect.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	protect.add_theme_font_override("font", P.font_for_text(protect.text, 24))
	protect.add_theme_font_size_override("font_size", 24)
	protect.toggled.connect(func(value): _protect_samples = value; _rebuild())
	P.apply_text_direction(protect)
	filters.add_child(protect)
	var scroll := ScrollContainer.new()
	scroll.name = "InventoryManagementScroll"
	scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	column.add_child(scroll)
	_list = VBoxContainer.new()
	_list.name = "InventoryManagementItems"
	_list.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_list.add_theme_constant_override("separation", 12)
	scroll.add_child(_list)
	_count = _host._label(column, "", 24, P.GOLD, false)
	var footer := HBoxContainer.new()
	footer.add_theme_constant_override("separation", 24)
	column.add_child(footer)
	_host._button(footer, P.localized("cancel"), queue_free)
	_submit = _host._button(footer, P.localized("inventory_manage_discard"), _confirm, true, "UI/CardCodex/card_codex_action_button_orange.png")
	_submit.name = "InventoryDiscardSubmit"
	_submit.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	resized.connect(_layout)
	Game.cache_changed.connect(_cache_changed)
	Game.authentication_required.connect(_authentication_required)
	_layout()
	_rebuild()

func _layout() -> void:
	if not is_instance_valid(_panel): return
	_panel.size = Vector2(minf(1180, size.x - 80), minf(880, size.y - 80))
	_panel.position = (size - _panel.size) / 2.0

func _rebuild() -> void:
	for node in _list.get_children():
		_list.remove_child(node)
		node.queue_free()
	var protected := Model.protected_ids(Game.lobby.get("equippedLoadouts", []), _host.gear_draft)
	var current := {}
	for item in _host.inventory.get("equipments", []): current[str(item.get("instanceId", ""))] = item.get("version", 0)
	for id in _selection.keys():
		if not current.has(id) or current[id] != _selection[id]: _selection.erase(id)
	for item in _host.inventory.get("equipments", []):
		if not Model.blocked_reason(item, _host.inventory, protected).is_empty() or _protect_samples and Model.is_unlearned_sample(item):
			_selection.erase(str(item.get("instanceId", "")))
	for item in Model.sorted_items(_host.inventory.get("equipments", []), _quality):
		var id := str(item.get("instanceId", ""))
		var reason := Model.blocked_reason(item, _host.inventory, protected)
		if reason.is_empty() and _protect_samples and Model.is_unlearned_sample(item): reason = "inventory_manage_sample"
		if not reason.is_empty(): _selection.erase(id)
		var row := HBoxContainer.new()
		row.name = "InventoryManageRow_" + id
		row.add_theme_constant_override("separation", 16)
		_list.add_child(row)
		var check := CheckBox.new()
		check.name = "InventorySelect_" + id
		check.custom_minimum_size = Vector2(52, 80)
		check.disabled = not reason.is_empty() or Game.busy
		check.button_pressed = _selection.has(id)
		check.toggled.connect(func(value):
			if value: _selection[id] = item.get("version", 0)
			else: _selection.erase(id)
			_update_footer())
		row.add_child(check)
		Art.image(row, Art.equipment_texture(item), Vector2(68, 80))
		var lines := VBoxContainer.new()
		lines.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		row.add_child(lines)
		var title: Label = _host._label(lines, EquipmentDetails.title(item), 26, P.MUTED if check.disabled else P.PAPER, false)
		title.name = "InventoryManageItemName"
		_host._label(lines, P.localized(reason) if not reason.is_empty() else P.localized("inventory_manage_ready"), 22, P.MUTED, false)
		row.tooltip_text = EquipmentDetails.description(item, _host.display_catalog_index())
	if _list.get_child_count() == 0: _host._label(_list, P.localized("no_equipment_hint"), 26, P.MUTED, false)
	_update_footer()
	_layout.call_deferred()

func _update_footer() -> void:
	_count.text = P.localized("inventory_manage_selected") % _selection.size()
	_submit.disabled = _selection.is_empty() or Game.busy

func _confirm() -> void:
	var body := Model.request(_host.inventory, Game.lobby.get("equippedLoadouts", []), _host.gear_draft, _selection)
	if body.is_empty():
		_host._toast(P.localized("inventory_manage_changed"))
		Game.refresh_cache("inventory")
		queue_free()
		return
	var generation: int = Game.gateway.session_generation
	var selected := _selection.duplicate(true)
	_host._confirm(P.localized("inventory_manage_confirm") % body.items.size(), func():
		var host := _host
		queue_free()
		if generation != Game.gateway.session_generation: return
		if Model.request(host.inventory, Game.lobby.get("equippedLoadouts", []), host.gear_draft, selected) != body:
			host._toast(P.localized("inventory_manage_changed"))
			Game.refresh_cache("inventory")
			return
		host._mutate("/inventory/discard", HTTPClient.METHOD_POST, body))

func _cache_changed(module: String) -> void:
	if module == "inventory" or module == "equippedLoadouts":
		_rebuild.call_deferred()

func _authentication_required(_reason: String) -> void:
	queue_free()

func _exit_tree() -> void:
	if Game.cache_changed.is_connected(_cache_changed): Game.cache_changed.disconnect(_cache_changed)
	if Game.authentication_required.is_connected(_authentication_required): Game.authentication_required.disconnect(_authentication_required)
