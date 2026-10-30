extends RefCounted

const P = preload("res://ui/palette.gd")
const Model = preload("res://ui/equipment_compare_model.gd")
static func stat_name(key: String) -> String:
	if key == "interval_seconds": return text("interval")
	var language: String = P.language()
	var words: Dictionary = P.language_pack_section("numerical").get("stat_text", {})
	for prefix in ["damage_", "resistance_"]:
		if key.begins_with(prefix): return str(words[prefix.trim_suffix("_")]) % P.word(key.trim_prefix(prefix))
	return str(words.get(key, P.word(key)))

static func text(key: String) -> String:
	var lang: String = P.language()
	var pack := P.language_pack_section("numerical")
	var words: Dictionary = pack.get("text", {})
	var cap_words: Dictionary = pack.get("cap_text", {})
	return str(words.get(key, cap_words.get(key, key)))

# All values are an equipment-only view; temporary acceleration is intentionally excluded.
static func inspect(loadout: Array, hero_class: String) -> Dictionary:
	var raw: Dictionary = Model.aggregate_attributes(loadout)
	var result := {}
	for key in raw:
		var value: float = float(raw[key])
		var effective: float = minf(0.60, value) if str(key).begins_with("resistance_") else value
		result[key] = {"raw":value, "effective":effective, "excess":maxf(0, value - effective)}
	var modifier: float = float(raw.get("draw_interval", 0.0))
	var seconds: float = 4.0 * (1.0 + modifier)
	var effective_seconds: float = clampf(seconds, 1.8, 6.0)
	result["interval_seconds"] = {"raw":seconds, "effective":effective_seconds, "excess":maxf(0.0, effective_seconds - seconds)}
	for kind in Model.AFFIXES:
		var state: Dictionary = Model.set_state(loadout, kind)
		var contributions := {}
		for field in Model.AFFIX_FIELDS[kind]: contributions[field] = 0.0
		for item in loadout:
			var contribution: Dictionary = Model.affix_contributions(item)
			if contribution.kind == kind:
				for field in contributions: contributions[field] += float(contribution.values.get(field, 0.0))
		var multiple: float = float(Model.MULTIPLIERS.get(clampi(int(state.count), 2, 5), 1.0))
		for field in contributions:
			var potential: float = floorf(float(contributions[field]) * 100.0 * multiple) / 100.0
			var effective: float = float(state.values.get(field, 0.0))
			var applicable: bool = field != "bulwark_reduction_percent" or hero_class == "Guardian"
			if not applicable: effective = 0.0
			var status := "NotApplicable" if not applicable else ("Active" if bool(state.active) else "Inactive")
			result[field] = {"raw":potential, "effective":effective, "excess":maxf(0, potential - effective) if applicable and bool(state.active) else 0.0, "active":state.active, "applicable":applicable, "status":status, "inactive_amount":potential if applicable and not bool(state.active) else 0.0, "not_applicable_amount":potential if not applicable else 0.0}
	return result

static func show_compare(host: Control, loadout: Array, selected: Dictionary, upgrade: bool = false) -> void:
	var before: Array = Model.replace_slot(loadout, selected) if upgrade else loadout
	var next: Dictionary = selected.duplicate(true)
	if upgrade:
		var gear: Dictionary = next.get("equipment", next)
		gear["level"] = mini(5, int(gear.get("level", 0)) + 1)
	var after: Array = Model.replace_slot(loadout, next)
	var lines := PackedStringArray([text("upgrade") if upgrade else text("compare"), text("hint"), text("columns"), ""])
	lines.append(text("resistance_stage"))
	lines.append(text("draw_stage"))
	lines.append(text("shield_stage"))
	lines.append("")
	var unsupported := false
	for item in before + after:
		if str(Model.gear(item).get("quality", "")) == "Red": unsupported = true
	if unsupported:
		lines.append(text("unsupported"))
	else:
		var old: Dictionary = inspect(before, Game.hero_class)
		var current: Dictionary = inspect(after, Game.hero_class)
		var keys: Array = old.keys()
		for key in current.keys():
			if key not in keys: keys.append(key)
		keys.sort()
		for key in keys:
			if key == "draw_interval": continue
			var a: Dictionary = old.get(key, {"raw":0.0,"effective":0.0,"excess":0.0})
			var b: Dictionary = current.get(key, {"raw":0.0,"effective":0.0,"excess":0.0})
			if is_zero_approx(float(a.raw)) and is_zero_approx(float(b.raw)): continue
			var scale: float = 1.0 if key == "interval_seconds" else 100.0
			var label: String = stat_name(str(key))
			lines.append("%s\n  %.2f / %.2f / %.2f → %.2f / %.2f / %.2f  (%+.2f)" % [label, float(a.raw)*scale, float(a.effective)*scale, float(a.excess)*scale, float(b.raw)*scale, float(b.effective)*scale, float(b.excess)*scale, (float(b.effective)-float(a.effective))*scale])
			if str(b.get("status", "Active")) == "NotApplicable": lines.append(text("not_applicable"))
			elif str(b.get("status", "Active")) == "Inactive": lines.append(text("inactive_affix"))
	show_lines(host, lines)

static func show_remainder(host: Control) -> void:
	var state: Dictionary = Game.room.get("player", {}).get("numerical_state", {})
	var lines := PackedStringArray([text("weapon") % int(state.get("guardian_remainder_tenths", 0))])
	if state.get("guardian_policy", "CurrentSteps") == "FractionalRemainder":
		var pack := P.language_pack_section("numerical")
		var labels: Dictionary = pack.get("guardian_impact", {})
		for rule in pack.get("guardian_rules", []):
			lines.append(str(rule))
		lines.append("")
		lines.append(labels.title)
		lines.append(labels.columns)
		var current := [1.0, 1.0, 2.0, 2.0, 3.0, 3.0]
		var mean := [1.0, 1.4, 1.8, 2.2, 2.6, 3.0]
		for level in range(6):
			lines.append(labels.row % [level, current[level], mean[level], mean[level] - current[level]])
		lines.append("")
		lines.append(labels.warning)
		lines.append(labels.scope)
	show_lines(host, lines)

static func show_lines(host: Control, lines: PackedStringArray) -> void:
	var dialog := AcceptDialog.new()
	dialog.title = text("title")
	var dialog_theme := P.theme()
	dialog_theme.default_font_size = 26
	dialog_theme.set_stylebox("panel", "AcceptDialog", P.box(Color("10272e"), P.GOLD))
	var window_frame := P.box(Color("10272e"), P.GOLD)
	window_frame.set_expand_margin(SIDE_TOP, 36)
	window_frame.content_margin_top = 36
	dialog_theme.set_stylebox("embedded_border", "Window", window_frame)
	dialog_theme.set_stylebox("embedded_unfocused_border", "Window", window_frame.duplicate())
	dialog_theme.set_font("title_font", "Window", P.font("title"))
	dialog_theme.set_font_size("title_font_size", "Window", 28)
	dialog_theme.set_color("title_color", "Window", P.GOLD)
	dialog.theme = dialog_theme
	var available := host.get_viewport_rect().size
	var popup_size := Vector2i(mini(1320, int(available.x) - 96), mini(860, int(available.y) - 96))
	dialog.min_size = Vector2i(mini(1080, popup_size.x), mini(640, popup_size.y))
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(popup_size.x - 64, popup_size.y - 128)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	var label := Label.new()
	label.text = P.system_display_text("\n".join(lines))
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(label)
	dialog.add_child(scroll)
	host.add_child(dialog)
	dialog.get_ok_button().text = P.localized("confirm")
	dialog.confirmed.connect(dialog.queue_free)
	dialog.canceled.connect(dialog.queue_free)
	dialog.popup_centered(popup_size)
