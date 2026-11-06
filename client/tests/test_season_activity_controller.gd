extends RefCounted

const Controller=preload("res://ui/season_activity_controller.gd")
const Inputs=preload("res://tests/test_season_activity_model.gd")

class Gateway extends Node:
	signal released
	var session_generation := 31
	var room_id := ""
	var room_revision := 0
	var requests: Array=[]
	var replies: Dictionary={}
	func request(path: String,method: int=HTTPClient.METHOD_GET,data: Variant=null,_quiet: Array=[]) -> Dictionary:
		var index := requests.size()
		requests.append({"path":path,"method":method,"data":data.duplicate(true) if data is Dictionary else data})
		while not replies.has(index): await released
		return replies[index]
	func complete(index: int,response: Dictionary) -> void:
		replies[index]=response;released.emit()

class Host extends Control:
	var screen := "activities"
	var confirmation: Callable
	func _schedule_render() -> void: pass
	func _confirm(_message: String,action: Callable,_options: Dictionary={}) -> void: confirmation=action

class MainHost extends "res://ui/main.gd":
	var confirmation: Callable
	func _render() -> void: pass
	func _schedule_render() -> void: pass
	func _sync_account_session() -> void: pass
	func _confirm(_message: String,action: Callable,_options: Dictionary={}) -> void: confirmation=action

func bootstrap() -> Dictionary:
	return {"configVersion":Game.CATALOG.data.version,"player":{"userId":"account","selectedClass":"Mage"},"wallet":{"gold":321},"materials":{},"shop":{},"inventory":{},"market":[],"mail":{},"activePreparation":null}

func run_test() -> Dictionary:
	var saved := {}
	var was_muted: bool=Sound.muted;Sound.muted=true
	for field in ["gateway","lobby","busy","room","preparation","ticket","settlement","_cache_versions","_lobby_request_epoch","mail","hero_class"]: saved[field]=Game.get(field)
	Game.room={};Game.preparation={};Game.ticket={};Game.settlement={};Game._cache_versions={}
	var gateway := Gateway.new();Game.gateway=gateway;Game.lobby=bootstrap();Game.busy=false
	var host := Host.new();var c := Controller.new();c.attach(host)
	var checks := {}
	c.reload();c.leave();c.reload()
	var e := Inputs.event()
	gateway.complete(0,{"ok":true,"data":{"events":[e]}})
	checks["old A read cannot replace current A"]=c.events.is_empty() and c.loading
	gateway.complete(1,{"ok":true,"data":{"events":[e]}})
	checks["current authenticated read loads its own budget"]=c.events.size()==1 and c.current().available==12 and not c.loading
	c.confirm_exchange(e.options[0]);var old: Callable=host.confirmation;c.leave();old.call()
	checks["A B A confirmation invalidated"]=gateway.requests.size()==2
	c.confirm_exchange(e.options[0]);c.events[0].accountVersion+=1;host.confirmation.call()
	checks["changed budget version invalidates confirmation"]=gateway.requests.size()==2
	c.events=[Inputs.event()];c.confirm_exchange(c.events[0].options[1]);c.choose_hero(1);host.confirmation.call()
	checks["changed class invalidates previous confirmation"]=gateway.requests.size()==2
	c.confirm_exchange(c.current().options[0]);host.confirmation.call()
	checks["actual intent submits original shared budget version"]=gateway.requests.size()==3 and gateway.requests[2].data.expectedAccountVersion==9007199254740997 and Game.busy
	gateway.complete(2,{"ok":true,"data":{"tokensRemaining":999999,"balanceAfter":999999}})
	checks["mutation response cannot credit funds or budget"]=gateway.requests.size()==4 and Game.lobby.wallet.gold==321 and c.current().available==12 and Game.busy
	var fresh := bootstrap();fresh.wallet.gold=300
	gateway.complete(3,{"ok":true,"data":fresh})
	checks["fresh bootstrap supplies current balance"]=gateway.requests.size()==5 and Game.lobby.wallet.gold==300 and not Game.busy
	var after := Inputs.event();after.spent=3;after.available=9;after.accountVersion+=1
	var reward := {"rewardId":"owned-reward","seasonId":after.seasonId,"eventId":after.eventId,"configVersion":after.configVersion,"rewardKind":"bound_fragments","rewardAmount":10,"state":"Pending","canClaim":true}
	after.rewards=[reward];gateway.complete(4,{"ok":true,"data":{"events":[after]}})
	checks["authoritative read restores pending entitlement"]=c.current().available==9 and c.current().rewards.size()==1
	c.confirm_claim(reward);c.events[0].rewards[0].state="Claimed";host.confirmation.call()
	checks["changed reward cannot claim twice"]=gateway.requests.size()==5
	c.events[0].rewards[0].state="Pending";c.confirm_claim(c.current().rewards[0]);host.confirmation.call()
	checks["claim path uses immutable original reward"]=gateway.requests.size()==6 and gateway.requests[5].path.ends_with("/owned-reward/claim") and gateway.requests[5].data.is_empty()
	gateway.session_generation+=1;Game.busy=true;gateway.complete(5,{"ok":true,"data":{"balanceAfter":999999}})
	checks["old account reply neither credits nor clears new busy state"]=Game.busy and Game.lobby.wallet.gold==300 and gateway.requests.size()==6
	Game.busy=false
	var main := MainHost.new();main.screen="activities";main.activity_controller.attach(main)
	main.activity_controller.events=[Inputs.event()];main.activity_controller.selected="old-season/activity-one"
	main.activity_controller.confirm_exchange(main.activity_controller.current().options[0])
	var main_confirm: Callable=main.confirmation
	main._navigate("hall");main._navigate("activities")
	var count := gateway.requests.size();main_confirm.call()
	checks["actual Main navigation invalidates original confirmation"]=count==7 and gateway.requests.size()==count and gateway.requests[-1].path.begins_with("/api/v1/season-activities?")
	gateway.complete(count-1,{"ok":true,"data":{"events":[Inputs.event()]}})
	checks["actual Main activity navigation reloads authoritative event"]=main.activity_controller.current().available==12 and not main.activity_controller.loading
	main.free()
	c.reset();Game.busy=false
	c.reload();var page := gateway.requests.size()-1
	gateway.complete(page,{"ok":true,"data":{"events":[Inputs.event()],"nextOffset":1}})
	var selection := c.selected;c.reload(true)
	checks["history cursor is sent as bounded original offset"]=gateway.requests[-1].path.ends_with("offset=1")
	var second := Inputs.event();second.eventId="activity-two"
	gateway.complete(page+1,{"ok":true,"data":{"events":[second],"nextOffset":null}})
	checks["history page appends without changing original selection"]=c.events.size()==2 and c.selected==selection and c.next_offset==null
	var before := gateway.requests.size();c.reload(true)
	checks["completed history has no further request"]=gateway.requests.size()==before
	c.reload();gateway.complete(before,{"ok":true,"data":{"events":[Inputs.event()],"nextOffset":0}})
	checks["nonadvancing cursor rejects page"]=c.failed and not c.loading
	c.confirm_exchange(c.current().options[0])
	checks["failed refreshed page blocks cached exchange"]=gateway.requests.size()==before+1
	for field in saved: Game.set(field,saved[field])
	host.free();gateway.free()
	Sound.muted=was_muted
	return {"ok":not checks.values().has(false),"checks":checks}
