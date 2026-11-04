extends RefCounted

const Controller=preload("res://ui/season_market_controller.gd")

class DeferredGateway extends Node:
	signal released
	var token := ""
	var session_generation := 8
	var requests: Array=[]
	var replies: Dictionary={}
	func request(path: String,method: int=HTTPClient.METHOD_GET,data: Variant=null,_quiet: Array=[]) -> Dictionary:
		var index := requests.size()
		requests.append({"path":path,"method":method,"data":data.duplicate(true) if data is Dictionary else data})
		while not replies.has(index):await released
		return replies[index]
	func complete(index: int,response: Dictionary) -> void:
		replies[index]=response;released.emit()

class Host extends Control:
	var screen := "market"
	var confirmation: Dictionary={}
	func _schedule_render() -> void:pass
	func _confirm(message: String,action: Callable,_options: Dictionary={}) -> void:confirmation={"message":message,"action":action}

func context(marker: String,gold: int=1000) -> Dictionary:
	var item := {"instanceId":"e","slot":"Head","quality":"Orange","element":"Fire","level":0,"version":3,"location":"Inventory","isBound":false,"originSeasonId":"s","seasonId":"s","assetScope":"ActiveSeason","statsVersion":"season-equipment-v1","sourceKind":"NaturalDrop","recipeExtracted":false}
	var listing := {"listingId":"listing","sellerId":"merchant","equipmentId":"e","currency":"Gold","price":100,"priceGold":100,"version":9,"status":"Active","seasonId":"s","expiresAt":"2099-12-31T00:00:00Z","equipment":item}
	return {"marker":marker,"policy":{"state":"Active","seasonId":"s","canTrade":true,"sharedSlots":8,"listingHours":48,"taxBasisPoints":1000,"minimumFee":1,"wallet":{"gold":gold,"diamond":500},"currencies":[{"currency":"Gold","orangePriceCap":99999,"redPriceCap":99999},{"currency":"Diamond","orangePriceCap":2000,"redPriceCap":8000}]},"inventory":{"equipments":[item],"summary":{"capacity":50,"equipmentCount":1}},"listings":[listing],"ownListings":[],"returns":[]}

func run_test() -> Dictionary:
	var checks := {}
	var saved := {}
	for field in ["gateway","lobby","busy","_cache_versions","_cache_syncing","_cache_sync_again"]:saved[field]=Game.get(field)
	var muted: bool=Sound.muted;Sound.muted=true
	var gateway := DeferredGateway.new();Game.gateway=gateway;Game.busy=false;Game._cache_versions={};Game._cache_syncing={};Game._cache_sync_again={}
	Game.lobby={"player":{"userId":"buyer"},"season":{"state":"Active","seasonId":"s"},"wallet":{"gold":321,"diamond":500},"inventory":{"equipments":[]}}
	var host := Host.new();var controller := Controller.new();controller.attach(host)
	controller.reload();controller.choose_filter("currency","Diamond");controller.choose_filter("currency","Gold")
	checks["actual read paths capture each currency"]=gateway.requests.size()==3 and gateway.requests[0].path.contains("currency=Gold") and gateway.requests[1].path.contains("currency=Diamond") and gateway.requests[2].path.contains("currency=Gold")
	gateway.complete(0,{"ok":true,"data":context("old A")})
	checks["A B A ignores first identical-currency response"]=controller.state.is_empty() and controller.loading
	gateway.complete(1,{"ok":true,"data":context("old B")})
	checks["other currency response cannot replace latest state"]=controller.state.is_empty()
	gateway.complete(2,{"ok":true,"data":context("current A")})
	checks["latest read publishes its own source wallet"]=controller.state.marker=="current A" and Game.lobby.wallet.gold==1000 and not controller.loading
	controller.confirm_buy(controller.state.listings[0])
	var captured: Callable=host.confirmation.action
	controller.state.listings[0].version=10;captured.call()
	checks["stale confirmation cannot send a write"]=gateway.requests.size()==3
	controller.state=context("ready")
	controller.confirm_buy(controller.state.listings[0]);host.confirmation.action.call()
	checks["purchase uses frozen canonical currency price and version"]=gateway.requests.size()==4 and gateway.requests[3].method==HTTPClient.METHOD_POST and gateway.requests[3].path=="/api/v1/market/listing/purchase?expectedVersion=9&currency=Gold&expectedPrice=100&seasonId=s"
	gateway.complete(3,{"ok":true,"status":200,"data":{"buyerGoldAfter":999999,"wallet":{"gold":999999,"diamond":999999},"seasonId":"old"}})
	checks["reply cannot optimistically credit a historical wallet"]=Game.lobby.wallet.gold==1000 and not Game.busy and gateway.requests.size()==5
	gateway.complete(4,{"ok":true,"data":context("after real read",900)})
	checks["current read supplies the post-purchase balance"]=Game.lobby.wallet.gold==900 and controller.state.marker=="after real read"
	controller.selected_item="e";controller.listing_currency="Diamond";controller.listing_price=2000
	controller.confirm_list()
	var args: Array=host.confirmation.action.get_bound_arguments()
	var body: Dictionary=args[1]
	controller.listing_currency="Gold";controller.listing_price=3
	checks["listing confirmation captures exact original item and source"]=body.currency=="Diamond" and body.price==2000 and body.priceGold==0 and body.expectedEquipmentVersion==3 and body.seasonId=="s"
	gateway.session_generation+=1;host.confirmation.action.call()
	checks["old-session confirmation never submits"]=gateway.requests.size()==5
	gateway.session_generation-=1
	controller.reload();host.screen="gear";gateway.complete(5,{"ok":true,"data":context("late offscreen",800)})
	checks["offscreen response cannot replace visible source"]=controller.state.marker=="after real read" and Game.lobby.wallet.gold==900
	for field in saved:Game.set(field,saved[field])
	host.free();gateway.free();Sound.stop_all();await Engine.get_main_loop().process_frame;Sound.muted=muted
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Production controller using deferred offline transport; scope/ordering and actual callbacks, not live HTTP or render evidence."}
