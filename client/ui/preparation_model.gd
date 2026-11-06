extends RefCounted

const CATALOG = preload("res://data/catalog.json")
const QUALITIES := ["White", "Green", "Blue", "Purple", "Orange", "Red"]

static func tables(index: Dictionary = {}) -> Dictionary:
	return index.get("tables", {}) if not index.is_empty() else CATALOG.data.tables

static func _whole(value: Variant, minimum: int, maximum: int) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) and float(value) == floor(float(value)) and float(value) >= minimum and float(value) <= maximum

static func backpack(tier: String, index: Dictionary = {}) -> Dictionary:
	var matches: Array = []
	for row in tables(index).get("Backpacks", []):
		if row is Dictionary and row.get("id") == tier: matches.append(row)
	if matches.size() != 1: return {}
	var row: Dictionary = matches[0]
	if not _whole(row.get("capacity"), 1, 2147483647) or not _whole(row.get("safe_slots"), 0, int(row.get("capacity", 0))): return {}
	var capacity: int = int(row.get("capacity", 0))
	var safe_count: int = int(row.get("safe_slots", -1))
	if capacity <= 0 or safe_count < 0 or safe_count > capacity: return {}
	return {"capacity": capacity, "safe_count": safe_count, "safe_indexes": range(capacity - safe_count, capacity)}

static func difficulty(tier: int, index: Dictionary = {}) -> Dictionary:
	if tier < 0 or tier > 5: return {}
	var matches: Array = []
	for row in tables(index).get("SeasonDifficulty", []):
		if row is Dictionary and row.get("difficulty_id") == "D%d" % tier: matches.append(row)
	if matches.size() != 1: return {}
	var row: Dictionary = matches[0]
	if not _whole(row.get("entry_quality_cap"), 0, QUALITIES.size() - 1): return {}
	var cap: int = int(row.get("entry_quality_cap", -1))
	if cap < 0 or cap >= QUALITIES.size(): return {}
	return {"tier": tier, "level_cap": tier, "entry_quality": QUALITIES[cap]}

static func borrowed_deck(hero_class: String, index: Dictionary = {}) -> Dictionary:
	var rows: Array = []
	for row in tables(index).get("SeasonBorrowedDecks", []):
		if row is Dictionary and row.get("hero_class") == hero_class:
			if not _whole(row.get("slot_index"), 0, 19): return {}
			rows.append(row)
	if rows.size() != 20: return {}
	rows.sort_custom(func(a, b): return int(a.slot_index) < int(b.slot_index))
	if not rows[0].get("template_id") is String: return {}
	var template: String = str(rows[0].get("template_id", ""))
	var ids: Array[String] = []
	for slot in rows.size():
		if int(rows[slot].get("slot_index", -1)) != slot or str(rows[slot].get("template_id", "")) != template: return {}
		if not rows[slot].get("card_id") is String: return {}
		var id: String = rows[slot].card_id
		if id.is_empty(): return {}
		ids.append(id)
	return {} if template.is_empty() else {"template_id": template, "card_ids": ids}
