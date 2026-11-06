extends RefCounted

const GatewayScript=preload("res://network/gateway.gd")

static func policy(shop: Dictionary) -> Dictionary:
	return shop.policy if shop.get("policy") is Dictionary else {}

static func copies_enabled(shop: Dictionary) -> bool:
	return bool(policy(shop).get("grantsPermanentCopies",false))

static func gold(shop: Dictionary,legacy_wallet: Dictionary) -> int:
	var rules := policy(shop)
	if rules.is_empty(): return int(legacy_wallet.get("gold",0)) if not shop.get("policy") is Dictionary else 0
	var wallet: Dictionary=rules.wallet if rules.get("wallet") is Dictionary else {}
	return maxi(0,int(wallet.get("gold",0)))

static func open(shop: Dictionary,now: float=-1) -> bool:
	var rules := policy(shop)
	if rules.is_empty(): return not shop.get("policy") is Dictionary
	if rules.get("state")!="Active" or not rules.get("canPurchase",false): return false
	if now<0: now=Time.get_unix_time_from_system()
	for field in ["seasonId","configVersion","catalogVersion","resetsAt","seasonEndsAt"]:
		if not rules.get(field) is String or str(rules[field]).is_empty(): return false
	return GatewayScript.parse_expiry(str(rules.resetsAt))>now and GatewayScript.parse_expiry(str(rules.seasonEndsAt))>now

static func reason(item: Dictionary,shop: Dictionary,consumables: Dictionary,stock_ready: bool,legacy_wallet: Dictionary,now: float=-1) -> String:
	if not open(shop,now): return "season_shop_closed"
	if int(item.get("priceGold",0))<1: return "quote_unavailable_short"
	var limit := int(item.get("limit",0))
	if limit>0 and int(item.get("purchased",0))>=limit: return "season_shop_limit_reached"
	var payload: Dictionary=item.payload if item.get("payload") is Dictionary else {}
	if item.get("kind") in ["AdvancedBag","TopBag"]:
		if not stock_ready: return "refresh_inventory"
		if int(consumables.get("advancedBagCount",0))+int(consumables.get("topBagCount",0))+int(payload.get("amount",1))>3: return "inventory_full"
	if not copies_enabled(shop) and item.get("alreadyOwned",false): return "activated"
	if gold(shop,legacy_wallet)<int(item.priceGold): return "season_shop_gold_short"
	return ""

static func purchase_body(item: Dictionary,shop: Dictionary) -> Dictionary:
	if str(item.get("productId","")).is_empty() or int(item.get("priceGold",0))<1: return {}
	var body := {"productId":str(item.productId),"quantity":1}
	var rules := policy(shop)
	if not rules.is_empty():
		if not open(shop) or str(shop.get("resetKey","")).is_empty() or str(shop.get("rotationKey","")).is_empty(): return {}
		body.merge({"seasonId":rules.seasonId,"resetKey":shop.resetKey,"rotationKey":shop.rotationKey,
			"expectedPriceGold":int(item.priceGold),"catalogVersion":rules.catalogVersion})
	return body

static func current_intent(body: Dictionary,shop: Dictionary) -> bool:
	for item in shop.get("products",[]):
		if item.get("productId")==body.get("productId"):
			return purchase_body(item,shop)==body and not body.is_empty()
	return false
