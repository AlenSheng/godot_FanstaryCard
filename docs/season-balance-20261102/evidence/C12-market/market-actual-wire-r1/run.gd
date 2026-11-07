extends SceneTree
const Proto=preload("res://network/protobuf.gd")
func _initialize() -> void:
    create_timer(30).timeout.connect(func(): quit(1))
    call_deferred("run")
func run() -> void:
    var game=get_root().get_node("Game")
    game.set_process(false);game.gateway.set_process(false);game.gateway.persist_session=false;game.gateway.reconnect_enabled=false;game.gateway.socket.close()
    var sound=get_root().get_node("Sound");sound.persist_settings=false;sound.stop_all();sound.set_process(false)
    var folder := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
    var checks := {}
    var proto := Proto.new()
    var events := {}
    for name in ["listed","sold-seller","sold-buyer"]:
        var envelope: Dictionary=proto.decode("ServerEnvelope",FileAccess.get_file_as_bytes(folder.path_join(name+".bin")))
        checks[name+" actual network event envelope"]=proto.error.is_empty() and envelope.type=="inventory.changed"
        var event: Dictionary=proto.decode("InventoryChangedEvent",envelope.payload)
        checks[name+" keeps diamond amount apart from gold"]=proto.error.is_empty() and event.listing.currency=="Diamond" and event.listing.price==2000 and event.listing.price_gold==0
        checks[name+" keeps original stats and sample source"]=event.listing.equipment.stats_version=="season-equipment-v1" and event.listing.equipment.source_kind=="NaturalDrop" and event.listing.equipment.recipe_extracted==false
        checks[name+" contains no private seller gold amount"]=event.seller_gold_after==null
        events[name]=event
    checks["only seller receives a personal wallet refresh signal"]=events["sold-seller"].seller_wallet_changed and not events["sold-buyer"].seller_wallet_changed
    var http := Proto.new(true)
    var context: Dictionary=http.decode_http("MarketInventoryContextResponse",FileAccess.get_file_as_bytes(folder.path_join("context.bin")))
    checks["actual HTTP policy exposes both currencies and shared8"]=http.error.is_empty() and context.policy.currencies.size()==2 and context.policy.sharedSlots==8
    checks["actual HTTP own listing keeps original currency and source"]=context.ownListings.size()==1 and context.ownListings[0].currency=="Diamond" and context.ownListings[0].price==2000 and context.ownListings[0].equipment.seasonId==context.policy.seasonId
    var returns: Dictionary=http.decode_http("MarketReturnsResponse",FileAccess.get_file_as_bytes(folder.path_join("returns.bin")))
    checks["actual held return stays full-bag and same-season"]=http.error.is_empty() and returns.items.size()==1 and not returns.items[0].canClaim and returns.items[0].equipment.location=="MarketReturnPending" and returns.items[0].equipment.seasonId==context.policy.seasonId
    var purchase: Dictionary=http.decode_http("MarketPurchaseResponse",FileAccess.get_file_as_bytes(folder.path_join("purchase.bin")))
    checks["actual purchase debit remains diamond only"]=http.error.is_empty() and purchase.wallet.diamond==1000 and purchase.wallet.gold==150000 and purchase.listing.priceGold==0 and purchase.listing.price==2000
    var ok: bool=not checks.values().has(false)
    FileAccess.open(folder.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":checks},"  "))
    print(JSON.stringify({"ok":ok,"checks":checks.size()}))
    quit(0 if ok else 1)
