extends RefCounted

const BoundedBar = preload("res://ui/bounded_bar.gd")
const P = preload("res://ui/palette.gd")
const HP_FILL := "UI/Encounter/encounter_hp_fill_normal.png"
const HP_TRACK := "UI/Encounter/encounter_hp_track_normal.png"
const ENERGY_FILL := "UI/Battle/battle_energy_cell_lit.png"
const ENERGY_TRACK := "UI/Battle/battle_energy_cell_unlit.png"

func run_test() -> Dictionary:
	var errors: Array[String] = []
	var host := Control.new()
	host.theme = P.theme()
	# A decorated ProgressBar theme must not impose its margins on these bars.
	var oversized := P.box()
	oversized.content_margin_left = 80
	oversized.content_margin_right = 80
	oversized.content_margin_top = 30
	oversized.content_margin_bottom = 30
	host.theme.set_stylebox("background", "ProgressBar", oversized)
	host.theme.set_stylebox("fill", "ProgressBar", oversized)
	var tree := Engine.get_main_loop() as SceneTree
	if tree != null: tree.root.add_child(host)
	for kind in ["health", "energy", "shield"]:
		var bar := BoundedBar.new()
		host.add_child(bar)
		bar.max_value = 100
		if kind == "health": bar.configure(HP_FILL, HP_TRACK)
		elif kind == "energy": bar.configure(ENERGY_FILL, ENERGY_TRACK)
		else: bar.configure_solid(Color("102128"), Color("c4d2d4"))
		for height in [20.0, 22.0, 30.0]:
			bar.size = Vector2(310, height)
			if not bar.size.is_equal_approx(Vector2(310, height)):
				errors.append("%s: theme enlarged the requested %s-pixel height" % [kind, height])
			if bar.get_combined_minimum_size().y > height:
				errors.append("%s: minimum height exceeds the requested height" % kind)
			for sample in [[0.0, 0.0], [1.0, 0.01], [55.0, 0.55], [100.0, 1.0], [-5.0, 0.0], [150.0, 1.0]]:
				bar.value = sample[0]
				_check_geometry(bar, _expected_slot(kind, bar.size), sample[1], "%s/%s/value=%s" % [kind, height, sample[0]], errors)
		bar.value = 1
		bar.size = Vector2(160, 22)
		_check_geometry(bar, _expected_slot(kind, bar.size), 0.01, kind + "/resized-small", errors)
		bar.size = Vector2(449, 30)
		_check_geometry(bar, _expected_slot(kind, bar.size), 0.01, kind + "/resized-large", errors)
		if kind == "shield" and not is_equal_approx(bar.get_node("FillClip").size.x, 4.49):
			errors.append("Shield at 1% must reveal 4.49 pixels of a 449-pixel bar, without a 48-pixel minimum")
		if kind == "energy":
			if not (bar.get_child(0) is NinePatchRect) or not (bar.get_node("FillClip").get_child(0) is NinePatchRect):
				errors.append("Energy charge must use nine-patch rendering so a single cell can widen without stretching its end caps")
			bar.max_value = 1.0
			bar.value = 0.005
			_check_geometry(bar, _expected_slot(kind, bar.size), 0.005, "energy/fractional-charge", errors)
		bar.max_value = 100
		bar.value = 50
		bar.max_value = 200
		_check_geometry(bar, _expected_slot(kind, bar.size), 0.25, kind + "/maximum-update", errors)
		bar.free()
	_check_reconfiguration(host, errors)
	_check_preconfigured_entry(host, errors)
	host.free()
	return {"ok": errors.is_empty(), "message": "Bounded health, charge and shield bars: clamping, exact low values, theme-independent height, value updates and resizing" if errors.is_empty() else "; ".join(errors)}

func _expected_slot(kind: String, dimensions: Vector2) -> Rect2:
	if kind == "health":
		return Rect2(Vector2(67.0 / 448.0, 14.0 / 48.0) * dimensions, Vector2(313.0 / 448.0, 15.0 / 48.0) * dimensions)
	if kind == "energy":
		return Rect2(Vector2(8.0 / 86.0, 7.0 / 32.0) * dimensions, Vector2(66.0 / 86.0, 17.0 / 32.0) * dimensions)
	return Rect2(Vector2.ZERO, dimensions)

func _check_geometry(bar: Range, slot: Rect2, ratio: float, context: String, errors: Array[String]) -> void:
	var clip := bar.get_node("FillClip") as Control
	var actual := Rect2(clip.position, clip.size)
	var expected := Rect2(slot.position, Vector2(slot.size.x * ratio, slot.size.y))
	if not actual.position.is_equal_approx(expected.position) or not actual.size.is_equal_approx(expected.size):
		errors.append("%s: visible fill is %s; expected %s" % [context, actual, expected])
	if not slot.grow(0.001).encloses(actual): errors.append(context + ": visible fill escapes the artwork slot")
	if not Rect2(Vector2.ZERO, bar.size).grow(0.001).encloses(actual): errors.append(context + ": visible fill escapes its bar")
	if clip.visible != (ratio > 0.0): errors.append(context + ": zero must hide the fill and positive values must reveal it")
	if not bar.clip_contents or not clip.clip_contents: errors.append(context + ": fill clipping is disabled")
	var fill := clip.get_child(0) as Control
	if not fill.size.is_equal_approx(slot.size) or not fill.position.is_equal_approx(Vector2.ZERO):
		errors.append(context + ": low values must clip a full-size fill instead of stretching its end caps")
	var track := bar.get_child(0) as Control
	if not bar.is_inside_tree() or not bar.is_visible_in_tree(): errors.append(context + ": test bar must be visible in the live SceneTree")
	if not track.is_visible_in_tree() or track.size.x <= 0.0 or track.size.y <= 0.0:
		errors.append(context + ": track artwork must be visible with nonzero dimensions after entering the tree")
	if ratio > 0.0 and (not fill.is_visible_in_tree() or fill.size.x <= 0.0 or fill.size.y <= 0.0):
		errors.append(context + ": positive fill must be visible with nonzero dimensions after entering the tree")
	for part in [track, fill]:
		if part is TextureRect and (part.texture == null or part.texture.get_size().x <= 0.0 or part.texture.get_size().y <= 0.0):
			errors.append(context + ": textured bars require a nonempty texture")
	if not track.position.is_equal_approx(Vector2.ZERO) or not track.size.is_equal_approx(bar.size):
		errors.append(context + ": artwork must follow the full resized bar")
	if bar.mouse_filter != Control.MOUSE_FILTER_IGNORE or clip.mouse_filter != Control.MOUSE_FILTER_IGNORE:
		errors.append(context + ": decorative bar must not block pointer input")

func _check_reconfiguration(host: Control, errors: Array[String]) -> void:
	var bar := BoundedBar.new()
	host.add_child(bar)
	bar.size = Vector2(310, 20)
	bar.max_value = 100
	bar.value = 25
	for kind in ["health", "energy", "shield"]:
		if kind == "health": bar.configure(HP_FILL, HP_TRACK)
		elif kind == "energy": bar.configure(ENERGY_FILL, ENERGY_TRACK)
		else: bar.configure_solid(Color.BLACK, Color.WHITE)
		_check_geometry(bar, _expected_slot(kind, bar.size), 0.25, "reconfigure/" + kind, errors)
		if bar.get_child_count() != 2 or bar.get_node("FillClip").get_child_count() != 1:
			errors.append("Reconfiguration must replace previous track and fill nodes")
		if kind != "shield":
			var image: Control = bar.get_node("FillClip").get_child(0)
			var expected_size := Vector2(416, 16) if kind == "health" else Vector2(53, 17)
			var texture: Texture2D = image.texture if image is TextureRect else (image as NinePatchRect).texture
			if texture == null or not texture.get_size().is_equal_approx(expected_size):
				errors.append(kind + ": fill texture must crop away the source artwork's transparent padding")
	bar.free()

func _check_preconfigured_entry(host: Control, errors: Array[String]) -> void:
	for kind in ["health", "energy", "shield"]:
		# Production creates and sizes bars before adding them to the UI tree.
		var bar := BoundedBar.new()
		if kind == "health": bar.configure(HP_FILL, HP_TRACK)
		elif kind == "energy": bar.configure(ENERGY_FILL, ENERGY_TRACK)
		else: bar.configure_solid(Color.BLACK, Color.WHITE)
		bar.size = Vector2(310, 30)
		bar.max_value = 100
		bar.value = 50
		host.add_child(bar)
		_check_geometry(bar, _expected_slot(kind, bar.size), 0.5, "preconfigured-entry/" + kind, errors)
		bar.free()
