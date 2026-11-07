extends RefCounted

const Proto=preload("res://network/protobuf.gd")
const View=preload("res://ui/red_reward_view.gd")
const Reference=preload("res://ui/reference_ui.gd")

class Host extends Control:
	func _schedule_render() -> void: pass

class CaptureGateway extends Node:
	var online := true
	var recovering := false
	var session_generation := 10
	var room_revision := 7
	var requests: Array=[]
	func new_id() -> String: return "offline-red-"+str(requests.size())
	func capture_context() -> Dictionary: return {"session_generation":session_generation}
	func send(action: String,payload: Dictionary={},request_id: String="") -> bool:
		requests.append({"action":action,"payload":payload.duplicate(true),"request_id":request_id})
		return true

func run_test() -> Dictionary:
	var checks := {}
	var item := {"item_id":"00000000-0000-0000-0000-000000000001","kind":"Equipment","quantity":1,"equipment":{"slot":"Head","quality":"Red","level":0,"element":"Fire","effect_affix":"Piercing","secondary_trait":"DrawInterval","unique_affix":"Inferno","unique_element":"Fire","stats_version":"season-equipment-v1"}}
	var proto := Proto.new()
	var decoded: Dictionary=proto.decode("RoomPlayer",proto.encode("RoomPlayer",{"red_evaluation_pending":true,"pending_red_item":item}))
	checks["wire preserves pending evaluation and original red"]=proto.error.is_empty() and decoded.red_evaluation_pending and decoded.pending_red_item.item_id==item.item_id and decoded.pending_red_item.equipment.unique_affix=="Inferno" and decoded.pending_red_item.equipment.unique_element=="Fire" and decoded.pending_red_item.equipment.stats_version=="season-equipment-v1" and decoded.pending_red_item.equipment.level==0
	var old: Dictionary=proto.decode("RoomPlayer",proto.encode("RoomPlayer",{}))
	checks["old wire defaults stay absent or false"]=not old.red_evaluation_pending and old.get("pending_red_item")==null
	var saved := {}
	for field in ["gateway","room","configuration_error","_queued_command","_pending_commands","_latest_commands","_sound_commands","_rejected_state_request","_command_recovery_context","_room_context_epoch","_play_deadline"]:
		saved[field]=Game.get(field)
	var gateway := CaptureGateway.new();Game.gateway=gateway
	Game.configuration_error="";Game._queued_command={};Game._pending_commands={};Game._latest_commands={};Game._sound_commands={};Game._rejected_state_request={};Game._command_recovery_context={}
	var replacement := {"item_id":"old-bag-item","kind":"HealthPotion","quantity":1,"slot_index":0}
	Game.room={"room_id":"offline-room","match_id":"offline-match","room_revision":7,"allowed_actions":["choice.read","choice.pick"],"player":{"phase":"Choice","pending_red_item":item,"inventory":[replacement]}}
	checks["pending red is a valid claim intent"]=Game._intent_valid("reward.choice.claim",{"option_id":"red:"+item.item_id})
	checks["other red id is rejected"]=not Game._intent_valid("reward.choice.claim",{"option_id":"red:other"})
	var pending := {"room_id":"offline-room","action":"reward.choice.claim","sent_revision":7,"payload":{"option_id":"red:"+item.item_id}}
	var newer: Dictionary=Game.room.duplicate(true);newer.room_revision=8
	checks["shared revision cannot confirm an unclaimed red"]=not Game._snapshot_confirms_command(pending,newer)
	newer.player.erase("pending_red_item")
	checks["claim confirmation waits for authoritative item removal"]=Game._snapshot_confirms_command(pending,newer)
	var host := Host.new();var ui := Reference.new();host.add_child(ui)
	View.build(ui,host,Game.room.player)
	checks["pending view uses reserved item and replacement control"]=ui.get_node_or_null("RedRewardPanel")!=null and ui.get_node_or_null("RedOpenReplacement")!=null
	ui.get_node("RedOpenReplacement").pressed.emit()
	checks["opening picker does not send a claim"]=host.get_meta("red_reward_stage")=="replace" and gateway.requests.is_empty()
	for child in ui.get_children(): child.free()
	View.build(ui,host,Game.room.player)
	ui.get_node("RedReplacementScroll").get_child(0).get_child(0).pressed.emit()
	checks["selecting a replacement requires confirmation"]=host.get_meta("red_reward_stage")=="confirm" and gateway.requests.is_empty()
	for child in ui.get_children(): child.free()
	View.build(ui,host,Game.room.player)
	ui.get_node("RedReplaceConfirm").pressed.emit()
	checks["confirm sends exact reserved id and replacement"]=gateway.requests.size()==1 and gateway.requests[0].action=="reward.choice.claim" and gateway.requests[0].payload.option_id=="red:"+item.item_id and gateway.requests[0].payload.replace_item_id==replacement.item_id
	Game._queued_command={};Game._pending_commands={};Game._sound_commands={}
	Game.room.player.erase("pending_red_item");View._claim(item,replacement.item_id)
	checks["stale confirmation after authoritative removal cannot send"]=gateway.requests.size()==1
	for field in saved:Game.set(field,saved[field])
	host.free();gateway.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Actual controller, replacement UI callbacks and binary codec using captured offline transport. Render and database evidence are separate."}
