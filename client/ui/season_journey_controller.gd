extends RefCounted

const Model=preload("res://ui/season_journey_model.gd")
var state: Dictionary={}
var seasons: Array=[]
var selected := ""
var next_offset: Variant=null
var loading := false
var failed := false
var level_scroll := -1
var contract_scroll := 0
var _epoch := 0
var _host: WeakRef

func attach(host: Control) -> void:
	_host=weakref(host)

func leave() -> void:
	_epoch+=1;loading=false

func reset() -> void:
	leave();state={};seasons=[];selected="";next_offset=null;failed=false;level_scroll=-1;contract_scroll=0

func _host_node() -> Control:
	return _host.get_ref() as Control if _host!=null else null

func _render() -> void:
	var host := _host_node()
	if host!=null: host._schedule_render()

func _current(generation: int,epoch: int) -> bool:
	var host := _host_node()
	return host!=null and host.screen=="journey" and generation==Game.gateway.session_generation and epoch==_epoch

func choose(index: int) -> void:
	if loading or Game.busy or index<0 or index>=seasons.size(): return
	selected=str(seasons[index].get("seasonId",""));level_scroll=-1;contract_scroll=0;state={};reload()

func reload(more: bool=false) -> void:
	var host := _host_node()
	if host==null or host.screen!="journey" or loading: return
	if more and (not next_offset is int or next_offset<0 or seasons.size()>=4096): return
	_epoch+=1
	var epoch := _epoch
	var generation: int=Game.gateway.session_generation
	var offset := int(next_offset) if more else 0
	var source := str(state.seasonId) if more and selected.is_empty() and state.get("seasonId") is String else selected
	var path := "/api/v1/season-journey?limit=50&offset="+str(offset)
	if not source.is_empty(): path+="&seasonId="+source.uri_encode()
	loading=true;failed=false;_render()
	var response: Dictionary=await Game.gateway.request(path)
	if not _current(generation,epoch) or response.get("stale_session",false): return
	loading=false
	var data: Dictionary=response.get("data",{}) if response.get("data") is Dictionary else {}
	if not response.get("ok",false) or not Model.valid(data): failed=true;state={};_render();return
	var cursor: Variant=data.get("nextOffset")
	if (cursor!=null and (not cursor is int or cursor<=offset or cursor>1000000)) or (more and seasons.size()+data.seasons.size()>4096): failed=true;state={};_render();return
	if not source.is_empty() and data.state!="None" and data.get("seasonId")!=source: failed=true;state={};_render();return
	var rows: Array=seasons.duplicate(true) if more else []
	for item in data.seasons:
		if not item is Dictionary or str(item.get("seasonId","")).is_empty(): failed=true;state={};_render();return
		rows=rows.filter(func(old):return old.get("seasonId")==null or old.get("seasonId")!=item.seasonId);rows.append(item)
	if data.get("seasonId") is String and not str(data.seasonId).is_empty() and not rows.any(func(row):return row.get("seasonId")==data.seasonId):
		rows.append({"seasonId":data.seasonId,"state":data.state,"configVersion":data.get("configVersion"),"startsAt":data.get("startsAt"),"endsAt":data.get("endsAt")})
	seasons=rows;next_offset=cursor;state=data;_render()

func save_level_scroll(value: float) -> void:
	level_scroll=int(value)

func save_contract_scroll(value: float) -> void:
	contract_scroll=int(value)
