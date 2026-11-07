extends SceneTree
const Proto=preload("res://network/protobuf.gd")
const Model=preload("res://ui/season_activity_model.gd")
func _initialize() -> void:
	create_timer(30).timeout.connect(func():quit(1))
	call_deferred("run")
func run() -> void:
	var game=get_root().get_node("Game")
	game.set_process(false);game.gateway.set_process(false);game.gateway.persist_session=false;game.gateway.reconnect_enabled=false;game.gateway.socket.close()
	var sound=get_root().get_node("Sound");sound.persist_settings=false;sound.stop_all();sound.set_process(false)
	var folder := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	var checks := {}
	var proto := Proto.new(true)
	var events: Dictionary=proto.decode_http("SeasonActivitiesResponse",FileAccess.get_file_as_bytes(folder.path_join("events.bin")))
	checks["real authenticated events decode"]=proto.error.is_empty() and events.events.size()==2
	var active := {}
	for event in events.events:
		checks["real event model accepts "+str(event.eventId)]=Model.valid(event)
		checks["real event original season "+str(event.eventId)]=event.seasonId=="activity-api" and event.configVersion=="season-v1-config-10" and event.tokenCap==12
		if event.state=="Active": active=event
	checks["real completed extraction budget"]=not active.is_empty() and active.earned==12 and active.available==12 and active.spent==0
	checks["real four exchange branches"]=active.options.size()==4
	for option in active.options:
		checks["real authorized quote "+str(option.ruleId)]=Model.option_valid(option) and not Model.exchange_body(active,option,"Priest").is_empty()
	var exchange: Dictionary=proto.decode_http("ActivityExchangeResponse",FileAccess.get_file_as_bytes(folder.path_join("exchange.bin")))
	checks["real reservation consumes only shared12"]=proto.error.is_empty() and exchange.tokensRemaining==0 and exchange.accountVersion==active.accountVersion+1
	checks["real reservation is pending40originalfragments"]=exchange.reward.state=="Pending" and exchange.reward.rewardAmount==40 and exchange.reward.tokenCost==12 and exchange.reward.seasonId==active.seasonId and exchange.reward.eventId==active.eventId
	var claim: Dictionary=proto.decode_http("ActivityClaimResponse",FileAccess.get_file_as_bytes(folder.path_join("claim.bin")))
	checks["real claim original entitlement"]=proto.error.is_empty() and claim.reward.rewardId==exchange.reward.rewardId and claim.reward.state=="Claimed" and not claim.reward.canClaim and claim.balanceAfter==40
	var updated: Dictionary=proto.decode_http("SeasonActivitiesResponse",FileAccess.get_file_as_bytes(folder.path_join("updated.bin")))
	for event in updated.events:
		if event.eventId!=active.eventId: continue
		checks["real fresh read zero available"]=proto.error.is_empty() and Model.valid(event) and event.available==0 and event.spent==12 and event.earned==12
		checks["real fresh read claimed once"]=event.rewards.size()==1 and event.rewards[0].state=="Claimed" and not event.rewards[0].canClaim
		checks["real exhausted model disables every exchange"]=event.options.all(func(option):return Model.exchange_body(event,option,"Mage").is_empty())
	var ok: bool=not checks.values().has(false)
	FileAccess.open(folder.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":checks},"  "))
	print(JSON.stringify({"ok":ok,"checks":checks.size()}));quit(0 if ok else 1)
