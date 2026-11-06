extends RefCounted

const Model=preload("res://ui/season_market_model.gd")
const GatewayScript=preload("res://network/gateway.gd")
const Proto=preload("res://network/protobuf.gd")
const Http=preload("res://network/http_protocol.gd")

func run_test() -> Dictionary:
	var checks := {}
	var policy := {"seasonId":"s","canTrade":true,"taxBasisPoints":1000,"minimumFee":1,"currencies":[{"currency":"Gold","orangePriceCap":99999,"redPriceCap":99999},{"currency":"Diamond","orangePriceCap":2000,"redPriceCap":8000}]}
	checks["independent currency caps"]=Model.cap(policy,"Gold","Red")==99999 and Model.cap(policy,"Diamond","Orange")==2000 and Model.cap(policy,"Diamond","Red")==8000 and Model.cap(policy,"Diamond","Purple")==0
	checks["one seller minimum and floor"]=Model.fee(policy,9)==1 and Model.fee(policy,99999)==9999 and 99999-Model.fee(policy,99999)==90000
	var item := {"instanceId":"00000000-0000-0000-0000-000000000001","version":9007199254740993,"quality":"Red","slot":"Head","level":0,"location":"Inventory","isBound":false,"seasonId":"s","assetScope":"ActiveSeason","statsVersion":"season-equipment-v1","uniqueAffix":"Inferno","uniqueElement":"Fire"}
	checks["real seasonal red can list in diamonds"]=Model.eligible(item,policy,"Diamond")
	var old: Dictionary=item.duplicate(true);old.seasonId="old";old.assetScope="ArchivedSeason"
	checks["archived item cannot become a new listing"]=not Model.eligible(old,policy,"Gold")
	old=item.duplicate(true);old.isBound=true
	checks["bound item cannot list"]=not Model.eligible(old,policy,"Gold")
	old=item.duplicate(true);old.location="InMatchBackpack"
	checks["temporary item cannot list"]=not Model.eligible(old,policy,"Gold")
	var body := Model.listing_body(item,policy,"Diamond",8000)
	checks["listing uses zero legacy gold and exact version"]=body.priceGold==0 and body.currency=="Diamond" and body.price==8000 and body.expectedEquipmentVersion==9007199254740993 and body.seasonId=="s"
	var proto := Proto.new(true)
	var decoded: Dictionary=proto.decode_http("CreateMarketListingRequest",proto.encode("CreateMarketListingRequest",Http.to_wire("CreateMarketListingRequest",body)))
	checks["HTTP codec preserves explicit currency source and integer64 version"]=proto.error.is_empty() and decoded==body
	decoded=proto.decode_http("CreateMarketListingRequest",proto.encode("CreateMarketListingRequest",{"equipment_id":item.instanceId,"price_gold":100}))
	checks["old listing request keeps new fields absent"]=decoded.currency==null and decoded.price==null and decoded.seasonId==null and decoded.expectedEquipmentVersion==null
	var listing := {"listingId":"l","version":7,"priceGold":0,"currency":"Diamond","price":8000,"seasonId":"s","status":"Active","expiresAt":"2099-12-31T00:00:00Z"}
	checks["diamond is never a free gold listing"]=Model.currency(listing)=="Diamond" and Model.price(listing)==8000 and Model.live(listing,policy)
	var path := Model.purchase_path(listing)
	checks["purchase captures currency price source and listing version"]=path.contains("expectedVersion=7") and path.contains("currency=Diamond") and path.contains("expectedPrice=8000") and path.contains("seasonId=s")
	var unknown: Dictionary=listing.duplicate(true);unknown.erase("price")
	checks["missing diamond price fails closed"]=Model.price(unknown)==-1 and not Model.live(unknown,policy)
	var next := GatewayScript._market_page_path("/api/v1/market/context?currency=Diamond&quality=Red&element=Fire&sort=material&offset=0&limit=2","/api/v1/market","2")
	checks["next page preserves currency and all market filters"]=next=="/api/v1/market?currency=Diamond&quality=Red&element=Fire&sort=material&offset=2&limit=200"
	checks["bootstrap does not forward unrelated parameters"]=GatewayScript._market_page_path("/api/v1/bootstrap?locale=ar","/api/v1/market","200")=="/api/v1/market?offset=200&limit=200"
	var saved := {}
	for field in ["lobby","gateway","_cache_versions","_cache_syncing","_cache_sync_again"]:saved[field]=Game.get(field)
	# A token-free stub makes authoritative refresh calls no-ops in this offline
	# event conversion control. Real authenticated reads are checked separately.
	var stub := EmptyGateway.new();Game.gateway=stub;Game._cache_versions={};Game._cache_syncing={};Game._cache_sync_again={}
	Game.lobby={"player":{"userId":"seller"},"wallet":{"gold":321,"diamond":543},"inventory":{"equipments":[],"summary":{"capacity":50,"equipmentCount":0}},"market":[]}
	var event := {"action":"market.listed","seller_gold_after":null,"listing":{"listing_id":"legacy","seller_id":"seller","equipment_id":"e","price_gold":100,"status":"Active","version":1,"expires_at_unix_ms":4102444800000,"equipment":{"instance_id":"e","slot":"Head","quality":"Blue","location":"MarketListed","version":2}}}
	Game._apply_market_event(event)
	checks["absent nullable seller balance does not erase gold"]=Game.lobby.wallet.gold==321
	Game.lobby.season={"state":"Active","seasonId":"s"};Game.lobby.market=[]
	event.listing["currency"]="Diamond";event.listing["price"]=8000;event.listing["season_id"]="s"
	event.listing.equipment.merge({"unique_affix":"Inferno","unique_element":"Fire","stats_version":"season-equipment-v1","origin_season_id":"s","season_id":"s","asset_scope":"ActiveSeason","source_kind":"RedBoss","recipe_extracted":false})
	Game._apply_market_event(event)
	checks["diamond broadcast does not pollute default gold cache"]=Game.lobby.market.is_empty()
	event.listing.currency="Gold";event.listing.price=100;Game._apply_market_event(event)
	var projected: Dictionary=Game.lobby.market[0].equipment
	checks["market realtime conversion keeps unique stats and source flags"]=projected.uniqueAffix=="Inferno" and projected.uniqueElement=="Fire" and projected.statsVersion=="season-equipment-v1" and projected.sourceKind=="RedBoss" and projected.recipeExtracted==false
	event.action="market.expired";event.listing.status="Expired";event.listing.season_id="old";event.listing.equipment.season_id="old";event.listing.equipment.asset_scope="ArchivedSeason";event.listing.equipment.location="MarketReturnPending"
	Game._apply_market_event(event)
	checks["old or held return is never credited into current inventory"]=Game.lobby.inventory.equipments.is_empty() and Game.lobby.wallet.gold==321
	for field in saved:Game.set(field,saved[field])
	stub.free()
	return {"ok":not checks.values().has(false),"checks":checks,"scope":"Actual market model, protocol, filter pagination and cache conversion; offline transport, not rendered or public-network evidence."}

class EmptyGateway extends Node:
	var token := ""
	var session_generation := 7
