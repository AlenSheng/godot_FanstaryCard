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

static func equipment_rules(stats_version: String, index: Dictionary = {}) -> Dictionary:
	if stats_version.is_empty(): return {}
	var tables: Dictionary = index.get("tables", {}) if not index.is_empty() else CATALOG.data.tables
	for row in tables.get("SeasonEquipmentRules", []):
		if str(row.get("stats_version", "")) == stats_version: return row
	return {}

static func reward_refresh_gold(refresh_index: int, index: Dictionary = {}) -> int:
	if refresh_index < 1 or refresh_index > 3: return -1
	var tables: Dictionary = index.get("tables", {}) if not index.is_empty() else CATALOG.data.tables
	var price := -1
	for row in tables.get("LootRules", []):
		if not row is Dictionary or row.get("refresh_index") != refresh_index: continue
		if price != -1: return -1
		var value: Variant = row.get("refresh_gold")
		if typeof(value) not in [TYPE_INT, TYPE_FLOAT]: return -1
		if not is_finite(float(value)) or float(value) != floor(float(value)) or float(value) <= 0 or float(value) > 2147483647: return -1
		price = int(value)
	return price

static func quality(id: String, index: Dictionary = {}, stats_version: String = "") -> Dictionary:
	ensure()
	var source: Dictionary = index.get("qualities", {}) if not index.is_empty() else _qualities
	var found: Variant = source.get(id, {})
	if not found is Dictionary or found.is_empty(): return {}
	if stats_version.is_empty(): return found
	var tables: Dictionary = index.get("tables", {}) if not index.is_empty() else CATALOG.data.tables
	if not tables.has("SeasonEquipmentRules"): return found # Explicit pre-C05 archive policy.
	if equipment_rules(stats_version, index).is_empty(): return {}
	for row in tables.get("SeasonEquipment", []):
		if str(row.get("quality_id", "")).to_lower() != id.to_lower() or str(row.get("stats_version", "")) != stats_version: continue
		var resolved: Dictionary = found.duplicate(true)
		resolved["damage_percent"] = float(row.damage_base)
		resolved["resistance_percent"] = float(row.resist_base)
		resolved["damage_per_level"] = float(row.damage_per_level)
		resolved["resistance_per_level"] = float(row.resist_per_level)
		resolved["draw_interval_percent"] = -float(row.speed_base)
		resolved["draw_interval_per_level"] = -float(row.speed_per_level)
		resolved["stats_version"] = stats_version
		return resolved
	return {}
