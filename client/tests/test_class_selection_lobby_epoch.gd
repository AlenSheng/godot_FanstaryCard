extends RefCounted
class ClassGateway extends Node:
	var session_generation := 1
	var token := "test-session"
	var room_id := ""
	var room_revision := 0
	var held := {"done":false}
	var old_bootstrap: Dictionary={}
	var calls: Array=[]
	func request(path: String,_method: int=HTTPClient.METHOD_GET,payload: Variant=null,_quiet: Array=[]) -> Dictionary:
		calls.append(path)
		if path=="/api/v1/bootstrap":
			while not held.done:await Engine.get_main_loop().process_frame
			return {"ok":true,"status":200,"data":old_bootstrap.duplicate(true)}
		return {"ok":true,"status":200,"data":{"userId":"player","displayName":"Profile","selectedClass":payload.selectedClass,"version":2}}
func run_test() -> Dictionary:
	var tree=Engine.get_main_loop();var store: Node=load("res://state/game_store.gd").new();var gateway:=ClassGateway.new();store.gateway=gateway
	store.lobby={"configVersion":store.CATALOG.data.version,"player":{"userId":"player","displayName":"Profile","selectedClass":"Mage","version":1},"wallet":{},"materials":{},"cards":[],"decks":[],"shop":{},"market":[],"inventory":{},"mail":{"items":[],"unreadCount":0},"activePreparation":null,"unfinishedMatch":null,"unfinishedSettlement":null}
	gateway.old_bootstrap=store.lobby.duplicate(true);store.hero_class="Mage";store.refresh_lobby();await tree.process_frame
	var checks: Dictionary={"old real lobby consumer is suspended before class write":gateway.calls==["/api/v1/bootstrap"] and not gateway.held.done}
	store.select_class("Priest")
	checks["successful class write applies new version before old reply"]=store.lobby.player.selectedClass=="Priest" and store.lobby.player.version==2 and store.hero_class=="Priest" and not store._class_switch_request_active
	gateway.held.done=true;await tree.process_frame;await tree.process_frame
	checks["late prewrite Bootstrap cannot restore old class or player version"]=store.lobby.player.selectedClass=="Priest" and store.lobby.player.version==2 and store.hero_class=="Priest"
	store.free();gateway.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"OFFLINE real public class selection and suspended Bootstrap consumer;no API/world/performance claim"}
