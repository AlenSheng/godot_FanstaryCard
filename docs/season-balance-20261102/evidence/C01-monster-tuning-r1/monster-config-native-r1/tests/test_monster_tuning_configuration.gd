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
		checks[name + " unchanged public count"] = decoded.tables.size() == 32
		checks[name + " server tuning stays hidden"] = not decoded.tables.has("SeasonMonsterTuning")
		checks[name + " cards and growth retained"] = decoded.tables.Cards.size() == 232 and decoded.tables.CardLevels.size() == 1320
		var changed: PackedByteArray = response.data.bundle.duplicate()
		changed[changed.size() - 1] ^= 1
		checks[name + " corruption rejected"] = reader.decode(changed, str(entry.version), str(entry.hash)).is_empty()
		checks[name + " truncation rejected"] = reader.decode(response.data.bundle.slice(0, response.data.bundle.size() - 1), str(entry.version), str(entry.hash)).is_empty()
		checks[name + " wrong version rejected"] = reader.decode(response.data.bundle, "wrong-version", str(entry.hash)).is_empty()
	checks["both real source versions consumed"] = visible.size() == 2
	checks["all original public values unchanged"] = visible.has("old14") and visible.has("current15") and visible.old14 == visible.current15
	checks["different original content hashes"] = cases.size() == 2 and str(cases[0].hash) != str(cases[1].hash)
	var ok := true
	for value in checks.values():
		if not value:
			ok = false
	return {"ok":ok,"checks":checks}
