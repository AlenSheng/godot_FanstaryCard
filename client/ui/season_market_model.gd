extends RefCounted

const P=preload("res://ui/palette.gd")
const GatewayScript=preload("res://network/gateway.gd")

static func currency(listing: Dictionary) -> String:
	var value: Variant=listing.get("currency")
	return "Gold" if value==null else str(value) if value in ["Gold","Diamond"] else ""

static func price(listing: Dictionary) -> int:
	var amount: Variant=listing.get("price")
	if amount is int: return amount
	return int(listing.get("priceGold",-1)) if currency(listing)=="Gold" else -1

static func offer(policy: Dictionary,value: String) -> Dictionary:
	for row in policy.get("currencies",[]):
		if row.get("currency")==value: return row
	return {}

static func cap(policy: Dictionary,value: String,quality: String) -> int:
	var row := offer(policy,value)
	if value=="Diamond" and quality not in ["Orange","Red"]: return 0
	return int(row.get("redPriceCap" if quality=="Red" else "orangePriceCap",0))

static func fee(policy: Dictionary,amount: int) -> int:
	if amount<1: return 0
	return maxi(int(policy.get("minimumFee",1)),int(amount*int(policy.get("taxBasisPoints",1000))/10000.0))

static func money(amount: int,value: String) -> String:
	return "%s %s" % [amount,P.word(value)]

static func eligible(item: Dictionary,policy: Dictionary,value: String) -> bool:
	if not policy.get("canTrade",false) or item.get("location")!="Inventory" or item.get("isBound",false): return false
	if item.get("slot") not in ["Head","Chest","Hands","Legs","Feet"] or item.get("sourceKind") in ["Borrowed","BotProjection"]: return false
	var season: Variant=policy.get("seasonId")
	if season==null:
		if item.get("seasonId")!=null or item.get("assetScope")!=null: return false
	elif item.get("seasonId")!=season or item.get("assetScope")!="ActiveSeason": return false
	return cap(policy,value,str(item.get("quality","")))>0

static func live(listing: Dictionary,policy: Dictionary) -> bool:
	if not policy.get("canTrade",false) or listing.get("status")!="Active" or price(listing)<1: return false
	if currency(listing) not in ["Gold","Diamond"] or offer(policy,currency(listing)).is_empty(): return false
	if listing.get("seasonId")!=policy.get("seasonId"): return false
	var end: Variant=listing.get("seasonEndsAt")
	if end!=null and GatewayScript.parse_expiry(str(end))<=Time.get_unix_time_from_system(): return false
	return GatewayScript.parse_expiry(str(listing.get("expiresAt","")))>Time.get_unix_time_from_system()

static func purchase_path(listing: Dictionary) -> String:
	var path: String="/api/v1/market/"+str(listing.get("listingId","")).uri_encode()+"/purchase?expectedVersion="+str(int(listing.get("version",0)))
	path+="&currency="+currency(listing).uri_encode()+"&expectedPrice="+str(price(listing))
	var season: Variant=listing.get("seasonId")
	if season!=null: path+="&seasonId="+str(season).uri_encode()
	return path

static func listing_body(item: Dictionary,policy: Dictionary,value: String,amount: int) -> Dictionary:
	var body := {"equipmentId":item.get("instanceId",""),"priceGold":amount if value=="Gold" else 0}
	if policy.get("seasonId")!=null:
		body.merge({"currency":value,"price":amount,"seasonId":policy.seasonId,"expectedEquipmentVersion":int(item.get("version",0))})
	return body

static func same_listing(a: Dictionary,b: Dictionary) -> bool:
	return a.get("listingId")==b.get("listingId") and a.get("version")==b.get("version") and a.get("seasonId")==b.get("seasonId") and currency(a)==currency(b) and price(a)==price(b)
