extends RefCounted

const Model=preload("res://ui/season_shop_model.gd")

class Gateway extends Node:
	signal released
	var session_generation := 21
	var requests: Array=[]
	var replies: Dictionary={}
	func request(path: String,method: int=HTTPClient.METHOD_GET,data: Variant=null,_quiet: Array=[]) -> Dictionary:
		var index := requests.size()
		requests.append({"path":path,"method":method,"data":data.duplicate(true) if data is Dictionary else data})
		while not replies.has(index): await released
		return replies[index]
	func complete(index: int,response: Dictionary) -> void:
		replies[index]=response;released.emit()

class Host extends "res://ui/main.gd":
	var confirmation: Callable
	func _render() -> void: pass
	func _schedule_render() -> void: pass
	func _sync_account_session() -> void: pass
	func _toast(_message: String) -> void: pass
	func _confirm(_message: String,action: Callable,_options: Dictionary={}) -> void: confirmation=action
	func _refresh_shop_authority() -> void:
		var generation: int=Game.gateway.session_generation
		var response: Dictionary=await Game.gateway.request("/test-current-authority")
		if generation!=Game.gateway.session_generation or not response.get("ok",false): return
		Game.lobby=response.data.duplicate(true);shop=Game.lobby.shop;inventory=Game.lobby.inventory

func snapshot() -> Dictionary:
	var item := {"productId":"daily_card_1","kind":"Cards","priceGold":80,"limit":1,"purchased":0,"alreadyOwned":true,"payload":{"cardId":"C01","count":1}}
	return {"wallet":{"gold":777},"inventory":{"consumables":{}},"shop":{"resetKey":"2098-12-31","rotationKey":"2098-12-31~0","products":[item],
		"policy":{"state":"Active","canPurchase":true,"grantsPermanentCopies":true,"seasonId":"s","configVersion":"v","catalogVersion":"v","wallet":{"gold":777},"resetsAt":"2099-01-01T20:00:00Z","seasonEndsAt":"2099-02-01T00:00:00Z"}}}

func run_test() -> Dictionary:
	var saved_gateway: Variant=Game.gateway;var saved_lobby: Dictionary=Game.lobby;var saved_busy: bool=Game.busy
	var muted: bool=Sound.muted;Sound.muted=true
	var gateway := Gateway.new();Game.gateway=gateway;Game.lobby=snapshot();Game.busy=false
	var host := Host.new();host.screen="shop";host.shop=Game.lobby.shop;host.inventory=Game.lobby.inventory;host._shop_inventory_ready=true
	var item: Dictionary=host.shop.products[0];var intent := Model.purchase_body(item,host.shop)
	host._complete_shop_purchase(item,intent,host._shop_epoch)
	var checks := {}
	checks["actual main sends all captured terms"]=gateway.requests.size()==1 and gateway.requests[0].data==intent
	gateway.complete(0,{"ok":true,"data":{"goldAfter":999999,"grants":[{"kind":"EquipmentFragments","amount":999999}]}})
	checks["main does not credit receipt amounts while current read is pending"]=gateway.requests.size()==2 and Game.lobby.wallet.gold==777 and host.shop.products[0].purchased==0
	var fresh := snapshot();fresh.wallet.gold=697;fresh.shop.policy.wallet.gold=697;fresh.shop.products[0].purchased=1
	gateway.complete(1,{"ok":true,"data":fresh})
	checks["only current authority supplies balances and counters"]=Game.lobby.wallet.gold==697 and host.shop.products[0].purchased==1 and not Game.busy
	Game.lobby=snapshot();host.shop=Game.lobby.shop;host.inventory=Game.lobby.inventory
	host._purchase_shop_item(host.shop.products[0],"card");var old_confirm: Callable=host.confirmation
	host._navigate("hall");host._navigate("shop")
	var reads := gateway.requests.size();old_confirm.call()
	checks["A B A cannot reuse the original identical offer confirmation"]=gateway.requests.size()==reads
	gateway.complete(reads-1,{"ok":true,"data":snapshot()})
	host._purchase_shop_item(host.shop.products[0],"card");host.shop.products[0].purchased=1
	var before := gateway.requests.size();host.confirmation.call()
	checks["confirmation rechecks latest quota instead of captured count"]=gateway.requests.size()==before
	host.shop=snapshot().shop;Game.busy=false
	host._complete_shop_purchase(host.shop.products[0],Model.purchase_body(host.shop.products[0],host.shop),host._shop_epoch)
	var request_index := gateway.requests.size()-1;gateway.session_generation+=1;Game.busy=true
	gateway.complete(request_index,{"ok":true,"data":{"goldAfter":999999}})
	checks["old account reply neither writes funds nor clears new account busy state"]=gateway.requests.size()==request_index+1 and Game.lobby.wallet.gold==777 and Game.busy
	host.free();gateway.free();Game.gateway=saved_gateway;Game.lobby=saved_lobby;Game.busy=saved_busy;Sound.muted=muted
	return {"ok":not checks.values().has(false),"checks":checks}
