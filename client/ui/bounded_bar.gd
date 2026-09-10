extends Range

const Art = preload("res://ui/art.gd")
const HP_TRACK := "UI/Encounter/encounter_hp_track_normal.png"
const ENERGY_TRACK := "UI/Battle/battle_energy_cell_unlit.png"
var _slot := Rect2(0, 0, 1, 1)
var _track: Control
var _clip: Control
var _fill: Control

func _init() -> void:
	step = 0.0
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	clip_contents = true
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	add_to_group("bounded_progress")
	resized.connect(_layout)
	changed.connect(_layout)
	value_changed.connect(func(_value): _layout())

func _ready() -> void:
	_layout()

func configure(fill_key: String, track_key: String) -> void:
	_clear()
	var energy: bool = track_key == ENERGY_TRACK
	var background: Control = _textured_part(self, Art.texture(track_key), Vector4(12, 5, 12, 5) if energy else Vector4.ZERO)
	_track = background
	var fill_texture: Texture2D = Art.texture(fill_key)
	var crop := Rect2()
	# These slots follow the source artwork, excluding its ornamental frame.
	if track_key == HP_TRACK:
		_slot = Rect2(67.0 / 448.0, 14.0 / 48.0, 313.0 / 448.0, 15.0 / 48.0)
		crop = Rect2(0, 7, 416, 16)
	elif track_key == ENERGY_TRACK:
		_slot = Rect2(8.0 / 86.0, 7.0 / 32.0, 66.0 / 86.0, 17.0 / 32.0)
		crop = Rect2(8, 7, 53, 17)
	if fill_texture != null and crop.has_area():
		var atlas := AtlasTexture.new()
		atlas.atlas = fill_texture
		atlas.region = crop
		atlas.filter_clip = true
		fill_texture = atlas
	_make_clip()
	var image: Control = _textured_part(_clip, fill_texture, Vector4(11, 5, 11, 5) if energy else Vector4.ZERO)
	_fill = image
	_layout()

func _textured_part(parent: Node, source: Texture2D, margins: Vector4) -> Control:
	if margins != Vector4.ZERO:
		var patch := NinePatchRect.new()
		patch.texture = source
		patch.set_patch_margin(SIDE_LEFT, int(margins.x))
		patch.set_patch_margin(SIDE_TOP, int(margins.y))
		patch.set_patch_margin(SIDE_RIGHT, int(margins.z))
		patch.set_patch_margin(SIDE_BOTTOM, int(margins.w))
		patch.mouse_filter = Control.MOUSE_FILTER_IGNORE
		parent.add_child(patch)
		return patch
	var image := Art.image(parent, source, Vector2.ZERO)
	image.stretch_mode = TextureRect.STRETCH_SCALE
	return image

func configure_solid(background: Color, foreground: Color) -> void:
	_clear()
	var track := ColorRect.new()
	track.color = background
	track.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(track)
	_track = track
	_make_clip()
	var fill := ColorRect.new()
	fill.color = foreground
	fill.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_clip.add_child(fill)
	_fill = fill
	_layout()

func slot_rect() -> Rect2:
	return Rect2(_slot.position * size, _slot.size * size)

func fill_rect() -> Rect2:
	var inner := slot_rect()
	return Rect2(inner.position, Vector2(inner.size.x * get_as_ratio(), inner.size.y))

func _clear() -> void:
	for child in get_children(): child.free()
	_track = null
	_clip = null
	_fill = null
	_slot = Rect2(0, 0, 1, 1)

func _make_clip() -> void:
	_clip = Control.new()
	_clip.name = "FillClip"
	_clip.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_clip.clip_contents = true
	add_child(_clip)

func _layout() -> void:
	if not is_instance_valid(_track) or not is_instance_valid(_fill): return
	_track.position = Vector2.ZERO
	_track.size = size
	var inner := slot_rect()
	var filled := fill_rect()
	_clip.position = filled.position
	_clip.size = filled.size
	_clip.visible = filled.size.x > 0.0 and filled.size.y > 0.0
	# Reveal a fixed full-width texture; a low value never stretches its end caps.
	_fill.position = Vector2.ZERO
	_fill.size = inner.size
