extends RefCounted

const Http=preload("res://network/http_protocol.gd")
const Proto=preload("res://network/protobuf.gd")

class CaptureGateway extends Node:
	var session_generation := 10
	var base_url := "http://127.0.0.1:9"
	var token := ""
	var requests: Array=[]
	func request(path: String,method: int=HTTPClient.METHOD_GET,data: Variant=null,_quiet: Array=[]) -> Dictionary:
		requests.append({"path":path,"method":method,"data":data.duplicate(true)})
		return {"ok":true,"data":{"preparationId":"offline-preference","snapshot":{"configVersion":Game.CATALOG.data.version,"lootPreferenceElement":data.lootPreferenceElement}}}

func run_test() -> Dictionary:
	var checks := {}
	var saved := {}
	for field in ["gateway","lobby","busy","preparation","ticket","server_info","_server_info_address","preparation_difficulty","use_borrowed_deck","preparation_loot_preference","_loot_preference_scope","configuration_error","hero_class"]:
		saved[field]=Game.get(field)
	var muted: bool=Sound.muted;Sound.muted=true
	var gateway := CaptureGateway.new();Game.gateway=gateway
	Game.hero_class="Mage";Game.busy=false;Game.preparation={};Game.ticket={};Game.configuration_error=""
	Game.server_info={"configVersion":Game.CATALOG.data.version};Game._server_info_address=gateway.base_url
	Game.preparation_difficulty=2;Game.use_borrowed_deck=false;Game._loot_preference_scope=""
	Game.lobby={"season":{"state":"Active","seasonId":"current","configVersion":Game.CATALOG.data.version,"highestOpenDifficulty":5,"highestUnlockedDifficulty":5},"decks":[{"heroClass":"Mage","version":4}],"equippedLoadouts":[{"heroClass":"Mage","equipmentIds":[null,null,null,null,null]}]}
	var default_element: String=str(Game.CATALOG.data.tables.SeasonLootPreference[0].default_element)
	checks["default comes from frozen config"]=Game.season_loot_preference()==default_element
	Game.select_loot_preference("Water")
	checks["selection changes before preparation"]=Game.season_loot_preference()=="Water"
	await Game.prepare("Free",0)
	checks["actual preparation command captures the selected preference"]=gateway.requests.size()==1 and gateway.requests[0].path=="/api/v1/preparations" and gateway.requests[0].method==HTTPClient.METHOD_POST and gateway.requests[0].data.lootPreferenceElement=="Water" and gateway.requests[0].data.seasonId=="current"
	checks["server snapshot remains the locked source"]=Game.preparation.snapshot.lootPreferenceElement=="Water" and not Game.busy
	Game.select_loot_preference("Fire")
	checks["prepared selector cannot change the lock"]=Game.preparation_loot_preference=="Water" and Game.preparation.snapshot.lootPreferenceElement=="Water"
	Game.preparation={};Game.lobby.season.seasonId="next"
	checks["new season resets local preference to its default"]=Game.season_loot_preference()==default_element
	Game.select_loot_preference("None")
	checks["invalid choice does not become a fallback element"]=Game.season_loot_preference()==default_element
	Game.busy=true;Game.select_loot_preference("Water")
	checks["busy preparation cannot change preference"]=Game.season_loot_preference()==default_element
	Game.lobby.season.state="Closed"
	checks["nonactive season has no preference control"]=Game.season_loot_preference().is_empty()
	var proto := Proto.new(true)
	var old: Dictionary=proto.decode_http("CreatePreparationRequest",proto.encode("CreatePreparationRequest",{"hero_class":"Mage","deck_version":4,"backpack_tier":"Free"}))
	checks["old request keeps the new field absent"]=old.lootPreferenceElement==null
	var body := {"heroClass":"Mage","deckVersion":9007199254740993,"backpackTier":"Free","difficulty":"D2","seasonId":"s","lootPreferenceElement":"Metal"}
	var decoded: Dictionary=proto.decode_http("CreatePreparationRequest",proto.encode("CreatePreparationRequest",Http.to_wire("CreatePreparationRequest",body)))
	checks["request codec keeps preference and exact version"]=proto.error.is_empty() and decoded.lootPreferenceElement=="Metal" and decoded.deckVersion==9007199254740993
	decoded=proto.decode_http("PreparationSnapshotResponse",proto.encode("PreparationSnapshotResponse",{"hero_class":"Mage","config_version":Game.CATALOG.data.version,"loot_preference_element":"Water"}))
	checks["snapshot codec preserves lock"]=proto.error.is_empty() and decoded.lootPreferenceElement=="Water"
	for field in saved:Game.set(field,saved[field])
	gateway.free();Sound.stop_all();await Engine.get_main_loop().process_frame;Sound.muted=muted
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Actual preparation controller using captured offline transport plus real codec; no rendered or live-server claim."}
