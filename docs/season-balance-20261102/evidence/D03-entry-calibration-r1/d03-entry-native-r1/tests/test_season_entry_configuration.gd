extends RefCounted

const Bundle = preload("res://data/config_bundle.gd")
const Http = preload("res://network/http_protocol.gd")

func run_test() -> Dictionary:
	var checks := {}
	var cases: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/monster-config/cases.json"))
	var visible := {}
	for entry in cases:
		var name := str(entry.name)
		var raw := FileAccess.get_file_as_bytes("res://tests/monster-config/" + name + ".envelope")
		var route := Http.route("/api/v1/config/" + str(entry.version), HTTPClient.METHOD_GET)
		var response := Http.decode_response(route, 200, PackedStringArray(["Content-Type: application/protobuf"]), raw)
		checks[name + " typed response"] = response.ok and response.data.bundle is PackedByteArray
		if not response.ok:
			continue
		var reader := Bundle.new()
		var decoded := reader.decode(response.data.bundle, str(entry.version), str(entry.hash))
		checks[name + " complete hash verified"] = not decoded.is_empty() and reader.error.is_empty()
		if decoded.is_empty():
			continue
		visible[name] = decoded.tables
		checks[name + " public count"] = decoded.tables.size() == 32
		checks[name + " tuning stays server only"] = not decoded.tables.has("SeasonMonsterTuning")
		var changed: PackedByteArray = response.data.bundle.duplicate()
		changed[changed.size() - 1] ^= 1
		checks[name + " corruption rejected"] = reader.decode(changed, str(entry.version), str(entry.hash)).is_empty()
		checks[name + " wrong version rejected"] = reader.decode(response.data.bundle, "wrong-version", str(entry.hash)).is_empty()
	checks["both actual versions"] = visible.has("old15") and visible.has("current16")
	if checks["both actual versions"]:
		var old_tables: Dictionary = visible.old15
		var current_tables: Dictionary = visible.current16
		var expected := old_tables.duplicate(true)
		checks["old D0 retained"] = expected.SeasonDifficulty[0].hp_scale == 1.0 and expected.SeasonDifficulty[0].shield_scale == 1.0
		expected.SeasonDifficulty[0].hp_scale = 0.5
		expected.SeasonDifficulty[0].shield_scale = 0.5
		checks["only D0 hp shield changed"] = expected == current_tables
		checks["six difficulty rows retained"] = current_tables.SeasonDifficulty.size() == 6
		checks["cards and growth retained"] = current_tables.Cards.size() == 232 and current_tables.CardLevels.size() == 1320
	var ok := true
	for value in checks.values():
		if not value:
			ok = false
	return {"ok": ok, "checks": checks}
