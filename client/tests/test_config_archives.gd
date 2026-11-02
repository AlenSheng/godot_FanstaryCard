extends RefCounted

const Bundle = preload("res://data/config_bundle.gd")
const Index = preload("res://data/catalog_index.gd")
const Http = preload("res://network/http_protocol.gd")
const Details = preload("res://ui/card_details.gd")
const Gear = preload("res://ui/equipment_compare_model.gd")
const P = preload("res://ui/palette.gd")

class QuietGateway extends "res://network/gateway.gd":
	var fixture: Dictionary = {}
	var paths: Array = []
	var delayed := false
	signal released
	func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
		paths.append(path)
		if delayed: await released
		if path.begins_with("/api/v1/config/") and has_meta("configuration_response"):
			return {"ok":true,"status":200,"data":get_meta("configuration_response").duplicate(true)}
		return {"ok": true, "status": 200, "data": fixture.duplicate(true)}
	func send(kind: String, payload: Dictionary = {}, request_id: String = "") -> bool:
		return true

class AwaitProbe extends RefCounted:
	var done := false
	var accepted := true
	signal finished
	func start(store: Node, version: String) -> void:
		accepted = await store._ensure_room_catalog(version)
		done = true
		finished.emit()

func run_test() -> Dictionary:
	var checks := {}
	var previous_language := P.language()
	var cases: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/config-client/cases.json"))
	var languages: Array = JSON.parse_string(FileAccess.get_file_as_string("res://tests/config-client/languages.json"))
	var gateway := QuietGateway.new()
	gateway.persist_session = false
	gateway.online = true
	var store: Node = load("res://state/game_store.gd").new()
	store.gateway = gateway
	var first_envelope := {}
	var first_version := ""
	for entry in cases:
		var version := str(entry.version)
		var packet := FileAccess.get_file_as_bytes("res://tests/config-client/" + str(entry.name) + ".envelope")
		var contract := Http.route("/api/v1/config/" + version, HTTPClient.METHOD_GET)
		var response := Http.decode_response(contract, 200, PackedStringArray(["Content-Type: application/protobuf"]), packet)
		checks[version + " typed HTTP envelope"] = response.ok and response.data.bundle is PackedByteArray
		if not response.ok: continue
		var envelope: Dictionary = response.data
		if first_envelope.is_empty():
			first_envelope = envelope
			first_version = version
		var reader := Bundle.new()
		var decoded := reader.decode(envelope.bundle, version, str(entry.hash))
		checks[version + " CSharp bundle verified"] = not decoded.is_empty() and reader.error.is_empty()
		if decoded.is_empty(): continue
		var index := Index.from_data(decoded)
		checks[version + " isolated source data"] = int(Index.card("C01", index).elemental_damage) == int(entry.damage) and int(Index.card_level("C01", 1, index).value_bonus) == int(entry.bonus)
		checks[version + " server fields hidden"] = not decoded.tables.has("SeasonRedRules") and not decoded.tables.LootRules[0].has("gold")
		checks[version + " typed zero and null"] = decoded.tables.Cards[0].is_class_reveal == false and decoded.tables.Cards[0].hero_class == null
		var effect := Details.at_level(Index.card("C01", index), 1, index)
		checks[version + " growth source"] = int(effect.elemental_damage) == int(entry.damage) + int(entry.bonus)
		var gear := {"slot": "Head", "quality": "White", "element": "Fire", "level": 0, "secondaryTrait": "DrawInterval"}
		checks[version + " equipment source"] = is_equal_approx(float(Gear.attribute_rows(gear, index)[0].value), float(entry.whiteDamage))
		for language in languages:
			P.set_language(str(language))
			var description := Details.face_description("C01", 1, {}, index)
			checks[version + " text " + str(language)] = P.language() == str(language) and description.contains(str(int(entry.damage) + int(entry.bonus)))
			var unavailable := P.localized("config_archive_unavailable")
			checks[version + " archive failure localized " + str(language)] = not unavailable.is_empty() and unavailable != "config_archive_unavailable"
		gateway.fixture = envelope
		checks[version + " cache loads"] = await store._ensure_room_catalog(version)
		var requests := gateway.paths.size()
		checks[version + " cache retained"] = await store._ensure_room_catalog(version) and gateway.paths.size() == requests
		store.room = {"config_version": version, "room_id": "room", "allowed_actions": ["battle.play_cards"],
			"player": {"hero_class": "Mage", "hp": 70, "maximum_hp": 70, "weapon_level": 0, "hand": [{"instance_id": "card", "card_id": "C01", "level": 1}],
				"battle_status": {"combo": 5, "core_element": "Fire"}, "numerical_state": {"fenxian_policy": "SeasonBoundedRhythm"}},
			"pve": {"battle_id": "battle", "current_target_id": "fire-bat", "monsters": [{"monster_id": "fire-bat", "hp": 1000, "shield": 0}]}}
		checks[version + " room accepts archived version"] = store.validate_config(version, "room")
		var preview: Dictionary = store._calculate_combat_preview(["card"])
		checks[version + " preview uses source and 15pct resistance"] = int(preview.get("damage", 0)) == (172 if entry.name == "old" else 345)
		checks[version + " season single card cannot preview passive draw"] = int(preview.get("immediate_draw", -1)) == 0 and is_equal_approx(float(preview.get("draw_charge", 0)), .18)
		store.room.player.hand.append({"instance_id":"card-two","card_id":"C02","level":0})
		var two_cards: Dictionary = store._calculate_combat_preview(["card","card-two"])
		checks[version + " season two cards cap passive draw at one"] = int(two_cards.get("immediate_draw", -1)) == 1
		store.room.player.numerical_state.fenxian_policy = "CurrentRhythm"
		var legacy: Dictionary = store._calculate_combat_preview(["card"])
		checks[version + " legacy preview keeps its separate policy"] = int(legacy.get("immediate_draw", -1)) == 2
		var altered: PackedByteArray = envelope.bundle.duplicate()
		altered[altered.size() - 1] ^= 1
		checks[version + " tamper rejected"] = reader.decode(altered, version, str(entry.hash)).is_empty() and not reader.error.is_empty()
		checks[version + " truncation rejected"] = reader.decode(envelope.bundle.slice(0, envelope.bundle.size() - 1), version, str(entry.hash)).is_empty()
		checks[version + " wrong version rejected"] = reader.decode(envelope.bundle, "other", str(entry.hash)).is_empty()
		checks[version + " wrong hash rejected"] = reader.decode(envelope.bundle, version, "0".repeat(64)).is_empty()
	checks["lobby index remains built in"] = Index.cards().size() == 232 and int(Index.card("C01").elemental_damage) == 8
	gateway.base_url = "http://other.example"
	checks["cached origin cannot cross server"] = store.room_catalog_index().get("cards", {}).is_empty()
	store._clear_authenticated_state()
	checks["logout removes archive caches"] = store._room_catalogs.is_empty()
	for change_origin in [false, true]:
		gateway.fixture = first_envelope
		gateway.delayed = true
		var probe := AwaitProbe.new()
		probe.start(store, str(first_envelope.configVersion))
		if change_origin: gateway.base_url += "/different"
		else: gateway.session_generation += 1
		gateway.released.emit()
		if not probe.done: await probe.finished
		checks["delayed response fenced " + str(change_origin)] = not probe.accepted and store._room_catalogs.is_empty()
	# Bootstrap must obtain the original configuration before it publishes an unfinished room route.
	var bootstrap_gateway := QuietGateway.new()
	bootstrap_gateway.persist_session = false
	var bootstrap_store: Node = load("res://state/game_store.gd").new()
	bootstrap_store.gateway = bootstrap_gateway
	var bootstrap := {"configVersion":str(bootstrap_store.CATALOG.data.version),"player":{},"wallet":{},"materials":{},
		"unfinishedMatch":{"roomId":"old-room","configVersion":first_version},"unfinishedSettlement":null,
		"shop":{},"market":[],"inventory":{},"mail":{"items":[],"unreadCount":0},"activePreparation":null}
	bootstrap_gateway.fixture = bootstrap
	bootstrap_gateway.set_meta("configuration_response",first_envelope)
	await bootstrap_store.refresh_lobby()
	checks["bootstrap caches original before adopting route"] = bootstrap_store._room_catalogs.has(first_version) and bootstrap_gateway.room_id == "old-room" and not bootstrap_store.lobby.is_empty()
	checks["bootstrap uses one configuration read"] = bootstrap_gateway.paths == ["/api/v1/bootstrap","/api/v1/config/"+first_version]
	bootstrap_store.free()
	bootstrap_gateway.free()
	store.free()
	gateway.free()
	P.set_language(previous_language)
	return {"ok": not checks.values().has(false), "checks": checks, "languages": languages, "rendered_frames": false}
