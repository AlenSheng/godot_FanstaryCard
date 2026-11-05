extends RefCounted

const Bundle = preload("res://data/config_bundle.gd")
const Index = preload("res://data/catalog_index.gd")
const Http = preload("res://network/http_protocol.gd")

func run_test() -> Dictionary:
	var checks := {}
	var cases: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/refresh-config/cases.json"))
	for entry in cases:
		var name: String = str(entry.name)
		var wire := FileAccess.get_file_as_bytes("res://tests/refresh-config/" + name + ".envelope")
		var response := Http.decode_response(Http.route("/api/v1/config/" + str(entry.version), HTTPClient.METHOD_GET), 200, PackedStringArray(["Content-Type: application/protobuf"]), wire)
		checks[name + " typed envelope"] = response.ok
		if not response.ok: continue
		var reader := Bundle.new()
		var data: Dictionary = reader.decode(response.data.bundle, str(entry.version), str(entry.hash))
		checks[name + " verified original bytes"] = not data.is_empty() and reader.error.is_empty()
		if data.is_empty(): continue
		var index := Index.from_data(data)
		for number in range(1, 4):
			checks[name + " original refresh price " + str(number)] = Index.reward_refresh_gold(number, index) == int(entry.prices[number - 1])
		checks[name + " other server fields remain hidden"] = not data.tables.LootRules[0].has("gold") and not data.tables.has("SeasonRedRules")
		checks[name + " no fourth refresh"] = Index.reward_refresh_gold(4, index) == -1
		var damaged: PackedByteArray = response.data.bundle.duplicate()
		damaged[damaged.size() - 1] ^= 1
		checks[name + " damaged price package rejected"] = reader.decode(damaged, str(entry.version), str(entry.hash)).is_empty()
	checks["built in prices come from formal catalog"] = [Index.reward_refresh_gold(1), Index.reward_refresh_gold(2), Index.reward_refresh_gold(3)] == [60, 180, 450]
	checks["missing original cannot borrow built in price"] = Index.reward_refresh_gold(1, {"version": "absent", "tables": {}}) == -1
	checks["zero ordinal rejected"] = Index.reward_refresh_gold(0) == -1
	for amount in [null, 0, -1, 2.5, "7", true, INF, NAN, 2147483648]:
		checks["invalid price " + str(amount)] = Index.reward_refresh_gold(1, {"tables": {"LootRules": [{"refresh_index": 1, "refresh_gold": amount}]}}) == -1
	checks["duplicate source ordinal rejected"] = Index.reward_refresh_gold(1, {"tables": {"LootRules": [{"refresh_index": 1, "refresh_gold": 7}, {"refresh_index": 1, "refresh_gold": 11}]}}) == -1
	return {"ok": not checks.values().has(false), "checks": checks, "fixture_only": true, "actual_game_matches": 0}
