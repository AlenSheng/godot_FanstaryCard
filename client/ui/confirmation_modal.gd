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

@onready var dialog_panel: Panel = $DialogPanel
@onready var title_label: Label = $DialogPanel/Title
@onready var description_label: Label = $DialogPanel/Description
@onready var cancel_button: Button = $DialogPanel/CancelButton
@onready var confirm_button: Button = $DialogPanel/ConfirmButton

func _ready() -> void:
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

func configure(message: String, action: Callable, options: Dictionary = {}) -> void:
	_action = action
	title_label.text = P.localized_text(str(options.get("title", "确认操作")))
	description_label.text = P.localized_text(message)
	confirm_button.text = P.localized_text(str(options.get("confirm_text", "确认")))
	cancel_button.text = P.localized_text(str(options.get("cancel_text", "取消")))
	P.fit_control_font(title_label, P.font("title"), 32, 36.0)
	for button in [cancel_button, confirm_button]:
		var typeface := P.font_for_text(button.text, 26)
		button.add_theme_font_override("font", typeface)
		P.fit_control_font(button, typeface, 26, 48.0)
	_fit_description.call_deferred()

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
	queue_free()
	if _action.is_valid(): _action.call()

func _cancel() -> void:
	if _completed: return
	_completed = true
	canceled.emit()
	queue_free()

func _unhandled_key_input(event: InputEvent) -> void:
	if event.is_action_pressed("ui_cancel"):
		get_viewport().set_input_as_handled()
		_cancel()
	elif event.is_action_pressed("ui_accept"):
		get_viewport().set_input_as_handled()
		_accept()
