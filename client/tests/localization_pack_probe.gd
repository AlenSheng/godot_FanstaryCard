extends SceneTree

const P = preload("res://ui/palette.gd")
const CardView = preload("res://ui/card_view.gd")
const CardDetails = preload("res://ui/card_details.gd")
const CatalogIndex = preload("res://data/catalog_index.gd")

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
	var regressions := {}
	for filename in ["test_localization.gd", "test_card_localization.gd", "test_card_description_levels.gd", "test_equipment_name.gd", "test_localization_boundaries.gd"]:
		P.set_language("zh-CN")
		var result: Dictionary = load("res://tests/" + filename).new().run_test()
		regressions[filename] = result
		if not result.get("ok", false): errors.append({"kind": "existing_regression", "file": filename, "result": result})
	P.set_language(locale)
	var report := {"ok": errors.is_empty(), "locale": locale, "catalog_cards_checked": count,
		"shop_cards_checked": shop_count, "glyphs_checked": characters.size(), "real_card_controls": true, "actual_game_matches": 0, "errors": errors, "regressions": regressions}
	var output := OS.get_environment("FANTASYCARD_LOCALE_PROBE_REPORT")
	if not output.is_empty():
		var file := FileAccess.open(output, FileAccess.WRITE)
		file.store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	P.clear_runtime_fonts()
	quit(0 if report.ok else 1)

func _collect_characters(value: Variant, characters: Dictionary) -> void:
	if value is Dictionary:
		for item in value.values(): _collect_characters(item, characters)
	elif value is Array:
		for item in value: _collect_characters(item, characters)
	elif value is String:
		for index in value.length():
			var codepoint: int = value.unicode_at(index)
			if codepoint > 32: characters[codepoint] = true
