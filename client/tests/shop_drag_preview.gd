extends Node

const OUTPUT := "res://evidence/shop-drag"
var errors: Array[String] = []

func _ready() -> void:
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.online = true
	Game.room = {}
	Game.connection = "金币商店 · 拖动测试"
	Game.lobby = {"player": {"userId": "shop-drag-preview"}, "wallet": {"gold": 100000}, "classWeapons": [], "equippedLoadouts": []}
	$UI.inventory = {"equipments": [], "consumables": {"advancedBagCount": 0, "topBagCount": 0}}
	$UI._shop_inventory_ready = true
	$UI.shop = {"products": _products()}
	$UI.screen = "shop"
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUTPUT))
	await _verify(Vector2i(1920, 1080))
	await _verify(Vector2i(1280, 720))
	var report := {"ok": errors.is_empty(), "errors": errors, "screenshots": 4}
	FileAccess.open(OUTPUT + "/report.json", FileAccess.WRITE).store_string(JSON.stringify(report, "  "))
	print(JSON.stringify(report))
	get_tree().quit(0 if report.ok else 1)

func _verify(resolution: Vector2i) -> void:
	Game.lobby["wallet"] = {"gold": 100000}
	$UI.shop = {"products": _products()}
	Game.lobby["shop"] = $UI.shop
	get_window().size = resolution
	$UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	var scroll = $UI._reference.get_node_or_null("ShopScroll")
	if scroll == null or scroll.get_script() != load("res://ui/drag_scroll.gd"):
		errors.append("Shop does not use click-drag scrolling at %s" % resolution.x)
		return
	if scroll.horizontal_scroll_mode != ScrollContainer.SCROLL_MODE_AUTO or scroll.vertical_scroll_mode != ScrollContainer.SCROLL_MODE_DISABLED:
		errors.append("Shop drag axis is incorrect at %s" % resolution.x)
	RenderingServer.force_draw(false)
	get_viewport().get_texture().get_image().save_png(OUTPUT + "/shop_start_%s.png" % resolution.x)
	scroll.scroll_horizontal = 0
	scroll._begin(Vector2(1200, 500))
	scroll._drag(Vector2(700, 500))
	scroll._finish()
	if scroll.scroll_horizontal < 450: errors.append("Shop product drag did not move horizontally at %s" % resolution.x)
	if scroll.can_activate(): errors.append("Shop drag did not suppress click activation at %s" % resolution.x)
	await get_tree().process_frame
	RenderingServer.force_draw(false)
	get_viewport().get_texture().get_image().save_png(OUTPUT + "/shop_dragged_%s.png" % resolution.x)
	var position_after_drag: int = scroll.scroll_horizontal
	$UI._render()
	$UI._render()
	await get_tree().process_frame
	await get_tree().process_frame
	var restored_scroll := $UI._reference.get_node_or_null("ShopScroll") as ScrollContainer
	if $UI.screen != "shop" or restored_scroll == null or abs(restored_scroll.scroll_horizontal - position_after_drag) > 1:
		errors.append("Shop page or scroll position changed after rebuilding at %s" % resolution.x)
	if restored_scroll == null: return
	var purchased_panel := restored_scroll.get_node_or_null("ShopProductRow/Product_drag-01")
	var other_panel := restored_scroll.get_node_or_null("ShopProductRow/Product_drag-02")
	$UI._apply_shop_purchase("drag-01", {"quantity": 1, "goldAfter": 99890})
	$UI._reference.sync_shop_state("drag-01")
	await get_tree().process_frame
	await get_tree().process_frame
	var current_scroll := $UI._reference.get_node_or_null("ShopScroll") as ScrollContainer
	if current_scroll == null or current_scroll != restored_scroll or current_scroll.scroll_horizontal != position_after_drag:
		errors.append("Shop purchase rebuilt or reset the shelf at %s" % resolution.x)
		return
	if not is_instance_valid(purchased_panel) or purchased_panel.get_node("ShopDetail").text.find("1 / 99") == -1:
		errors.append("Purchased shelf count was not updated at %s" % resolution.x)
	if current_scroll.get_node_or_null("ShopProductRow/Product_drag-02") != other_panel:
		errors.append("An unrelated shelf was replaced at %s" % resolution.x)
	if $UI._reference.get_node("WalletGold").text.find("99890") == -1:
		errors.append("Shop wallet was not updated at %s" % resolution.x)

func _products() -> Array:
	var products: Array = []
	var kinds := ["AdvancedBag", "EquipmentFragments", "TopBag", "WarriorSoul", "HealthPotion", "EquipmentFragments"]
	for index in range(12):
		var kind: String = kinds[index % kinds.size()]
		products.append({"kind": kind, "productId": "drag-%02d" % index, "priceGold": 100 + index * 10, "purchased": 0, "limit": 99, "payload": JSON.stringify({"amount": index + 1})})
	return products
