extends Control

## A lightweight 2D-only backdrop for the hall and the Chaos Realm.
##
## The old GLB scenes remain as source/archive material, but the live client
## never instantiates them. The backdrop is intentionally made from ordinary
## TextureRects plus a few procedural 2D silhouettes so it remains cheap on
## the compatibility renderer and scales with the 1920x1080 UI canvas.

const DESIGN_SIZE := Vector2(1920.0, 1080.0)
const FAR_PATH := "res://assets/backgrounds/chaos_realm/hall_far.png"
const MID_PATH := "res://assets/backgrounds/chaos_realm/hall_mid.png"

var _far: TextureRect
var _mid: TextureRect
var _near: Control
var _glow: Polygon2D
var _mode := ""
var _time := 0.0

func _ready() -> void:
	name = "Layered2DBackdrop"
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	# Keep the backdrop in the normal canvas layer. A negative z-index would
	# place it behind the viewport clear color on some Godot render paths.
	z_index = 0
	_far = _texture_layer("FarLayer", FAR_PATH, Color.WHITE, 0)
	_mid = _texture_layer("MidLayer", MID_PATH, Color(0.92, 0.97, 1.0, 1.0), 0)
	_near = Control.new()
	_near.name = "Near2DLayer"
	_near.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_near.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# Keep every backdrop layer below later UI siblings. The tree order still
	# gives far -> mid -> near compositing without letting the near layer cover
	# login or battle controls.
	_near.z_index = 0
	add_child(_near)
	_build_near_layer()
	_sync_canvas_size()
	set_mode("hall")

func _texture_layer(layer_name: String, path: String, tint: Color, order: int) -> TextureRect:
	var node := TextureRect.new()
	node.name = layer_name
	node.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	node.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	node.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	node.texture_filter = CanvasItem.TEXTURE_FILTER_LINEAR
	node.mouse_filter = Control.MOUSE_FILTER_IGNORE
	# Do not gate fresh project assets behind ResourceLoader.exists(). During
	# the first import pass Godot can resolve load(path) before exists(path)
	# reports the imported resource.
	node.texture = load(path)
	node.modulate = tint
	node.z_index = order
	add_child(node)
	return node

func _build_near_layer() -> void:
	# The third ImageGen call for an alpha-only prop sheet was unavailable in
	# this environment. These quiet silhouettes provide the same near-camera
	# depth cue without introducing another opaque background plate.
	_add_polygon("LeftPillarShadow", [
		Vector2(0, 0), Vector2(165, 0), Vector2(180, 370), Vector2(145, 610),
		Vector2(95, 750), Vector2(0, 820)
	], Color(0.005, 0.025, 0.035, 0.48))
	_add_polygon("RightPillarShadow", [
		Vector2(1920, 0), Vector2(1755, 0), Vector2(1740, 370), Vector2(1775, 610),
		Vector2(1825, 750), Vector2(1920, 820)
	], Color(0.005, 0.025, 0.035, 0.48))
	_add_polygon("BottomLeftMasonry", [
		Vector2(0, 765), Vector2(280, 830), Vector2(470, 1080), Vector2(0, 1080)
	], Color(0.012, 0.035, 0.045, 0.66))
	_add_polygon("BottomRightMasonry", [
		Vector2(1920, 765), Vector2(1640, 830), Vector2(1450, 1080), Vector2(1920, 1080)
	], Color(0.012, 0.035, 0.045, 0.66))
	_glow = _circle("PortalAtmosphere", Vector2(960, 520), 270.0, Color(0.03, 0.65, 0.88, 0.055))
	# A few simple cyan rune strokes make the depth read as layered 2D rather
	# than as a single stretched bitmap, while staying behind all UI input.
	_add_line("LeftRune", PackedVector2Array([Vector2(62, 230), Vector2(104, 272), Vector2(62, 314), Vector2(20, 272)]), Color(0.15, 0.72, 0.86, 0.25), 3.0)
	_add_line("RightRune", PackedVector2Array([Vector2(1858, 230), Vector2(1900, 272), Vector2(1858, 314), Vector2(1816, 272)]), Color(0.15, 0.72, 0.86, 0.25), 3.0)

func _add_polygon(node_name: String, points: Array[Vector2], color: Color) -> Polygon2D:
	var polygon := Polygon2D.new()
	polygon.name = node_name
	polygon.polygon = PackedVector2Array(points)
	polygon.color = color
	_near.add_child(polygon)
	return polygon

func _circle(node_name: String, center: Vector2, radius: float, color: Color) -> Polygon2D:
	var points := PackedVector2Array()
	for index in range(40):
		var angle := TAU * float(index) / 40.0
		points.append(center + Vector2(cos(angle), sin(angle)) * radius)
	return _add_polygon(node_name, points, color)

func _add_line(node_name: String, points: PackedVector2Array, color: Color, width: float) -> Line2D:
	var line := Line2D.new()
	line.name = node_name
	line.points = points
	line.width = width
	line.default_color = color
	line.joint_mode = Line2D.LINE_JOINT_ROUND
	_near.add_child(line)
	return line

func set_mode(mode: String) -> void:
	if _mode == mode: return
	_mode = mode
	var is_codex := mode == "codex"
	_far.visible = true
	_mid.visible = not is_codex
	_near.visible = not is_codex
	if mode == "exploration":
		_far.texture = load(FAR_PATH)
		_far.modulate = Color(0.72, 0.89, 0.98, 1.0)
		_mid.modulate = Color(0.62, 0.78, 0.86, 0.72)
		_near.modulate = Color(0.78, 0.92, 1.0, 0.9)
	elif is_codex:
		_far.texture = load("res://assets/imported/UI/CardCodex/card_codex_background_normal.png")
		if _far.texture == null: _far.texture = load(FAR_PATH)
		_far.modulate = Color.WHITE
	else:
		_far.texture = load(FAR_PATH)
		_far.modulate = Color.WHITE
		_mid.modulate = Color(0.92, 0.97, 1.0, 1.0)
	_apply_parallax()
	if is_instance_valid(_glow) and is_codex: _glow.color.a = 0.0
	set_process(not is_codex)

func _process(delta: float) -> void:
	_time += delta
	_apply_parallax()
	if is_instance_valid(_glow):
		_glow.color.a = 0.045 + sin(_time * 0.8) * 0.012 if _mode != "codex" else 0.0

func _notification(what: int) -> void:
	if what == NOTIFICATION_RESIZED:
		_sync_canvas_size()
		_apply_parallax()

func _sync_canvas_size() -> void:
	if not is_inside_tree() or not is_instance_valid(_near): return
	# All layers use full-rect anchors; avoid assigning size here because Godot
	# will immediately override it and emit a layout warning during _ready().

func _apply_parallax() -> void:
	if not is_instance_valid(_far): return
	var motion := Vector2(sin(_time * 0.20) * 2.0, cos(_time * 0.17) * 1.0)
	_set_layer_offsets(_far, motion * 0.35, 32.0, 20.0)
	if is_instance_valid(_mid): _set_layer_offsets(_mid, motion * 1.25, 44.0, 28.0)

func _set_layer_offsets(layer: TextureRect, offset: Vector2, margin_x: float, margin_y: float) -> void:
	layer.offset_left = -margin_x + offset.x
	layer.offset_top = -margin_y + offset.y
	layer.offset_right = margin_x + offset.x
	layer.offset_bottom = margin_y + offset.y
