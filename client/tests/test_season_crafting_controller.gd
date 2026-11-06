extends RefCounted

# Exercise the production controller with deferred transport results. This is
# an offline ownership control; the separate real HTTP test covers transport.
class DeferredGateway extends Node:
	signal released
	var session_generation := 7
	var token := "offline-controller-token"
	var requests: Array = []
	var replies := {}
	var automatic := {}
	func request(path: String, method: int = HTTPClient.METHOD_GET, data: Variant = null, _quiet: Array = []) -> Dictionary:
		var index := requests.size()
		requests.append({"path":path,"method":method,"data":data.duplicate(true) if data is Dictionary else data})
		if automatic.has(path): return automatic[path].duplicate(true)
		while not replies.has(index): await released
		return replies[index]
	func complete(index: int, data: Dictionary) -> void:
		replies[index]=data
		released.emit()

class Controller extends "res://ui/main.gd":
	var confirmation := {}
	func _schedule_render() -> void: pass
	func _confirm(message: String, action: Callable, options: Dictionary = {}) -> void:
		confirmation={"message":message,"action":action,"options":options}
	func _toast(_message: String) -> void: pass

func run_test() -> Dictionary:
	var checks := {}
	var old_gateway: Node=Game.gateway
	var old_lobby: Dictionary=Game.lobby
	var old_busy: bool=Game.busy
	var old_muted: bool=Sound.muted
	Sound.muted=true
	var gateway := DeferredGateway.new()
	Game.gateway=gateway
	Game.busy=false
	Game.lobby={"season":{"seasonId":"s","state":"Active","hasJoined":true,"wallet":{"seasonId":"s","version":10,"blueprintMarks":5,"orangeBlueprintMarks":14,"equipmentFragments":80},"fragmentWallets":[{"seasonId":"s","version":10,"blueprintMarks":5,"orangeBlueprintMarks":14,"equipmentFragments":80}]},"materials":{"equipmentFragments":99999},"inventory":{"equipments":[]}}
	var host := Controller.new()
	host.screen="crafting"
	host._crafting_state={"season":{"seasonId":"s"},"wallet":Game.lobby.season.wallet.duplicate(true),"maximumDifficulty":5,"offers":[{"quality":"Purple","minimumDifficulty":1,"markKind":"Blueprint","markCost":4}]}
	host._craft_recipe="recipe"
	host._craft_select_body({"instanceId":"A"})
	host._craft_select_body({"instanceId":"B"})
	host._craft_select_body({"instanceId":"A"})
	gateway.complete(0,{"ok":true,"data":{"marker":"stale A"}})
	checks["A B A rejects earlier identical-body response"]=host._craft_quote.get("loading",false) and not host._craft_quote.has("marker")
	gateway.complete(1,{"ok":true,"data":{"marker":"stale B"}})
	checks["different body response rejected"]=not host._craft_quote.has("marker")
	gateway.complete(2,{"ok":true,"data":{"marker":"current A"}})
	checks["latest quote accepted"]=host._craft_quote.get("marker")=="current A"
	host._craft_select_body({"instanceId":"A"})
	host._craft_select_recipe("other")
	gateway.complete(3,{"ok":true,"data":{"marker":"old recipe"}})
	checks["recipe change clears and rejects quote"]=host._craft_quote.is_empty()
	host._craft_select_body({"instanceId":"B"})
	gateway.session_generation+=1
	gateway.complete(4,{"ok":true,"data":{"marker":"old account"}})
	checks["old account quote rejected"]=not host._craft_quote.has("marker")
	host._craft_select_body({"instanceId":"B"})
	host._crafting_epoch+=1
	gateway.complete(5,{"ok":true,"data":{"marker":"old overview"}})
	checks["overview refresh invalidates quote"]=not host._craft_quote.has("marker")
	host._craft_select_body({"instanceId":"B"})
	host.screen="gear"
	gateway.complete(6,{"ok":true,"data":{"marker":"closed screen"}})
	checks["navigation rejects late quote"]=not host._craft_quote.has("marker")
	host.screen="crafting"
	host._crafting_selection={"quality":"Purple","slot":"Hands","element":"Water","wishedEffect":"Vitality"}
	host._confirm_craft()
	var action: Callable=host.confirmation.action
	var payload: Dictionary=action.get_bound_arguments()[1]
	host._crafting_selection.element="Fire"
	checks["confirmed craft captures intent and wallet version"]=payload.element=="Water" and payload.slot=="Hands" and payload.wishedEffect=="Vitality" and payload.expectedWalletVersion==10 and payload.seasonId=="s"
	action.call()
	checks["actual command uses canonical authenticated route and captured body"]=gateway.requests[7].path=="/api/v1/season-crafting/craft" and gateway.requests[7].method==HTTPClient.METHOD_POST and gateway.requests[7].data==payload
	host.screen="gear"
	gateway.complete(7,{"ok":false,"data":{}})
	checks["rejection clears busy without touching balance"]=not Game.busy and Game.lobby.season.wallet.blueprintMarks==5 and Game.lobby.materials.equipmentFragments==99999
	var receipt := {"seasonId":"s","version":11,"blueprintMarks":1,"orangeBlueprintMarks":14,"equipmentFragments":79}
	gateway.automatic={"/api/v1/season-crafting/reforge":{"ok":true,"data":{"wallet":receipt}},"/api/v1/inventory/":{"ok":true,"data":{"equipments":[{"instanceId":"same-real-body","level":0}]}},"/api/v1/loadouts/Mage":{"ok":true,"data":{"heroClass":"Mage","equipmentIds":[]}},"/api/v1/loadouts/Priest":{"ok":true,"data":{"heroClass":"Priest","equipmentIds":[]}},"/api/v1/loadouts/Guardian":{"ok":true,"data":{"heroClass":"Guardian","equipmentIds":[]}}}
	await host._change_crafting("reforge",{"bodyEquipmentId":"same-real-body"})
	checks["success refreshes inventory and all loadouts"]=Game.lobby.inventory.equipments[0].instanceId=="same-real-body" and Game.lobby.equippedLoadouts.size()==3 and gateway.requests.size()==13
	checks["full typed wallet receipt keeps historical materials separate"]=Game.lobby.season.wallet==receipt and Game.lobby.season.fragmentWallets[0]==receipt and Game.lobby.materials.equipmentFragments==99999 and not Game.busy
	host.free()
	gateway.free()
	Game.gateway=old_gateway
	Game.lobby=old_lobby
	Game.busy=old_busy
	Sound.stop_all()
	await Engine.get_main_loop().process_frame
	Sound.muted=old_muted
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Production controller with deferred offline transport; no live HTTP or rendered screen claim."}
