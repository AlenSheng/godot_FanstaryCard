extends RefCounted

const MANIFEST = preload("res://assets/imported/manifest.json")
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
