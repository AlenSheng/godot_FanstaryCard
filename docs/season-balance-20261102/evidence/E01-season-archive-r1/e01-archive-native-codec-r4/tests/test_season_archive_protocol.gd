extends RefCounted

const Http = preload("res://network/http_protocol.gd")
const Bundle = preload("res://data/config_bundle.gd")
const Index = preload("res://data/catalog_index.gd")
const Model = preload("res://ui/season_archive_model.gd")

func _read(name: String, route: String, status: int = 200) -> Dictionary:
	var bytes := FileAccess.get_file_as_bytes("res://tests/archive-read-wire/" + name + ".bin")
	return Http.decode_response(Http.route(route, HTTPClient.METHOD_GET), status, PackedStringArray(["Content-Type: application/protobuf"]), bytes)

func run_test() -> Dictionary:
	var checks := {}
	var list := _read("list", "/api/v1/season-archives?limit=1")
	checks["actual HTTP list decodes and validates"] = list.ok and Model.list_valid(list.data, 0) and list.data.items.size() == 1
	if not checks["actual HTTP list decodes and validates"]: return {"ok": false, "checks": checks}
	var source: Dictionary = list.data.items[0]
	checks["actual original15 metadata and exact int64 gold"] = source.configVersion == "season-v1-config-15" and source.wallet.gold == 9007199254740993
	checks["opaque and new marks remain separate"] = source.wallet.challengeMarks == 77 and source.wallet.blueprintMarks == 4 and source.wallet.orangeBlueprintMarks == 14
	for section in Model.SECTIONS:
		var route: String = "/api/v1/season-archives/" + str(source.seasonId) + "/" + section + "?limit=2"
		var page := _read(section, route)
		checks[section + " actual typed readonly section validates"] = page.ok and Model.section_valid(page.data, source, section, 0)
		if not page.ok: continue
		checks[section + " original source and progressing cursor"] = page.data.season.configSha256 == source.configSha256 and page.data.nextOffset == 2
		if section == "equipment":
			checks["physical item identity original stats and archived location"] = page.data.equipments.size() == 2 and page.data.equipments[0].seasonId == source.seasonId and page.data.equipments[0].statsVersion == source.statsVersion and page.data.equipments[0].location == "SeasonArchive"
		if section == "loadouts": checks["original references resolve through own snapshots"] = page.data.referencedEquipments.size() == 3 and page.data.loadouts.size() == 2
	var configuration := _read("configuration", "/api/v1/config/season-v1-config-15")
	checks["actual original configuration HTTP reply"] = configuration.ok and configuration.data.configVersion == source.configVersion and configuration.data.contentHash == source.configSha256
	if configuration.ok:
		var reader := Bundle.new()
		var decoded := reader.decode(configuration.data.bundle, str(source.configVersion), str(source.configSha256))
		var index := Index.from_data(decoded) if not decoded.is_empty() else {}
		checks["actual published bundle hash and original index"] = index.get("version") == source.configVersion and index.get("content_hash") == source.configSha256
	var invalid := _read("invalid-page", "/api/v1/season-archives?limit=51", 400)
	checks["typed HTTP page rejection is decoded as error data"] = invalid.ok and invalid.data.get("status") == 400 and invalid.data.get("title") == "Cannot read season archive" and not invalid.data.has("items")
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "Actual CSharp HTTP packets decoded by nativeGodot; no newgame or UI verdict."}
