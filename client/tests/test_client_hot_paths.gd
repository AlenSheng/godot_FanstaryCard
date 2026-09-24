extends RefCounted

func run_test() -> Dictionary:
	var failures: Array[String] = []
	_check_catalog(failures)
	_check_card_levels(failures)
	_check_sort_cache(failures)
	_check_styles(failures)
	_check_owned_index(failures)
	_check_cells(failures)
	_check_preview_relations(failures)
	var timings := _benchmark(failures)
	return {
		"ok": failures.is_empty(),
		"message": "Shared catalog, style, ownership and map indexes stay correct. " + timings if failures.is_empty() else "; ".join(failures),
	}

func _check_catalog(failures: Array[String]) -> void:
	var index = load("res://data/catalog_index.gd")
	var catalog = load("res://data/catalog.json")
	if index.card_count() != catalog.data.tables.Cards.size():
		failures.append("Card index size drifted from the catalog")
	if index.level_count() != catalog.data.tables.CardLevels.size():
		failures.append("Card level index size drifted from the catalog")
	for growth in catalog.data.tables.CardLevels:
		var row: Dictionary = index.card_level(str(growth.card_id), int(growth.level))
		if row.is_empty() or int(row.value_bonus) != int(growth.value_bonus) or not is_equal_approx(float(row.duration_bonus), float(growth.duration_bonus)):
			failures.append("Level index mismatch for %s:%s" % [growth.card_id, growth.level])
			return
	if not index.card_level("C01", 99).is_empty() or not index.card("missing-card").is_empty():
		failures.append("Missing catalog keys must stay empty")
	var blue: Dictionary = index.quality("Blue")
	if blue.is_empty() or not is_equal_approx(float(blue.damage_percent), 0.11) or str(blue.display_color) != "#558CB8":
		failures.append("Equipment quality index lost the Blue row")
	if not index.quality("missing").is_empty():
		failures.append("Missing quality must stay empty")

func _check_card_levels(failures: Array[String]) -> void:
	var details = load("res://ui/card_details.gd")
	var index = load("res://data/catalog_index.gd")
	var source: Dictionary = index.card("C01")
	var before := int(source.elemental_damage)
	var leveled: Dictionary = details.at_level(source, 5)
	var growth: Dictionary = index.card_level("C01", 5)
	if int(source.elemental_damage) != before:
		failures.append("Level lookup mutated the shared catalog row")
	if int(leveled.elemental_damage) != before + int(growth.value_bonus):
		failures.append("Indexed level bonus did not apply to elemental damage")
	var untouched: Dictionary = details.at_level(source, 99)
	if int(untouched.elemental_damage) != before:
		failures.append("Unknown level changed the card")
	var cards: Dictionary = index.cards()
	var first: Array = details.sorted_ids(cards.keys(), cards)
	first.append("extra")
	var second: Array = details.sorted_ids(cards.keys(), cards)
	if second.size() != cards.size() or second.has("extra"):
		failures.append("Cached catalog order must be returned as a copy")

func _check_sort_cache(failures: Array[String]) -> void:
	var details = load("res://ui/card_details.gd")
	var index = load("res://data/catalog_index.gd")
	var cards: Dictionary = index.cards()
	var cached: Array = details.sorted_ids(cards.keys(), cards)
	var custom: Array = details.sorted_ids(["C11", "C01", "C09"], cards)
	var expected: Array = ["C11", "C01", "C09"]
	expected.sort_custom(func(left, right): return details.card_before(str(left), str(right), cards))
	if custom != expected:
		failures.append("Partial card lists must keep the explicit sort")
	if cached.size() != cards.size():
		failures.append("Full catalog sort dropped cards")

func _check_styles(failures: Array[String]) -> void:
	var art = load("res://ui/art.gd")
	var key := "UI/CardCodex/card_codex_dialog_panel_normal.png"
	var margins: Array = art.MANIFEST.data.files[key].border_lbrt
	var first: StyleBoxTexture = art.style(key)
	if first == null or first.get_texture_margin(SIDE_TOP) != float(margins[3]) or first.get_texture_margin(SIDE_BOTTOM) != float(margins[1]):
		failures.append("Cached style lost manifest borders")
		return
	first.set_texture_margin(SIDE_TOP, float(margins[3]) + 9.0)
	first.set_content_margin(SIDE_LEFT, 3.0)
	var second: StyleBoxTexture = art.style(key)
	if second.get_texture_margin(SIDE_TOP) != float(margins[3]) or second.get_content_margin(SIDE_LEFT) != 24.0:
		failures.append("Style mutations leaked into the shared prototype")
	var left := Button.new()
	var right := Button.new()
	art.button(left, key)
	art.button(right, key)
	var shared: StyleBox = art._style_prototype(key, Color.WHITE)
	if not is_same(left.get_theme_stylebox("normal"), shared) or not is_same(right.get_theme_stylebox("normal"), shared):
		failures.append("Buttons with the same art should share one style box")
	left.free()
	right.free()

func _check_owned_index(failures: Array[String]) -> void:
	var ui = load("res://ui/main.gd").new()
	ui.owned = [{"cardId": "C01", "copyCount": 1}, {"cardId": "C02", "copyCount": 2}]
	if int(ui._owned_card("C02").copyCount) != 2 or not ui._owned_card("missing").is_empty():
		failures.append("Owned-card index returned the wrong row")
	ui._owned_card("C01")["copyCount"] = 4
	if int(ui.owned[0].copyCount) != 4:
		failures.append("Owned-card lookup must keep the live row")
	ui._replace_owned_card({"cardId": "C02", "copyCount": 9})
	if int(ui._owned_card("C02").copyCount) != 9:
		failures.append("Replacing an owned card left the index stale")
	ui.owned = [{"cardId": "C03", "copyCount": 1}]
	if not ui._owned_card("C01").is_empty() or int(ui._owned_card("C03").copyCount) != 1:
		failures.append("Replacing the owned array did not refresh the index")
	ui.free()

func _check_cells(failures: Array[String]) -> void:
	var cells = load("res://ui/cell_index.gd")
	var indexed: Dictionary = cells.by_position([
		{"row": 1, "column": 2, "is_boss": false, "label": "first"},
		{"row": 1, "column": 2, "is_boss": true, "label": "second"},
		{"row": 0, "column": 0, "has_spring": true},
	])
	var boss: Dictionary = indexed.get(Vector2i(1, 2), {})
	if str(boss.get("label", "")) != "first" or not indexed.get(Vector2i(0, 0), {}).get("has_spring", false):
		failures.append("Cell index must keep the first occupant of a tile")
	if not indexed.get(Vector2i(3, 3), {}).is_empty():
		failures.append("Missing map tile must stay empty")

func _check_preview_relations(failures: Array[String]) -> void:
	var store = load("res://state/game_store.gd").new()
	if not store._counter("Water", "Fire") or store._counter("Fire", "Water") or not store._conflict_pair("Wood", "Earth") or store._conflict_pair("Wood", "Fire") or store._conflict_pair("Fire", "Fire"):
		failures.append("Element counter or conflict tables changed")
	if store._generated("Earth") != "Metal":
		failures.append("Generated element table changed")
	store.free()

func _benchmark(failures: Array[String]) -> String:
	var index = load("res://data/catalog_index.gd")
	var catalog = load("res://data/catalog.json")
	var cards: Array = catalog.data.tables.Cards
	var repeats := 40
	var sink := 0
	var started := Time.get_ticks_usec()
	for _repeat in repeats:
		for growth in catalog.data.tables.CardLevels:
			for card in cards:
				if str(card.id) == str(growth.card_id):
					sink += int(card.elemental_damage)
					break
	var linear_us := Time.get_ticks_usec() - started
	started = Time.get_ticks_usec()
	for _repeat in repeats:
		for growth in catalog.data.tables.CardLevels:
			sink += int(index.card(str(growth.card_id)).get("elemental_damage", 0))
	var indexed_us := Time.get_ticks_usec() - started
	if indexed_us <= 0 or linear_us < indexed_us * 3:
		failures.append("Card index was not faster than a table scan (%s us vs %s us)" % [indexed_us, linear_us])
	var art = load("res://ui/art.gd")
	var key := "UI/CardCodex/card_codex_action_button_blue.png"
	started = Time.get_ticks_usec()
	for _repeat in 300:
		var built: StyleBoxTexture = art.style(key)
		sink += int(built.get_content_margin(SIDE_LEFT))
	var style_us := Time.get_ticks_usec() - started
	var ui = load("res://ui/main.gd").new()
	var rows: Array = []
	var ids: Array = []
	for card in cards:
		var card_id := str(card.id)
		rows.append({"cardId": card_id, "copyCount": 1})
		ids.append(card_id)
	ui.owned = rows
	started = Time.get_ticks_usec()
	for _repeat in 20:
		for card_id in ids:
			sink += int(ui._owned_card(card_id).get("copyCount", 0))
	var owned_us := Time.get_ticks_usec() - started
	started = Time.get_ticks_usec()
	for _repeat in 20:
		for card_id in ids:
			for entry in rows:
				if str(entry.get("cardId", "")) == card_id:
					sink += int(entry.get("copyCount", 0))
					break
	var owned_linear_us := Time.get_ticks_usec() - started
	ui.free()
	if owned_us <= 0 or owned_linear_us < owned_us * 3:
		failures.append("Owned-card index was not faster than a row scan (%s us vs %s us)" % [owned_us, owned_linear_us])
	return "card lookup %s us indexed vs %s us scanned; owned cards %s us indexed vs %s us scanned; 300 styles %s us; sink %s" % [indexed_us, linear_us, owned_us, owned_linear_us, style_us, sink]
