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
    var http := Proto.new(true)
    var shop: Dictionary=http.decode_http("ShopResponse",FileAccess.get_file_as_bytes(folder.path_join("shop.bin")))
    checks["actual HTTP current season and frozen catalog"]=http.error.is_empty() and shop.policy.state=="Active" and shop.policy.canPurchase and shop.policy.seasonId=="shop-api" and shop.policy.catalogVersion=="season-v1-config-9"
    checks["actual original Gold wallet"]=shop.policy.wallet.gold==5000
    checks["actual fixed and daily products"]=shop.products.size()==12
    checks["actual copy policy"]=shop.policy.grantsPermanentCopies
    var classes := 0
    var unlimited := 0
    for product in shop.products:
        if product.kind=="ClassSoul": classes+=1;checks[product.productId+" shared daily limit"]=product.limit==1 and product.purchased==0
        if product.kind in ["AdvancedBag","TopBag"]: unlimited+=1;checks[product.productId+" no daily limit"]=product.limit==0
    checks["actual three class options and two bag types"]=classes==3 and unlimited==2
    var fragments: Dictionary=http.decode_http("ShopPurchaseResponse",FileAccess.get_file_as_bytes(folder.path_join("fragments.bin")))
    checks["actual fragment source and direct quantity"]=http.error.is_empty() and fragments.seasonId==shop.policy.seasonId and fragments.grants.size()==1 and fragments.grants[0].kind=="EquipmentFragments" and fragments.grants[0].amount==20
    checks["actual purchase current Gold only"]=fragments.goldAfter==4880 and fragments.wallet.gold==4880 and fragments.catalogVersion==shop.policy.catalogVersion
    var pack: Dictionary=http.decode_http("ShopPurchaseResponse",FileAccess.get_file_as_bytes(folder.path_join("pack.bin")))
    var copies := 0
    var all_existing := true
    for grant in pack.grants:
        copies+=int(grant.amount);all_existing=all_existing and not grant.get("newlyUnlocked",false) and grant.copiesAfter>=2 and not grant.cardId.is_empty()
    checks["actual full-codex pack has three real copies"]=http.error.is_empty() and copies==3 and all_existing
    checks["actual pack debit"]=pack.goldAfter==4630 and pack.wallet.gold==4630
    var cards: Dictionary=http.decode_http("CardListResponse",FileAccess.get_file_as_bytes(folder.path_join("cards.bin")))
    var permanent: bool= not cards.items.is_empty()
    for card in cards.items: permanent=permanent and card.permanentCopies and card.copyCount==1
    checks["actual cards explicitly expose permanent-copy mode"]=http.error.is_empty() and permanent
    var ok: bool=not checks.values().has(false)
    FileAccess.open(folder.path_join("checks.json"),FileAccess.WRITE).store_string(JSON.stringify({"ok":ok,"checks":checks},"  "))
    print(JSON.stringify({"ok":ok,"checks":checks.size()}));quit(0 if ok else 1)
