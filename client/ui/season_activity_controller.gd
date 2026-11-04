extends RefCounted

const P=preload("res://ui/palette.gd")
const Model=preload("res://ui/season_activity_model.gd")
var events: Array=[]
var selected := ""
var hero := "Mage"
var loading := false
var notice := ""
var failed := false
var next_offset: Variant=null
var _host: WeakRef
var _epoch := 0
var _action := 0

func attach(host: Control) -> void:
	_host=weakref(host)

func leave() -> void:
	_epoch+=1
	loading=false

func reset() -> void:
	leave();_action+=1;events=[];selected="";hero="Mage";notice="";failed=false;next_offset=null

func _host_node() -> Control:
	return _host.get_ref() as Control if _host!=null else null

func _render() -> void:
	var host := _host_node()
	if host!=null: host._schedule_render()

func _current(generation: int,epoch: int) -> bool:
	var host := _host_node()
	return host!=null and host.screen=="activities" and generation==Game.gateway.session_generation and epoch==_epoch

func current() -> Dictionary:
	for event in events:
		if Model.key(event)==selected: return event
	return {}

func choose(index: int) -> void:
	if Game.busy or index<0 or index>=events.size(): return
	selected=Model.key(events[index]);notice="";_epoch+=1;_render()

func choose_hero(index: int) -> void:
	if Game.busy or index<0 or index>2: return
	hero=["Mage","Priest","Guardian"][index];_epoch+=1;_render()

func reload(more: bool=false) -> void:
	var host := _host_node()
	if host==null or host.screen!="activities" or loading: return
	if more and (not next_offset is int or next_offset<0 or events.size()>=4096): return
	_epoch+=1
	var epoch := _epoch
	var generation: int=Game.gateway.session_generation
	var offset := int(next_offset) if more else 0
	loading=true;failed=false;_render()
	var response: Dictionary=await Game.gateway.request("/api/v1/season-activities?limit=50&offset="+str(offset))
	if not _current(generation,epoch) or response.get("stale_session",false): return
	loading=false
	var data: Dictionary=response.get("data",{}) if response.get("data") is Dictionary else {}
	if not response.get("ok",false) or not data.get("events") is Array:
		failed=true;notice=P.localized("activity_unavailable");_render();return
	var rows: Array=events.duplicate(true) if more else []
	var cursor: Variant=data.get("nextOffset")
	if (cursor!=null and (not cursor is int or cursor<=offset)) or rows.size()+data.events.size()>4096:
		failed=true;notice=P.localized("invalid_page_cursor");_render();return
	for event in data.events:
		if not event is Dictionary or not Model.valid(event):
			failed=true;notice=P.localized("activity_unavailable");_render();return
		rows=rows.filter(func(old):return Model.key(old)!=Model.key(event));rows.append(event)
	events=rows;next_offset=cursor
	if current().is_empty():
		selected=""
		for event in events:
			if event.get("state")=="Active": selected=Model.key(event);break
		if selected.is_empty() and not events.is_empty(): selected=Model.key(events[0])
	_render()

func confirm_exchange(option: Dictionary) -> void:
	var host := _host_node()
	var event := current().duplicate(true)
	var body := Model.exchange_body(event,option,hero)
	if host==null or Game.busy or loading or failed or body.is_empty(): return
	var message: String=P.localized("activity_confirm_exchange") % [option.costTokens,Model.reward_title(option.merged({"heroClass":hero})),Model.event_title(event)]
	host._confirm(message,_exchange.bind(event,body,Game.gateway.session_generation,_epoch))

func _exchange(event: Dictionary,body: Dictionary,generation: int,epoch: int) -> void:
	if not _current(generation,epoch) or failed or loading: return
	var latest := current()
	if Model.key(latest)!=Model.key(event) or latest.get("accountVersion")!=event.get("accountVersion"): return
	for option in latest.get("options",[]):
		if option.get("ruleId")==body.ruleId and Model.exchange_body(latest,option,str(body.get("heroClass",hero)))==body:
			_write("/api/v1/season-activities/"+str(event.eventId).uri_encode()+"/exchanges",body,generation);return

func confirm_claim(reward: Dictionary) -> void:
	var host := _host_node()
	if host==null or Game.busy or loading or failed or not reward.get("canClaim",false) or reward.get("state")!="Pending": return
	var captured := reward.duplicate(true)
	host._confirm(P.localized("activity_confirm_claim") % [Model.reward_title(captured),str(captured.get("seasonId",""))],_claim.bind(captured,Game.gateway.session_generation,_epoch))

func _claim(reward: Dictionary,generation: int,epoch: int) -> void:
	if not _current(generation,epoch) or failed or loading: return
	for latest in current().get("rewards",[]):
		if latest==reward and latest.get("state")=="Pending" and latest.get("canClaim",false):
			_write("/api/v1/season-activities/rewards/"+str(reward.rewardId).uri_encode()+"/claim",{},generation);return

func _write(path: String,body: Dictionary,generation: int) -> void:
	if Game.busy or generation!=Game.gateway.session_generation: return
	_action+=1
	var action := _action
	Game.busy=true;_render()
	var response: Dictionary=await Game.gateway.request(path,HTTPClient.METHOD_POST,body)
	if action!=_action or generation!=Game.gateway.session_generation or response.get("stale_session",false): return
	# The receipt describes the original event. Current balances always come from
	# authenticated reads, including after a timeout whose commit is uncertain.
	await Game.refresh_lobby()
	if action!=_action or generation!=Game.gateway.session_generation: return
	Game.busy=false
	notice=P.localized("operation_success" if response.get("ok",false) else "activity_refresh_after_write")
	failed=false
	reload()
