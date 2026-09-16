extends Control

const MODEL_PATH := "res://assets/characters/blue_gold_mage.glb"
const IDLE_ACTIONS := ["Idle_Breathe", "Idle_LookAround", "Idle_StaffFocus"]

var viewport: SubViewport
var animation_player: AnimationPlayer
var rng := RandomNumberGenerator.new()
var idle_timer: Timer

func setup() -> void:
	# The caller owns this Control's position and size so the model occupies the
	# same rectangle as the former 2D portrait. Only the internal viewport fills
	# this control.
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	if not ResourceLoader.exists(MODEL_PATH):
		return

	var container := SubViewportContainer.new()
	container.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	container.mouse_filter = Control.MOUSE_FILTER_IGNORE
	container.stretch = true
	add_child(container)
	viewport = SubViewport.new()
	viewport.size = Vector2i(720, 720)
	viewport.transparent_bg = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	container.add_child(viewport)

	var world := WorldEnvironment.new()
	var environment := Environment.new()
	environment.background_mode = Environment.BG_COLOR
	environment.background_color = Color(0.035, 0.055, 0.07, 0.0)
	environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.ambient_light_color = Color(0.55, 0.64, 0.78)
	environment.ambient_light_energy = 0.75
	world.environment = environment
	viewport.add_child(world)

	var key := DirectionalLight3D.new()
	key.rotation_degrees = Vector3(-28.0, -25.0, 0.0)
	key.light_energy = 1.15
	key.light_color = Color(0.82, 0.9, 1.0)
	viewport.add_child(key)
	var fill := DirectionalLight3D.new()
	fill.rotation_degrees = Vector3(-18.0, 145.0, 0.0)
	fill.light_energy = 0.45
	fill.light_color = Color(0.12, 0.35, 0.8)
	viewport.add_child(fill)

	var camera := Camera3D.new()
	# Blender exports Z-up, while the imported Godot scene is Y-up. The authored
	# character front therefore faces +Z in Godot; place the camera on that axis
	# instead of looking along Y (which produces a feet-first view).
	# Imported bounds are about 3.60 m tall including the staff. This distance
	# fits the whole silhouette inside the former portrait rectangle while a
	# slight X offset retains the concept art's near-front three-quarter view.
	camera.position = Vector3(0.65, 1.72, 7.5)
	camera.fov = 28.0
	camera.current = true
	viewport.add_child(camera)
	# A Camera3D must be inside the scene tree before look_at() can update its
	# global transform. Calling it earlier leaves the camera at its default
	# forward direction and the character renders outside the frustum.
	camera.look_at(Vector3(0.0, 1.70, 0.0), Vector3.UP)

	var model: Node = load(MODEL_PATH).instantiate()
	model.position = Vector3(0.0, 0.0, 0.03)
	viewport.add_child(model)
	animation_player = _find_animation_player(model)
	rng.randomize()
	_play_random_idle()
	idle_timer = Timer.new()
	idle_timer.one_shot = true
	idle_timer.timeout.connect(_play_random_idle)
	add_child(idle_timer)
	idle_timer.start(rng.randf_range(5.0, 9.0))

func _find_animation_player(node: Node) -> AnimationPlayer:
	for child in node.get_children():
		if child is AnimationPlayer:
			return child
		var nested := _find_animation_player(child)
		if nested != null:
			return nested
	return null

func _play_random_idle() -> void:
	if animation_player == null:
		return
	var available: Array[String] = []
	for action in IDLE_ACTIONS:
		if animation_player.has_animation(action):
			available.append(action)
	if available.is_empty():
		return
	var chosen := available[rng.randi_range(0, available.size() - 1)]
	animation_player.play(chosen, 0.35)
	if idle_timer != null:
		idle_timer.start(rng.randf_range(5.0, 9.0))
