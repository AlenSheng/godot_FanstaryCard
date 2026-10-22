extends RefCounted
class ProjectionGateway extends Node:
	var token := "projection-test"
	var session_generation := 1
	var room_id := "room"
	var room_revision := 1
	var calls: Array=[]
	var response: Dictionary={}
	func request(path: String,_method: int=HTTPClient.METHOD_GET,_data: Variant=null,_quiet: Array=[]) -> Dictionary:
		calls.append(path);return response.duplicate(true)
func run_test() -> Dictionary:
	var store: Node=load("res://state/game_store.gd").new()
	var gateway:=ProjectionGateway.new();store.gateway=gateway
	var match_id: String="00000000-0000-4000-8000-000000000001"
	store.room={"match_id":match_id,"room_id":"room","player":{"phase":"Dead"}}
	store.lobby={"player":{"userId":"existing"},"cards":[{"cardId":"existing-card"}],"wallet":{"gold":123}}
	var lobby_before: Dictionary=store.lobby.duplicate(true)
	gateway.response={"ok":true,"status":200,"data":{"configVersion":store.CATALOG.data.version,"unfinishedSettlement":null}}
	store.retry_settlement()
	var checks: Dictionary={"unknown-ID recovery selects exact match projection":gateway.calls==["/api/v1/bootstrap?settlementMatchId="+match_id],"Pending projection does not create receipt or replace lobby":store.settlement.is_empty() and store.lobby==lobby_before}
	gateway.response.data.unfinishedSettlement={"settlementId":"ready","matchId":match_id}
	store.retry_settlement()
	checks["minimal projection adopts same ready receipt without lobby mutation"]=store.settlement.get("settlementId")=="ready" and store.lobby==lobby_before
	store.settlement={}
	gateway.response.data={"configVersion":store.CATALOG.data.version,"player":{"userId":"unrelated-cached-value"},"cards":[{"cardId":"unrelated"}],"wallet":{"gold":999},"unfinishedSettlement":{"settlementId":"older-server","matchId":match_id}}
	store.retry_settlement()
	checks["older server full Bootstrap reply remains safe same-match fallback"]=store.settlement.get("settlementId")=="older-server" and store.lobby==lobby_before
	store.settlement={};gateway.response.data.unfinishedSettlement.matchId="other-match"
	store.retry_settlement()
	checks["projection never adopts another match receipt"]=store.settlement.is_empty() and store.lobby==lobby_before
	store.free();gateway.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE actual current GameStore with minimal and old full wire-adapted reply shapes;no API/world/performance claim"}
