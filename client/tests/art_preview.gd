extends Node

var output := "res://evidence/art"
var layout_errors: Array = []
var screenshot_count := 0

func _ready() -> void:
	var evidence_directory := OS.get_environment("FANTASYCARD_ART_EVIDENCE")
	if not evidence_directory.is_empty(): output = evidence_directory
	Game.gateway.set_process(false)
	Game.gateway.persist_session = false
	Game.gateway.online = true
	Game.connection = "美术预览 · 测试数据"
	Game.lobby = {"player": {"userId": "preview-player"}, "wallet": {"gold": 1200}, "decks": [{"heroClass": "Mage", "cardIds": ["MAG-01", "MAG-04", "GP01", "MAG-10", "C01"]}], "materials": {"equipmentFragments": 32}, "equippedLoadouts": [], "classWeapons": [{"heroClass": "Mage", "level": 2, "version": 1}]}
	$UI.inventory = {"equipments": [], "consumables": {"healthPotionCount": 2, "advancedBagCount": 1, "topBagCount": 1}}
	$UI._shop_inventory_ready = true
	$UI.gear_draft = [null, null, null, null, null]
	_run.call_deferred()

func _capture(name: String, rebuild: bool = true) -> void:
	if rebuild: $UI._render()
	await get_tree().create_timer(0.4).timeout
	if not is_instance_valid($UI._reference): layout_errors.append(name + ": reference composition not active")
	else:
		for label in $UI._reference.find_children("*", "Label", true, false):
			if label.is_visible_in_tree() and not label.text.is_empty() and label.get_visible_line_count() == 0:
				layout_errors.append(name + ": no visible text line: " + label.text.left(40))
		for node in $UI._reference.get_children():
			if node is Button and not Rect2(0, 0, 1921, 1081).encloses(Rect2(node.position, node.size * node.scale)):
				layout_errors.append(name + ": button outside canvas: " + node.text)
		for bar in get_tree().get_nodes_in_group("bounded_progress"):
			if not bar.slot_rect().encloses(bar.fill_rect()):
				layout_errors.append(name + ": progress fill outside its artwork slot")
			var track: Control = bar.get_child(0)
			var clip: Control = bar.get_node("FillClip")
			if not track.is_visible_in_tree() or not track.size.is_equal_approx(bar.size):
				layout_errors.append(name + ": progress artwork is missing or incorrectly sized")
			if not clip.size.is_equal_approx(bar.fill_rect().size) or not clip.position.is_equal_approx(bar.fill_rect().position):
				layout_errors.append(name + ": rendered fill does not match its value")
			if bar.value > bar.min_value and not clip.is_visible_in_tree():
				layout_errors.append(name + ": nonempty progress fill is hidden")
		var action_panel: Control = $UI._reference.get_node_or_null("ActionPanel")
		var action_title: Control = $UI._reference.get_node_or_null("ActionTitle")
		if action_panel != null and action_title != null and not action_panel.get_global_rect().encloses(action_title.get_global_rect()):
			layout_errors.append(name + ": action heading outside panel")
	RenderingServer.force_draw(false)
	var save_error := get_viewport().get_texture().get_image().save_png(output + "/" + name + ".png")
	if save_error == OK: screenshot_count += 1
	else: layout_errors.append("Screenshot save failed: " + name)

func _run() -> void:
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(output))
	for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720)]:
		get_window().size = resolution
		var suffix := "_%s" % resolution.x
		Game.room = {}
		$UI.screen = "hall"
		await _capture("hall" + suffix)
		$UI.screen = "prep"
		await _capture("prep" + suffix)
		await _portrait_previews(suffix)
		for view in ["gear", "enhance", "shop", "market"]:
			$UI.screen = view
			$UI.shop = _shop_fixture()
			await _capture(view + suffix)
			if view == "shop":
				_check_shop()
				$UI._reference.get_node("ShopScroll").scroll_horizontal = 10000
				await _capture("shop_tail" + suffix, false)
		$UI.screen = "cards"
		$UI.deck_draft = []
		$UI.owned = []
		for id in ["MAG-01", "MAG-04", "GP01", "MAG-10", "C01", "GG01"]:
			$UI.owned.append({"cardId": id, "heroClass": null, "unlocked": true, "copyCount": 1, "level": 1})
		await _capture("cards" + suffix)
		Game.room = {"allowed_actions": ["battle.play_cards", "battle.select_target"], "player": {"player_id": "preview-player", "hero_class": "Mage", "phase": "Pve", "combat": {"hp": 48, "maximum_hp": 70, "shield": 6}, "draw_charge": "0.55", "hand": []}, "pve": {"battle_id": "preview", "current_target_id": "fire-bat", "monsters": []}}
		for id in ["MAG-01", "MAG-04", "GP01", "M-FIREBAT", "M-VOIDCORE"]:
			Game.room.player.hand.append({"instance_id": id, "card_id": id})
		for id in ["fire-bat", "rust-rat"]:
			Game.room.pve.monsters.append({"monster_id": id, "hp": 24, "maximum_hp": 44, "shield": 8, "intent_kind": "Attack", "intent_element": "Fire", "intent_value": 2})
		Game.selected_cards = ["MAG-01"]
		await _capture("battle" + suffix)
		var control: Button = $UI._reference.get_node_or_null("Card_MAG-01")
		if control == null: layout_errors.append("Missing interactive battle card")
		else:
			control.pressed.emit()
			if "MAG-01" in Game.selected_cards: layout_errors.append("Card button did not toggle selected state")
		await _monster_previews(suffix)
		Game.room.player.phase = "Pvp"
		Game.room.duel = {"duel_id": "preview-duel", "opponent_id": "preview-opponent", "opponent": {"hp": 60, "maximum_hp": 100, "shield": 8}, "escape_remaining_ms": 0}
		await _capture("pvp" + suffix)
		await _passive_previews(suffix)
		Game.room.erase("duel")
		Game.room.player.phase = "Choice"
		Game.room.reward_choice = {"refresh_count": 0, "options": [{"option_id": "equipment", "kind": 1, "quantity": 1}, {"option_id": "fragments", "kind": 2, "quantity": 18}, {"option_id": "heal", "kind": 3, "quantity": 1, "heal_percent": 14}]}
		Game.room.allowed_actions = ["choice.pick", "choice.refresh"]
		await _capture("choose" + suffix)
		Game.room.erase("reward_choice")
		Game.room.player.phase = "ActionBar"
		Game.room.player.inventory = []
		Game.room.self = {"row": 3, "column": 2}
		Game.room.map = []
		for y in range(6):
			for x in range(6): Game.room.map.append({"row": y, "column": x, "has_spring": y == 0 and x == 3, "is_boss": y == 2 and x == 2})
		Game.room.legal_moves = [{"row": 2, "column": 2}, {"row": 3, "column": 3}]
		Game.room.current_cell = {"has_evacuation": true, "spring_consumed": false, "relic_pile_ids": ["preview-relic"], "relic_piles": [{"pile_id": "preview-relic", "owner_name": "旅人", "version": 1, "items": []}]}
		Game.room.allowed_actions = ["room.move", "action.spring", "action.potion", "action.extract"]
		$UI.set_meta("exploration_map_open", false)
		await _capture("action" + suffix)
		_check_action_icons()
		$UI.set_meta("exploration_map_open", true)
		await _capture("map" + suffix)
		$UI.set_meta("pending_move", Vector2i(2, 2))
		await _capture("midlayer" + suffix)
		# An authoritative refresh must retain the user's pending decision.
		$UI._render()
		if not $UI.has_meta("pending_move"): layout_errors.append("Midlayer decision lost after snapshot render")
		$UI.remove_meta("pending_move")
		Game.room = {}
		Game.settlement = {"result": "Dead", "settlementId": "fixture", "details": {"items": [
			{"item": {"kind": "HealthPotion", "quantity": 1}},
			{"item": {"kind": "EquipmentFragments", "quantity": 1}},
			{"item": {"kind": "Equipment", "quantity": 1, "equipment": {"quality": "White", "element": "Water", "slot": "Chest", "level": 0}}}
		]}}
		await _capture("settlement" + suffix)
		Game.settlement = {}
	await _regressions()
	var report := FileAccess.open(output + "/report.json", FileAccess.WRITE)
	report.store_string(JSON.stringify({"ok": layout_errors.is_empty(), "fixture_only": true, "screenshots": screenshot_count, "layout_errors": layout_errors}))
	report.close()
	get_tree().quit()

func _portrait_previews(suffix: String) -> void:
	var Art = preload("res://ui/art.gd")
	for hero_class in ["Priest", "Guardian"]:
		Game.hero_class = hero_class
		for screen in ["hall", "prep", "gear"]:
			$UI.screen = screen
			await _capture(screen + "_" + hero_class.to_lower() + suffix)
			var portrait: TextureRect = $UI._reference.get_node_or_null("HeroPortrait")
			if portrait == null or portrait.texture != Art.portrait(hero_class):
				layout_errors.append("Wrong character portrait in " + screen + ": " + hero_class)
	Game.hero_class = "Mage"

func _shop_fixture() -> Dictionary:
	# The HTTP Protobuf gateway supplies ShopProductPayload as an object.
	var products: Array = []
	for kind in ["Cards", "EquipmentFragments", "AdvancedBag", "TopBag", "WarriorSoul", "HealthPotion"]:
		products.append({"kind": kind, "productId": "fixture-" + kind, "priceGold": 120, "purchased": 0, "limit": 3, "payload": ({"count": 3} if kind == "Cards" else {"amount": 1})})
	for hero_class in ["Priest", "Mage", "Guardian"]:
		products.append({"kind": "ClassSoul", "productId": "fixture-" + hero_class, "priceGold": 400, "purchased": 0, "limit": 1, "payload": {"heroClass": hero_class, "amount": 12}})
	products.append({"kind": "Cards", "productId": "fixture-daily", "priceGold": 150, "purchased": 0, "limit": 1, "alreadyOwned": true, "payload": {"cardId": "C01", "count": 1}})
	return {"products": products}

func _check_shop() -> void:
	var Art = preload("res://ui/art.gd")
	var P = preload("res://ui/palette.gd")
	for product in $UI.shop.products:
		var node: Node = $UI._reference.find_child("Product_" + product.productId, true, false)
		if node == null:
			layout_errors.append("Missing server product row: " + product.productId)
			continue
		var image: TextureRect = node.get_node("ProductArt")
		var payload: Dictionary = product.payload
		if image.texture == null: layout_errors.append("Empty server product image: " + product.productId)
		if product.kind in ["Cards", "EquipmentFragments", "AdvancedBag", "TopBag"] and not payload.has("cardId") and image.texture != Art.product(product.kind):
			layout_errors.append("New shop artwork not applied: " + product.kind)
		if payload.has("cardId") and (image.texture != Art.card(payload.cardId) or $UI._reference._product_title(product.kind, payload) == "卡包"):
			layout_errors.append("Guaranteed daily card incorrectly presented as a random pack")
		if payload.has("cardId"):
			var info: Dictionary = $UI.cards.get(str(payload.cardId), {})
			var quality := str(info.get("quality", payload.get("quality", "White"))).capitalize()
			var frame := node.get_node_or_null("ProductCardFrame") as TextureRect
			var face_name := node.get_node_or_null("ShopCardName") as Label
			var face_effect := node.get_node_or_null("ShopCardEffect") as Label
			if frame == null or frame.texture != Art.texture("UI/Codex/qframe_%s.png" % quality.to_lower()):
				layout_errors.append("Guaranteed card does not use its external quality frame: " + product.productId)
			if node.get_node_or_null("CardQuality") != null:
				layout_errors.append("Guaranteed card repeats its quality above the identifying frame: " + product.productId)
			if face_name == null or face_name.text.is_empty() or face_effect == null or face_effect.text.is_empty():
				layout_errors.append("Guaranteed card frame omits its name or effect: " + product.productId)
			elif not frame.get_rect().encloses(face_name.get_rect()) or not frame.get_rect().encloses(face_effect.get_rect()):
				layout_errors.append("Guaranteed card text extends outside its card frame: " + product.productId)
			elif face_name.position.y + face_name.size.y >= face_effect.position.y:
				layout_errors.append("Guaranteed card name overlaps its effect: " + product.productId)
			elif face_effect.position.y + face_effect.size.y >= frame.position.y + frame.size.y - 18:
				layout_errors.append("Guaranteed card effect overlaps the bottom frame decoration: " + product.productId)
			elif face_effect.max_lines_visible != 2 or face_effect.autowrap_mode == TextServer.AUTOWRAP_OFF or face_effect.horizontal_alignment != HORIZONTAL_ALIGNMENT_CENTER:
				layout_errors.append("Guaranteed card effect does not reserve two centered lines: " + product.productId)
			if not node.tooltip_text.contains((P.localized("equipment_quality_line") % P.word(quality)).strip_edges()):
				layout_errors.append("Guaranteed card tooltip omits quality: " + product.productId)
			var purchase := node.get_node_or_null("Purchase") as Button
			if product.get("alreadyOwned", false) and (purchase == null or not purchase.disabled or purchase.text != P.localized_text("已激活")):
				layout_errors.append("Activated shop card remains purchasable: " + product.productId)
		if product.kind == "ClassSoul" and image.texture != Art.texture("UI/Item/exploration_prep_item_icon_%s_soul.png" % str(payload.heroClass).to_lower()):
			layout_errors.append("Class soul icon does not match payload: " + product.productId)
		if image.mouse_filter != Control.MOUSE_FILTER_IGNORE:
			layout_errors.append("Product artwork blocks mouse input")

func _passive_previews(suffix: String) -> void:
	var Art = preload("res://ui/art.gd")
	var duel: Dictionary = Game.room.duel.duplicate(true)
	for hero_class in ["Priest", "Guardian"]:
		# A battle's frozen class must take precedence over the lobby selection.
		Game.room.player.hero_class = hero_class
		for phase in ["Pve", "Pvp"]:
			Game.room.player.phase = phase
			if phase == "Pve": Game.room.erase("duel")
			else: Game.room.duel = duel
			await _capture("passive_" + hero_class.to_lower() + "_" + phase.to_lower() + suffix)
			var emblem: TextureRect = $UI._reference.get_node_or_null("PlayerPassiveIcon_" + hero_class)
			if emblem == null or emblem.texture != Art.passive(hero_class):
				layout_errors.append("Passive emblem does not match room class: " + hero_class)
	Game.room.player.hero_class = "Mage"

func _check_action_icons() -> void:
	var Art = preload("res://ui/art.gd")
	for kind in ["spring", "relic", "extract"]:
		var icon: TextureRect = $UI._reference.find_child("ActionIcon_" + kind, true, false)
		if icon == null or icon.texture != Art.action_icon(kind.capitalize()) or icon.mouse_filter != Control.MOUSE_FILTER_IGNORE:
			layout_errors.append("Missing/obstructing action icon: " + kind)
	var relic: Button = $UI._reference.find_child("Action_relic", true, false)
	if relic == null or not relic.disabled: layout_errors.append("Relic without read permission must stay disabled")
	var map: Button = $UI._reference.find_child("Action_map", true, false)
	if map == null:
		layout_errors.append("Map action missing")
		return
	map.pressed.emit()
	if not $UI.get_meta("exploration_map_open", false): layout_errors.append("Action artwork prevented map navigation")

func _monster_previews(suffix: String) -> void:
	var Art = preload("res://ui/art.gd")
	var species := ["fire-bat", "thorn-mite", "murk-snail", "sand-lizard", "rust-rat", "metal-guard", "fire-herald", "marsh-mother", "stone-guard", "thorn-guard", "annihilation-core", "box-spirit"]
	var cards := ["M-FIREBAT", "M-THORNMITE", "M-MUDHYDRA", "M-SANDLIZARD", "M-RUSTRAT", "M-GOLDGUARD", "M-FIREREAVER", "M-SWAMPMOTHER", "M-STONEGUARD", "M-THORNGUARD", "M-VOIDCORE", "M-BOXSPIRIT"]
	for pair in range(6):
		Game.room.pve.monsters = []
		Game.room.player.hand = []
		for offset in range(2):
			var index: int = pair * 2 + offset
			Game.room.pve.monsters.append({"monster_id": species[index], "hp": 24, "maximum_hp": 44, "shield": 0, "intent_kind": "Attack", "intent_element": "Earth" if offset == 0 else "Water", "intent_value": 6, "boss_phase": 1})
			Game.room.player.hand.append({"instance_id": cards[index], "card_id": cards[index]})
		Game.room.pve.current_target_id = species[pair * 2]
		Game.selected_cards = [cards[pair * 2]]
		await _capture("monsters_%s%s" % [pair + 1, suffix])
		for offset in range(2):
			var id: String = cards[pair * 2 + offset]
			var card: Button = $UI._reference.get_node_or_null("Card_" + id)
			if card == null or card.get_node("Illustration").texture != Art.monster(species[pair * 2 + offset]):
				layout_errors.append("Battle/card species art mismatch: " + id)
			elif card.get_node("CardFrame").texture != Art.texture("UI/Cards/card_frame_monster_clean.png"):
				layout_errors.append("Monster card missing dedicated frame: " + id)
	Game.room.pve.monsters = [{"monster_id": "annihilation-core", "hp": 40, "maximum_hp": 180, "shield": 0, "intent_kind": "Attack", "intent_element": "Earth", "intent_value": 12, "boss_phase": 1}]
	Game.room.pve.current_target_id = "annihilation-core"
	for phase in [1, 2]:
		Game.room.pve.monsters[0].boss_phase = phase
		await _capture("boss_phase_%s%s" % [phase, suffix])
		var enemy: TextureRect = $UI._reference.get_node_or_null("Monster_annihilation-core")
		if enemy == null or enemy.texture != Art.monster("annihilation-core", phase):
			layout_errors.append("Boss illustration must follow server phase %s" % phase)

func _regressions() -> void:
	var Art = preload("res://ui/art.gd")
	$UI.screen = "prep"
	$UI.inventory.consumables = {"healthPotionCount": 2, "advancedBagCount": 0, "topBagCount": 0}
	$UI.bag_tier = "Top"
	$UI._render()
	if $UI.bag_tier != "Free" or not $UI._reference.get_node("Backpack_Top").disabled or not $UI._reference.get_node("Backpack_Advanced").disabled:
		layout_errors.append("Unowned paid backpacks must not be selectable")
	$UI.inventory.consumables.topBagCount = 1
	$UI._render()
	$UI._reference.get_node("Backpack_Top").pressed.emit()
	if $UI.bag_tier != "Top": layout_errors.append("Backpack artwork prevented tier selection")
	var locked_cards: Array = []
	locked_cards.resize(20)
	locked_cards.fill("GUA-01")
	Game.preparation = {"snapshot": {"heroClass": "Guardian", "maximumHp": 99, "cardIds": locked_cards, "equipmentIds": ["frozen", null, null, null, null], "equipmentSnapshots": [{"instanceId": "frozen", "slot": "Head", "quality": "Green", "level": 4, "element": "Fire"}], "classWeaponLevel": 4, "backpackTier": "Top", "backpackCapacity": 36, "safeSlotIndexes": [33, 34, 35], "potionCount": 2}}
	$UI.screen = "prep"
	$UI._render()
	var previous_resolution := get_window().size
	for resolution in [Vector2i(1920, 1080), Vector2i(1280, 720)]:
		get_window().size = resolution
		await _capture("prep_locked_snapshot_%s" % resolution.x)
		var summary := $UI._reference.get_node_or_null("PreparationDeckSummary") as Label
		var bag_title := $UI._reference.get_node_or_null("PreparationBagTitle") as Label
		var stock := $UI._reference.get_node_or_null("PreparationBagStockSummary") as Label
		if summary == null or bag_title == null or stock == null:
			layout_errors.append("Locked preparation header is missing")
		elif summary.get_global_rect().intersects(bag_title.get_global_rect()) or summary.get_global_rect().intersects(stock.get_global_rect()):
			layout_errors.append("Locked preparation summary overlaps bag heading or stock")
	get_window().size = previous_resolution
	var labels := ""
	for node in $UI._reference.get_children():
		if node is Label: labels += node.text + "\n"
	if not ("已锁定编组 20 / 20" in labels and "生命上限 99" in labels and "本命 +4" in labels):
		layout_errors.append("Locked preparation must render frozen deck, HP and weapon level")
	if $UI._reference.get_node("HeroPortrait").texture != Art.portrait("Guardian"):
		layout_errors.append("Locked preparation portrait must use the frozen class")
	Game.preparation = {}
	$UI.screen = "shop"
	$UI.shop = _shop_fixture()
	$UI.inventory.consumables.advancedBagCount = 2
	$UI._render()
	for kind in ["AdvancedBag", "TopBag"]:
		var product: Node = $UI._reference.find_child("Product_fixture-" + kind, true, false)
		if not product.get_node("Purchase").disabled:
			layout_errors.append("Paid bag purchase exceeds combined stock cap: " + kind)
	$UI.inventory.consumables.advancedBagCount = 0
	$UI._shop_inventory_ready = false
	$UI._render()
	if not $UI._reference.find_child("Product_fixture-TopBag", true, false).get_node("Purchase").disabled:
		layout_errors.append("Paid bag purchase requires current inventory")
	$UI._shop_inventory_ready = true
	for product in $UI.shop.products:
		if product.productId == "fixture-daily": product.alreadyOwned = false
	$UI._render()
	var daily: Node = $UI._reference.find_child("Product_fixture-daily", true, false)
	daily.get_node("Purchase").pressed.emit()
	var confirmation_found := false
	var confirmation := $UI.get_node_or_null("ConfirmationModal")
	if confirmation != null:
		var description := confirmation.get_node("DialogPanel/Description") as Label
		confirmation_found = str($UI.cards.C01.name) in description.text and "150" in description.text
		confirmation.get_node("DialogPanel/CancelButton").pressed.emit()
	if not confirmation_found: layout_errors.append("Daily card purchase confirmation lost card name or price")
	$UI.screen = "market"
	$UI._market_item = "already-listed"
	$UI._render()
	if not $UI._market_item.is_empty(): layout_errors.append("Invalid market item survived inventory refresh")
	for node in $UI._reference.get_children():
		if node is Button and node.text == "上架物品" and not node.disabled:
			layout_errors.append("Market submission enabled without available inventory item")
	$UI.inventory.equipments = [{"instanceId": "locked-item", "slot": "Chest", "quality": "Blue", "element": "Fire", "level": 3, "location": "PreparationLocked"}]
	$UI._enhance_item = "locked-item"
	$UI.screen = "enhance"
	$UI._render()
	for node in $UI._reference.get_children():
		if node is Button and node.text == "强化到 +4" and not node.disabled:
			layout_errors.append("Locked equipment enhancement must be disabled")
	await get_tree().process_frame
