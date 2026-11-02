extends RefCounted

const CATALOG = preload("res://data/catalog.json")

static var _cards: Dictionary = {}
static var _levels: Dictionary = {}
static var _qualities: Dictionary = {}
static var _built := false

static func ensure() -> void:
	if _built: return
	_built = true
	for card in CATALOG.data.tables.Cards:
		_cards[str(card.id)] = card
	for growth in CATALOG.data.tables.CardLevels:
		_levels["%s:%d" % [str(growth.card_id), int(growth.level)]] = growth
	for row in CATALOG.data.tables.EquipmentQuality:
		_qualities[str(row.id)] = row

static func from_data(data: Dictionary) -> Dictionary:
	var tables: Dictionary = data.get("tables", {})
	var index := {"version": str(data.get("version", "")), "content_hash": str(data.get("content_hash", "")), "cards": {}, "levels": {}, "qualities": {}, "tables": tables}
	if index.version.is_empty(): return {}
	for table in ["Cards", "CardLevels", "EquipmentQuality"]:
		if not tables.get(table) is Array or tables[table].is_empty(): return {}
	for row in tables.Cards:
		if not row is Dictionary or not row.get("id") is String or str(row.id).is_empty() or index.cards.has(row.id): return {}
		index.cards[row.id] = row
	for row in tables.CardLevels:
		if not row is Dictionary or not row.get("card_id") is String or not row.has("level"): return {}
		var key := "%s:%d" % [str(row.card_id), int(row.level)]
		if index.levels.has(key): return {}
		index.levels[key] = row
	for row in tables.EquipmentQuality:
		if not row is Dictionary or not row.get("id") is String or index.qualities.has(row.id): return {}
		index.qualities[row.id] = row
	return index

static func cards(index: Dictionary = {}) -> Dictionary:
	if not index.is_empty(): return index.get("cards", {})
	ensure()
	return _cards

static func card_count() -> int:
	ensure()
	return _cards.size()

static func card(id: String, index: Dictionary = {}) -> Dictionary:
	if not index.is_empty(): return index.get("cards", {}).get(id, {})
	ensure()
	var found: Variant = _cards.get(id, {})
	return found if found is Dictionary else {}

static func level_count() -> int:
	ensure()
	return _levels.size()

static func card_level(card_id: String, level: int, index: Dictionary = {}) -> Dictionary:
	if not index.is_empty(): return index.get("levels", {}).get("%s:%d" % [card_id, level], {})
	ensure()
	var found: Variant = _levels.get("%s:%d" % [card_id, level], {})
	return found if found is Dictionary else {}

static func quality(id: String, index: Dictionary = {}) -> Dictionary:
	if not index.is_empty(): return index.get("qualities", {}).get(id, {})
	ensure()
	var found: Variant = _qualities.get(id, {})
	return found if found is Dictionary else {}
