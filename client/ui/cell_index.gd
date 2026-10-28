extends RefCounted

## First cell at each grid position. Map and legal-move rendering share this
## instead of scanning the full list once per tile.
static func by_position(entries: Array) -> Dictionary:
	var indexed := {}
	for entry in entries:
		if not entry is Dictionary: continue
		var key := Vector2i(int(entry.get("row", -1)), int(entry.get("column", -1)))
		if not indexed.has(key): indexed[key] = entry
	return indexed
