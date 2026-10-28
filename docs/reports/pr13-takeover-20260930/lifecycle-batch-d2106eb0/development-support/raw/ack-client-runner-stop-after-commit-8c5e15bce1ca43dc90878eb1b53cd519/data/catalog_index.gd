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

static func cards() -> Dictionary:
	ensure()
	return _cards

static func card_count() -> int:
	ensure()
	return _cards.size()

static func card(id: String) -> Dictionary:
	ensure()
	var found: Variant = _cards.get(id, {})
	return found if found is Dictionary else {}

static func level_count() -> int:
	ensure()
	return _levels.size()

static func card_level(card_id: String, level: int) -> Dictionary:
	ensure()
	var found: Variant = _levels.get("%s:%d" % [card_id, level], {})
	return found if found is Dictionary else {}

static func quality(id: String) -> Dictionary:
	ensure()
	var found: Variant = _qualities.get(id, {})
	return found if found is Dictionary else {}
