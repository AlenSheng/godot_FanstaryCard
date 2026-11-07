extends RefCounted

const SECTIONS := ["equipment", "recipes", "wishes", "loadouts"]

static func summary_valid(value: Variant) -> bool:
	if not value is Dictionary or not value.get("seasonId") is String or str(value.seasonId).is_empty(): return false
	if value.get("rulesetId") not in ["season-v1", "legacy"] or value.get("status") not in ["Pending", "WaitingAssets", "Running", "Completed", "Failed", "Legacy"]: return false
	for key in ["equipmentCount", "recipeCount", "wishCount", "loadoutCount"]:
		if not value.get(key) is int or value[key] < 0: return false
	var wallet: Variant = value.get("wallet")
	if wallet != null:
		if not wallet is Dictionary or wallet.get("seasonId") != value.seasonId: return false
		for key in ["gold", "equipmentFragments", "challengeMarks", "blueprintMarks", "orangeBlueprintMarks", "version"]:
			if not wallet.get(key) is int or wallet[key] < 0: return false
	if value.rulesetId == "legacy":
		return value.get("configVersion") == null and value.get("configSha256") == null and value.get("statsVersion") == null and value.get("startsAt") == null and value.get("endsAt") == null
	return value.get("configVersion") is String and value.get("configSha256") is String and str(value.configSha256).length() == 64 and value.get("statsVersion") is String

static func list_valid(data: Variant, offset: int) -> bool:
	if not data is Dictionary or not data.get("items") is Array or data.items.size() > 50: return false
	var seen := {}
	for item in data.items:
		if not summary_valid(item) or seen.has(item.seasonId): return false
		seen[item.seasonId] = true
	return cursor_valid(data.get("nextOffset"), offset)

static func cursor_valid(value: Variant, offset: int) -> bool:
	return value == null or value is int and value > offset and value <= 1000000

static func section_valid(data: Variant, selected: Dictionary, section: String, offset: int) -> bool:
	if section not in SECTIONS: return false
	if not data is Dictionary or data.get("readOnly") != true or data.get("section") != section or not summary_valid(data.get("season")): return false
	for key in ["seasonId", "rulesetId", "configVersion", "configSha256", "statsVersion"]:
		if data.season.get(key) != selected.get(key): return false
	var fields := {"equipment": "equipments", "recipes": "recipes", "wishes": "wishes", "loadouts": "loadouts"}
	for name in fields.values():
		if not data.get(name) is Array or data[name].size() > 50 or name != fields[section] and not data[name].is_empty(): return false
	for item in data[fields[section]]:
		if not item is Dictionary: return false
		if section in ["equipment", "recipes", "loadouts"] and item.get("seasonId") != selected.seasonId: return false
		if section == "equipment" and item.get("assetScope") not in ["ActiveSeason", "ArchivedSeason"]: return false
	if not data.get("referencedEquipments") is Array or data.referencedEquipments.size() > 15: return false
	if section != "loadouts" and not data.referencedEquipments.is_empty(): return false
	var ids := {}
	for row in data.get("loadouts", []):
		for id in row.get("equipmentIds", []):
			if id != null: ids[str(id)] = true
	for item in data.referencedEquipments:
		if not item is Dictionary or item.get("seasonId") != selected.seasonId or not ids.has(str(item.get("instanceId", ""))): return false
	return cursor_valid(data.get("nextOffset"), offset)

static func entries(state: Dictionary, section: String) -> Array:
	return state.get({"equipment": "equipments", "recipes": "recipes", "wishes": "wishes", "loadouts": "loadouts"}.get(section, ""), [])
