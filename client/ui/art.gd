extends RefCounted

const MANIFEST = preload("res://assets/imported/manifest.json")
const CATALOG = preload("res://data/catalog.json")
const CatalogIndex = preload("res://data/catalog_index.gd")
const QUALITY_LADDER := ["", "White", "Green", "Blue", "Purple", "Orange", "Red"]
const SAFE_SLOT_FRAME_TEXTURE: Texture2D = preload("res://assets/generated/ui/safe_slot_frame_locked.png")
## Shared item-cell art used by inventory, preparation and reward/mail grids.
## The source is a 144x144 square and should be rendered 1:1 as 96x96.
const COMMON_CELL_KEY := "UI/Prep/exploration_prep_backpack_cell_empty_normal.png"
const COMMON_CELL_SOURCE_SIZE := Vector2i(144, 144)
const COMMON_CELL_DISPLAY_SIZE := Vector2(96, 96)
const COMMON_CELL_GAP := 8
const QUALITY_FILL_INSET_RATIO := 12.0 / 192.0
## Shared dark state for an empty equipment slot. Keep it visually distinct from White gear.
const UNEQUIPPED_SLOT_COLOR := Color8(25, 28, 29, 255)
const UNEQUIPPED_FRAME_MODULATE := Color8(105, 108, 108, 220)
const UNEQUIPPED_ITEM_MODULATE := Color8(115, 115, 115, 200)
static var _textures: Dictionary = {}
static var _styles: Dictionary = {}

static func clear_texture_cache() -> void:
	_textures.clear()

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
	return texture(equipment_texture_key(item))

## Keeps equipment art strictly bound to the equipment's own quality.  In
## particular, Orange must never fall through to the reserved Red asset path.
static func equipment_texture_key(item: Dictionary) -> String:
	var gear: Dictionary = item.get("equipment", item) if item.get("equipment", item) is Dictionary else item
	var quality := quality_name(gear.get("quality", ""))
	var element := str(gear.get("element", "")).to_lower()
	var slot := str(gear.get("slot", "")).to_lower()
	if quality.is_empty() or element.is_empty() or slot.is_empty(): return ""
	return "Equipment/%s/%s_%s.png" % [quality, slot, element]

static func item_texture(item: Dictionary) -> Texture2D:
	var equipment := equipment_texture(item)
	if equipment != null: return equipment
	var id := str(item.get("item_id", item.get("itemId", "")))
	var kind := str(item.get("kind", item.get("Kind", "")))
	for row in CATALOG.data.get("tables", {}).get("Items", []):
		if not id.is_empty() and str(row.get("id", "")) == id:
			var key := str(row.get("icon_key", ""))
			if not key.is_empty(): return texture(key)
	for row in CATALOG.data.get("tables", {}).get("Items", []):
		if str(row.get("kind", "")) == kind and kind != "ClassSoul":
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

static func _style_prototype(key: String, tint: Color) -> StyleBoxTexture:
	var cache_key := "%s|%s" % [key, tint]
	var cached: StyleBoxTexture = _styles.get(cache_key)
	if cached != null: return cached
	var box := StyleBoxTexture.new()
	box.texture = texture(key)
	box.modulate_color = tint
	var borders: Array = MANIFEST.data.files.get(key, {}).get("border_lbrt", [12, 12, 12, 12])
	# Source manifests use Unity's left/bottom/right/top order.
	for pair in [[SIDE_LEFT, 0], [SIDE_BOTTOM, 1], [SIDE_RIGHT, 2], [SIDE_TOP, 3]]:
		box.set_texture_margin(pair[0], float(borders[pair[1]]))
	for side in [SIDE_LEFT, SIDE_RIGHT]: box.set_content_margin(side, 24)
	for side in [SIDE_TOP, SIDE_BOTTOM]: box.set_content_margin(side, 12)
	_styles[cache_key] = box
	return box

## Independent copy. Search fields and scrollbars adjust margins after this returns.
static func style(key: String, tint: Color = Color.WHITE) -> StyleBoxTexture:
	return _style_prototype(key, tint).duplicate() as StyleBoxTexture

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
	# Buttons do not edit these boxes, so every button of the same art shares one.
	node.add_theme_stylebox_override("normal", _style_prototype(key, Color.WHITE))
	node.add_theme_stylebox_override("hover", _style_prototype(key, Color(1.2, 1.15, 1.05)))
	node.add_theme_stylebox_override("pressed", _style_prototype(key, Color(0.8, 0.85, 0.9)))
	node.add_theme_stylebox_override("disabled", _style_prototype(key, Color(0.55, 0.55, 0.55)))

static func cell_style(tint: Color = Color.WHITE) -> StyleBoxTexture:
	return style(COMMON_CELL_KEY, tint)

static func add_safe_slot_frame(parent: Control) -> TextureRect:
	var frame := TextureRect.new()
	frame.name = "SafeSlotFrame"
	frame.texture = SAFE_SLOT_FRAME_TEXTURE
	frame.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	frame.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	frame.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	frame.mouse_filter = Control.MOUSE_FILTER_IGNORE
	parent.add_child(frame)
	return frame

static func apply_safe_slot_button(node: Button) -> void:
	var normal := StyleBoxFlat.new()
	normal.bg_color = Color.TRANSPARENT
	normal.set_content_margin_all(8)
	var hover := normal.duplicate() as StyleBoxFlat
	hover.bg_color = Color.TRANSPARENT
	var pressed := normal.duplicate() as StyleBoxFlat
	pressed.bg_color = Color.TRANSPARENT
	var disabled := normal.duplicate() as StyleBoxFlat
	disabled.bg_color = Color.TRANSPARENT
	node.add_theme_stylebox_override("normal", normal)
	node.add_theme_stylebox_override("hover", hover)
	node.add_theme_stylebox_override("pressed", pressed)
	node.add_theme_stylebox_override("disabled", disabled)
	add_safe_slot_frame(node)

static func quality_name(rank: Variant) -> String:
	if rank is String:
		var raw := str(rank).capitalize()
		if raw in QUALITY_LADDER and not raw.is_empty(): return raw
	return QUALITY_LADDER[clampi(int(rank), 0, 6)]

static func item_quality_rank(item: Dictionary) -> int:
	var gear: Dictionary = item.get("equipment", {}) if item.get("equipment") is Dictionary else {}
	if not gear.is_empty() and gear.has("quality"):
		var gear_quality := quality_name(gear.get("quality"))
		return QUALITY_LADDER.find(gear_quality)
	var raw_quality: Variant = item.get("quality", item.get("Quality", 0))
	if raw_quality is String and not str(raw_quality).is_empty():
		var named := quality_name(raw_quality)
		var named_rank := QUALITY_LADDER.find(named)
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

static func item_background_key(item: Dictionary) -> String:
	return str(CatalogIndex.quality(item_quality_name(item)).get("item_background_key", COMMON_CELL_KEY))

static func item_frame_key(item: Dictionary) -> String:
	return str(CatalogIndex.quality(item_quality_name(item)).get("item_frame_key", ""))

static func quality_color(rank: Variant) -> Color:
	var quality := quality_name(rank)
	var row := CatalogIndex.quality(quality)
	if not row.is_empty():
		var configured := str(row.get("display_color", ""))
		if not configured.is_empty(): return Color(configured)
	return [Color.WHITE, Color("d0c9b6"), Color("789a70"), Color("558cb8"), Color("9979b1"), Color("d99b48"), Color("ce5651")][clampi(int(rank), 1, 6)]

static func item_cell_style(item: Dictionary) -> StyleBoxTexture:
	var rank := item_quality_rank(item)
	return cell_style(quality_color(rank).darkened(0.35))
