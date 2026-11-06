extends RefCounted

const P=preload("res://ui/palette.gd")
const Model=preload("res://ui/season_market_model.gd")
const Details=preload("res://ui/equipment_details.gd")

var state: Dictionary={}
var filters := {"currency":"Gold","quality":"","slot":"","element":"","effect":"","sort":"recent","materialsOnly":false}
var tab := "browse"
var selected_item := ""
var listing_currency := "Gold"
var listing_price := 100
var relist_target: Dictionary={}
var displayed := 30
var loading := false
var notice := ""
var _host: WeakRef
var _epoch := 0
var _publishing := false
var _refresh_queued := false
var _returns_loading := false

func attach(host: Control) -> void:
	_host=weakref(host)

func reset() -> void:
	_epoch+=1
	state={};tab="browse";selected_item="";listing_currency="Gold";listing_price=100;relist_target={};displayed=30;loading=false;notice=""
	filters={"currency":"Gold","quality":"","slot":"","element":"","effect":"","sort":"recent","materialsOnly":false}
	_publishing=false;_refresh_queued=false;_returns_loading=false

func _host_node() -> Control:
	return _host.get_ref() as Control if _host!=null else null

func _render() -> void:
	var host := _host_node()
	if host!=null: host._schedule_render()

func _current(generation: int,epoch: int) -> bool:
	var host := _host_node()
	return host!=null and host.screen=="market" and generation==Game.gateway.session_generation and epoch==_epoch

func on_cache_changed(module: String) -> void:
	var host := _host_node()
	if _publishing or host==null or host.screen!="market" or module not in ["market","inventory","wallet","season"]: return
	if _refresh_queued: return
	_refresh_queued=true
	call_deferred("_queued_reload",Game.gateway.session_generation,_epoch)

func _queued_reload(generation: int,epoch: int) -> void:
	if epoch!=_epoch or generation!=Game.gateway.session_generation: return
	_refresh_queued=false
	if _current(generation,epoch): reload()

func reload() -> void:
	_refresh_queued=false
	var host := _host_node()
	if host==null or host.screen!="market": return
	_epoch+=1
	var epoch := _epoch
	var generation: int=Game.gateway.session_generation
	loading=true
	_render()
	var parts: Array[String]=[]
	for key in ["currency","quality","slot","element","effect","sort"]:
		if not str(filters[key]).is_empty(): parts.append(key+"="+str(filters[key]).uri_encode())
	if filters.materialsOnly: parts.append("materialsOnly=true")
	var response: Dictionary=await Game.gateway.request("/api/v1/market/context?"+"&".join(parts))
	if not _current(generation,epoch) or response.get("stale_session",false): return
	loading=false
	var data: Dictionary=response.get("data",{}) if response.get("data") is Dictionary else {}
	if not response.get("ok",false) or not data.get("policy") is Dictionary:
		state={"error":true};_render();return
	var summary: Dictionary=Game.lobby.get("season",{}) if Game.lobby.get("season") is Dictionary else {}
	var season: Variant=summary.get("seasonId") if summary.get("state")=="Active" else null
	if data.policy.get("seasonId")!=season:
		state={"stale":true}
		Game.refresh_lobby()
		_render()
		return
	state=data
	_publishing=true
	if data.get("inventory") is Dictionary: Game.update_cache("inventory",data.inventory)
	if data.policy.get("wallet") is Dictionary: Game.update_cache("wallet",data.policy.wallet)
	_publishing=false
	_render()

func choose_filter(field: String,value: Variant) -> void:
	if Game.busy or not filters.has(field): return
	filters[field]=value;displayed=30;state={}
	reload()

func choose_tab(value: String) -> void:
	tab=value;displayed=30;relist_target={};_render()

func select_item(id: String) -> void:
	selected_item=id;listing_price=mini(listing_price,maxi(1,selected_cap()));_render()

func choose_currency(value: String) -> void:
	listing_currency=value
	if relist_target.is_empty() and not Model.eligible(selected(),state.get("policy",{}),value): selected_item=""
	listing_price=mini(listing_price,maxi(1,selected_cap()));_render()

func selected() -> Dictionary:
	if not relist_target.is_empty(): return relist_target.get("equipment",{})
	for item in state.get("inventory",{}).get("equipments",[]):
		if str(item.get("instanceId",""))==selected_item: return item
	return {}

func selected_cap() -> int:
	return Model.cap(state.get("policy",{}),listing_currency,str(selected().get("quality","")))

func edit_listing(listing: Dictionary) -> void:
	if Game.busy: return
	relist_target=listing.duplicate(true);listing_currency=Model.currency(listing);listing_price=Model.price(listing);tab="sell";_render()

func show_more() -> void:
	displayed+=30;_render()

func more_returns() -> void:
	var offset: Variant=state.get("returnsNextOffset")
	if _returns_loading or not offset is int or offset<0: return
	var epoch := _epoch
	var generation: int=Game.gateway.session_generation
	_returns_loading=true;_render()
	var response: Dictionary=await Game.gateway.request("/api/v1/market/returns?limit=32&offset="+str(offset))
	if not _current(generation,epoch) or response.get("stale_session",false): return
	_returns_loading=false
	if response.get("ok",false) and response.get("data") is Dictionary:
		var rows: Array=state.get("returns",[]).duplicate(true)
		var next_offset: Variant=response.data.get("nextOffset")
		if rows.size()+response.data.get("items",[]).size()>4096 or (next_offset!=null and int(next_offset)<=int(offset)):
			notice=P.localized("invalid_page_cursor")
		else:
			for row in response.data.get("items",[]):
				rows=rows.filter(func(old):return old.get("returnId")!=row.get("returnId"));rows.append(row)
			state["returns"]=rows;state["returnsNextOffset"]=next_offset;displayed=rows.size()
	else: notice=P.localized("season_market_error")
	_render()

func _find_listing(captured: Dictionary) -> bool:
	for entry in state.get("listings",[])+state.get("ownListings",[]):
		if Model.same_listing(captured,entry): return true
	return false

func confirm_buy(listing: Dictionary) -> void:
	var host := _host_node()
	if host==null or Game.busy or loading or not Model.live(listing,state.get("policy",{})): return
	var captured := listing.duplicate(true)
	var label: String=P.localized("season_market_confirm_buy") % [Details.title(captured.get("equipment",{})),Model.money(Model.price(captured),Model.currency(captured))]
	host._confirm(label,_buy.bind(captured,Game.gateway.session_generation))

func _buy(captured: Dictionary,generation: int) -> void:
	if generation!=Game.gateway.session_generation or not _find_listing(captured) or not Model.live(captured,state.get("policy",{})):
		notice=P.localized("season_market_stale");_render();return
	_write(Model.purchase_path(captured),HTTPClient.METHOD_POST,{},generation,"purchase")

func confirm_list() -> void:
	var host := _host_node()
	var item := selected().duplicate(true)
	var policy: Dictionary=state.get("policy",{})
	var maximum: int=Model.cap(policy,listing_currency,str(item.get("quality","")))
	if host==null or Game.busy or loading or item.is_empty() or listing_price<1 or listing_price>maximum: return
	var generation: int=Game.gateway.session_generation
	var price := listing_price
	var currency := listing_currency
	var fee: int=Model.fee(policy,price)
	var message: String=P.localized("season_market_confirm_list") % [Details.title(item),Model.money(price,currency),Model.money(price-fee,currency)]
	if not relist_target.is_empty():
		var captured := relist_target.duplicate(true)
		var body := {"currency":currency,"price":price,"expectedVersion":int(captured.get("version",0)),"seasonId":policy.get("seasonId")}
		host._confirm(message,_relist.bind(captured,body,generation))
	elif Model.eligible(item,policy,currency):
		var body := Model.listing_body(item,policy,currency,price)
		host._confirm(message,_list.bind(item,body,generation))

func _list(item: Dictionary,body: Dictionary,generation: int) -> void:
	if generation!=Game.gateway.session_generation or state.get("policy",{}).get("seasonId")!=body.get("seasonId"): return
	if not state.get("inventory",{}).get("equipments",[]).any(func(current):return current.get("instanceId")==item.get("instanceId") and current.get("version")==item.get("version")):
		notice=P.localized("season_market_stale");_render();return
	_write("/api/v1/market/listings",HTTPClient.METHOD_POST,body,generation,"list")

func _relist(captured: Dictionary,body: Dictionary,generation: int) -> void:
	if generation!=Game.gateway.session_generation or not _find_listing(captured) or state.get("policy",{}).get("seasonId")!=body.get("seasonId"): return
	_write("/api/v1/market/listings/"+str(captured.listingId).uri_encode()+"/relist",HTTPClient.METHOD_POST,body,generation,"list")

func confirm_cancel(listing: Dictionary) -> void:
	var host := _host_node()
	if host==null or Game.busy or listing.get("sellerId")!=Game.lobby.get("player",{}).get("userId"): return
	var captured := listing.duplicate(true)
	host._confirm(P.localized("season_market_confirm_cancel") % Details.title(captured.get("equipment",{})),_cancel.bind(captured,Game.gateway.session_generation))

func _cancel(captured: Dictionary,generation: int) -> void:
	if generation!=Game.gateway.session_generation or not _find_listing(captured): return
	_write("/api/v1/market/listings/"+str(captured.listingId).uri_encode(),HTTPClient.METHOD_DELETE,{},generation,"cancel")

func confirm_return(hold: Dictionary) -> void:
	var host := _host_node()
	if host==null or Game.busy or not hold.get("canClaim",false): return
	var item: Dictionary=hold.get("equipment",{}).duplicate(true)
	var body := {"expectedEquipmentVersion":int(item.get("version",0)),"seasonId":item.get("seasonId")}
	host._confirm(P.localized("season_market_confirm_return") % [Details.title(item),str(item.get("seasonId",P.localized("season_market_legacy")))],
		_return.bind(str(hold.get("returnId","")),body,Game.gateway.session_generation))

func _return(id: String,body: Dictionary,generation: int) -> void:
	if generation!=Game.gateway.session_generation or not state.get("returns",[]).any(func(row):return row.get("returnId")==id and row.get("equipment",{}).get("version")==body.expectedEquipmentVersion): return
	_write("/api/v1/market/returns/"+id.uri_encode()+"/claim",HTTPClient.METHOD_POST,body,generation,"return")

func _write(path: String,method: int,body: Dictionary,generation: int,action: String) -> void:
	var host := _host_node()
	if host==null or host.screen!="market" or generation!=Game.gateway.session_generation or Game.busy: return
	Game.busy=true;_render()
	var result: Dictionary=await Game.gateway.request(path,method,body)
	if generation!=Game.gateway.session_generation or result.get("stale_session",false): return
	_publishing=true
	await Game.refresh_cache("inventory")
	if generation!=Game.gateway.session_generation: return
	await Game.refresh_cache("wallet")
	if generation!=Game.gateway.session_generation: return
	_publishing=false
	Game.busy=false
	if result.get("ok",false):
		notice=P.localized("operation_success");Sound.play_cue("purchase" if action=="purchase" else "equip")
		if action=="list": tab="own";relist_target={};selected_item=""
	else:
		notice=P.localized("season_market_unknown" if int(result.get("status",0))==0 else "season_market_stale")
		Sound.play_cue("error")
	# Mutation replies may belong to the preceding season. Balances and available
	# inventory always come from current authenticated reads, never optimistic credit.
	reload()
