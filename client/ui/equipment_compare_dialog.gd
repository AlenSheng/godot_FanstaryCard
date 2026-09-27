extends Control

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
const EquipmentDetails = preload("res://ui/equipment_details.gd")
const CompareModel = preload("res://ui/equipment_compare_model.gd")
const ItemVisual = preload("res://ui/item_visual.gd")
const COPY = preload("res://data/equipment_compare_text.json")

const POSITIVE := Color("62dc83")
const NEGATIVE := Color("ef5c5c")
const PANEL := Color("07191f")
const SUBPANEL := Color("0b252d")

var _selected: Dictionary
var _current: Dictionary
var _loadout: Array
var _action: Callable
var _action_title := ""
var _busy := false

func open(selected: Dictionary, current: Dictionary, loadout: Array, action: Callable = Callable(), action_title: String = "", busy: bool = false) -> void:
	_selected = selected
	_current = current
	_loadout = loadout
	_action = action
	_action_title = action_title
	_busy = busy
	name = "EquipmentComparisonDialog"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 500
	_build()

func _build() -> void:
	var dimmer := ColorRect.new()
	dimmer.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	dimmer.color = Color(0.0, 0.02, 0.025, 0.68)
	dimmer.mouse_filter = Control.MOUSE_FILTER_STOP
	add_child(dimmer)

	var shell := PanelContainer.new()
	shell.name = "ComparisonShell"
	shell.set_anchors_preset(Control.PRESET_CENTER)
	shell.position = Vector2(-590, -500)
	shell.size = Vector2(1180, 1000)
	shell.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	add_child(shell)

	var margin := MarginContainer.new()
	for side in ["left", "right"]: margin.add_theme_constant_override("margin_" + side, 34)
	for side in ["top", "bottom"]: margin.add_theme_constant_override("margin_" + side, 28)
	shell.add_child(margin)
	var body := VBoxContainer.new()
	body.add_theme_constant_override("separation", 10)
	margin.add_child(body)

	_build_title(body)
	var item_row := HBoxContainer.new()
	item_row.add_theme_constant_override("separation", 18)
	body.add_child(item_row)
	_item_card(item_row, _current, _t("current"), true)
	_item_card(item_row, _selected, _t("selected"), false)

	_section_title(body, _t("attributes"))
	var attributes := HBoxContainer.new()
	attributes.add_theme_constant_override("separation", 14)
	body.add_child(attributes)
	_attribute_card(attributes, _current, _t("current_attributes"), _t("removed"), NEGATIVE)
	var exchange := _label(attributes, "⇄", 34, P.GOLD)
	exchange.custom_minimum_size.x = 48
	exchange.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	exchange.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	_attribute_card(attributes, _selected, _t("selected_attributes"), _t("gained"), POSITIVE)

	_section_title(body, _t("affix"))
	var affixes := HBoxContainer.new()
	affixes.add_theme_constant_override("separation", 14)
	body.add_child(affixes)
	_affix_card(affixes, _current, NEGATIVE)
	_affix_card(affixes, _selected, POSITIVE)

	_section_title(body, _t("set_changes"))
	var before := _loadout
	var after := CompareModel.replace_slot(_loadout, _selected)
	var changes := CompareModel.changed_sets(before, after)
	var set_row := HBoxContainer.new()
	set_row.add_theme_constant_override("separation", 12)
	body.add_child(set_row)
	if changes.is_empty():
		var unchanged := _panel(set_row, SUBPANEL)
		_label(unchanged, "—", 22, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	else:
		for change in changes: _set_card(set_row, change)

	var spacer := Control.new()
	spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	body.add_child(spacer)
	_build_actions(body)
	var hint := _label(body, _t("empty_hint"), 17, P.MUTED)
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

func _build_title(parent: Node) -> void:
	var bar := PanelContainer.new()
	bar.custom_minimum_size.y = 70
	bar.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_title_bar_normal.png"))
	parent.add_child(bar)
	var row := HBoxContainer.new()
	bar.add_child(row)
	var title := _label(row, _t("title"), 34, P.GOLD, "title")
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

func _item_card(parent: Node, item: Dictionary, heading: String, is_current: bool) -> void:
	var panel := _panel(parent, SUBPANEL)
	panel.get_parent().size_flags_stretch_ratio = 1.0
	var heading_label := _label(panel, heading, 22, P.GOLD, "title")
	heading_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 14)
	panel.add_child(row)
	if item.is_empty():
		var empty_visual := Control.new()
		empty_visual.custom_minimum_size = Vector2(140, 140)
		row.add_child(empty_visual)
		var empty := _label(row, _t("empty"), 24, P.MUTED)
		empty.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
		return
	ItemVisual.equipment(row, item, Vector2(140, 140))
	var gear := CompareModel.gear(item)
	var info := VBoxContainer.new()
	info.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	info.add_theme_constant_override("separation", 8)
	row.add_child(info)
	var quality := str(gear.get("quality", "White")).capitalize()
	_label(info, _item_title(item), 25, Art.quality_color(quality), "title")
	_badge(info, P.word(quality), Art.quality_color(quality))
	var affix := str(gear.get("effect_affix", gear.get("effectAffix", "")))
	if affix not in ["", "<null>"]: _badge(info, P.word(affix), P.TEAL)
	if bool(gear.get("is_bound", gear.get("isBound", false))): _label(info, P.localized("bound_unlisted"), 16, P.MUTED)
	if is_current: panel.get_parent().tooltip_text = _t("removed")

func _attribute_card(parent: Node, item: Dictionary, heading: String, footer: String, footer_color: Color) -> void:
	var panel := _panel(parent, PANEL)
	panel.get_parent().size_flags_stretch_ratio = 1.0
	var title := _label(panel, heading, 20, P.PAPER, "title")
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	if item.is_empty():
		_label(panel, _t("empty"), 19, P.MUTED)
	else:
		for entry in CompareModel.attribute_rows(item):
			var line := HBoxContainer.new()
			panel.add_child(line)
			var text := _label(line, _attribute_name(entry), 19, P.PAPER)
			text.size_flags_horizontal = Control.SIZE_EXPAND_FILL
			var value := _label(line, _signed_percent(float(entry.value)), 20, P.ELEMENT.get(entry.element, P.PAPER), "number")
			value.custom_minimum_size.x = 110
			value.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	var footer_label := _label(panel, footer, 18, footer_color)
	footer_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER

func _affix_card(parent: Node, item: Dictionary, tint: Color) -> void:
	var panel := _panel(parent, PANEL)
	panel.get_parent().size_flags_stretch_ratio = 1.0
	var contribution := CompareModel.affix_contributions(item)
	if contribution.kind.is_empty():
		_label(panel, "—", 20, P.MUTED).horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		return
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 10)
	panel.add_child(row)
	var icon := Art.image(row, Art.texture(_affix_icon(contribution.kind)), Vector2(42, 42))
	icon.modulate = tint.lightened(0.12)
	var name_label := _label(row, P.word(contribution.kind) + "：", 20, Art.quality_color(CompareModel.gear(item).get("quality", "White")), "title")
	name_label.custom_minimum_size.x = 90
	name_label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var description := _label(row, _affix_text(contribution), 19, tint)
	description.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	description.vertical_alignment = VERTICAL_ALIGNMENT_CENTER

func _set_card(parent: Node, change: Dictionary) -> void:
	var panel := _panel(parent, PANEL)
	panel.get_parent().size_flags_stretch_ratio = 1.0
	var before: Dictionary = change.before
	var after: Dictionary = change.after
	var title_row := HBoxContainer.new()
	panel.add_child(title_row)
	var icon := Art.image(title_row, Art.texture(_affix_icon(change.kind)), Vector2(40, 40))
	icon.modulate = P.GOLD
	var title := _label(title_row, P.word(change.kind), 21, P.GOLD, "title")
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	var status := _label(title_row, "%s/%s %s  →  %s/%s %s" % [before.count, before.required, _t("active") if before.active else _t("inactive"), after.count, after.required, _t("active") if after.active else _t("inactive")], 17, POSITIVE if after.active else NEGATIVE)
	status.custom_minimum_size.x = 310
	status.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	for field in CompareModel.AFFIX_FIELDS[change.kind]:
		var old_value := float(before.values.get(field, 0.0))
		var new_value := float(after.values.get(field, 0.0))
		var difference := new_value - old_value
		var color := POSITIVE if difference > 0.0001 else (NEGATIVE if difference < -0.0001 else P.MUTED)
		var suffix := " · " + _t("guardian_only") if field == "bulwark_reduction_percent" else ""
		var line := "%s %s → %s   %s%s" % [_field_name(field), _percent(old_value), _percent(new_value), _signed_percent(difference), suffix]
		_label(panel, line, 17, color)
	if bool(after.has_high_quality) and int(after.required) == 2:
		var hint := _label(panel, _t("high_quality_hint"), 15, P.MUTED)
		hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT

func _build_actions(parent: Node) -> void:
	var row := HBoxContainer.new()
	row.alignment = BoxContainer.ALIGNMENT_CENTER
	row.add_theme_constant_override("separation", 24)
	parent.add_child(row)
	if _action.is_valid():
		var confirm := Button.new()
		confirm.name = "ConfirmEquip"
		confirm.text = _action_title if not _action_title.is_empty() else _t("confirm")
		confirm.disabled = _busy
		confirm.custom_minimum_size = Vector2(300, 62)
		confirm.pressed.connect(_confirm)
		Art.button(confirm, "UI/CardCodex/card_codex_action_button_orange.png")
		row.add_child(confirm)
		P.fit_control_font(confirm, P.font_for_text(confirm.text, 24), 24, 48.0)
	var cancel := Button.new()
	cancel.name = "CancelEquip"
	cancel.text = _t("cancel")
	cancel.custom_minimum_size = Vector2(220, 62)
	cancel.pressed.connect(queue_free)
	Art.button(cancel, "UI/CardCodex/card_codex_action_button_blue.png")
	row.add_child(cancel)
	P.fit_control_font(cancel, P.font_for_text(cancel.text, 24), 24, 48.0)

func _confirm() -> void:
	var action := _action
	queue_free()
	if action.is_valid(): action.call()

func _panel(parent: Node, color: Color) -> VBoxContainer:
	var container := PanelContainer.new()
	container.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var style := StyleBoxFlat.new()
	style.bg_color = color
	style.border_color = Color("8a7145")
	for side in [SIDE_LEFT, SIDE_TOP, SIDE_RIGHT, SIDE_BOTTOM]:
		style.set_border_width(side, 1)
		style.set_content_margin(side, 12)
	for corner in [CORNER_TOP_LEFT, CORNER_TOP_RIGHT, CORNER_BOTTOM_LEFT, CORNER_BOTTOM_RIGHT]: style.set_corner_radius(corner, 4)
	container.add_theme_stylebox_override("panel", style)
	parent.add_child(container)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 5)
	container.add_child(column)
	return column

func _section_title(parent: Node, text: String) -> void:
	var label := _label(parent, text, 22, P.GOLD, "title")
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.custom_minimum_size.y = 30

func _label(parent: Node, text: String, size: int, color: Color, role: String = "body") -> Label:
	var label := Label.new()
	label.text = text
	label.add_theme_font_override("font", P.font(role))
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	label.autowrap_mode = TextServer.AUTOWRAP_OFF
	label.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	label.custom_minimum_size.y = ceilf(float(size) * 1.4)
	parent.add_child(label)
	return label

func _badge(parent: Node, text: String, tint: Color) -> void:
	var badge := Label.new()
	badge.text = text
	badge.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	badge.custom_minimum_size = Vector2(94, 30)
	badge.add_theme_font_override("font", P.font())
	badge.add_theme_font_size_override("font_size", 17)
	badge.add_theme_color_override("font_color", tint.lightened(0.25))
	var style := StyleBoxFlat.new()
	style.bg_color = tint.darkened(0.68)
	style.border_color = tint
	style.set_border_width_all(1)
	style.set_corner_radius_all(10)
	badge.add_theme_stylebox_override("normal", style)
	parent.add_child(badge)

func _attribute_name(entry: Dictionary) -> String:
	match entry.kind:
		"damage": return _t("damage") % P.word(entry.element)
		"resistance": return _t("resistance") % P.word(entry.element)
		"draw_interval": return _t("draw_interval")
		"forced_escape": return _t("forced_escape")
	return str(entry.kind)

func _item_title(item: Dictionary) -> String:
	return EquipmentDetails.title(item)

func _affix_text(contribution: Dictionary) -> String:
	var values: Dictionary = contribution.values
	match contribution.kind:
		"Piercing": return "%s %s" % [_t("piercing"), _signed_percent(float(values.piercing_percent))]
		"Bulwark": return "%s %s · %s %s（%s）" % [_t("shield"), _signed_percent(float(values.bulwark_shield_percent)), _t("reduction"), _signed_percent(float(values.bulwark_reduction_percent)), _t("guardian_only")]
		"Vitality": return "%s %s · %s %s" % [_t("healing"), _signed_percent(float(values.vitality_heal_percent)), _t("overcap"), _signed_percent(float(values.vitality_overcap_percent))]
	return "—"

func _field_name(field: String) -> String:
	return {"piercing_percent": _t("piercing"), "bulwark_shield_percent": _t("shield"), "bulwark_reduction_percent": _t("reduction"), "vitality_heal_percent": _t("healing"), "vitality_overcap_percent": _t("overcap")}.get(field, field)

func _affix_icon(kind: String) -> String:
	return {"Piercing": "UI/Prep/exploration_prep_attribute_icon_break.png", "Bulwark": "UI/Prep/exploration_prep_attribute_icon_bulwark.png", "Vitality": "UI/Prep/exploration_prep_attribute_icon_regen.png"}.get(kind, "")

func _percent(value: float) -> String:
	return EquipmentDetails.percent(value) + "%"

func _signed_percent(value: float) -> String:
	if absf(value) < 0.0001: return "0%"
	return ("+" if value > 0.0 else "") + _percent(value)

func _t(key: String) -> String:
	var language := P.language()
	var table: Dictionary = COPY.data.get(language, COPY.data.get("zh-CN", {}))
	return str(table.get(key, key))

func _unhandled_key_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		queue_free()
