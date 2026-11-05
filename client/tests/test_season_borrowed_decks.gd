extends RefCounted

const Index = preload("res://data/catalog_index.gd")
const Http = preload("res://network/http_protocol.gd")
const Proto = preload("res://network/protobuf.gd")
const P = preload("res://ui/palette.gd")

class Store extends "res://state/game_store.gd":
	func _ready() -> void: set_process(false)
	func refresh_cache(module: String) -> void: pass

class RecordingGateway extends "res://network/gateway.gd":
	var requests: Array = []
	func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, quiet_statuses: Array = []) -> Dictionary:
		requests.append({"path":path,"method":method,"data":data.duplicate(true) if data is Dictionary else data})
		return {"ok":false,"status":409,"data":{}}

func run_test() -> Dictionary:
	var checks := {}
	var gateway := RecordingGateway.new()
	gateway.persist_session = false
	gateway.base_url = "http://127.0.0.1:9"
	var store := Store.new()
	store.gateway = gateway
	store.hero_class = "Mage"
	store.server_info = {"configVersion":str(Index.CATALOG.data.version)}
	store._server_info_address = gateway.base_url
	store.lobby = {"season":{"state":"Active","seasonId":"loans","configVersion":str(Index.CATALOG.data.version),"highestOpenDifficulty":5,"highestUnlockedDifficulty":2}}
	store.use_borrowed_deck = true
	store.preparation_difficulty = 5
	await store.prepare("Free",0)
	checks["borrowed works without saved permanent deck"] = gateway.requests.size() == 1
	if not gateway.requests.is_empty():
		var data: Dictionary = gateway.requests[0].data
		checks["selected difficulty bounded by personal unlock"] = data.difficulty == "D2" and data.seasonId == "loans" and store.preparation_difficulty == 2
		checks["virtual mode has explicit flag and no permanent deck version"] = data.useBorrowedDeck == true and data.deckVersion == 0
		var contract := Http.route("/api/v1/preparations",HTTPClient.METHOD_POST)
		var wire := Proto.new(true).encode(contract.request,Http.to_wire(contract.request,data))
		checks["new request flag has independent protobuf tag nine"] = wire.has(72) and Proto.new(true).decode_http(contract.request,wire).useBorrowedDeck == true
		checks["borrowed request also freezes configured loot preference"] = data.lootPreferenceElement == Index.CATALOG.data.tables.SeasonLootPreference[0].default_element
	store.use_borrowed_deck = false
	await store.prepare("Free",0)
	checks["owned mode still needs saved deck"] = gateway.requests.size() == 1
	store.lobby.season.state = "Ended"
	store.use_borrowed_deck = true
	await store.prepare("Free",0)
	checks["closed season cannot borrow with missing deck"] = gateway.requests.size() == 1 and store.season_preparation_cap() == 0
	var rows: Array = Index.CATALOG.data.tables.get("SeasonBorrowedDecks",[])
	checks["public current catalog has all sixty borrowed slots"] = rows.size() == 60
	var previous := P.language()
	var languages: Array = P.languages().keys()
	for language in languages:
		P.set_language(str(language))
		for key in ["season_borrowed_deck","season_borrowed_deck_hint","season_level_cap_hint"]:
			checks[str(language)+" "+key] = not P.localized(key).is_empty() and P.localized(key) != key
	P.set_language(previous)
	store._clear_authenticated_state()
	checks["logout clears borrowed selection and difficulty"] = not store.use_borrowed_deck and store.preparation_difficulty == 0 and store.preparation_loot_preference.is_empty() and store._loot_preference_scope.is_empty()
	store.free()
	gateway.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Offline real GameStore + generated request schema + eleven locale values. No rendered-frame or server-capacity claim."}
