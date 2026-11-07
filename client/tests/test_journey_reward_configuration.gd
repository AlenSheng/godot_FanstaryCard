extends RefCounted

const Bundle = preload("res://data/config_bundle.gd")
const Http = preload("res://network/http_protocol.gd")
const COSMETICS := ["trail-seeker", "relic-seeker", "first-threshold", "waymark-seal", "veil-warden", "veilbound-seal", "fivefold-chronicle", "convergent-sigil", "veil-cartographer", "relicbound-pathfinder"]

func run_test() -> Dictionary:
	var checks := {}
	var cases: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/refresh-config/cases.json"))
	var formal := {}
	for entry in cases:
		if str(entry.name) == "formal14":
			formal = entry
	checks["actual C# formal14 input exists"] = not formal.is_empty()
	if formal.is_empty():
		return {"ok": false, "checks": checks}
	var wire := FileAccess.get_file_as_bytes("res://tests/refresh-config/formal14.envelope")
	var response := Http.decode_response(Http.route("/api/v1/config/" + str(formal.version), HTTPClient.METHOD_GET), 200, PackedStringArray(["Content-Type: application/protobuf"]), wire)
	checks["actual typed HTTP response decodes"] = response.ok
	if not response.ok:
		return {"ok": false, "checks": checks}
	var reader := Bundle.new()
	var data: Dictionary = reader.decode(response.data.bundle, str(formal.version), str(formal.hash))
	checks["formal14 binary hash and version verified"] = not data.is_empty() and reader.error.is_empty()
	if data.is_empty():
		return {"ok": false, "checks": checks}
	checks["32 public tables"] = data.tables.size() == 32
	checks["server quota and activity policy remain private"] = not data.tables.has("SeasonRedRules") and not data.tables.has("SeasonActivityRules")
	var rewards: Array = data.tables.get("SeasonJourneyRewards", [])
	var cosmetics: Array = data.tables.get("SeasonCosmetics", [])
	checks["30 reward levels"] = rewards.size() == 30
	checks["10 cosmetics"] = cosmetics.size() == 10
	if rewards.size() != 30 or cosmetics.size() != 10:
		return {"ok": false, "checks": checks}
	var totals := {"EquipmentFragments": 0, "WarriorSoul": 0, "ClassSoul": 0, "CardPack": 0, "Cosmetic": 0}
	for index in range(30):
		var level := index + 1
		var row: Dictionary = rewards[index]
		var expected := ["Cosmetic", 1]
		if level <= 20:
			match level % 5:
				1, 4: expected = ["EquipmentFragments", 10]
				2: expected = ["WarriorSoul", 6]
				3: expected = ["ClassSoul", 2]
				0: expected = ["CardPack", 1]
		checks["level %d exact identity and amount" % level] = row.level is int and row.amount is int and row.level == level and row.reward_id == "journey-level-%02d" % level and row.kind == expected[0] and row.amount == expected[1]
		checks["level %d original ownership" % level] = row.ownership == ("SeasonalBound" if row.kind == "EquipmentFragments" else "PermanentBound")
		checks["level %d typed class choice" % level] = row.requires_class_choice is bool and row.requires_class_choice == (row.kind == "ClassSoul")
		checks["level %d nullable cosmetic source" % level] = row.cosmetic_id == (null if level <= 20 else COSMETICS[level - 21])
		if totals.has(row.kind):
			totals[row.kind] += int(row.amount)
	checks["separate exact reward budget"] = totals == {"EquipmentFragments": 80, "WarriorSoul": 24, "ClassSoul": 8, "CardPack": 4, "Cosmetic": 10}
	for code in ["zh-CN", "en", "es", "fr", "pt", "id", "hi", "ar", "ru", "ja", "ko"]:
		var pack: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://data/locales/" + code + ".json"))
		var complete := true
		for cosmetic in cosmetics:
			complete = complete and not str(pack.strings.get(cosmetic.name_key, "")).is_empty() and not str(pack.strings.get(cosmetic.description_key, "")).is_empty()
		checks[code + " all names and descriptions are present"] = complete
	var old_bytes := FileAccess.get_file_as_bytes("res://tests/journey-rewards/archive13.bundle")
	var old_hash := FileAccess.get_file_as_string("res://tests/journey-rewards/archive13.sha256").strip_edges()
	var old := reader.decode(old_bytes, "season-v1-config-13", old_hash)
	checks["archive13 verifies independently"] = not old.is_empty() and old.version == "season-v1-config-13"
	checks["archive13 never inherits current rewards"] = not old.is_empty() and not old.tables.has("SeasonJourneyRewards") and not old.tables.has("SeasonCosmetics")
	var damaged: PackedByteArray = response.data.bundle.duplicate()
	damaged[damaged.size() - 1] ^= 1
	checks["damaged reward package is rejected"] = reader.decode(damaged, str(formal.version), str(formal.hash)).is_empty()
	checks["wrong original version is rejected"] = reader.decode(response.data.bundle, "season-v1-config-13", str(formal.hash)).is_empty()
	checks["wrong original hash is rejected"] = reader.decode(response.data.bundle, str(formal.version), old_hash).is_empty()
	return {"ok": not checks.values().has(false), "checks": checks, "fixture_only": true, "actual_game_matches": 0, "rendered_frames": false}
