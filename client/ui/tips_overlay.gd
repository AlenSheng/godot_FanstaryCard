extends CanvasLayer

const P = preload("res://ui/palette.gd")

const DISPLAY_DURATION := 2.0
const FADE_DURATION := 0.55
const RISE_DISTANCE := 56.0
const VIEWPORT_Y_RATIO := 0.28
const MIN_WIDTH := 180.0
const MAX_WIDTH_RATIO := 0.72
const HORIZONTAL_PADDING := 48.0
const VERTICAL_PADDING := 16.0

var panel: PanelContainer
var label: Label
var _tween: Tween
var _serial := 0
var _start_position := Vector2.ZERO

func _init() -> void:
	layer = 120
	panel = PanelContainer.new()
	panel.name = "TipsPanel"
	panel.visible = false
	panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.z_index = 120
	var background := StyleBoxFlat.new()
	background.bg_color = Color("101b21")
	background.border_color = Color("d3ae68")
	background.set_border_width_all(2)
	background.set_corner_radius_all(6)
	background.content_margin_left = HORIZONTAL_PADDING * 0.5
	background.content_margin_right = HORIZONTAL_PADDING * 0.5
	background.content_margin_top = VERTICAL_PADDING * 0.5
	background.content_margin_bottom = VERTICAL_PADDING * 0.5
	panel.add_theme_stylebox_override("panel", background)
	add_child(panel)

	label = Label.new()
	label.name = "TipsText"
	label.theme = P.theme()
	label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	label.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", 22)
	label.add_theme_color_override("font_color", Color("ffe36b"))
	label.add_theme_color_override("font_outline_color", Color(0, 0, 0, 0.95))
	label.add_theme_constant_override("outline_size", 4)
	label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	panel.add_child(label)

func show_tip(message: String, viewport_y_ratio: float = VIEWPORT_Y_RATIO) -> void:
	var localized := P.localized_text(message).strip_edges()
	if P.is_unlocalized_english_sentence(localized): localized = P.localized("operation_rejected")
	if localized.is_empty():
		clear()
		return
	offset = Vector2.ZERO
	_serial += 1
	var serial := _serial
	if is_instance_valid(_tween):
		_tween.kill()
	label.text = localized
	_layout_at_start(viewport_y_ratio)
	panel.visible = true
	panel.modulate = Color.WHITE
	panel.scale = Vector2(0.96, 0.96)
	panel.pivot_offset = panel.size * 0.5

	_tween = create_tween()
	_tween.set_parallel(true)
	_tween.tween_property(panel, "position:y", _start_position.y - RISE_DISTANCE, DISPLAY_DURATION).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	_tween.tween_property(panel, "scale", Vector2.ONE, 0.16).set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	_tween.tween_property(panel, "modulate:a", 0.0, FADE_DURATION).set_delay(DISPLAY_DURATION - FADE_DURATION)
	_tween.finished.connect(_finish.bind(serial))

func set_viewport_anchor(viewport_y_ratio: float = VIEWPORT_Y_RATIO) -> void:
	if not panel.visible: return
	var viewport_size := get_viewport().get_visible_rect().size
	# Translate the whole layer; the running rise/fade tween and its lifetime
	# remain unchanged when the underlying screen changes.
	var target := Vector2((viewport_size.x - panel.size.x) * 0.5,
		viewport_size.y * viewport_y_ratio - panel.size.y * 0.5)
	offset = target - _start_position

func clear() -> void:
	offset = Vector2.ZERO
	_serial += 1
	if is_instance_valid(_tween):
		_tween.kill()
	label.text = ""
	panel.visible = false
	panel.modulate = Color.WHITE

func start_position() -> Vector2:
	return _start_position + offset

func _layout_at_start(viewport_y_ratio: float = VIEWPORT_Y_RATIO) -> void:
	var viewport_size := Vector2(1920, 1080)
	if is_inside_tree():
		viewport_size = get_viewport().get_visible_rect().size
	label.custom_minimum_size = Vector2.ZERO
	label.reset_size()
	panel.custom_minimum_size = Vector2.ZERO
	var font := label.get_theme_font("font")
	var font_size := label.get_theme_font_size("font_size")
	var natural_text_width := font.get_string_size(label.text, HORIZONTAL_ALIGNMENT_LEFT, -1.0, font_size).x
	var natural_width := natural_text_width + HORIZONTAL_PADDING
	var target_width := clampf(natural_width, MIN_WIDTH, viewport_size.x * MAX_WIDTH_RATIO)
	var text_width := maxf(1.0, target_width - HORIZONTAL_PADDING)
	label.autowrap_mode = TextServer.AUTOWRAP_OFF if natural_text_width <= text_width else TextServer.AUTOWRAP_WORD_SMART
	var measured_text := font.get_multiline_string_size(label.text, HORIZONTAL_ALIGNMENT_CENTER, text_width, font_size)
	label.custom_minimum_size = Vector2(text_width, measured_text.y)
	panel.size = Vector2(target_width, measured_text.y + VERTICAL_PADDING)
	panel.custom_minimum_size = panel.size
	_start_position = Vector2(
		(viewport_size.x - panel.size.x) * 0.5,
		viewport_size.y * viewport_y_ratio - panel.size.y * 0.5
	)
	panel.position = _start_position

func _finish(serial: int) -> void:
	if serial != _serial:
		return
	label.text = ""
	panel.visible = false
	panel.modulate = Color.WHITE
