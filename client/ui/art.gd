extends RefCounted

const MANIFEST = preload("res://assets/imported/manifest.json")
const CATALOG = preload("res://data/catalog.json")
## Shared item-cell art used by inventory, preparation and reward/mail grids.
## The source is a 144x144 square and should be rendered 1:1 as 96x96.
const COMMON_CELL_KEY := "UI/Prep/exploration_prep_backpack_cell_empty_normal.png"
const COMMON_CELL_SOURCE_SIZE := Vector2i(144, 144)
const COMMON_CELL_DISPLAY_SIZE := Vector2(96, 96)
const COMMON_CELL_GAP := 8
static var _textures: Dictionary = {}

static func texture(key: String) -> Texture2D:
	if key.is_empty(): return null
	if not _textures.has(key):
		var entry: Dictionary = MANIFEST.data.files.get(key, {})
		var path: String = entry.get("path", "")
		_textures[key] = load(path) if not path.is_empty() and ResourceLoader.exists(path) else null
	return _textures[key]

static func card(id: String) -> Texture2D:
	return texture(MANIFEST.data.cards.get(id, ""))

static func portrait(hero_class: String) -> Texture2D:
	return texture(MANIFEST.data.get("portraits", {}).get(hero_class, "UI/Prep/exploration_prep_hero_portrait_%s.png" % hero_class.to_lower()))

static func passive(hero_class: String) -> Texture2D:
	return texture(MANIFEST.data.get("passives", {}).get(hero_class, ""))

static func product(kind: String) -> Texture2D:
	return texture(MANIFEST.data.get("products", {}).get(kind, ""))

static func action_icon(kind: String) -> Texture2D:
	return texture(MANIFEST.data.get("action_icons", {}).get(kind, ""))

static func equipment_texture(item: Dictionary) -> Texture2D:
	var gear: Dictionary = item.get("equipment", item) if item.get("equipment", item) is Dictionary else item
	var quality := str(gear.get("quality", "")).capitalize()
	var element := str(gear.get("element", "")).to_lower()
	var slot := str(gear.get("slot", "")).to_lower()
	if quality.is_empty() or element.is_empty() or slot.is_empty(): return null
	return texture("Equipment/%s/%s_%s.png" % [quality, slot, element])

static func item_texture(item: Dictionary) -> Texture2D:
	var equipment := equipment_texture(item)
	if equipment != null: return equipment
	var id := str(item.get("item_id", item.get("itemId", "")))
	var kind := str(item.get("kind", item.get("Kind", "")))
	for row in CATALOG.data.get("tables", {}).get("Items", []):
		if str(row.get("id", "")) == id or (str(row.get("kind", "")) == kind and not id.begins_with("class_soul:")):
			var key := str(row.get("icon_key", ""))
			if not key.is_empty(): return texture(key)
	return null

static func monster(id: String, phase: int = 1) -> Texture2D:
	id = MANIFEST.data.get("monster_aliases", {}).get(id, id)
	var variants: Dictionary = MANIFEST.data.get("monster_variants", {}).get(id, {})
	var key: String = variants.get("phase_%s" % phase, MANIFEST.data.monsters.get(id, ""))
	return texture(key)

static func element(value: String) -> Texture2D:
	if value == "Earth": return texture("UI/Battle/element_earth_clean.png")
	if value not in ["Fire", "Wood", "Water", "Metal"]: return null
	return texture("UI/Battle/battle_element_icon_%s.png" % value.to_lower())

static func style(key: String, tint: Color = Color.WHITE) -> StyleBoxTexture:
	var box := StyleBoxTexture.new()
	box.texture = texture(key)
	box.modulate_color = tint
	var borders: Array = MANIFEST.data.files.get(key, {}).get("border_lbrt", [12, 12, 12, 12])
	# Source manifests use Unity's left/bottom/right/top order.
	for pair in [[SIDE_LEFT, 0], [SIDE_BOTTOM, 1], [SIDE_RIGHT, 2], [SIDE_TOP, 3]]:
		box.set_texture_margin(pair[0], float(borders[pair[1]]))
	for side in [SIDE_LEFT, SIDE_RIGHT]: box.set_content_margin(side, 24)
	for side in [SIDE_TOP, SIDE_BOTTOM]: box.set_content_margin(side, 12)
	return box

static func image(parent: Node, source: Texture2D, minimum: Vector2) -> TextureRect:
	var node := TextureRect.new()
	node.texture = source
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	node.custom_minimum_size = minimum
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(node)
	return node

static func button(node: Button, key: String) -> void:
	node.add_theme_stylebox_override("normal", style(key))
	node.add_theme_stylebox_override("hover", style(key, Color(1.2, 1.15, 1.05)))
	node.add_theme_stylebox_override("pressed", style(key, Color(0.8, 0.85, 0.9)))
	node.add_theme_stylebox_override("disabled", style(key, Color(0.55, 0.55, 0.55)))

static func cell_style(tint: Color = Color.WHITE) -> StyleBoxTexture:
	return style(COMMON_CELL_KEY, tint)

static func quality_name(rank: Variant) -> String:
	if rank is String:
		var raw := str(rank).capitalize()
		if raw in ["White", "Green", "Blue", "Purple", "Orange", "Red"]: return raw
	var numeric := int(rank)
	return ["", "White", "Green", "Blue", "Purple", "Orange", "Red"][clampi(numeric, 0, 6)]

static func item_quality_rank(item: Dictionary) -> int:
	var gear: Dictionary = item.get("equipment", {}) if item.get("equipment") is Dictionary else {}
	if not gear.is_empty() and gear.has("quality"):
		var gear_quality := quality_name(gear.get("quality"))
		return ["", "White", "Green", "Blue", "Purple", "Orange", "Red"].find(gear_quality)
	var raw_quality: Variant = item.get("quality", item.get("Quality", 0))
	if raw_quality is String and not str(raw_quality).is_empty():
		var named := quality_name(raw_quality)
		var named_rank := ["", "White", "Green", "Blue", "Purple", "Orange", "Red"].find(named)
		if named_rank > 0: return named_rank
	if int(raw_quality) > 0: return clampi(int(raw_quality), 1, 6)
	var id := str(item.get("item_id", item.get("itemId", "")))
	var kind := str(item.get("kind", item.get("Kind", "")))
	for row in CATALOG.data.get("tables", {}).get("Items", []):
		if str(row.get("id", "")) == id: return clampi(int(row.get("quality", 1)), 1, 6)
		if str(row.get("kind", "")) == kind and not id.begins_with("class_soul:"): return clampi(int(row.get("quality", 1)), 1, 6)
		if kind == "ClassSoul" and id == "class_soul:" + str(row.get("id", "")).trim_prefix("class_soul:"): return clampi(int(row.get("quality", 1)), 1, 6)
	return 1

static func item_quality_name(item: Dictionary) -> String:
	return quality_name(item_quality_rank(item))

static func quality_color(rank: Variant) -> Color:
	var quality := quality_name(rank)
	for row in CATALOG.data.get("tables", {}).get("EquipmentQuality", []):
		if str(row.get("id", "")) == quality:
			var configured := str(row.get("display_color", ""))
			if not configured.is_empty(): return Color(configured)
	return [Color.WHITE, Color("d0c9b6"), Color("789a70"), Color("558cb8"), Color("9979b1"), Color("d99b48"), Color("ce5651")][clampi(int(rank), 1, 6)]

static func item_cell_style(item: Dictionary) -> StyleBoxTexture:
	var rank := item_quality_rank(item)
	return cell_style(quality_color(rank).darkened(0.35))
