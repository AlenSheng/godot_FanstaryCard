extends Control

const P = preload("res://ui/palette.gd")
const Art = preload("res://ui/art.gd")
signal language_selected(code: String)

const BUTTON_SIZE := Vector2(432, 64)
const ROW_HEIGHT := 48.0
const ROW_GAP := 4.0
var _button: Button
var _panel: PanelContainer
var _scroll: ScrollContainer
var _column: VBoxContainer
var _enabled := true
var header_guard: Control

func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_button = Button.new()
	_button.name = "LoginLanguageButton"
	_button.size = BUTTON_SIZE
	_button.clip_text = true
	Art.button(_button, "UI/CardCodex/card_codex_action_button_blue.png")
	_button.pressed.connect(func():
		if _panel.visible: close()
		else: open()
	)
	_button.resized.connect(_refit)
	add_child(_button)
	_panel = PanelContainer.new()
	_panel.name = "LoginLanguageListPanel"
	_panel.add_theme_stylebox_override("panel", Art.style("UI/CardCodex/card_codex_dialog_panel_normal.png"))
	_panel.position = Vector2(0, BUTTON_SIZE.y + 12)
	_panel.hide()
	add_child(_panel)
	_scroll = ScrollContainer.new()
	_scroll.name = "LoginLanguageListScroll"
	_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	_scroll.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_scroll.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_panel.add_child(_scroll)
	_column = VBoxContainer.new()
	_column.name = "LoginLanguageChoices"
	_column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	_column.add_theme_constant_override("separation", int(ROW_GAP))
	_scroll.add_child(_column)
	get_viewport().size_changed.connect(_layout)
	if is_instance_valid(header_guard): header_guard.resized.connect(_layout)
	refresh(false, false)

func refresh(on_login: bool, enabled: bool) -> void:
	visible = on_login
	_enabled = enabled
	if not on_login or not enabled: close()
	if not is_instance_valid(_button): return
	theme = P.theme()
	_button.disabled = not enabled
	_button.text = "%s: %s" % [P.localized("language"), str(P.languages()[P.language()].name)]
	_button.add_theme_font_override("font", P.font("body"))
	_button.add_theme_font_size_override("font_size", 24)
	_refit()
	_layout()

func _refit() -> void:
	if is_instance_valid(_button):
		_button.add_theme_font_size_override("font_size", P.fit_font_size(P.font("body"), 24, BUTTON_SIZE.y, BUTTON_SIZE.x - 48, _button.text))

func _layout() -> void:
	var viewport_size := get_viewport_rect().size
	var top := maxf(156, header_guard.get_global_rect().end.y + 24 if is_instance_valid(header_guard) else 156)
	position = Vector2(maxf(40, viewport_size.x - 128 - BUTTON_SIZE.x), minf(top, viewport_size.y - BUTTON_SIZE.y - 40))
	size = BUTTON_SIZE
	if not is_instance_valid(_panel): return
	var padding := Art.COMMON_PANEL_PADDING
	var natural := P.languages().size() * ROW_HEIGHT + maxi(0, P.languages().size() - 1) * ROW_GAP + padding.y + padding.w
	var below := viewport_size.y - position.y - BUTTON_SIZE.y - 12 - 40
	var above := position.y - 12 - 40
	var available := maxf(below, above) if below < ROW_HEIGHT + padding.y + padding.w else below
	var height := minf(natural, maxf(ROW_HEIGHT + padding.y + padding.w, available))
	_panel.position.y = BUTTON_SIZE.y + 12 if below >= height else -height - 12
	_panel.size = Vector2(BUTTON_SIZE.x, height)

func open() -> void:
	if not visible or not _enabled: return
	for child in _column.get_children(): child.free()
	var selected: Button
	for code in P.languages():
		var choice := Button.new()
		choice.name = "LanguageChoice_" + str(code).replace("-", "_")
		choice.text = str(P.languages()[code].name)
		choice.custom_minimum_size.y = ROW_HEIGHT
		choice.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		choice.add_theme_font_override("font", P.font("body"))
		choice.add_theme_font_size_override("font_size", 24)
		for state in ["normal", "hover", "pressed", "focus"]:
			var style := P.box(P.INK, P.GOLD if code == P.language() or state != "normal" else Color("47626a"), 1)
			style.content_margin_left = 12
			style.content_margin_right = 12
			style.content_margin_top = 4
			style.content_margin_bottom = 4
			choice.add_theme_stylebox_override(state, style)
		choice.pressed.connect(_choose.bind(str(code)))
		_column.add_child(choice)
		if code == P.language(): selected = choice
	_layout()
	_panel.show()
	if selected != null: selected.grab_focus()

func close() -> void:
	if is_instance_valid(_panel): _panel.hide()

func _choose(code: String) -> void:
	if not visible or not _enabled: return
	close()
	language_selected.emit(code)

func _input(event: InputEvent) -> void:
	if not is_instance_valid(_panel) or not _panel.visible: return
	if event.is_action_pressed("ui_cancel"):
		close()
		get_viewport().set_input_as_handled()
	elif event is InputEventMouseButton and event.pressed:
		var point := get_global_mouse_position()
		if not _panel.get_global_rect().has_point(point) and not _button.get_global_rect().has_point(point): close()
