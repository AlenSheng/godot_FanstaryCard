extends RefCounted

func run_test() -> Dictionary:
	var Art = load("res://ui/art.gd")
	var catalog = load("res://data/catalog.json")
	var count := 0
	var monster_count := 0
	for card in catalog.data.tables.Cards:
		var texture: Texture2D = Art.card(card.id)
		if texture == null:
			return {"ok": false, "message": "Missing or invalid card art: " + card.id}
		if card.is_codex:
			if texture.get_size() != Vector2(512, 768):
				return {"ok": false, "message": "Invalid codex illustration size: " + card.id}
			count += 1
		else: monster_count += 1
	for id in Art.MANIFEST.data.monsters:
		if Art.monster(id) == null: return {"ok": false, "message": "Missing monster species " + id}
	for id in ["fire-bat", "murk-snail"]:
		if Art.monster(id + "-a") != Art.monster(id) or Art.monster(id + "-b") != Art.monster(id):
			return {"ok": false, "message": "Paired monsters must share species art: " + id}
	if Art.monster("annihilation-core", 1) == Art.monster("annihilation-core", 2):
		return {"ok": false, "message": "Authoritative boss phases require distinct art"}
	if Art.monster("annihilation-core", 99) != Art.monster("annihilation-core", 1) or Art.monster("unknown-species") != null:
		return {"ok": false, "message": "Unknown phase/species fallback is unsafe"}
	for value in ["Fire", "Wood", "Water", "Metal", "Earth"]:
		if Art.element(value) == null: return {"ok": false, "message": "Missing element icon " + value}
	if Art.element("Earth") == Art.texture("UI/Battle/battle_element_icon_earth.png"):
		return {"ok": false, "message": "Earth must not use the old flame illustration"}
	if Art.texture("UI/Cards/card_frame_monster_clean.png") == null:
		return {"ok": false, "message": "Missing dedicated dark-red monster frame"}
	for pair in [["fire-bat", "M-FIREBAT", "fire_bat"], ["rust-rat", "M-RUSTRAT", "rustblade_rat"], ["stone-guard", "M-STONEGUARD", "stone_guardian"]]:
		var clean: Texture2D = Art.texture("UI/Monsters/%s_clean.png" % pair[2])
		if clean == null or Art.monster(pair[0]) != clean or Art.card(pair[1]) != clean:
			return {"ok": false, "message": "Battle/card must both use cleaned monster art: " + pair[0]}
	for hero_class in ["Mage", "Priest", "Guardian"]:
		if Art.portrait(hero_class) == null or Art.passive(hero_class) == null:
			return {"ok": false, "message": "Missing class portrait or passive: " + hero_class}
		if hero_class != "Mage" and Art.portrait(hero_class) != Art.texture("UI/Characters/%s_consistent.png" % hero_class.to_lower()):
			return {"ok": false, "message": "Class still uses old placeholder portrait: " + hero_class}
	for kind in ["Cards", "EquipmentFragments", "AdvancedBag", "TopBag"]:
		if Art.product(kind) == null: return {"ok": false, "message": "Missing server product art: " + kind}
	for kind in ["Relic", "Spring", "Extract"]:
		if Art.action_icon(kind) == null: return {"ok": false, "message": "Missing action art: " + kind}
	var common_cell: Texture2D = Art.texture(Art.COMMON_CELL_KEY)
	if common_cell == null or common_cell.get_size() != Vector2(Art.COMMON_CELL_SOURCE_SIZE.x, Art.COMMON_CELL_SOURCE_SIZE.y):
		return {"ok": false, "message": "Common item cell must remain a 144x144 square"}
	if Art.COMMON_CELL_DISPLAY_SIZE != Vector2(96, 96) or Art.COMMON_CELL_GAP != 8:
		return {"ok": false, "message": "Common item cell display spec changed unexpectedly"}
	for quality in ["White", "Green", "Blue", "Purple", "Orange"]:
		for element in ["Fire", "Wood", "Water", "Metal", "Earth"]:
			for slot in ["Head", "Chest", "Hands", "Legs", "Feet"]:
				var equipment: Texture2D = Art.equipment_texture({"quality": quality, "element": element, "slot": slot})
				if equipment == null: return {"ok": false, "message": "Missing generated equipment art: %s|%s|%s" % [quality, element, slot]}
	if Art.monster("frost-wraith") != null or Art.texture("UI/Monsters/frost_wraith_clean.png") == null:
		return {"ok": false, "message": "Frost wraith should be registered but not assigned to an undefined species"}
	var box: StyleBoxTexture = Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png")
	var margins: Array = Art.MANIFEST.data.files["UI/CardCodex/card_codex_dialog_panel_normal.png"].border_lbrt
	var ok: bool = count == 200 and monster_count == 12 and Art.MANIFEST.data.monsters.size() == 12 and box.get_texture_margin(SIDE_TOP) == margins[3] and box.get_texture_margin(SIDE_BOTTOM) == margins[1]
	return {"ok": ok, "message": "212 card textures, 12 species, paired aliases, boss phases, five elements and texture borders"}
