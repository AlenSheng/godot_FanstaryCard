extends RefCounted

const Http = preload("res://network/http_protocol.gd")
const Index = preload("res://data/catalog_index.gd")
const Model = preload("res://ui/preparation_model.gd")
const Details = preload("res://ui/card_details.gd")
const Bundle = preload("res://data/config_bundle.gd")
const Gear = preload("res://ui/equipment_compare_model.gd")
const P = preload("res://ui/palette.gd")

class Store extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
	func refresh_cache(module: String) -> void: pass

class RecordingGateway extends "res://network/gateway.gd":
	var bootstrap_value: Dictionary = {}
	var configuration_value: Dictionary = {}
	var preparation_value: Dictionary = {}
	var fallback_preparation: Dictionary = {}
	var requests: Array = []
	var missing_config := false
	var delay_config := false
	signal released
	func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
		requests.append({"path": path, "method": method, "data": data.duplicate(true) if data is Dictionary else data})
		if path.begins_with("/api/v1/config/"):
			if delay_config: await released
			return {"ok": false, "status": 404, "data": {}} if missing_config else {"ok": true, "status": 200, "data": configuration_value.duplicate(true)}
		if path == "/api/v1/bootstrap": return {"ok": true, "status": 200, "data": bootstrap_value.duplicate(true)}
		if path == "/api/v1/preparations" and method == HTTPClient.METHOD_GET:
			return {"ok": false, "status": 404, "data": {}} if fallback_preparation.is_empty() else {"ok": true, "status": 200, "data": fallback_preparation.duplicate(true)}
		if path == "/api/v1/preparations": return {"ok": true, "status": 200, "data": preparation_value.duplicate(true)}
		if path == "/api/v1/matches/enqueue": return {"ok": true, "status": 200, "data": {"ticketId": "native-ticket"}}
		return {"ok": false, "status": 409, "data": {}}

class Probe extends RefCounted:
	var done := false
	func start(store: Node) -> void:
		await store.refresh_lobby()
		done = true

func decode(name: String, path: String, method: int = HTTPClient.METHOD_GET) -> Dictionary:
	var result: Dictionary = Http.decode_response(Http.route(path, method), 200, PackedStringArray(["Content-Type: application/protobuf"]), FileAccess.get_file_as_bytes("res://tests/preparation-client/" + name))
	assert(result.ok)
	return result.data

func new_gateway(entry: Dictionary, locked: bool = false) -> RecordingGateway:
	var gateway := RecordingGateway.new()
	gateway.persist_session = false
	gateway.online = true
	gateway.base_url = "http://preparation-source.example"
	gateway.token = "isolated-fixture-token"
	gateway.configuration_value = decode("original.configuration.envelope", "/api/v1/config/" + str(entry.sourceVersion))
	gateway.preparation_value = decode(str(entry.name) + ".preparation.envelope", "/api/v1/preparations", HTTPClient.METHOD_POST)
	gateway.bootstrap_value = decode(str(entry.name) + (".locked" if locked else ".draft") + ".bootstrap.envelope", "/api/v1/bootstrap")
	if locked: gateway.fallback_preparation = gateway.preparation_value.duplicate(true)
	return gateway

func new_store(gateway: RecordingGateway) -> Store:
	var store := Store.new()
	store.gateway = gateway
	store.server_info = {"configVersion": str(Index.CATALOG.data.version)}
	store._server_info_address = gateway.base_url
	store.hero_class = "Mage"
	return store

func run_test() -> Dictionary:
	var checks := {}
	var observed := {}
	var cases: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/preparation-client/cases.json"))
	checks["formal D0 cap is Blue and D1 cap is Purple"] = Model.difficulty(0).entry_quality == "Blue" and Model.difficulty(1).entry_quality == "Purple"
	checks["formal free backpack unchanged"] = Model.backpack("Free").capacity == 20
	for entry in cases:
		var key: String = str(entry.name)
		var gateway := new_gateway(entry)
		var store := new_store(gateway)
		await store.refresh_lobby()
		checks[key + " active source loaded before draft adoption"] = store._room_catalogs.has(entry.sourceVersion) and store.preparation_catalog_ready() and store.preparation.is_empty()
		checks[key + " lobby catalog remains current"] = store.lobby.configVersion == Index.CATALOG.data.version and store.lobby.season.configVersion == entry.sourceVersion
		checks[key + " exactly one original configuration read"] = gateway.requests.filter(func(row): return row.path.begins_with("/api/v1/config/")).size() == 1
		store.preparation_difficulty = 1
		store.use_borrowed_deck = bool(entry.borrowed)
		var index: Dictionary = store.preparation_catalog_index()
		checks[key + " source free backpack has21 slots"] = Model.backpack("Free", index).capacity == int(entry.originalBag)
		checks[key + " source D1 cap is control Green"] = Model.difficulty(1, index).entry_quality == entry.entryQuality
		checks[key + " source theme preference is Wood"] = store.season_loot_preference() == entry.originalPreference
		checks[key + " source damage differs from built in"] = int(Details.at_level(Index.card("C01", index), 1, index).elemental_damage) == int(entry.originalDamage)
		var before: String = JSON.stringify(store.lobby)
		var preview: Dictionary = store.preparation_preview_snapshot("Free")
		checks[key + " effective and actual weapon split"] = preview.classWeaponLevel == 1 and preview.actualClassWeaponLevel == 5
		checks[key + " armor keeps its real plus5 level"] = preview.equipmentSnapshots.size() == 1 and preview.equipmentSnapshots[0].level == 5
		checks[key + " original equipment stats can be read"] = Gear.can_inspect(preview.equipmentSnapshots, index)
		var deck: Dictionary = store.preparation_deck_preview()
		observed[key] = {"ids": deck.card_ids, "expected_ids": entry.cardIds, "levels": deck.levels, "expected_levels": entry.cardLevels, "borrowed": deck.borrowed, "expected_borrowed": entry.borrowed, "id_array_type": deck.card_ids.get_typed_builtin(), "expected_id_array_type": entry.cardIds.get_typed_builtin(), "level_array_type": deck.levels.get_typed_builtin(), "expected_level_array_type": entry.cardLevels.get_typed_builtin()}
		# C# metadata is JSON (untyped arrays and floating JSON numbers), while
		# the real preview uses typed arrays. Compare every actual slot/value.
		var same_slots: bool = deck.card_ids.size() == 20 and deck.levels.size() == 20 and entry.cardIds.size() == 20 and entry.cardLevels.size() == 20
		if same_slots:
			for slot in 20:
				same_slots = same_slots and deck.card_ids[slot] == entry.cardIds[slot] and float(deck.levels[slot]) == float(entry.cardLevels[slot])
		checks[key + " original twenty card preview"] = same_slots and deck.borrowed == entry.borrowed
		checks[key + " previews never mutate lobby assets"] = before == JSON.stringify(store.lobby)
		if entry.borrowed:
			checks[key + " original template and zero based slot12"] = Model.borrowed_deck("Mage", index).template_id == entry.templateId and deck.card_ids[12] == "C30"
		await store.prepare("Free", 0)
		var writes: Array = gateway.requests.filter(func(row): return row.path == "/api/v1/preparations" and row.method == HTTPClient.METHOD_POST)
		checks[key + " only one preparation command"] = writes.size() == 1
		if not writes.is_empty():
			var payload: Dictionary = writes[0].data
			checks[key + " original season preference and safe slots sent"] = payload.seasonId == entry.seasonId and payload.difficulty == "D1" and payload.lootPreferenceElement == "Wood" and payload.safeSlotIndexes.is_empty()
			checks[key + " virtual mode does not submit permanent deck version"] = payload.get("useBorrowedDeck", false) == entry.borrowed and (not entry.borrowed or payload.deckVersion == 0)
		checks[key + " old preparation accepted without ending login"] = store.preparation.preparationId == entry.preparationId and store.configuration_error.is_empty() and gateway.token == "isolated-fixture-token"
		checks[key + " saved original version stays selected"] = store.preparation_catalog_index().version == entry.sourceVersion and store._preparation_config_valid(store.preparation)
		await store.enqueue()
		checks[key + " matching uses original preparation id"] = gateway.requests.any(func(row): return row.path == "/api/v1/matches/enqueue" and row.data.preparationId == entry.preparationId)
		store.lobby.season.configVersion = str(Index.CATALOG.data.version)
		store.lobby.season.seasonId = "new-scope"
		checks[key + " saved preparation preference remains frozen"] = store.season_loot_preference() == "Wood" and store.preparation_catalog_index().version == entry.sourceVersion
		store.preparation = {}
		checks[key + " new draft resets to new season preference"] = store.season_loot_preference() == Index.CATALOG.data.tables.SeasonLootPreference[0].default_element
		store.free()
		gateway.free()
	var first: Dictionary = cases[0]
	for failure in ["missing", "corrupt", "wrong-version"]:
		var gateway := new_gateway(first, true)
		if failure == "missing": gateway.missing_config = true
		if failure == "corrupt": gateway.configuration_value.bundle[gateway.configuration_value.bundle.size() - 1] ^= 1
		if failure == "wrong-version": gateway.configuration_value.configVersion = "other-version"
		var store := new_store(gateway)
		await store.refresh_lobby()
		checks[failure + " known preparation retained for cancellation"] = store.preparation.preparationId == first.preparationId and not store.lobby.is_empty()
		checks[failure + " no fallback source or forced logout"] = not store.preparation_catalog_ready() and Model.backpack("Free", store.preparation_catalog_index()).is_empty() and gateway.token == "isolated-fixture-token" and store.configuration_error.is_empty()
		checks[failure + " precise preparation failure state"] = not store.preparation_configuration_error.is_empty()
		await store.enqueue()
		checks[failure + " matching cannot submit without original"] = not gateway.requests.any(func(row): return row.path == "/api/v1/matches/enqueue") and not store.busy
		checks[failure + " card preview unavailable instead of invented values"] = store.preparation_deck_preview().is_empty()
		store.free()
		gateway.free()
	var fallback := new_gateway(first, true)
	fallback.bootstrap_value.erase("activePreparation")
	var fallback_store := new_store(fallback)
	await fallback_store.refresh_lobby()
	checks["older bootstrap preparation endpoint loads original before adoption"] = fallback_store.preparation.preparationId == first.preparationId and fallback_store.preparation_catalog_ready() and fallback.requests.any(func(row): return row.path == "/api/v1/preparations")
	fallback_store.preparation.snapshot.borrowedTemplateId = null
	checks["nullable owned template is not a borrowed deck"] = not fallback_store.preparation_deck_preview().borrowed
	fallback_store.free()
	fallback.free()
	for change_origin in [false, true]:
		var gateway := new_gateway(first)
		gateway.delay_config = true
		var store := new_store(gateway)
		var probe := Probe.new()
		probe.start(store)
		await Engine.get_main_loop().process_frame
		checks["delayed original load suspended " + str(change_origin)] = not probe.done
		if change_origin: gateway.base_url = "http://different-origin.example"
		else: store._clear_authenticated_state()
		gateway.released.emit()
		await Engine.get_main_loop().process_frame
		checks["late bootstrap cannot adopt after identity or origin change " + str(change_origin)] = probe.done and store.lobby.is_empty() and store._room_catalogs.is_empty()
		store.free()
		gateway.free()
	var collision_gateway := new_gateway(first)
	collision_gateway.configuration_value = decode("collision.configuration.envelope", "/api/v1/config/" + str(first.sourceVersion))
	collision_gateway.delay_config = true
	var collision_store := new_store(collision_gateway)
	var collision_probe := Probe.new()
	collision_probe.start(collision_store)
	await Engine.get_main_loop().process_frame
	var original: Dictionary = decode("original.configuration.envelope", "/api/v1/config/" + str(first.sourceVersion))
	var original_data: Dictionary = Bundle.new().decode(original.bundle, str(first.sourceVersion), str(first.originalHash))
	var registered: Dictionary = Index.from_data(original_data)
	registered["_origin"] = collision_gateway.base_url
	collision_store._room_catalogs[first.sourceVersion] = registered
	collision_gateway.released.emit()
	await Engine.get_main_loop().process_frame
	checks["concurrent same version different hash cannot replace original"] = collision_probe.done and collision_store._room_catalogs[first.sourceVersion].content_hash == first.originalHash and Model.backpack("Free", collision_store._room_catalogs[first.sourceVersion]).capacity == 21
	collision_store.free()
	collision_gateway.free()
	var isolated: Dictionary = Index.from_data(Index.CATALOG.data.duplicate(true))
	for row in isolated.tables.Backpacks:
		if row.id == "Advanced": row.capacity = 29
	checks["safe indexes derive from original capacity"] = Model.backpack("Advanced", isolated).safe_indexes == [28]
	checks["missing source cannot select current difficulty"] = Model.difficulty(1, {"tables": {}}).is_empty()
	checks["missing source cannot borrow current template"] = Model.borrowed_deck("Mage", {"tables": {}}).is_empty()
	var previous: String = P.language()
	for language in P.languages():
		P.set_language(str(language))
		for label in ["preparation_backpack_details", "preparation_deck_preview", "preparation_deck_button", "season_preparation_limits", "season_preparation_level_projection"]:
			checks[str(language) + " " + label] = not P.localized(label).is_empty() and P.localized(label) != label
	P.set_language(previous)
	return {"ok": not checks.values().has(false), "checks": checks, "observed": observed, "actual_game_matches": 0, "rendered_frames": false, "source": "Real PostgreSQL preparation/bootstrap typed bytes, replayed through isolated GameStore and gateway boundary."}
