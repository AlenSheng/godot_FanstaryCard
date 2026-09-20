extends Control

const Art = preload("res://ui/art.gd")
const P = preload("res://ui/palette.gd")
const PANEL := "UI/CardCodex/card_codex_dialog_panel_normal.png"
const CONFIRM_BUTTON := "UI/CardCodex/card_codex_action_button_orange.png"
const CANCEL_BUTTON := "UI/CardCodex/card_codex_action_button_blue.png"

signal accepted
signal canceled

var _action: Callable
var _completed := false
var _wired := false

@onready var dialog_panel: Panel = $DialogPanel
@onready var title_label: Label = $DialogPanel/Title
@onready var description_label: Label = $DialogPanel/Description
@onready var cancel_button: Button = $DialogPanel/CancelButton
@onready var confirm_button: Button = $DialogPanel/ConfirmButton

func _ensure_nodes() -> bool:
	if dialog_panel == null: dialog_panel = get_node_or_null("DialogPanel") as Panel
	if title_label == null: title_label = get_node_or_null("DialogPanel/Title") as Label
	if description_label == null: description_label = get_node_or_null("DialogPanel/Description") as Label
	if cancel_button == null: cancel_button = get_node_or_null("DialogPanel/CancelButton") as Button
	if confirm_button == null: confirm_button = get_node_or_null("DialogPanel/ConfirmButton") as Button
	return is_instance_valid(dialog_panel) and is_instance_valid(title_label) and is_instance_valid(description_label) and is_instance_valid(cancel_button) and is_instance_valid(confirm_button)

func _setup() -> void:
	if _wired or not _ensure_nodes(): return
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 4096
	var backdrop := get_node_or_null("Backdrop") as Control
	if backdrop != null:
		backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		backdrop.mouse_filter = Control.MOUSE_FILTER_STOP
	if dialog_panel != null: dialog_panel.mouse_filter = Control.MOUSE_FILTER_STOP
	dialog_panel.add_theme_stylebox_override("panel", Art.style(PANEL))
	Art.button(confirm_button, CONFIRM_BUTTON)
	Art.button(cancel_button, CANCEL_BUTTON)
	for label in [title_label, description_label]:
		label.add_theme_color_override("font_color", P.PAPER)
		label.mouse_filter = Control.MOUSE_FILTER_IGNORE
	title_label.add_theme_font_override("font", P.font("title"))
	description_label.add_theme_font_override("font", P.font("body"))
	for button in [cancel_button, confirm_button]:
		button.add_theme_font_override("font", P.font_for_text(button.text, 26))
		button.clip_text = true
		button.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
		P.fit_control_font(button, P.font_for_text(button.text, 26), 26, 48.0)
	cancel_button.pressed.connect(_cancel)
	confirm_button.pressed.connect(_accept)
	description_label.resized.connect(_fit_description)
	_fit_description.call_deferred()
	_wired = true

func _ready() -> void:
	_setup()

func _localized_display(value: String) -> String:
	var translated := P.localized(value)
	return translated if translated != value else P.localized_text(value)

func configure(message: String, action: Callable, options: Dictionary = {}) -> void:
	_setup()
	if not _ensure_nodes(): return
	_action = action
	title_label.text = _localized_display(str(options.get("title", "confirm_action")))
	description_label.text = _localized_display(message)
	confirm_button.text = _localized_display(str(options.get("confirm_text", "confirm")))
	cancel_button.text = _localized_display(str(options.get("cancel_text", "cancel")))
	var info_only := bool(options.get("info_only", false))
	var tall := bool(options.get("tall", false))
	cancel_button.visible = not info_only
	if info_only:
		# Keep the information dialog on the same shared modal/panel artwork,
		# but present one centered close action instead of a confirmation pair.
		confirm_button.position = Vector2(345, 326)
		confirm_button.size = Vector2(270, 74)
	else:
		confirm_button.position = Vector2(530, 326)
		confirm_button.size = Vector2(270, 74)
	if tall:
		dialog_panel.offset_top = -300.0
		dialog_panel.offset_bottom = 300.0
		description_label.offset_bottom = 385.0
		cancel_button.position.y = 426.0
		cancel_button.size.y = 74.0
		confirm_button.position.y = 426.0
		confirm_button.size.y = 74.0
		description_label.max_lines_visible = 12
	else:
		dialog_panel.offset_top = -230.0
		dialog_panel.offset_bottom = 230.0
		description_label.offset_bottom = 285.0
		cancel_button.position.y = 326.0
		cancel_button.size.y = 74.0
		confirm_button.position.y = 326.0
		confirm_button.size.y = 74.0
		description_label.max_lines_visible = 4
	P.fit_control_font(title_label, P.font("title"), 32, 36.0)
	for button in [cancel_button, confirm_button]:
		var typeface := P.font_for_text(button.text, 26)
		button.add_theme_font_override("font", typeface)
		P.fit_control_font(button, typeface, 26, 48.0)
	_fit_description.call_deferred()

func dismiss() -> void:
	if _completed: return
	_completed = true
	_close_immediately()

func _close_immediately() -> void:
	visible = false
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	var backdrop := get_node_or_null("Backdrop") as Control
	if backdrop != null: backdrop.mouse_filter = Control.MOUSE_FILTER_IGNORE
	if dialog_panel != null: dialog_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	queue_free()

func _fit_description() -> void:
	if not is_instance_valid(description_label): return
	var typeface := P.font_for_text(description_label.text, 28)
	var fitted := 28
	var available := Vector2(maxf(1.0, description_label.size.x - 24.0), maxf(1.0, description_label.size.y - 12.0))
	while fitted > 18:
		var measured := typeface.get_multiline_string_size(description_label.text, HORIZONTAL_ALIGNMENT_CENTER, available.x, fitted)
		if measured.y <= available.y: break
		fitted -= 1
	description_label.add_theme_font_override("font", typeface)
	description_label.add_theme_font_size_override("font_size", fitted)

func _accept() -> void:
	if _completed: return
	_completed = true
	accepted.emit()
	_close_immediately()
	if _action.is_valid(): _action.call()

func _cancel() -> void:
	if _completed: return
	_completed = true
	canceled.emit()
	_close_immediately()

func _input(event: InputEvent) -> void:
	if not visible: return
	if not event is InputEventMouseButton: return
	var point := (event as InputEventMouse).position
	# Keep the modal's full-screen hit area authoritative even if a lower
	# control is also eligible for the same pointer event. Let the action
	# buttons receive their own clicks so they can close the modal normally.
	if confirm_button != null and confirm_button.visible and confirm_button.get_global_rect().has_point(point):
		if event.pressed and event.button_index == MOUSE_BUTTON_LEFT: _accept()
		get_viewport().set_input_as_handled()
		return
	if cancel_button != null and cancel_button.visible and cancel_button.get_global_rect().has_point(point):
		if event.pressed and event.button_index == MOUSE_BUTTON_LEFT: _cancel()
		get_viewport().set_input_as_handled()
		return
	get_viewport().set_input_as_handled()

func _unhandled_key_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		_cancel()
	elif event.is_action_pressed("ui_accept"):
		get_viewport().set_input_as_handled()
		_accept()
