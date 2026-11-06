extends RefCounted

const Model=preload("res://ui/season_shop_model.gd")

func run_test() -> Dictionary:
	var product := {"productId":"advanced_bag","kind":"AdvancedBag","priceGold":800,"limit":0,"purchased":30,"payload":{"amount":1}}
	var policy := {"state":"Active","canPurchase":true,"grantsPermanentCopies":true,"seasonId":"s","configVersion":"active",
		"catalogVersion":"frozen","resetsAt":"2099-01-01T20:00:00+00:00","seasonEndsAt":"2099-02-01T00:00:00+00:00","wallet":{"gold":1000}}
	var shop := {"policy":policy,"resetKey":"2098-12-31","rotationKey":"2098-12-31~0","products":[product]}
	var checks := {}
	checks["no invented daily bag limit"]=Model.reason(product,shop,{},true,{"gold":0}).is_empty()
	checks["both paid bag types share storage3"]=Model.reason(product,shop,{"advancedBagCount":2,"topBagCount":1},true,{})=="inventory_full"
	checks["unknown stock cannot buy"]=Model.reason(product,shop,{},false,{})=="refresh_inventory"
	checks["current seasonal wallet overrides a richer permanent wallet"]=Model.gold(shop,{"gold":999999})==1000
	var body := Model.purchase_body(product,shop)
	checks["confirmation pins all actual offer terms"]=body=={"productId":"advanced_bag","quantity":1,"seasonId":"s","resetKey":"2098-12-31","rotationKey":"2098-12-31~0","expectedPriceGold":800,"catalogVersion":"frozen"}
	checks["current confirmation matches"]=Model.current_intent(body,shop)
	var newer: Dictionary=shop.duplicate(true);newer.policy.seasonId="next"
	checks["cross-season confirmation rejected"]=not Model.current_intent(body,newer)
	newer=shop.duplicate(true);newer.rotationKey="2098-12-31~1"
	checks["refreshed confirmation rejected"]=not Model.current_intent(body,newer)
	newer=shop.duplicate(true);newer.products[0].priceGold=1
	checks["changed price confirmation rejected"]=not Model.current_intent(body,newer)
	var card := {"productId":"daily_card_1","kind":"Cards","priceGold":80,"limit":1,"purchased":0,"alreadyOwned":true,"payload":{"cardId":"C01"}}
	checks["owned single remains a purchasable copy"]=Model.reason(card,shop,{},true,{}).is_empty()
	checks["same daily slot cannot be bought twice"]=Model.reason(card.merged({"purchased":1},true),shop,{},true,{})=="season_shop_limit_reached"
	checks["legacy owned single keeps its old rule"]=Model.reason(card,{}, {},true,{"gold":1000})=="activated"
	newer=shop.duplicate(true);newer.policy.state="Unavailable";newer.policy.canPurchase=false
	checks["missing frozen catalog does not use legacy funds"]=Model.purchase_body(product,newer).is_empty() and not Model.open(newer)
	checks["expired reset is closed"]=not Model.open(shop,4102444801.0)
	return {"ok":not checks.values().has(false),"checks":checks}
