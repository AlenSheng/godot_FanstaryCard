extends RefCounted

const Model = preload("res://ui/season_archive_model.gd")
const Controller = preload("res://ui/season_archive_controller.gd")

class Host extends Control:
	var screen := "archive"
	func _schedule_render() -> void: pass

class Gateway extends Node:
	signal released
	var session_generation := 1
	var base_url := "https://original.invalid"
	var requests: Array = []
	var replies := {}
	func request(path: String, method: int = HTTPClient.METHOD_GET, body: Variant = null, _quiet: Array = []) -> Dictionary:
		var index := requests.size()
		requests.append({"path": path, "method": method, "body": body})
		while not replies.has(index): await released
		return replies[index]
	func complete(index: int, data: Dictionary) -> void:
		replies[index] = data
		released.emit()

class CatalogRead extends RefCounted:
	var result: Dictionary = {}
	var finished := false
	func run(version: String, content_hash: String) -> void:
		result = await Game.read_historical_catalog(version, content_hash)
		finished = true

static func legacy() -> Dictionary:
	return {"seasonId": "legacy-gdd-0.70", "rulesetId": "legacy", "configVersion": null, "configSha256": null, "statsVersion": null, "startsAt": null, "endsAt": null, "archivedAt": "2026-11-01T00:00:00Z", "status": "Legacy", "phase": null, "wallet": {"seasonId": "legacy-gdd-0.70", "gold": 9007199254740993, "equipmentFragments": 456, "challengeMarks": 77, "blueprintMarks": 0, "orangeBlueprintMarks": 0, "version": 1, "canFundWeapon": false}, "equipmentCount": 1, "recipeCount": 0, "wishCount": 0, "loadoutCount": 0}

static func section(source: Dictionary, name: String = "equipment") -> Dictionary:
	return {"season": source.duplicate(true), "section": name, "readOnly": true, "equipments": [], "recipes": [], "wishes": [], "loadouts": [], "referencedEquipments": [], "nextOffset": null}

func _frames() -> void:
	await Game.get_tree().process_frame
	await Game.get_tree().process_frame

func run_test() -> Dictionary:
	var checks := {}
	var source := legacy()
	checks["unknown historical metadata stays null"] = Model.summary_valid(source) and source.configVersion == null and source.startsAt == null
	checks["opaque marks and exact int64 gold preserved"] = source.wallet.gold == 9007199254740993 and source.wallet.challengeMarks == 77 and source.wallet.blueprintMarks == 0
	checks["own source and read-only page valid"] = Model.section_valid(section(source), source, "equipment", 0)
	var wrong := section(source)
	wrong.readOnly = false
	checks["writable archive refused"] = not Model.section_valid(wrong, source, "equipment", 0)
	wrong = section(source); wrong.season.seasonId = "another"
	checks["mixed original season refused"] = not Model.section_valid(wrong, source, "equipment", 0)
	wrong = section(source); wrong.nextOffset = 0
	checks["nonprogressing cursor refused"] = not Model.section_valid(wrong, source, "equipment", 0)
	wrong = section(source); wrong.referencedEquipments = [{"instanceId": "foreign", "seasonId": source.seasonId}]
	checks["unrequested referenced item refused"] = not Model.section_valid(wrong, source, "equipment", 0)
	checks["unknown section refused"] = not Model.section_valid(section(source), source, "other", 0)
	var original: Node = Game.gateway
	var gateway := Gateway.new()
	Game.add_child(gateway); Game.gateway = gateway; Game.set_process(false)
	var host := Host.new()
	Game.get_tree().root.add_child(host)
	var controller := Controller.new(); controller.attach(host)
	controller.reload()
	await _frames()
	gateway.complete(0, {"ok": true, "data": {"items": [source], "nextOffset": null}})
	await _frames()
	checks["list selection requests only original source"] = gateway.requests.size() == 2 and str(gateway.requests[1].path).contains("legacy-gdd-0.70/equipment")
	gateway.complete(1, {"ok": true, "data": section(source)})
	await _frames()
	checks["legacy renders without requesting a current catalog"] = not controller.loading and not controller.failed and not controller.catalog_ready and gateway.requests.size() == 2 and controller.state.readOnly
	controller.reset(); var index := gateway.requests.size(); controller.reload(); controller.leave()
	gateway.complete(index, {"ok": true, "data": {"items": [source], "nextOffset": null}})
	await _frames()
	checks["leaving page invalidates pending list"] = controller.seasons.is_empty()
	controller.reset(); index = gateway.requests.size(); controller.reload(); gateway.session_generation += 1
	gateway.complete(index, {"ok": true, "data": {"items": [source], "nextOffset": null}})
	await _frames()
	checks["account epoch invalidates pending list"] = controller.seasons.is_empty()
	controller.reset(); index = gateway.requests.size(); controller.reload(); gateway.base_url = "https://changed.invalid"
	gateway.complete(index, {"ok": true, "data": {"items": [source], "nextOffset": null}})
	await _frames()
	checks["address change invalidates pending list"] = controller.seasons.is_empty()
	controller.reset(); controller.seasons = [source]; index = gateway.requests.size(); controller.choose(0)
	gateway.complete(index, {"ok": true, "data": section(source, "recipes")})
	await _frames()
	checks["wrong section never replaces selected data"] = controller.failed and controller.state.is_empty()
	checks["all archive requests are GET with no body"] = gateway.requests.all(func(row): return row.method == HTTPClient.METHOD_GET and row.body == null)
	var old_bytes := FileAccess.get_file_as_bytes(OS.get_environment("FANTASYCARD_ARCHIVE_CONFIG15_BYTES"))
	var old_hash := OS.get_environment("FANTASYCARD_ARCHIVE_CONFIG15_HASH")
	assert(not old_bytes.is_empty() and old_hash.length() == 64)
	var caches := JSON.stringify(Game._room_catalogs)
	var read := CatalogRead.new(); index = gateway.requests.size(); read.run("season-v1-config-15", old_hash)
	gateway.complete(index, {"ok": true, "data": {"configVersion": "season-v1-config-15", "contentHash": old_hash, "bundle": old_bytes}})
	await _frames()
	checks["actual original bytes and expected hash verified"] = read.finished and read.result.get("version") == "season-v1-config-15" and read.result.get("content_hash") == old_hash
	read = CatalogRead.new(); index = gateway.requests.size(); read.run("season-v1-config-15", old_hash)
	gateway.complete(index, {"ok": true, "data": {"configVersion": "season-v1-config-15", "contentHash": "b".repeat(64), "bundle": old_bytes}})
	await _frames()
	checks["different declared original hash refused"] = read.finished and read.result.is_empty()
	read = CatalogRead.new(); index = gateway.requests.size(); read.run("season-v1-config-15", old_hash)
	var damaged := old_bytes.duplicate(); damaged[damaged.size() - 1] ^= 1
	gateway.complete(index, {"ok": true, "data": {"configVersion": "season-v1-config-15", "contentHash": old_hash, "bundle": damaged}})
	await _frames()
	checks["damaged original refuses current fallback"] = read.finished and read.result.is_empty()
	read = CatalogRead.new(); index = gateway.requests.size(); read.run(str(Game.CATALOG.data.version), "a".repeat(64))
	gateway.complete(index, {"ok": false, "status": 404, "data": {}})
	await _frames()
	checks["even current-version archive requires original hash proof"] = read.finished and read.result.is_empty() and gateway.requests.size() == index + 1
	read = CatalogRead.new(); index = gateway.requests.size(); read.run("season-v1-config-15", old_hash); gateway.session_generation += 1
	gateway.complete(index, {"ok": true, "data": {"configVersion": "season-v1-config-15", "contentHash": old_hash, "bundle": old_bytes}})
	await _frames()
	checks["catalog account epoch rejects stale original result"] = read.finished and read.result.is_empty()
	checks["archive catalog reads never alter room catalog caches"] = caches == JSON.stringify(Game._room_catalogs)
	controller.leave(); host.free(); Game.gateway = original; gateway.queue_free()
	return {"ok": not checks.values().has(false), "checks": checks, "scope": "Read-only archive model and fakegateway races, not liveHTTP or renderedUI."}
