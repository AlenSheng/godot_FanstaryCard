extends SceneTree

const P = preload("res://ui/palette.gd")
const CardView = preload("res://ui/card_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")
const BATTLE_LEVELS_WITH_FRAMES := [0, 5, 10]
const BATTLE_FONT_SIZE := 24
const BATTLE_TEXT_WIDTH := 174.0
const BATTLE_TEXT_HEIGHT_BUDGET := 308.0
const BATTLE_BREAK_FLAGS := TextServer.BREAK_MANDATORY | TextServer.BREAK_WORD_BOUND | TextServer.BREAK_ADAPTIVE

func _initialize() -> void:
	call_deferred("_run")

func _run() -> void:
	var game: Variant = root.get_node("Game")
	game.set_process(false)
	game.gateway.reconnect_enabled = false
	game.gateway.set_process(false)
	game.gateway.socket.close()
	var sound: Variant = root.get_node("Sound")
	sound.persist_settings = false
	sound.stop_all()
	var locale := OS.get_environment("FANTASYCARD_REVIEW_LOCALES")
	if locale.is_empty(): locale = "es"
	P.set_language(locale)
	var errors: Array = []
	if P.language() != locale: errors.append({"kind": "unavailable_locale", "locale": locale})
	var phrase := P.localized("word_equipment") + " ×1"
	if P.localized_text("装备 ×1") != phrase or P.localized_text(phrase) != phrase:
		errors.append({"kind": "translation_must_not_cascade", "expected": phrase, "actual": P.localized_text("装备 ×1")})
	var characters := {}
	_collect_characters(P.languages().get(locale, {}).get("strings", {}), characters)
	for section in ["numerical", "card_names", "card_face_names", "equipment_compare", "monster_pool"]:
		_collect_characters(P.language_pack_section(section), characters)
	for codepoint in characters:
		if not P.font("body").has_char(codepoint): errors.append({"kind": "missing_glyph", "codepoint": codepoint})
	var view := CardView.new()
	view.theme = P.theme()
	root.add_child(view)
	view.size = Vector2(218, 376)
	var shop_ui: Variant = load("res://ui/reference_ui.gd").new()
	shop_ui.theme = P.theme()
	var shop_host: Variant = load("res://ui/main.gd").new()
	shop_ui.host = shop_host
	root.add_child(shop_ui)
	var shop_panel := Panel.new()
	shop_ui.add_child(shop_panel)
	var count := 0
	var shop_count := 0
	for id in CatalogIndex.cards():
		var info: Dictionary = CatalogIndex.card(id)
		var effect := CardDetails.face_description(id, 5, info)
		view.configure(id, info, effect, false, {"collection": true, "copy_count": 1, "level": 5})
		await process_frame
		var label: Label = view.get_node_or_null("CardName")
		if label == null: label = view.get_node_or_null("MonsterName")
		if label == null:
			errors.append({"kind": "missing_card_name_control", "id": id})
		else:
			if label.get_visible_line_count() < label.get_line_count():
				errors.append({"kind": "clipped_card_name", "id": id, "text": label.text, "lines": label.get_line_count(), "visible_lines": label.get_visible_line_count()})
			var typeface: Font = label.get_theme_font("font")
			var width := typeface.get_string_size(label.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, label.get_theme_font_size("font_size")).x
			if width > label.size.x + 0.5: errors.append({"kind": "card_name_too_wide", "id": id, "text": label.text, "width": width, "available": label.size.x})
		if effect.is_empty(): errors.append({"kind": "empty_card_effect", "id": id})
		var face_effect: Label = view.get_node_or_null("CardEffect")
		if face_effect != null and face_effect.get_theme_font_size("font_size") < 16:
			errors.append({"kind": "undersized_card_summary", "id": id})
		if view.tooltip_text.is_empty(): errors.append({"kind": "missing_full_card_tooltip", "id": id})
		if id == "M-BOXSPIRIT":
			for element in ["Fire", "None"]:
				var variant: Dictionary = CardDetails.with_element(info, element)
				var expected := CardDetails.face_description(id, 5, variant)
				view.configure(id, variant, "stale-text-sentinel", false, {"level": 5})
				if view.get_node("MonsterEffect").text != expected:
					errors.append({"kind": "stale_monster_effect", "element": element, "expected": expected, "actual": view.get_node("MonsterEffect").text})
		if str(info.get("source", "")) != "Monster":
			for child in shop_panel.get_children(): child.free()
			var image := TextureRect.new()
			shop_panel.add_child(image)
			shop_ui._shop_card_presentation(shop_panel, image, {"cardId": id})
			await process_frame
			var shop_name: Label = shop_panel.get_node("ShopCardName")
			var font: Font = shop_name.get_theme_font("font")
			var text_width := font.get_string_size(shop_name.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, shop_name.get_theme_font_size("font_size")).x
			if text_width > shop_name.size.x + 0.5:
				errors.append({"kind": "shop_card_name_too_wide", "id": id, "text": shop_name.text, "width": text_width, "available": shop_name.size.x})
			shop_count += 1
		count += 1
	view.free()
	shop_ui.free()
	shop_host.free()
	var battle_report: Dictionary = await _check_battle_catalog(locale, errors)
	var regressions := {}
	for filename in ["test_localization.gd", "test_card_localization.gd", "test_card_description_levels.gd", "test_equipment_name.gd", "test_localization_boundaries.gd"]:
		P.set_language("zh-CN")
		var result: Dictionary = load("res://tests/" + filename).new().run_test()
		regressions[filename] = result
		if not result.get("ok", false): errors.append({"kind": "existing_regression", "file": filename, "result": result})
	P.set_language(locale)
	var report := {"ok": errors.is_empty(), "locale": locale, "catalog_cards_checked": count,
		"shop_cards_checked": shop_count, "glyphs_checked": characters.size(), "real_card_controls": true,
		"battle_layout": battle_report, "actual_game_matches": 0, "errors": errors, "regressions": regressions}
	var output := OS.get_environment("FANTASYCARD_LOCALE_PROBE_REPORT")
	if not output.is_empty():
		var file := FileAccess.open(output, FileAccess.WRITE)
		file.store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	P.clear_runtime_fonts()
	quit(0 if report.ok else 1)

func _check_battle_catalog(locale: String, errors: Array) -> Dictionary:
	var started := Time.get_ticks_msec()
	var error_start := errors.size()
	var saved_window_size: Vector2i = root.size
	var saved_scale_size: Vector2i = root.content_scale_size
	var saved_scale_mode: int = root.content_scale_mode
	# This probe runs under the caller's private-desktop guard. Use the actual
	# minimum window and project canvas, rather than labelling 24 design px as
	# readable without checking the effective control transform.
	root.content_scale_size = Vector2i(1920, 1080)
	root.content_scale_mode = Window.CONTENT_SCALE_MODE_CANVAS_ITEMS
	root.size = Vector2i(960, 540)
	await process_frame
	var logical_size := root.get_visible_rect().size
	var pixel_scale := float(root.size.y) / maxf(1.0, logical_size.y)
	if root.size != Vector2i(960, 540) or not logical_size.is_equal_approx(Vector2(1920, 1080)):
		errors.append({"kind": "battle_minimum_window_unavailable", "window": [root.size.x, root.size.y], "logical_viewport": [logical_size.x, logical_size.y]})
	var view := CardView.new()
	view.theme = P.theme()
	view.size = Vector2(218, 376)
	root.add_child(view)
	var font_cases := 0
	var catalog_level_cases := 0
	var box_element_level_cases := 0
	var control_cases := 0
	var mag10_control_cases := 0
	var box_control_cases := 0
	var minimum_effective_font := INF
	var worst_case: Dictionary = {}
	var box_elements: Array[String] = ["Fire", "Wood", "Water", "Metal", "Earth", "None"]
	for id in CatalogIndex.cards():
		var base: Dictionary = CatalogIndex.card(id)
		var variants: Array[Dictionary] = [{"element": "catalog", "info": base}]
		if id == "M-BOXSPIRIT":
			for element in box_elements:
				variants.append({"element": element, "info": CardDetails.with_element(base, element)})
		for variant in variants:
			var info: Dictionary = variant.info
			for level in range(11):
				var context := {"id": id, "level": level, "element": str(variant.element)}
				var face_name := CardDetails.localized_face_name(id, info)
				var effect := CardDetails.face_description(id, level, info)
				var summary := P.localized_text(effect.replace(P.localized("card_face_separator"), "\n"))
				var title_font := P.scaled_font("title")
				var effect_font := P.font_for_text(summary, BATTLE_FONT_SIZE, true)
				# Font measurements cover all 0..10 numeric/duration growth. The
				# separate framed cases below inspect native Label layout as well.
				var title_height := ceilf(title_font.get_multiline_string_size(P.localized_text(face_name), HORIZONTAL_ALIGNMENT_CENTER, BATTLE_TEXT_WIDTH, BATTLE_FONT_SIZE, -1, BATTLE_BREAK_FLAGS).y)
				var effect_height := ceilf(effect_font.get_multiline_string_size(summary, HORIZONTAL_ALIGNMENT_CENTER, BATTLE_TEXT_WIDTH, BATTLE_FONT_SIZE, -1, BATTLE_BREAK_FLAGS).y)
				var required := title_height + effect_height + 22.0
				if required > BATTLE_TEXT_HEIGHT_BUDGET + 0.5:
					errors.append(context.merged({"kind": "battle_font_measurement_exceeds_card", "required_height": required, "budget": BATTLE_TEXT_HEIGHT_BUDGET, "name": face_name, "summary": summary}))
				if effect.is_empty(): errors.append(context.merged({"kind": "battle_empty_summary"}))
				if required > float(worst_case.get("required_height", 0.0)):
					worst_case = context.merged({"required_height": required, "title_height": title_height, "effect_height": effect_height, "name": face_name, "summary": summary})
				font_cases += 1
				if variant.element == "catalog": catalog_level_cases += 1
				else: box_element_level_cases += 1
				if level not in BATTLE_LEVELS_WITH_FRAMES: continue
				var full_name := CardDetails.localized_name(id, info)
				var full_effect := CardDetails.effect_text(CardDetails.at_level(info, level))
				var tooltip_source := full_name + "\n\n" + full_effect
				var expected_tooltip := P.localized_text(tooltip_source)
				view.configure(id, info, tooltip_source, level == 5, {"battle_layout": true, "battle_font_size": BATTLE_FONT_SIZE, "level": level, "selected_overlay": true})
				await process_frame
				var observed: Dictionary = _check_battle_controls(view, context, face_name, summary, full_name, expected_tooltip, pixel_scale, errors)
				minimum_effective_font = minf(minimum_effective_font, float(observed.get("minimum_effective_font", INF)))
				control_cases += 1
				if id == "MAG-10": mag10_control_cases += 1
				if id == "M-BOXSPIRIT" and variant.element != "catalog": box_control_cases += 1
	view.free()
	root.content_scale_size = saved_scale_size
	root.content_scale_mode = saved_scale_mode
	root.size = saved_window_size
	await process_frame
	return {"ok": errors.size() == error_start, "locale": locale,
		"catalog_cards": CatalogIndex.cards().size(), "levels": [0, 10],
		"catalog_card_level_cases": catalog_level_cases, "box_element_level_cases": box_element_level_cases,
		"font_measurement_cases": font_cases, "native_control_cases": control_cases,
		"native_control_levels": BATTLE_LEVELS_WITH_FRAMES, "mag10_native_control_cases": mag10_control_cases,
		"box_element_native_control_cases": box_control_cases, "box_elements": box_elements,
		"native_window": [960, 540], "logical_viewport": [logical_size.x, logical_size.y], "pixel_scale": pixel_scale,
		"minimum_effective_font_size": minimum_effective_font, "font_size": BATTLE_FONT_SIZE,
		"text_width": BATTLE_TEXT_WIDTH, "text_height_budget": BATTLE_TEXT_HEIGHT_BUDGET, "worst_case": worst_case,
		"seconds": float(Time.get_ticks_msec() - started) / 1000.0,
		"scope": "All registered catalog cards at levels 0..10 use real Godot Font shaping. Levels 0/5/10 additionally use real CardView/Label controls after a process frame at actual 960x540 canvas stretching, including all six Box Spirit elements. No screenshot, five-card hand composition, real-match, or whole-language acceptance claim."}

func _check_battle_controls(view: Control, context: Dictionary, expected_name: String, expected_summary: String, full_name: String, expected_tooltip: String, pixel_scale: float, errors: Array) -> Dictionary:
	var title := view.get_node_or_null("CardName") as Label
	if title == null: title = view.get_node_or_null("MonsterName") as Label
	var summary := view.get_node_or_null("CardEffect") as Label
	if summary == null: summary = view.get_node_or_null("MonsterEffect") as Label
	var panel := view.get_node_or_null("BattleTextPanel") as Control
	if title == null or summary == null or panel == null:
		errors.append(context.merged({"kind": "battle_missing_native_controls", "title": title != null, "summary": summary != null, "panel": panel != null}))
		return {}
	for artwork_name in ["Illustration", "MonsterBackdrop", "SelectedIllustrationOverlay"]:
		var artwork := view.get_node_or_null(artwork_name) as Control
		if artwork == null: continue
		if not artwork.get_rect().is_equal_approx(Rect2(14, 14, 190, 285)):
			errors.append(context.merged({"kind": "battle_original_artwork_bounds_changed", "artwork": artwork_name, "rect": _rect_values(artwork.get_rect())}))
		if panel.get_index() <= artwork.get_index():
			errors.append(context.merged({"kind": "battle_text_panel_below_artwork", "artwork": artwork_name}))
	if title.text != P.localized_text(expected_name): errors.append(context.merged({"kind": "battle_wrong_card_name", "actual": title.text, "expected": expected_name}))
	if summary.text != expected_summary: errors.append(context.merged({"kind": "battle_stale_or_incomplete_effect", "actual": summary.text, "expected": expected_summary}))
	var minimum_effective_font := INF
	for label in [title, summary]:
		var role := "name" if label == title else "effect"
		var effective_font := float(label.get_theme_font_size("font_size")) * absf(label.get_global_transform().get_scale().y) * pixel_scale
		minimum_effective_font = minf(minimum_effective_font, effective_font)
		if effective_font < 12.0 - 0.001:
			errors.append(context.merged({"kind": "battle_undersized_primary_text", "role": role, "effective_font_size": effective_font}))
		if not label.get_meta("battle_primary_text", false): errors.append(context.merged({"kind": "battle_missing_primary_text_metadata", "role": role}))
		if label.get_line_count() <= 0 or label.get_visible_line_count() < label.get_line_count():
			errors.append(context.merged({"kind": "battle_clipped_primary_text", "role": role, "text": label.text, "lines": label.get_line_count(), "visible_lines": label.get_visible_line_count()}))
		if label.max_lines_visible >= 0 or label.text_overrun_behavior != TextServer.OVERRUN_NO_TRIMMING:
			errors.append(context.merged({"kind": "battle_primary_text_elided", "role": role}))
		if not panel.get_global_rect().grow(0.5).encloses(label.get_global_rect()):
			errors.append(context.merged({"kind": "battle_text_outside_panel", "role": role, "label_rect": _rect_values(label.get_global_rect()), "panel_rect": _rect_values(panel.get_global_rect())}))
	if not view.get_global_rect().grow(0.5).encloses(panel.get_global_rect()):
		errors.append(context.merged({"kind": "battle_panel_outside_card", "panel_rect": _rect_values(panel.get_global_rect()), "card_rect": _rect_values(view.get_global_rect())}))
	var required_height := float(view.get_meta("battle_required_text_height", INF))
	if required_height > BATTLE_TEXT_HEIGHT_BUDGET + 0.5:
		errors.append(context.merged({"kind": "battle_native_text_height_exceeds_budget", "required_height": required_height, "budget": BATTLE_TEXT_HEIGHT_BUDGET}))
	if not view.tooltip_text.begins_with(expected_tooltip) or not view.tooltip_text.contains(full_name):
		errors.append(context.merged({"kind": "battle_full_tooltip_lost", "expected": expected_tooltip, "actual": view.tooltip_text}))
	return {"minimum_effective_font": minimum_effective_font}

func _rect_values(rect: Rect2) -> Array:
	return [rect.position.x, rect.position.y, rect.size.x, rect.size.y]

func _collect_characters(value: Variant, characters: Dictionary) -> void:
	if value is Dictionary:
		for item in value.values(): _collect_characters(item, characters)
	elif value is Array:
		for item in value: _collect_characters(item, characters)
	elif value is String:
		for index in value.length():
			var codepoint: int = value.unicode_at(index)
			if codepoint > 32: characters[codepoint] = true
